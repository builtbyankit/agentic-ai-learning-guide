# Module 9 — Orchestration Patterns and Multi-Agent Design

## Learning objective

Choose between a fixed workflow, a single bounded agent, handoff to a specialist, or a manager that calls specialists. Design the delegation contract and measure whether the extra coordination improves the result.

This module fills the orchestration design checkpoint in the roadmap. It applies the support-agent baseline and then considers where specialist agents would—and would not—help.

## Separate the control-flow choice from the agent count

“Multi-agent” is not one architecture. First decide whether the system needs model judgment, then decide who owns each branch and final response.

| Pattern | Who chooses the next step? | Best fit | Main trade-off |
|---|---|---|---|
| Fixed workflow | Application code | Stable, auditable task paths | New cases require code changes; branching grows with requirements |
| Single bounded agent | One model loop | Steps depend on observations or ambiguous intent | Serial model calls, broader context, one prompt/tool surface to govern |
| Router + specialist handoff | Router, then specialist owns the branch | Different intents need distinct policies or tools | Context transfer and ownership boundaries must be explicit |
| Manager + specialist tools | Manager retains the user conversation and calls bounded workers | The manager must synthesize distinct expert outputs | More calls, coordination, and failure modes; workers may duplicate or contradict |
| Parallel fan-out + merge | Deterministic or model planner launches independent work | Independent subtasks can run concurrently | Lower critical-path latency may cost more; merge quality and partial failure matter |
| Draft + evaluator loop | Generator and evaluator alternate | Output benefits from a bounded critique/revision pass | Additional latency/cost; evaluator can share the same blind spots |

OpenAI’s current orchestration guidance distinguishes handoffs, where a specialist takes over, from agents-as-tools, where a manager keeps the final response. It recommends a narrow specialist contract and splitting only when the specialist materially differs in tools, policy, or instructions. Anthropic’s research system is an example where broad independent web research benefited from an orchestrator delegating parallel work. These are patterns to evaluate, not templates to copy: [OpenAI orchestration and handoffs](https://developers.openai.com/api/docs/guides/agents/orchestration), [Anthropic’s multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system).

## Worked comparison: the support assistant

### Request A: “Where is ORD-100, and what is the return window?”

The state access is deterministic, the two facts come from known services, and there is no reasoning dependency between them.

- **Fixed workflow:** Read order, read policy, format the answer. The local v3 baseline already covers this class without model calls.
- **Single agent:** Ask the model to choose two read tools and synthesize. Flexible if the request wording changes, but it adds model latency and cost.
- **Manager with two specialists:** Ask an order agent and a policy agent for structured facts, then have the manager merge them. Both specialists call the same known services. That adds calls and coordination without adding a capability or a new policy boundary.

**Choice:** Keep a workflow for this request. The fixed workflow covers the simple v4 regression suite. Expanded v5/v6 cases show where a fixed router needs additional explicit branches: multiple orders, multiple policy topics, and unsupported payment-ledger questions. V6 also tests a mid-run session revocation. These are synthetic development results, not evidence of live model behavior.

### Request B: broad, independent investigation

Consider an analyst asking for a report comparing several independently researched markets, recent regulatory changes, and technical approaches, with cited sources. The subtasks can be partitioned and researched in parallel, and a manager can deduplicate claims and assemble the report.

- **Fixed workflow:** It can execute known search/query stages, but the plan may depend on discovered evidence.
- **Single agent:** Easier to trace and cheaper to coordinate, but research is mostly sequential and one context may become crowded.
- **Manager + parallel research specialists:** Each worker gets a distinct question, allowed sources, an evidence schema, and a deadline. The manager deduplicates sources, resolves conflicts, and produces one sourced answer.

**Candidate choice:** Try a small bounded fan-out only if measured latency or evidence coverage is inadequate in the single-agent baseline. This is a hypothesis; benchmark the same report tasks before keeping it.

## Delegation contract

Every delegated task should carry a structured contract, not just a vague natural-language instruction:

```json
{
  "task_id": "parent-run-42/worker-2",
  "objective": "Find current return-window rules for order ORD-100",
  "allowed_sources": ["policy-service", "order-service"],
  "actor_scope": "authenticated-customer-ada",
  "allowed_tools": ["search_policy", "get_order"],
  "deadline_ms": 8000,
  "max_model_turns": 3,
  "output_schema": {
    "facts": [{"claim": "string", "source_id": "string"}],
    "denials": ["string"],
    "status": "complete | partial | blocked"
  }
}
```

In a real service, `actor_scope` is trusted runtime metadata, not a field the parent model can alter. Each worker independently receives least privilege and rechecks access at its tool boundary. The worker returns only the agreed data shape. The manager treats worker output as untrusted evidence, validates the schema, checks citations and contradictions, and does not convert an unsupported worker claim into a fact.

Do not pass payment credentials, approval authority, or broad service tokens from one agent to another. Delegation creates a new trust edge: identity, scope, deadline, budget, allowed tools, data retention, and cancellation must be defined for that edge. OWASP’s Agentic Applications Top 10 includes insecure inter-agent communication and cascading failures among its risks; see the [OWASP 2026 overview](https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/).

## Cost, latency, and failure math

Let `Lᵢ` be model and tool time for worker `i`, and `Cᵢ` its total cost.

- Sequential fan-out: approximate critical-path time is `Σ Lᵢ`; total cost is `Σ Cᵢ + manager cost`.
- Parallel fan-out: approximate critical-path time is `max(Lᵢ) + queue/merge overhead`; total cost is still `Σ Cᵢ + manager cost`.
- A manager can itself add a planning call, a merge call, retries, and a second model context containing worker outputs.

Concurrency can improve elapsed time without reducing spend. Measure total model tokens and tool calls across every child, not only the manager. Bound worker count, depth, retries, output size, and total run deadline. On a worker timeout, decide whether to cancel all work, return a partial result, retry that worker, or hand off; do not let retries recursively spawn new workers.

## Evaluation plan for an orchestration change

Compare architectures on identical tasks, data, graders, and model settings. Record:

- Task success and factual/source support.
- Tool/path correctness and unauthorized-action count.
- Coverage of independent subtasks and duplicate work.
- Contradiction and merge error rates.
- Handoff/partial-result quality.
- Total model calls, total input/output tokens, tool calls, wall-clock latency, and estimated cost.
- Worker failures, cancellations, and retry amplification.

Run multiple trials when the model is involved. Keep a holdout set. Review full parent and worker traces because an apparently good answer can hide an unsafe worker path or an unsupported merge. Require zero critical privacy/authorization failures; set quality, latency, and spend thresholds from the task owner’s requirements and measured baseline.

## Design exercise

Choose a real task and draw both architectures:

1. One fixed workflow or single-agent design.
2. One specialist/handoff or manager/worker design.

Mark each model call, tool, state write, trust boundary, and approval gate. Predict which metrics will improve and worsen. Name the smallest evaluation set that could falsify your multi-agent hypothesis. Recommend the simpler design if the experiment shows no material gain.

## Checkpoint on this capstone

For the current support assistant, adding an order specialist and a policy specialist is not yet justified: they would access simple services with the same user scope. The v5/v6 workflow misses a request that needs two policy lookups and a separate comparison across two orders, but a bounded workflow can be extended to handle both. The improved workflow now passes all 17 authored v7 cases without model calls. Compare the live single-agent evaluator against this stronger baseline and a new independently labeled challenge set before claiming value from dynamic planning or adding specialists. Original-router v5/v6 misses above are historical evidence, not the current baseline.

## Senior engineering extension: delegation as capability attenuation

Each child run should receive less authority and only the context needed for its subtask. Define parent/child identity, allowed sources, tool ACLs, deadline, token/cost budget, maximum fan-out/depth, cancellation propagation, and result schema. Do not copy broad parent credentials into a worker. A worker result remains untrusted input and may contain unsupported claims or injection text.

Specify partial failure: which workers can be cancelled, which results are mandatory, how conflicts are resolved, how citations are deduplicated, and whether the parent may return a partial answer. Bound retries and recursion so one failure cannot restart an unbounded delegation tree. Prefer structured evidence packets with source IDs and provenance over free-form reports.

Measure the whole orchestration tree: critical-path latency, total model/tool spend, duplicate work, disagreement, merge error, partial-result rate, and unsafe cross-agent access. Compare with workflow and one-agent baselines on identical tasks. Parallel speedup is useful only when quality remains sound and total cost and security surface are acceptable.
