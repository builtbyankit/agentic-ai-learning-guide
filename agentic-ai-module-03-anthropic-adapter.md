# Module 3 — Connect a Model Without Giving It Authority

## Learning objective

Connect Claude to the existing harness while keeping identity, tool authorization, and side-effect policy in application code. Learn to read the provider’s tool-call protocol and measure what each model call costs in tokens and time.

## The request and response cycle

Anthropic’s Messages API returns an assistant message that can contain a structured `tool_use` block. The application executes a client-side tool and sends the assistant message back along with a user message containing a `tool_result` tied to the tool call’s ID. The model then continues or ends the turn. See Anthropic’s [tool-use overview](https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview) and [tool-call handling guide](https://platform.claude.com/docs/en/agents-and-tools/tool-use/handle-tool-calls).

The sandbox implements that round trip in `AnthropicPlanner`:

1. Send the current request, system instructions, and tool schemas to `client.messages.create`.
2. If Claude returns one `tool_use`, convert it to a `Decision`.
3. Let `AgentLoop` enforce the run budget, then let `ToolRuntime` validate arguments and permissions.
4. Send the original assistant content and a matching `tool_result` back on the next call.
5. If Claude returns a final text response, return it to the caller. If it stops unexpectedly or requests multiple tools at once, hand off safely.

The official SDK example shows the same manual `messages.create` pattern in [Python](https://github.com/anthropics/anthropic-sdk-python/blob/main/examples/tools.py). The SDK also offers a tool runner, but this lesson keeps the loop explicit so you can see where the application checks authority and budgets.

## Why one tool per response for now?

Some model responses can contain multiple tool calls. The current adapter asks for one at a time and refuses to execute a multi-call response. This preserves a simple serial transcript and avoids accidentally dropping one of the model’s requested results. It can add turns and latency. Later, compare the serial design with a batch executor that validates every call, enforces per-tool limits, and returns every result under its matching ID.

## Where the authority stays

- `ANTHROPIC_TOOLS` tells the model which operations it may request; it does not grant access by itself.
- `RunContext.subject_id` is created by the application after authentication and is not sent to the model.
- `ToolRuntime` checks ownership and eligibility again when a request arrives.
- The model has no payment execution tool. A pending human-review request remains pending.
- Turn and tool-call limits are applied by `AgentLoop`, outside the model.

## Measure each call

`RunResult.model_metrics` accumulates model turns, input/output tokens, prompt-cache read/write tokens, and elapsed time around each Messages API call. These metrics make quality/cost/latency trade-offs measurable. They do not calculate currency cost; apply the rates for the model and account you actually use. The optional cache marker sits on the stable system prefix after the stable tool definitions; request-specific content remains later in the message list. The cache flag is off by default, and a short prefix may be below the model-specific minimum. Verify actual cache reads/writes before claiming savings. The trace may include customer requests and tool arguments, so a production implementation needs data minimization, redaction, access control, and retention limits before it stores traces.

## Evaluation state

- The nine deterministic scenarios pass against the harness.
- Three adapter checks pass with a fake client: one verifies the complete `tool_use` / `tool_result` / final-answer round trip; one verifies the optional prompt-cache marker and usage metrics; one verifies that multiple requested tools are not executed.
- The live ten-scenario `support-agent-live-v4` evaluation and 1–10 repeat-trial option are ready in `run_live_evals.py`, but have not been run against Anthropic here. Scripted runner checks cover the repeat/aggregation path. Live runs require an Anthropic API key and an account-enabled model and make real API calls.

The live evaluation checks policy grounding, own-order lookup, cross-customer data protection, eligible and ineligible refund handling, and an instruction attempting to override order ownership. Its synthetic dataset is a starting point, not a production assurance result. Review the actual traces and add failures to the dataset before drawing broader conclusions.

## Exercise: inspect the cost-quality trade-off

Run the live evaluation and record for each scenario:

| Scenario | Pass? | Tool sequence | Input/output tokens | Cache read/write tokens | Model latency | Failure cause |
|---|---|---|---:|---:|---:|---|
| Policy answer |  |  |  |  |  |  |
| Own-order lookup |  |  |  |  |  |  |
| Cross-customer denial |  |  |  |  |  |  |
| Eligible refund |  |  |  |  |  |  |
| Ineligible refund |  |  |  |  |  |  |
| Ownership override attempt |  |  |  |  |  |  |

Then change only one thing—tool descriptions, system instructions, or the turn budget—and rerun the same scenarios. Explain which metric improved, which regressed, and whether the change is worth keeping.

For the cache experiment, compare `run_live_evals.py` with caching disabled and enabled only when the stable prefix is long enough for the selected model. Keep case order, model, and prompts fixed. Compare cache read/write tokens, latency, and rate-card cost. Do not add irrelevant prompt text just to cross a cache minimum.

## Senior engineering extension: provider isolation and drift

Keep a provider adapter boundary so business policy does not depend on one SDK's message types. The adapter should own authentication, request construction, structured response parsing, stop-reason mapping, usage extraction, retry classification, provider request IDs, and compatibility checks. The control plane still owns permissions, budgets, durable history, and which tools can execute.

Specify behavior for rate limits, overloaded responses, connection reset, request timeout, malformed provider output, safety refusal, model retirement, and partial streaming. Bound retries by the task deadline and global budget; do not retry a write through the model loop when the tool outcome is uncertain. Make fallback explicit: a lower-capability model, deterministic workflow, read-only mode, or human handoff are different service choices.

For each provider/model change, run adapter contract checks, the same held-out behavior suite, a latency/cost comparison, and a trace compatibility check. Persist the configured alias plus resolved model/version metadata where available. Do not assume a stable alias means stable behavior. Prompt caching is a performance feature, never an authorization mechanism; verify actual usage fields and scope cached prefixes to the data/privacy design.

## Next module

Extend the evaluation method beyond a tiny scenario list: define task-level success, trajectory checks, safety properties, regression data, and trace review. Then compare the single-agent system with a fixed workflow using the same dataset.
