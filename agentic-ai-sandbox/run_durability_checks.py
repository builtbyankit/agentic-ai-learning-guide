"""Exercise SQLite recovery after a tool side effect but before its journal result."""

from __future__ import annotations

import tempfile
from pathlib import Path
from types import SimpleNamespace

from durable_state import SQLiteIdempotencyStore, SQLiteRunJournal
from support_agent import AgentLoop, AnthropicPlanner, Decision, RunContext, ScriptedPlanner, ToolRuntime


class SimulatedCrash(RuntimeError):
    pass


class CrashAfterReviewWrite(ToolRuntime):
    def call(self, name, arguments, context):
        result = super().call(name, arguments, context)
        if name == "request_human_review":
            raise SimulatedCrash("process stopped after review write, before journal result")
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
        journal = SQLiteRunJournal(database_path)
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
        restarted_journal = SQLiteRunJournal(database_path)
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
        transcript_journal = SQLiteRunJournal(transcript_db)
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

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
