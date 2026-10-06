"""Exercise SQLite recovery after a tool side effect but before its journal result."""

from __future__ import annotations

import sqlite3
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from types import SimpleNamespace

from durable_state import (
    RunLeaseBusy,
    RunLeaseLost,
    RunNotClaimable,
    RunStateConflict,
    SQLiteIdempotencyStore,
    SQLiteRunJournal,
)
from support_agent import AgentLoop, AnthropicPlanner, Decision, RunContext, ScriptedPlanner, ToolRuntime


class SimulatedCrash(RuntimeError):
    pass


class ManualClock:
    def __init__(self, now=1_000.0):
        self.now = now

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class CrashAfterReviewWrite(ToolRuntime):
    def call(self, name, arguments, context):
        result = super().call(name, arguments, context)
        if name == "request_human_review":
            raise SimulatedCrash("process stopped after review write, before journal result")
        return result


class SlowReviewWrite(ToolRuntime):
    def __init__(self, idempotency_store, journal):
        super().__init__(idempotency_store=idempotency_store)
        self.journal = journal

    def call(self, name, arguments, context):
        result = super().call(name, arguments, context)
        if name == "request_human_review":
            deadline = time.monotonic() + 1.0
            while self.journal.renew_count < 8 and time.monotonic() < deadline:
                time.sleep(0.005)
        return result


class CountingRunJournal(SQLiteRunJournal):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.renew_count = 0

    def renew_lease(self, lease):
        self.renew_count += 1
        return super().renew_lease(lease)


class FailingHeartbeatJournal(SQLiteRunJournal):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fail_heartbeat = False

    def renew_lease(self, lease):
        if self.fail_heartbeat:
            raise RunLeaseLost("simulated heartbeat failure")
        return super().renew_lease(lease)


class FailHeartbeatDuringReview(ToolRuntime):
    def __init__(self, idempotency_store, journal):
        super().__init__(idempotency_store=idempotency_store)
        self.journal = journal

    def call(self, name, arguments, context):
        result = super().call(name, arguments, context)
        if name == "request_human_review":
            self.journal.fail_heartbeat = True
            time.sleep(0.18)
        return result


class MustNotRun:
    def next_action(self, user_request, observations):
        raise AssertionError("A completed run should be returned from the journal without another model call.")


class FakeMessages:
    def __init__(self, actions):
        self.actions = list(actions)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        action = self.actions.pop(0)
        if isinstance(action, Exception):
            raise action
        return action


def fake_response(stop_reason, content, input_tokens, output_tokens):
    return SimpleNamespace(
        stop_reason=stop_reason,
        content=content,
        usage=SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens),
    )


def main() -> int:
    request = "Please refund ORD-100; it arrived too late."
    context = RunContext(subject_id="customer-ada", task_id="durable-review-check")
    clock = ManualClock()
    decisions = [
        Decision.call(
            "prepare_refund_proposal",
            {"order_ref": "ORD-100", "reason": "arrived too late"},
        ),
        Decision.call("request_human_review", {"proposal_id": {"$last": "proposal_id"}}),
        Decision.answer("The refund proposal remains pending human review."),
    ]

    with tempfile.TemporaryDirectory(prefix="agentic-state-") as temp_dir:
        database_path = Path(temp_dir) / "agent-state.sqlite3"
        journal = SQLiteRunJournal(database_path, lease_seconds=5, clock=clock)
        first_store = SQLiteIdempotencyStore(database_path)
        crashing_runtime = CrashAfterReviewWrite(first_store)
        try:
            AgentLoop(crashing_runtime).run(
                request,
                context,
                ScriptedPlanner(decisions),
                journal=journal,
            )
        except SimulatedCrash:
            pass
        else:
            raise AssertionError("The crash point did not run.")

        assert len(first_store.all("reviews")) == 1
        clock.advance(6)
        restarted_journal = SQLiteRunJournal(database_path, lease_seconds=5, clock=clock)
        restarted_store = SQLiteIdempotencyStore(database_path)
        restarted_runtime = ToolRuntime(idempotency_store=restarted_store)
        resumed = AgentLoop(restarted_runtime).run(
            request,
            context,
            ScriptedPlanner([Decision.answer("The refund proposal remains pending human review.")]),
            journal=restarted_journal,
        )
        assert resumed.status == "complete"
        assert [event["tool"] for event in resumed.tool_trace] == [
            "prepare_refund_proposal",
            "request_human_review",
        ]
        assert restarted_runtime.review_count(context.task_id) == 1
        assert len(restarted_store.all("reviews")) == 1
        assert not restarted_runtime.payment_events
        print("PASS  resume replays an interrupted tool request with one durable review item")

        repeated = AgentLoop(restarted_runtime).run(
            request,
            context,
            MustNotRun(),
            journal=restarted_journal,
        )
        assert repeated == resumed
        assert restarted_runtime.review_count(context.task_id) == 1
        print("PASS  completed run returns from the journal without another planner call")

        restarted_store.put_if_absent("demo", "same-key", {"order_ref": "ORD-100"}, {"status": "saved"})
        try:
            restarted_store.put_if_absent("demo", "same-key", {"order_ref": "ORD-200"}, {"status": "saved"})
        except ValueError:
            print("PASS  idempotency key cannot silently bind to a different request")
        else:
            raise AssertionError("Idempotency store accepted a conflicting request under the same key.")

        try:
            restarted_journal.start_run(
                context.task_id,
                request,
                RunContext(subject_id="customer-blair", task_id=context.task_id),
            )
        except ValueError:
            print("PASS  run ID cannot be resumed under a different authenticated subject")
        else:
            raise AssertionError("Journal accepted a run ID bound to a different subject.")

        # Verify the journal can rebuild the Anthropic assistant/tool-result transcript.
        transcript_db = Path(temp_dir) / "anthropic-session.sqlite3"
        transcript_journal = SQLiteRunJournal(transcript_db, lease_seconds=5, clock=clock)
        transcript_context = RunContext(subject_id="customer-ada", task_id="durable-anthropic-check")
        tool_content = [
            {"type": "text", "text": "I will check the approved policy."},
            {
                "type": "tool_use",
                "id": "toolu-durable-policy",
                "name": "search_policy",
                "input": {"topic": "refunds"},
            },
        ]
        first_client = SimpleNamespace(
            messages=FakeMessages(
                [
                    fake_response("tool_use", tool_content, 5, 2),
                    SimulatedCrash("worker stopped before the next model response"),
                ]
            )
        )
        try:
            AgentLoop(ToolRuntime()).run(
                "What is the return window?",
                transcript_context,
                AnthropicPlanner(model="fake-model", client=first_client),
                journal=transcript_journal,
            )
        except SimulatedCrash:
            pass
        else:
            raise AssertionError("The provider crash point did not run.")

        clock.advance(6)
        final_client = SimpleNamespace(
            messages=FakeMessages(
                [fake_response("end_turn", [{"type": "text", "text": "30 days (RET-01)."}], 7, 3)]
            )
        )
        final_result = AgentLoop(ToolRuntime()).run(
            "What is the return window?",
            transcript_context,
            AnthropicPlanner(model="fake-model", client=final_client),
            journal=SQLiteRunJournal(transcript_db),
        )
        resumed_messages = final_client.messages.calls[0]["messages"]
        assert final_result.status == "complete"
        assert len(resumed_messages) == 3
        assert resumed_messages[1] == {"role": "assistant", "content": tool_content}
        assert resumed_messages[2]["content"][0]["tool_use_id"] == "toolu-durable-policy"
        assert final_result.model_metrics["model_turns"] == 2
        assert final_result.model_metrics["input_tokens"] == 12
        assert final_result.model_metrics["output_tokens"] == 5
        print("PASS  Anthropic tool transcript and usage resume after a worker restart")

        lease_db = Path(temp_dir) / "lease-check.sqlite3"
        lease_journal = SQLiteRunJournal(lease_db, lease_seconds=5, clock=clock)
        lease_context = RunContext(subject_id="customer-ada", task_id="lease-check")
        lease_journal.start_run("lease-check", "Explain the return policy.", lease_context)
        first_lease = lease_journal.claim_run("lease-check", "worker-a")
        try:
            lease_journal.claim_run("lease-check", "worker-b")
        except RunLeaseBusy:
            print("PASS  only one worker can hold an unexpired run lease")
        else:
            raise AssertionError("A second worker claimed a run with an active lease.")

        race_context = RunContext(subject_id="customer-ada", task_id="claim-race")
        lease_journal.start_run("claim-race", "Race for this run claim.", race_context)
        claim_barrier = Barrier(2)

        def attempt_claim(worker):
            claim_barrier.wait(timeout=2)
            try:
                return lease_journal.claim_run("claim-race", worker)
            except RunLeaseBusy:
                return None

        with ThreadPoolExecutor(max_workers=2) as pool:
            race_results = list(pool.map(attempt_claim, ("race-worker-a", "race-worker-b")))
        assert sum(result is not None for result in race_results) == 1
        print("PASS  concurrent claim race grants the run to exactly one worker")

        clock.advance(6)
        second_lease = lease_journal.claim_run("lease-check", "worker-b")
        assert second_lease.fencing_token > first_lease.fencing_token
        try:
            lease_journal.record_decision(first_lease, 1, Decision.answer("Stale answer."))
        except RunLeaseLost:
            print("PASS  expired worker is fenced out after lease takeover")
        else:
            raise AssertionError("An expired worker appended a run decision.")

        advanced_lease = lease_journal.record_decision(
            second_lease, 1, Decision.answer("Returns are accepted within 30 days.")
        )
        try:
            lease_journal.finish_run(
                second_lease,
                SimpleNamespace(
                    status="complete",
                    answer="Stale version.",
                    tool_trace=[],
                    turns=1,
                    model_metrics={},
                ),
            )
        except RunStateConflict:
            print("PASS  compare-and-swap state version rejects an obsolete worker snapshot")
        else:
            raise AssertionError("A stale run-state version was allowed to finish the run.")

        from support_agent import RunResult

        lease_journal.finish_run(
            advanced_lease,
            RunResult("complete", "Returns are accepted within 30 days.", [], 1, {}),
        )
        try:
            lease_journal.claim_run("lease-check", "worker-c")
        except RunNotClaimable:
            print("PASS  terminal run cannot be claimed again")
        else:
            raise AssertionError("A terminal run was claimed for new execution.")

        legacy_db = Path(temp_dir) / "legacy-journal.sqlite3"
        with sqlite3.connect(legacy_db) as connection:
            connection.executescript(
                """
                CREATE TABLE agent_runs (
                    run_id TEXT PRIMARY KEY,
                    subject_id TEXT NOT NULL,
                    request TEXT NOT NULL,
                    status TEXT NOT NULL,
                    turns INTEGER NOT NULL DEFAULT 0,
                    final_result_json TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE agent_run_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL REFERENCES agent_runs(run_id),
                    event_type TEXT NOT NULL,
                    turn_number INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
        migrated_journal = SQLiteRunJournal(legacy_db, lease_seconds=5, clock=clock)
        migrated_journal.start_run(
            "legacy-run",
            "Resume a run created with the earlier schema.",
            RunContext(subject_id="customer-ada", task_id="legacy-run"),
        )
        migrated_lease = migrated_journal.claim_run("legacy-run", "migration-worker")
        assert migrated_lease.fencing_token == 1
        with sqlite3.connect(legacy_db) as connection:
            migrated_columns = {
                row[1] for row in connection.execute("PRAGMA table_info(agent_runs)")
            }
        assert {"state_version", "fencing_token", "lease_owner", "lease_until"} <= migrated_columns
        print("PASS  existing journal schema receives additive lease/version fields")

        slow_db = Path(temp_dir) / "slow-tool.sqlite3"
        slow_journal = CountingRunJournal(slow_db, lease_seconds=0.06)
        slow_store = SQLiteIdempotencyStore(slow_db)
        slow_context = RunContext(subject_id="customer-ada", task_id="slow-tool-heartbeat")
        slow_result = AgentLoop(SlowReviewWrite(slow_store, slow_journal)).run(
            request,
            slow_context,
            ScriptedPlanner(decisions),
            journal=slow_journal,
        )
        assert slow_result.status == "complete"
        assert slow_journal.renew_count >= 8
        assert len(slow_store.all("reviews")) == 1
        print("PASS  background heartbeat keeps the lease alive during a slow tool call")

        fail_db = Path(temp_dir) / "heartbeat-failure.sqlite3"
        fail_journal = FailingHeartbeatJournal(fail_db, lease_seconds=0.06)
        fail_store = SQLiteIdempotencyStore(fail_db)
        fail_context = RunContext(subject_id="customer-ada", task_id="heartbeat-failure")
        try:
            AgentLoop(FailHeartbeatDuringReview(fail_store, fail_journal)).run(
                request,
                fail_context,
                ScriptedPlanner(decisions),
                journal=fail_journal,
            )
        except RunLeaseLost:
            pass
        else:
            raise AssertionError("A worker continued after its heartbeat failed.")
        interrupted = fail_journal.snapshot(fail_context.task_id)
        assert interrupted.pending_decision is not None
        assert interrupted.pending_decision.tool_name == "request_human_review"
        assert len(fail_store.all("reviews")) == 1
        fail_journal.fail_heartbeat = False
        recovered = AgentLoop(ToolRuntime(idempotency_store=fail_store)).run(
            request,
            fail_context,
            ScriptedPlanner([Decision.answer("The refund proposal remains pending human review.")]),
            journal=fail_journal,
        )
        assert recovered.status == "complete"
        assert len(fail_store.all("reviews")) == 1
        print("PASS  heartbeat failure stops journal progress and idempotent replay recovers")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
