"""Check Anthropic message/tool wiring with a fake client; makes no API calls."""

from __future__ import annotations

from types import SimpleNamespace

from support_agent import ANTHROPIC_TOOLS, AgentLoop, AnthropicPlanner, RunContext, ToolRuntime


class FakeMessages:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)


def response(
    stop_reason,
    content,
    input_tokens=10,
    output_tokens=8,
    cache_read_input_tokens=0,
    cache_creation_input_tokens=0,
):
    return SimpleNamespace(
        stop_reason=stop_reason,
        content=content,
        usage=SimpleNamespace(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_input_tokens=cache_read_input_tokens,
            cache_creation_input_tokens=cache_creation_input_tokens,
        ),
    )


def main() -> int:
    first_assistant_content = [
        {"type": "text", "text": "I will check the approved policy."},
        {
            "type": "tool_use",
            "id": "toolu-policy-1",
            "name": "search_policy",
            "input": {"topic": "refunds"},
        },
    ]
    fake_messages = FakeMessages(
        [
            response("tool_use", first_assistant_content),
            response("end_turn", [{"type": "text", "text": "The return period is 30 days (RET-01)."}], 15, 10),
        ]
    )
    fake_client = SimpleNamespace(messages=fake_messages)
    planner = AnthropicPlanner(model="fake-model", client=fake_client)
    result = AgentLoop(ToolRuntime()).run(
        "What is the return period?",
        RunContext(subject_id="customer-ada", task_id="adapter-check"),
        planner,
    )
    assert result.status == "complete"
    assert "30 days" in result.answer
    assert [trace["tool"] for trace in result.tool_trace] == ["search_policy"]
    second_messages = fake_messages.calls[1]["messages"]
    assert second_messages[0] == {"role": "user", "content": "What is the return period?"}
    assert second_messages[1] == {"role": "assistant", "content": first_assistant_content}
    tool_result = second_messages[2]["content"][0]
    assert tool_result["type"] == "tool_result"
    assert tool_result["tool_use_id"] == "toolu-policy-1"
    assert '"article_id": "RET-01"' in tool_result["content"]
    assert result.model_metrics["model_turns"] == 2
    assert result.model_metrics["input_tokens"] == 25
    assert result.model_metrics["output_tokens"] == 18
    print("PASS  tool_use -> tool_result -> final response round trip")

    cache_messages = FakeMessages([
        response(
            "end_turn",
            [{"type": "text", "text": "The answer is grounded."}],
            input_tokens=50,
            output_tokens=7,
            cache_read_input_tokens=12,
            cache_creation_input_tokens=30,
        )
    ])
    cache_planner = AnthropicPlanner(
        model="fake-model",
        client=SimpleNamespace(messages=cache_messages),
        enable_prompt_caching=True,
        prompt_cache_ttl="1h",
    )
    cache_decision = cache_planner.next_action("Give me the current policy.", [])
    cache_call = cache_messages.calls[0]
    assert cache_call["system"][0]["cache_control"] == {"type": "ephemeral", "ttl": "1h"}
    assert cache_call["tools"] == ANTHROPIC_TOOLS
    assert cache_decision.model_metrics["cache_read_input_tokens"] == 12
    assert cache_decision.model_metrics["cache_creation_input_tokens"] == 30
    print("PASS  optional Anthropic cache breakpoint and cache usage metrics")

    multiple_tool_response = response(
        "tool_use",
        [
            {"type": "tool_use", "id": "toolu-a", "name": "get_order", "input": {"order_ref": "ORD-100"}},
            {"type": "tool_use", "id": "toolu-b", "name": "search_policy", "input": {"topic": "refunds"}},
        ],
    )
    multiple_messages = FakeMessages([multiple_tool_response])
    result = AgentLoop(ToolRuntime()).run(
        "Check my order and policy.",
        RunContext(subject_id="customer-ada", task_id="adapter-multiple"),
        AnthropicPlanner(model="fake-model", client=SimpleNamespace(messages=multiple_messages)),
    )
    assert result.status == "handoff"
    assert result.tool_trace == []
    print("PASS  multiple tool calls are handed off without executing either")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
