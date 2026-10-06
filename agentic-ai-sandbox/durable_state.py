"""SQLite journals and idempotency records for crash-recovery exercises."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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


class SQLiteRunJournal:
    """Persist model decisions and tool results so a run can resume after a crash.

    This teaching implementation assumes one active worker per run. Production
    systems also need a lease or compare-and-swap claim so concurrent workers do
    not both advance the same session.
    """

    def __init__(self, database_path: str | Path):
        self.database_path = str(database_path)
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

    def record_decision(self, run_id: str, turn_number: int, decision: Decision) -> None:
        payload = {
            "kind": decision.kind,
            "text": decision.text,
            "tool_name": decision.tool_name,
            "arguments": decision.arguments,
            "provider_message": decision.provider_message,
            "tool_use_id": decision.tool_use_id,
            "model_metrics": decision.model_metrics,
        }
        with _connect(self.database_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT turns, status FROM agent_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            if row is None or row["status"] != "running" or row["turns"] != turn_number - 1:
                connection.rollback()
                raise RuntimeError("Run changed before this decision could be recorded.")
            connection.execute(
                "INSERT INTO agent_run_events(run_id, event_type, turn_number, payload_json) VALUES (?, 'decision', ?, ?)",
                (run_id, turn_number, json.dumps(payload, ensure_ascii=False)),
            )
            connection.execute(
                "UPDATE agent_runs SET turns = ?, updated_at = CURRENT_TIMESTAMP WHERE run_id = ?",
                (turn_number, run_id),
            )
            connection.commit()

    def record_tool_result(
        self, run_id: str, turn_number: int, observation: dict[str, Any]
    ) -> None:
        payload = {key: observation[key] for key in ("tool", "ok", "result")}
        with _connect(self.database_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "INSERT INTO agent_run_events(run_id, event_type, turn_number, payload_json) VALUES (?, 'tool_result', ?, ?)",
                (run_id, turn_number, json.dumps(payload, ensure_ascii=False)),
            )
            connection.execute(
                "UPDATE agent_runs SET updated_at = CURRENT_TIMESTAMP WHERE run_id = ? AND status = 'running'",
                (run_id,),
            )
            connection.commit()

    def finish_run(self, run_id: str, result: RunResult) -> None:
        payload = {
            "status": result.status,
            "answer": result.answer,
            "tool_trace": result.tool_trace,
            "turns": result.turns,
            "model_metrics": result.model_metrics,
        }
        with _connect(self.database_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "UPDATE agent_runs SET status = ?, final_result_json = ?, updated_at = CURRENT_TIMESTAMP WHERE run_id = ? AND status = 'running'",
                (result.status, json.dumps(payload, ensure_ascii=False), run_id),
            )
            connection.commit()

    def snapshot(self, run_id: str) -> RunSnapshot:
        with _connect(self.database_path) as connection:
            run = connection.execute(
                "SELECT status, turns, final_result_json FROM agent_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            if run is None:
                raise KeyError(f"Run does not exist: {run_id}")
            events = connection.execute(
                "SELECT event_type, turn_number, payload_json FROM agent_run_events WHERE run_id = ? ORDER BY event_id",
                (run_id,),
            ).fetchall()

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
