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

    def __init__(
        self,
        database_path: str | Path,
        proposal_store: SQLiteIdempotencyStore,
        authorized_operators: set[str],
    ):
        self.database_path = str(database_path)
        self.proposal_store = proposal_store
        self.authorized_operators = set(authorized_operators)
        Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        with _connect(self.database_path) as connection:
            connection.execute("PRAGMA journal_mode = WAL")
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
        now = time.time() if now_epoch is None else now_epoch
        if now >= proposal["expires_at_epoch"]:
            raise ApprovalError("Refund proposal has expired.")

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

            connection.execute(
                "INSERT INTO refund_approvals(proposal_id, proposal_digest, operator_id, status, approval_id, decided_at_epoch) VALUES (?, ?, ?, 'approved', ?, ?)",
                (proposal_id, digest, operator_id, approval_id, now),
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
                    now,
                    now,
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
