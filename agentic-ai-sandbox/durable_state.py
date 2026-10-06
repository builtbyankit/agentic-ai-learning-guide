"""SQLite journals and idempotency records for crash-recovery exercises."""

from __future__ import annotations

import json
import math
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from support_agent import Decision, RunContext, RunResult


def _connect(path: str) -> sqlite3.Connection:
    connection = sqlite3.connect(path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


class SQLiteIdempotencyStore:
    """Persist write-once operation results behind a unique key."""

    def __init__(self, database_path: str | Path):
        self.database_path = str(database_path)
        Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        with _connect(self.database_path) as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute(
                """CREATE TABLE IF NOT EXISTS idempotent_operations (
                    namespace TEXT NOT NULL,
                    operation_key TEXT NOT NULL,
                    request_json TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    PRIMARY KEY(namespace, operation_key)
                )"""
            )

    def put_if_absent(
        self,
        namespace: str,
        key: str,
        request: dict[str, Any],
        value: dict[str, Any],
    ) -> dict[str, Any]:
        request_encoded = json.dumps(request, ensure_ascii=False, sort_keys=True)
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True)
        with _connect(self.database_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "INSERT OR IGNORE INTO idempotent_operations(namespace, operation_key, request_json, result_json) VALUES (?, ?, ?, ?)",
                (namespace, key, request_encoded, encoded),
            )
            row = connection.execute(
                "SELECT request_json, result_json FROM idempotent_operations WHERE namespace = ? AND operation_key = ?",
                (namespace, key),
            ).fetchone()
            connection.commit()
        if row is None:
            raise RuntimeError("Idempotent operation result was not stored.")
        if row["request_json"] != request_encoded:
            raise ValueError("Idempotency key was reused with a different request.")
        return json.loads(row["result_json"])

    def get(self, namespace: str, key: str) -> dict[str, Any] | None:
        with _connect(self.database_path) as connection:
            row = connection.execute(
                "SELECT result_json FROM idempotent_operations WHERE namespace = ? AND operation_key = ?",
                (namespace, key),
            ).fetchone()
        return json.loads(row["result_json"]) if row else None

    def all(self, namespace: str) -> list[dict[str, Any]]:
        with _connect(self.database_path) as connection:
            rows = connection.execute(
                "SELECT result_json FROM idempotent_operations WHERE namespace = ? ORDER BY operation_key",
                (namespace,),
            ).fetchall()
        return [json.loads(row["result_json"]) for row in rows]


@dataclass
class RunSnapshot:
    status: str
    observations: list[dict[str, Any]]
    tool_trace: list[dict[str, Any]]
    turns: int
    model_metrics: dict[str, int | float]
    pending_decision: Decision | None = None
    terminal_result: RunResult | None = None


class RunLeaseBusy(RuntimeError):
    """Another worker currently owns an unexpired lease for this run."""


class RunLeaseLost(RuntimeError):
    """A worker no longer owns a valid lease for a run."""


class RunStateConflict(RuntimeError):
    """A worker attempted a write from an obsolete run-state version."""


class RunNotClaimable(RuntimeError):
    """A run is terminal or otherwise cannot be claimed for execution."""


@dataclass(frozen=True)
class RunLease:
    run_id: str
    worker_id: str
    fencing_token: int
    state_version: int
    expires_at: float


class SQLiteRunJournal:
    """Persist run events and coordinate workers with leases and fencing tokens.

    SQLite serializes claim/write transactions. Every journal mutation requires
    the current lease token and state version; downstream side effects still
    need idempotency or their own fencing support.
    """

    def __init__(
        self,
        database_path: str | Path,
        lease_seconds: float = 60.0,
        clock: Callable[[], float] = time.time,
    ):
        if not math.isfinite(lease_seconds) or lease_seconds <= 0:
            raise ValueError("Lease duration must be a finite positive number.")
        self.database_path = str(database_path)
        self.lease_seconds = lease_seconds
        self._clock = clock
        Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        with _connect(self.database_path) as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute(
                """CREATE TABLE IF NOT EXISTS agent_runs (
                    run_id TEXT PRIMARY KEY,
                    subject_id TEXT NOT NULL,
                    request TEXT NOT NULL,
                    status TEXT NOT NULL,
                    turns INTEGER NOT NULL DEFAULT 0,
                    state_version INTEGER NOT NULL DEFAULT 0,
                    fencing_token INTEGER NOT NULL DEFAULT 0,
                    lease_owner TEXT,
                    lease_until REAL,
                    final_result_json TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )"""
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS agent_run_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL REFERENCES agent_runs(run_id),
                    event_type TEXT NOT NULL,
                    turn_number INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )"""
            )
            # Keep existing teaching databases readable when the schema grows.
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(agent_runs)").fetchall()
            }
            for name, definition in (
                ("state_version", "INTEGER NOT NULL DEFAULT 0"),
                ("fencing_token", "INTEGER NOT NULL DEFAULT 0"),
                ("lease_owner", "TEXT"),
                ("lease_until", "REAL"),
            ):
                if name not in columns:
                    connection.execute(f"ALTER TABLE agent_runs ADD COLUMN {name} {definition}")

    def start_run(self, run_id: str, request: str, context: RunContext) -> None:
        with _connect(self.database_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT subject_id, request FROM agent_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            if row is None:
                connection.execute(
                    "INSERT INTO agent_runs(run_id, subject_id, request, status) VALUES (?, ?, ?, 'running')",
                    (run_id, context.subject_id, request),
                )
            elif row["subject_id"] != context.subject_id or row["request"] != request:
                connection.rollback()
                raise ValueError("Run ID is already bound to a different subject or request.")
            connection.commit()

    def claim_run(self, run_id: str, worker_id: str) -> RunLease:
        if not isinstance(worker_id, str) or not worker_id.strip() or len(worker_id) > 200:
            raise ValueError("Worker ID must be a non-empty string of at most 200 characters.")
        now = self._clock()
        expires_at = now + self.lease_seconds
        with _connect(self.database_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT status, state_version, fencing_token, lease_owner, lease_until "
                "FROM agent_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            if row is None:
                connection.rollback()
                raise KeyError(f"Run does not exist: {run_id}")
            if row["status"] != "running":
                connection.rollback()
                raise RunNotClaimable(f"Run cannot be claimed from status {row['status']}.")
            if row["lease_owner"] is not None and row["lease_until"] is not None and row["lease_until"] > now:
                connection.rollback()
                raise RunLeaseBusy(f"Run is leased by worker {row['lease_owner']}.")
            token = row["fencing_token"] + 1
            version = row["state_version"]
            changed = connection.execute(
                "UPDATE agent_runs SET lease_owner = ?, lease_until = ?, fencing_token = ?, "
                "updated_at = CURRENT_TIMESTAMP WHERE run_id = ? AND status = 'running' "
                "AND state_version = ? AND fencing_token = ?",
                (worker_id, expires_at, token, run_id, version, row["fencing_token"]),
            ).rowcount
            if changed != 1:
                connection.rollback()
                raise RunStateConflict("Run changed while the worker was claiming it.")
            connection.commit()
        return RunLease(run_id, worker_id, token, version, expires_at)

    def renew_lease(self, lease: RunLease) -> RunLease:
        now = self._clock()
        expires_at = now + self.lease_seconds
        with _connect(self.database_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._assert_lease(connection, lease, now)
            changed = connection.execute(
                "UPDATE agent_runs SET lease_until = ?, updated_at = CURRENT_TIMESTAMP "
                "WHERE run_id = ? AND status = 'running' AND lease_owner = ? "
                "AND fencing_token = ? AND state_version = ? AND lease_until > ?",
                (
                    expires_at,
                    lease.run_id,
                    lease.worker_id,
                    lease.fencing_token,
                    lease.state_version,
                    now,
                ),
            ).rowcount
            if changed != 1:
                connection.rollback()
                raise RunLeaseLost("Worker lease expired before it could be renewed.")
            connection.commit()
        return RunLease(
            lease.run_id,
            lease.worker_id,
            lease.fencing_token,
            lease.state_version,
            expires_at,
        )

    @staticmethod
    def _assert_lease(
        connection: sqlite3.Connection, lease: RunLease, now: float
    ) -> sqlite3.Row:
        row = connection.execute(
            "SELECT status, state_version, fencing_token, lease_owner, lease_until, turns "
            "FROM agent_runs WHERE run_id = ?",
            (lease.run_id,),
        ).fetchone()
        if (
            row is None
            or row["status"] != "running"
            or row["lease_owner"] != lease.worker_id
            or row["fencing_token"] != lease.fencing_token
            or row["lease_until"] is None
            or row["lease_until"] <= now
        ):
            raise RunLeaseLost("Worker no longer holds a live lease for this run.")
        if row["state_version"] != lease.state_version:
            raise RunStateConflict("Worker state version is stale; reload the run before writing.")
        return row

    def record_decision(
        self, lease: RunLease, turn_number: int, decision: Decision
    ) -> RunLease:
        payload = {
            "kind": decision.kind,
            "text": decision.text,
            "tool_name": decision.tool_name,
            "arguments": decision.arguments,
            "provider_message": decision.provider_message,
            "tool_use_id": decision.tool_use_id,
            "model_metrics": decision.model_metrics,
        }
        now = self._clock()
        with _connect(self.database_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = self._assert_lease(connection, lease, now)
            if row["turns"] != turn_number - 1:
                connection.rollback()
                raise RuntimeError("Run changed before this decision could be recorded.")
            previous = connection.execute(
                "SELECT event_type, payload_json FROM agent_run_events "
                "WHERE run_id = ? ORDER BY event_id DESC LIMIT 1",
                (lease.run_id,),
            ).fetchone()
            if previous is not None and previous["event_type"] == "decision":
                connection.rollback()
                raise RuntimeError("The previous decision has not been resolved in the journal.")
            connection.execute(
                "INSERT INTO agent_run_events(run_id, event_type, turn_number, payload_json) VALUES (?, 'decision', ?, ?)",
                (lease.run_id, turn_number, json.dumps(payload, ensure_ascii=False)),
            )
            changed = connection.execute(
                "UPDATE agent_runs SET turns = ?, state_version = state_version + 1, "
                "updated_at = CURRENT_TIMESTAMP WHERE run_id = ? AND status = 'running' "
                "AND lease_owner = ? AND fencing_token = ? AND state_version = ? AND lease_until > ?",
                (
                    turn_number,
                    lease.run_id,
                    lease.worker_id,
                    lease.fencing_token,
                    lease.state_version,
                    now,
                ),
            ).rowcount
            if changed != 1:
                connection.rollback()
                raise RunLeaseLost("Lease or run state changed before the decision was committed.")
            connection.commit()
        return RunLease(
            lease.run_id,
            lease.worker_id,
            lease.fencing_token,
            lease.state_version + 1,
            lease.expires_at,
        )

    def record_tool_result(
        self, lease: RunLease, turn_number: int, observation: dict[str, Any]
    ) -> RunLease:
        payload = {key: observation[key] for key in ("tool", "ok", "result")}
        now = self._clock()
        with _connect(self.database_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = self._assert_lease(connection, lease, now)
            previous = connection.execute(
                "SELECT event_type, turn_number, payload_json FROM agent_run_events "
                "WHERE run_id = ? ORDER BY event_id DESC LIMIT 1",
                (lease.run_id,),
            ).fetchone()
            if previous is None or previous["event_type"] != "decision" or previous["turn_number"] != turn_number:
                connection.rollback()
                raise RuntimeError("Tool result does not match the current journal decision.")
            decision_payload = json.loads(previous["payload_json"])
            if decision_payload.get("kind") != "tool" or decision_payload.get("tool_name") != payload["tool"]:
                connection.rollback()
                raise RuntimeError("Tool result does not match the recorded tool request.")
            connection.execute(
                "INSERT INTO agent_run_events(run_id, event_type, turn_number, payload_json) VALUES (?, 'tool_result', ?, ?)",
                (lease.run_id, turn_number, json.dumps(payload, ensure_ascii=False)),
            )
            changed = connection.execute(
                "UPDATE agent_runs SET state_version = state_version + 1, updated_at = CURRENT_TIMESTAMP "
                "WHERE run_id = ? AND status = 'running' AND lease_owner = ? AND fencing_token = ? "
                "AND state_version = ? AND lease_until > ?",
                (
                    lease.run_id,
                    lease.worker_id,
                    lease.fencing_token,
                    lease.state_version,
                    now,
                ),
            ).rowcount
            if changed != 1:
                connection.rollback()
                raise RunLeaseLost("Lease or run state changed before the tool result was committed.")
            connection.commit()
        return RunLease(
            lease.run_id,
            lease.worker_id,
            lease.fencing_token,
            lease.state_version + 1,
            lease.expires_at,
        )

    def finish_run(self, lease: RunLease, result: RunResult) -> None:
        payload = {
            "status": result.status,
            "answer": result.answer,
            "tool_trace": result.tool_trace,
            "turns": result.turns,
            "model_metrics": result.model_metrics,
        }
        now = self._clock()
        with _connect(self.database_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = self._assert_lease(connection, lease, now)
            if row["turns"] != result.turns:
                connection.rollback()
                raise RunStateConflict("Final result turn count does not match the journal.")
            changed = connection.execute(
                "UPDATE agent_runs SET status = ?, final_result_json = ?, state_version = state_version + 1, "
                "lease_owner = NULL, lease_until = NULL, updated_at = CURRENT_TIMESTAMP "
                "WHERE run_id = ? AND status = 'running' AND lease_owner = ? AND fencing_token = ? "
                "AND state_version = ? AND lease_until > ?",
                (
                    result.status,
                    json.dumps(payload, ensure_ascii=False),
                    lease.run_id,
                    lease.worker_id,
                    lease.fencing_token,
                    lease.state_version,
                    now,
                ),
            ).rowcount
            if changed != 1:
                connection.rollback()
                raise RunLeaseLost("Lease or run state changed before the final result was committed.")
            connection.commit()

    def snapshot(self, run_id: str) -> RunSnapshot:
        with _connect(self.database_path) as connection:
            connection.execute("BEGIN")
            run = connection.execute(
                "SELECT status, turns, final_result_json FROM agent_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            if run is None:
                raise KeyError(f"Run does not exist: {run_id}")
            events = connection.execute(
                "SELECT event_type, turn_number, payload_json FROM agent_run_events WHERE run_id = ? ORDER BY event_id",
                (run_id,),
            ).fetchall()
            connection.commit()

        if run["final_result_json"]:
            final = json.loads(run["final_result_json"])
            return RunSnapshot(
                status=run["status"],
                observations=[],
                tool_trace=final["tool_trace"],
                turns=final["turns"],
                model_metrics=final["model_metrics"],
                terminal_result=RunResult(
                    final["status"],
                    final["answer"],
                    final["tool_trace"],
                    final["turns"],
                    final["model_metrics"],
                ),
            )

        observations: list[dict[str, Any]] = []
        trace: list[dict[str, Any]] = []
        pending: tuple[int, dict[str, Any]] | None = None
        pending_terminal: Decision | None = None
        metrics: dict[str, int | float] = {
            "model_turns": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "latency_ms": 0,
        }
        for event in events:
            payload = json.loads(event["payload_json"])
            if event["event_type"] == "decision":
                pending = (event["turn_number"], payload) if payload["kind"] == "tool" else None
                pending_terminal = None
                for key, value in payload["model_metrics"].items():
                    metrics[key] = metrics.get(key, 0) + value
                if payload["kind"] in ("final", "handoff"):
                    pending_terminal = Decision(
                        kind=payload["kind"],
                        text=payload["text"],
                        model_metrics=payload["model_metrics"],
                    )
            elif event["event_type"] == "tool_result":
                if pending is None or pending[0] != event["turn_number"]:
                    raise RuntimeError("Journal contains a tool result without its decision.")
                decision = pending[1]
                observation = {
                    "tool": payload["tool"],
                    "ok": payload["ok"],
                    "result": payload["result"],
                    "_assistant_content": decision["provider_message"],
                    "_tool_use_id": decision["tool_use_id"],
                }
                observations.append(observation)
                trace.append(
                    {
                        "tool": decision["tool_name"],
                        "arguments": decision["arguments"],
                        "ok": payload["ok"],
                        "result": payload["result"],
                    }
                )
                pending = None
                pending_terminal = None
        pending_decision = None
        if pending is not None:
            turn_number, payload = pending
            pending_decision = Decision(
                kind="tool",
                tool_name=payload["tool_name"],
                arguments=payload["arguments"],
                provider_message=payload["provider_message"],
                tool_use_id=payload["tool_use_id"],
            )
        elif pending_terminal is not None:
            pending_decision = pending_terminal
        return RunSnapshot(
            status=run["status"],
            observations=observations,
            tool_trace=trace,
            turns=run["turns"],
            model_metrics=metrics,
            pending_decision=pending_decision,
        )
