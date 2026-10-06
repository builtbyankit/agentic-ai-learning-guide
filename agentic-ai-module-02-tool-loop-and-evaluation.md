# Module 2 — The Tool Loop and What the Evaluation Proves

## Learning objective

Read a minimal agent harness end to end. Identify which choices belong to the planner and which rules the application must enforce. Then interpret the first evaluation results without claiming more than they establish.

## Run the sandbox

Open the [sandbox README](agentic-ai-sandbox/README.md) and run its evaluation command. The source files are [support_agent.py](agentic-ai-sandbox/support_agent.py) and [run_evals.py](agentic-ai-sandbox/run_evals.py).

The current scenario run reports **9/9 passing**. That is evidence that this scripted harness meets those nine expected outcomes. It is not evidence that a real model will choose the right tools or follow instructions.

## Follow one request through the code

Suppose the user asks for a refund on `ORD-100`.

1. The application creates a `RunContext` with an authenticated subject and a task ID. The planner never gets to choose the subject.
2. The `Planner` interface returns a `Decision`. In a live system, a model adapter would produce that decision. In these scenarios, `ScriptedPlanner` supplies it deterministically.
3. `AgentLoop.run` checks the decision kind and enforces the overall turn and tool-call budgets.
4. `ToolRuntime.call` routes only to known tools. Each tool validates its arguments and applies its own authorization and eligibility checks.
5. The runtime returns a structured observation. The next planner turn sees that actual result, including safe error messages.
6. The trace records each tool and outcome so an evaluator can inspect the path, not only the final answer.

The model-facing planner proposes actions. The application-owned runtime decides which proposals can execute.

## Read the refund path

The proposal tool checks that the authenticated customer owns the order, applies a mock eligibility rule, and creates an idempotent proposal. The review tool checks that proposal again and creates a pending review request. Repeating the same operation for the same task yields the same identifiers.

There is no payment execution tool. A model cannot call one by guessing a name: the gateway only dispatches registered tools. In a real product, an approval service would pass a short-lived, scoped authorization to separate backend code after an authorized human decision.

## What the nine scenarios cover

| Scenario | System property exercised |
|---|---|
| Policy answer | Tool can return a source identifier for the answer. |
| Owned order lookup | The session owner receives a limited order summary. |
| Cross-customer lookup | The service denies a record owned by someone else without confirming whether it exists. |
| Eligible refund | Proposal can reach a pending human-review state; no payment event occurs. |
| Ineligible refund | Review service refuses an ineligible proposal. |
| Tool-call budget | The loop stops when the tool-call limit is reached. |
| Malformed arguments | An extra model-supplied identity field is rejected; a later valid call can recover. |
| Untrusted note | An internal note containing an instruction-like string is not returned by the order tool. |
| Repeated review | Repeating proposal and review requests does not create duplicate review items. |

## Limits of this evidence

These scenarios use predetermined decisions, synthetic records, and in-memory state. They do **not** test model reasoning, model refusals, prompt injection through content the model actually sees, concurrent requests, process restarts, real identity controls, payment systems, latency, or cost. The evaluation harness itself is hand-authored and small. A production release would need broader test data, integration tests, operational measurements, and human review of representative traces.

That distinction is central to agent engineering: a clean architecture and a green evaluation report are only as strong as the behavior and risks those evaluations actually cover.

## Design exercise

The review ID is derived from the task ID and proposal ID. Decide what should happen if a customer starts a second support task for the same order and reason while the first review is still pending:

- Create a second review request because each task is independent?
- Reuse the first pending request to avoid duplicate work?
- Ask a support operator to merge or close one request?

State the rule, the idempotency key that implements it, and the evaluation case that would distinguish the chosen behavior.

## Senior engineering extension: the agent-computer interface

Treat tools as public APIs offered to an unreliable planner. Specify a semantic contract, not only a JSON schema: permitted actor scope, side-effect class, idempotency, timeouts, output size, data classification, error categories, and whether a result may be stale. Keep read, propose, approve, and execute capabilities distinct. A schema-valid argument can still be unauthorized or inappropriate.

Normalize provider-specific stop reasons and tool blocks into internal types, but retain the original provider event for replay and diagnosis. Validate that every tool result matches the call ID and expected schema; handle malformed, duplicate, unknown, and missing results explicitly. Before returning a result to the model, strip secrets, cap size, preserve source/version, and mark untrusted content as data. Tool errors must not echo credentials, raw SQL, or hidden records.

For each tool, include contract checks for valid input, boundary values, unknown fields, unauthorized actor, timeout, partial result, duplicate request, and oversized output. Decide which failures the model may retry and which must hand off. These contracts form the Tool Broker section in Module 12.

## Next step

The Anthropic adapter is in [Module 3](agentic-ai-module-03-anthropic-adapter.md); its live evaluation still needs an account-enabled run. The fixed-workflow comparison, durable execution, approval/outbox lab, and threat model follow in [Modules 4–7](agentic-ai-mastery-roadmap.md). The next build step is the production architecture and operations plan.
