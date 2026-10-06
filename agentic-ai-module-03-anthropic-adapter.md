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

`RunResult.model_metrics` accumulates model turns, input/output tokens, prompt-cache read/write tokens split by 5-minute and 1-hour TTL, and elapsed time around each Messages API call. For a full input-token count, include uncached input, cache creation, and cache reads. These metrics help compare cost and latency. The runner can estimate token charges from an explicit rate card; it does not hardcode provider prices. Anthropic's cache prefix order is tools, then system, then messages, so the system breakpoint in this adapter covers the preceding stable tool schemas. The cache flag is off by default, and a short prefix may be below the model-specific minimum. Verify actual cache reads/writes before claiming savings. The trace may include customer requests and tool arguments, so a production implementation needs data minimization, redaction, access control, and retention limits before it stores traces.

### Optional model-token rate card

For a cost comparison, create a local JSON file using the rates currently applicable to the configured model and account. Keep the file outside the repository if its rates reveal commercial terms. The model name must exactly match `ANTHROPIC_MODEL`:

```json
{
  "configured_model": "REPLACE_WITH_ANTHROPIC_MODEL",
  "currency": "USD",
  "rates_per_million_tokens": {
    "input": "REPLACE_WITH_RATE",
    "output": "REPLACE_WITH_RATE",
    "cache_read": "REPLACE_WITH_RATE",
    "cache_write_5m": "REPLACE_WITH_RATE",
    "cache_write_1h": "REPLACE_WITH_RATE"
  }
}
```

Replace every placeholder with the current rate as a non-negative number. Store the file at `~/.config/agentic-ai/rate-card.json`, then run `python3 run_live_evals.py --dataset evals/live_scenarios_v6.json --rate-card ~/.config/agentic-ai/rate-card.json --trials 3 --output live-v6.json`. The report fingerprints the rate card, prices the two cache-write TTLs separately, reports model-token cost per successful trial, and labels the estimate scope. If cache-write token usage lacks a TTL breakdown, the runner marks the estimate unavailable rather than guessing. This excludes tools, infrastructure, taxes, and fees; compare the estimate against your provider invoice.

## Evaluation state

- The nine deterministic scenarios pass against the harness.
- Three adapter checks pass with a fake client: one verifies the complete `tool_use` / `tool_result` / final-answer round trip; one verifies the optional prompt-cache marker and usage metrics; one verifies that multiple requested tools are not executed.
- The live evaluator supports `support-agent-live-v4`, v5, and v6 through `--dataset`, with 1–10 repeat trials, 95% Wilson score intervals, synthetic mid-run revocation interventions, and an optional explicit rate card. It has not been run against Anthropic here. Scripted runner checks cover repeat aggregation, dataset grading, session revocation, tag summaries, interval calculations, TTL-specific token usage, and rate-card math. Live runs require an Anthropic API key and an account-enabled model and make real API calls.

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

For the cache experiment, run the same cases with caching disabled, with the 5-minute cache, and with the 1-hour cache. Keep model, dataset, trial count, request order, and rate card fixed:

```sh
python3 run_live_evals.py --dataset evals/live_scenarios_v6.json --rate-card ~/.config/agentic-ai/rate-card.json --trials 3 --output eval-no-cache.json
python3 run_live_evals.py --dataset evals/live_scenarios_v6.json --rate-card ~/.config/agentic-ai/rate-card.json --trials 3 --prompt-caching --output eval-cache-5m.json
python3 run_live_evals.py --dataset evals/live_scenarios_v6.json --rate-card ~/.config/agentic-ai/rate-card.json --trials 3 --prompt-caching --prompt-cache-ttl 1h --output eval-cache-1h.json
```

Compare cache read/write tokens, model latency, pass rates, and estimated token cost per successful trial. Check that the stable prefix exceeds the model's cache minimum and that repeated requests actually register cache reads. These calls use the live provider and may incur charges. Do not add irrelevant prompt text just to cross a cache minimum.

## Senior engineering extension: provider isolation and drift

Keep a provider adapter boundary so business policy does not depend on one SDK's message types. The adapter should own authentication, request construction, structured response parsing, stop-reason mapping, usage extraction, retry classification, provider request IDs, and compatibility checks. The control plane still owns permissions, budgets, durable history, and which tools can execute.

Specify behavior for rate limits, overloaded responses, connection reset, request timeout, malformed provider output, safety refusal, model retirement, and partial streaming. Bound retries by the task deadline and global budget; do not retry a write through the model loop when the tool outcome is uncertain. Make fallback explicit: a lower-capability model, deterministic workflow, read-only mode, or human handoff are different service choices.

For each provider/model change, run adapter contract checks, the same held-out behavior suite, a latency/cost comparison, and a trace compatibility check. Persist the configured alias plus resolved model/version metadata where available. Do not assume a stable alias means stable behavior. Prompt caching is a performance feature, never an authorization mechanism; verify actual usage fields and scope cached prefixes to the data/privacy design.

## Next module

Extend the evaluation method beyond a tiny scenario list: define task-level success, trajectory checks, safety properties, regression data, and trace review. Then compare the single-agent system with a fixed workflow using the same dataset.
