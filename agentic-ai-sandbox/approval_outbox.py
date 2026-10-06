"""Human approval and outbox simulation; no real payment integration."""

from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
import time
from pathlib import Path
from typing import Any

from durable_state import SQLiteIdempotencyStore, _connect


def proposal_digest(proposal: dict[str, Any]) -> str:
    """Hash the exact action and expiry an operator is being asked to approve."""
    action = {
        key: proposal[key]
        for key in (
            "proposal_id",
            "task_id",
            "owner",
            "order_ref",
            "reason",
            "amount_cents",
            "currency",
            "policy_version",
            "expires_at_epoch",
        )
    }
    encoded = json.dumps(action, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _stable_id(*parts: str) -> str:
    encoded = "\x1f".join(parts).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:20]


class ApprovalError(Exception):
    """An expected approval or outbox policy rejection."""


class RefundApprovalOutbox:
    """Record a human decision and enqueue its exact action in one transaction."""

    DEFAULT_AUTHORITY_STATE = {
        "policy_version": "returns-v1",
        "orders": {
            "ORD-100": {
                "owner": "customer-ada",
                "eligible": True,
                "amount_cents": 2000,
                "currency": "USD",
            },
            "ORD-200": {
                "owner": "customer-blair",
                "eligible": False,
                "amount_cents": 4550,
                "currency": "USD",
            },
        },
    }

    def __init__(
        self,
        database_path: str | Path,
        proposal_store: SQLiteIdempotencyStore,
        authorized_operators: set[str],
    ):
        self.database_path = str(database_path)
        self.proposal_store = proposal_store
        if Path(proposal_store.database_path).resolve() != Path(self.database_path).resolve():
            raise ValueError("Proposal, review, authority, approval, and outbox state must share one database.")
        self.authorized_operators = set(authorized_operators)
        Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        with _connect(self.database_path) as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute(
                """CREATE TABLE IF NOT EXISTS refund_authority_state (
                    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                    state_json TEXT NOT NULL
                )"""
            )
            connection.execute(
                "INSERT OR IGNORE INTO refund_authority_state(singleton, state_json) VALUES (1, ?)",
                (json.dumps(self.DEFAULT_AUTHORITY_STATE, ensure_ascii=False, sort_keys=True),),
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS refund_approvals (
                    proposal_id TEXT PRIMARY KEY,
                    proposal_digest TEXT NOT NULL,
                    operator_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    approval_id TEXT NOT NULL UNIQUE,
                    decided_at_epoch REAL NOT NULL
                )"""
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS refund_outbox (
                    outbox_id TEXT PRIMARY KEY,
                    proposal_id TEXT NOT NULL UNIQUE,
                    approval_id TEXT NOT NULL UNIQUE,
                    proposal_digest TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    payload_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    claim_token TEXT,
                    lease_until_epoch REAL,
                    provider_refund_id TEXT,
                    created_at_epoch REAL NOT NULL,
                    updated_at_epoch REAL NOT NULL
                )"""
            )

    def update_authoritative_state(
        self,
        *,
        policy_version: str | None = None,
        order_updates: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Change current policy/order facts in the same database used by approval."""
        if policy_version is not None and (
            not isinstance(policy_version, str) or not policy_version.strip() or len(policy_version) > 64
        ):
            raise ValueError("Policy version must be non-empty text of at most 64 characters.")
        order_updates = order_updates or {}
        allowed_fields = {"owner", "eligible", "amount_cents", "currency"}
        for order_ref, changes in order_updates.items():
            if not isinstance(order_ref, str) or not isinstance(changes, dict) or not changes:
                raise ValueError("Order updates must map a known order reference to non-empty changes.")
            if set(changes) - allowed_fields:
                raise ValueError("Order update contains an unsupported field.")
            if "owner" in changes and (
                not isinstance(changes["owner"], str) or not changes["owner"].strip()
            ):
                raise ValueError("Order owner must be non-empty text.")
            if "eligible" in changes and not isinstance(changes["eligible"], bool):
                raise ValueError("Order eligibility must be a boolean.")
            if "amount_cents" in changes and (
                isinstance(changes["amount_cents"], bool)
                or not isinstance(changes["amount_cents"], int)
                or changes["amount_cents"] < 0
            ):
                raise ValueError("Order amount must be a non-negative integer number of cents.")
            if "currency" in changes and (
                not isinstance(changes["currency"], str)
                or len(changes["currency"]) != 3
                or not changes["currency"].isalpha()
            ):
                raise ValueError("Currency must be a three-letter code.")

        with _connect(self.database_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT state_json FROM refund_authority_state WHERE singleton = 1"
            ).fetchone()
            state = json.loads(row["state_json"])
            if policy_version is not None:
                state["policy_version"] = policy_version
            for order_ref, changes in order_updates.items():
                if order_ref not in state["orders"]:
                    connection.rollback()
                    raise ValueError("Order update refers to an unknown order.")
                state["orders"][order_ref].update(changes)
            connection.execute(
                "UPDATE refund_authority_state SET state_json = ? WHERE singleton = 1",
                (json.dumps(state, ensure_ascii=False, sort_keys=True),),
            )
            connection.commit()
        return state

    @staticmethod
    def _matches_current_authority(connection: sqlite3.Connection, proposal: dict[str, Any]) -> bool:
        row = connection.execute(
            "SELECT state_json FROM refund_authority_state WHERE singleton = 1"
        ).fetchone()
        if row is None:
            return False
        current = json.loads(row["state_json"])
        order = current["orders"].get(proposal["order_ref"])
        return bool(
            current["policy_version"] == proposal["policy_version"]
            and order is not None
            and order["owner"] == proposal["owner"]
            and order["eligible"] is True
            and order["amount_cents"] == proposal["amount_cents"]
            and order["currency"] == proposal["currency"]
        )

    def _load_pending_proposal(self, proposal_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
        proposal = self.proposal_store.get("proposals", proposal_id)
        if proposal is None:
            raise ApprovalError("Refund proposal does not exist.")
        if not proposal.get("eligible") or proposal.get("status") != "awaiting_human_review":
            raise ApprovalError("Refund proposal is not eligible for approval.")
        reviews = [
            review
            for review in self.proposal_store.all("reviews")
            if review.get("proposal_id") == proposal_id and review.get("status") == "pending"
        ]
        if not reviews:
            raise ApprovalError("Refund proposal is not pending human review.")
        return proposal, reviews[0]

    def approve(
        self,
        proposal_id: str,
        expected_digest: str,
        operator_id: str,
        now_epoch: float | None = None,
    ) -> dict[str, Any]:
        if operator_id not in self.authorized_operators:
            raise ApprovalError("Operator is not authorized to approve refunds.")
        proposal, review = self._load_pending_proposal(proposal_id)
        digest = proposal_digest(proposal)
        if expected_digest != digest:
            raise ApprovalError("Proposal changed after it was presented for approval.")
        approval_id = _stable_id("approval", proposal_id, digest)
        outbox_id = _stable_id("refund-outbox", proposal_id, digest)
        idempotency_key = f"refund:{proposal_id}:{digest}"
        payload = {
            "approval_id": approval_id,
            "proposal_id": proposal_id,
            "proposal_digest": digest,
            "task_id": proposal["task_id"],
            "owner": proposal["owner"],
            "order_ref": proposal["order_ref"],
            "reason": proposal["reason"],
            "amount_cents": proposal["amount_cents"],
            "currency": proposal["currency"],
            "policy_version": proposal["policy_version"],
            "idempotency_key": idempotency_key,
        }
        with _connect(self.database_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT proposal_digest, status, approval_id, operator_id FROM refund_approvals WHERE proposal_id = ?",
                (proposal_id,),
            ).fetchone()
            if existing is not None:
                if existing["proposal_digest"] != digest:
                    connection.rollback()
                    raise ApprovalError("A different proposal version already has a decision.")
                if existing["status"] == "approved":
                    row = connection.execute(
                        "SELECT * FROM refund_outbox WHERE proposal_id = ?", (proposal_id,)
                    ).fetchone()
                    connection.commit()
                    return self._approval_result(existing, row)
                connection.rollback()
                raise ApprovalError(f"Proposal already has status {existing['status']}.")

            decision_epoch = time.time() if now_epoch is None else now_epoch
            if decision_epoch >= proposal["expires_at_epoch"]:
                connection.rollback()
                raise ApprovalError("Refund proposal has expired.")
            if not self._matches_current_authority(connection, proposal):
                connection.rollback()
                raise ApprovalError("Refund proposal is stale; current policy or order facts changed.")

            connection.execute(
                "INSERT INTO refund_approvals(proposal_id, proposal_digest, operator_id, status, approval_id, decided_at_epoch) VALUES (?, ?, ?, 'approved', ?, ?)",
                (proposal_id, digest, operator_id, approval_id, decision_epoch),
            )
            connection.execute(
                """INSERT INTO refund_outbox(
                    outbox_id, proposal_id, approval_id, proposal_digest,
                    idempotency_key, payload_json, status, created_at_epoch, updated_at_epoch
                ) VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?)""",
                (
                    outbox_id,
                    proposal_id,
                    approval_id,
                    digest,
                    idempotency_key,
                    json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    decision_epoch,
                    decision_epoch,
                ),
            )
            connection.commit()
        return {
            "proposal_id": proposal_id,
            "proposal_digest": digest,
            "operator_id": operator_id,
            "status": "approved",
            "approval_id": approval_id,
            "outbox_id": outbox_id,
            "review_id": review["review_id"],
        }

    @staticmethod
    def _approval_result(approval: sqlite3.Row, outbox: sqlite3.Row | None) -> dict[str, Any]:
        if outbox is None:
            raise RuntimeError("Approved refund is missing its outbox record.")
        return {
            "proposal_id": outbox["proposal_id"],
            "proposal_digest": outbox["proposal_digest"],
            "operator_id": approval["operator_id"],
            "status": approval["status"],
            "approval_id": approval["approval_id"],
            "outbox_id": outbox["outbox_id"],
        }

    def reject(
        self,
        proposal_id: str,
        expected_digest: str,
        operator_id: str,
        now_epoch: float | None = None,
    ) -> dict[str, Any]:
        if operator_id not in self.authorized_operators:
            raise ApprovalError("Operator is not authorized to reject refunds.")
        proposal, review = self._load_pending_proposal(proposal_id)
        digest = proposal_digest(proposal)
        if expected_digest != digest:
            raise ApprovalError("Proposal changed after it was presented for review.")
        now = time.time() if now_epoch is None else now_epoch
        if now >= proposal["expires_at_epoch"]:
            raise ApprovalError("Refund proposal has expired.")
        approval_id = _stable_id("rejection", proposal_id, digest)
        with _connect(self.database_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT proposal_digest, status, operator_id FROM refund_approvals WHERE proposal_id = ?",
                (proposal_id,),
            ).fetchone()
            if existing is not None:
                connection.rollback()
                raise ApprovalError(f"Proposal already has status {existing['status']}.")
            connection.execute(
                "INSERT INTO refund_approvals(proposal_id, proposal_digest, operator_id, status, approval_id, decided_at_epoch) VALUES (?, ?, ?, 'rejected', ?, ?)",
                (proposal_id, digest, operator_id, approval_id, now),
            )
            connection.commit()
        return {
            "proposal_id": proposal_id,
            "proposal_digest": digest,
            "operator_id": operator_id,
            "status": "rejected",
            "approval_id": approval_id,
            "review_id": review["review_id"],
        }

    def outbox_status(self, outbox_id: str) -> dict[str, Any] | None:
        with _connect(self.database_path) as connection:
            row = connection.execute("SELECT * FROM refund_outbox WHERE outbox_id = ?", (outbox_id,)).fetchone()
        if row is None:
            return None
        return dict(row)

    def outbox_count(self, proposal_id: str | None = None) -> int:
        with _connect(self.database_path) as connection:
            if proposal_id is None:
                row = connection.execute("SELECT COUNT(*) AS count FROM refund_outbox").fetchone()
            else:
                row = connection.execute(
                    "SELECT COUNT(*) AS count FROM refund_outbox WHERE proposal_id = ?", (proposal_id,)
                ).fetchone()
        return int(row["count"])

    def claim_next(self, now_epoch: float | None = None, lease_seconds: int = 30) -> dict[str, Any] | None:
        now = time.time() if now_epoch is None else now_epoch
        token = secrets.token_hex(16)
        with _connect(self.database_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """SELECT * FROM refund_outbox
                   WHERE status = 'pending' OR (status = 'processing' AND lease_until_epoch <= ?)
                   ORDER BY created_at_epoch, outbox_id LIMIT 1""",
                (now,),
            ).fetchone()
            if row is None:
                connection.commit()
                return None
            connection.execute(
                """UPDATE refund_outbox SET status = 'processing', claim_token = ?,
                   lease_until_epoch = ?, attempts = attempts + 1, updated_at_epoch = ?
                   WHERE outbox_id = ?""",
                (token, now + lease_seconds, now, row["outbox_id"]),
            )
            connection.commit()
        claimed = dict(row)
        claimed["claim_token"] = token
        claimed["lease_until_epoch"] = now + lease_seconds
        claimed["attempts"] = row["attempts"] + 1
        claimed["payload"] = json.loads(row["payload_json"])
        return claimed

    def complete(self, outbox_id: str, claim_token: str, provider_result: dict[str, Any], now_epoch: float | None = None) -> dict[str, Any]:
        now = time.time() if now_epoch is None else now_epoch
        with _connect(self.database_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT status, claim_token FROM refund_outbox WHERE outbox_id = ?", (outbox_id,)
            ).fetchone()
            if row is None or row["status"] != "processing" or row["claim_token"] != claim_token:
                connection.rollback()
                raise ApprovalError("Outbox claim is stale or no longer owned by this worker.")
            connection.execute(
                """UPDATE refund_outbox SET status = 'completed', provider_refund_id = ?,
                   claim_token = NULL, lease_until_epoch = NULL, updated_at_epoch = ?
                   WHERE outbox_id = ?""",
                (provider_result["refund_id"], now, outbox_id),
            )
            connection.commit()
        return {"outbox_id": outbox_id, **provider_result, "status": "completed"}

    def process_one(
        self,
        provider: "MockPaymentProvider",
        now_epoch: float | None = None,
        lease_seconds: int = 30,
        crash_after_provider: bool = False,
    ) -> dict[str, Any] | None:
        claim = self.claim_next(now_epoch=now_epoch, lease_seconds=lease_seconds)
        if claim is None:
            return None
        result = provider.refund(claim["payload"], claim["idempotency_key"])
        if crash_after_provider:
            raise SimulatedWorkerCrash("worker stopped after provider success, before outbox completion")
        return self.complete(claim["outbox_id"], claim["claim_token"], result, now_epoch=now_epoch)


class SimulatedWorkerCrash(RuntimeError):
    pass


class MockPaymentProvider:
    """External-provider stand-in with its own durable idempotency ledger."""

    def __init__(self, database_path: str | Path):
        self.store = SQLiteIdempotencyStore(database_path)
        self.attempts = 0

    def refund(self, payload: dict[str, Any], idempotency_key: str) -> dict[str, Any]:
        self.attempts += 1
        request = {
            key: payload[key]
            for key in ("proposal_id", "proposal_digest", "order_ref", "amount_cents", "currency")
        }
        refund_id = "rf_" + _stable_id(idempotency_key)
        return self.store.put_if_absent(
            "provider_refunds",
            idempotency_key,
            request,
            {"refund_id": refund_id, "status": "succeeded"},
        )

    def unique_refund_count(self) -> int:
        return len(self.store.all("provider_refunds"))
