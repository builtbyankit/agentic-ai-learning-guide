# Module 4 — Evaluate Outcomes, Tool Paths, and Risk

Baseline revision note: numeric original-workflow results in this document are historical. Reproduce them with `--baseline original`. The improved router now passes 17/17 v7 authored cases with zero model calls; see [upgrade validation](agentic-ai-interview-upgrade-validation.md). The evaluated datasets and prior results were preserved.

## Learning objective

Build an evaluation approach that catches both bad answers and bad actions. A conversational agent can sound correct while using an unauthorized tool, skipping a required review, or exceeding its operating budget.

Anthropic’s [agent evaluation guidance](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents) describes a task as an input with success criteria, a trial as one attempt, a grader as checks over behavior or outcome, and a transcript as the complete interaction. It recommends combining code-based, model-based, and human grading because each catches different failures.

## The four layers

### 1. Tool contract checks

Check the deterministic rules close to the tools: required arguments, access ownership, response minimization, policy eligibility, idempotency, and side-effect boundaries. These should be code checks wherever possible. Our existing scripted suite covers these properties without a model.

### 2. End-to-end model scenarios

Give the actual model representative requests and inspect both the final answer and the full tool trajectory. Regression set [live_scenarios.json](agentic-ai-sandbox/evals/live_scenarios.json) covers policy grounding, order lookup, access denial, refund review, ownership override, and data minimization. Expanded comparison set [live_scenarios_v5.json](agentic-ai-sandbox/evals/live_scenarios_v5.json) adds ambiguity, multi-order authorization, read-only refund eligibility, multiple policy topics, and an unsupported payment-ledger request. The newest [v6 state-transition set](agentic-ai-sandbox/evals/live_scenarios_v6.json) adds a synthetic session revocation after a private order read.

The graders can check required phrases, forbidden disclosures, required or forbidden tools, exact required argument subsets, allowed terminal statuses, expected tool-error counts, review/payment state, and per-case tags. This makes failures easy to diagnose, but phrase matching can miss semantically correct wording or accept a misleading sentence. Human review is needed before treating these as product-quality measures. Tool-error counts are opt-in so older cases do not need to define every expected authorization denial.

### 3. Trace review and subjective quality

Review a sample of complete traces for whether the assistant understood the request, chose a sensible next action, used the minimum necessary data, handled errors clearly, and stopped at the right point. For tone and interaction quality, define a rubric and calibrate any model-based grader against human judgments. Do not delegate high-impact access or payment invariants to a language-model judge when the application can inspect actual state directly.

### 4. Production monitoring and controlled changes

After deployment, monitor task completion, handoff rate, errors, repeated tool calls, latency, token use, cost per resolved task, and policy violations. Sample traces for human review. Run the offline suite before prompt, tool, or model changes; then compare a canary or A/B rollout on real traffic before broad release.

## Compare architectures on the same tasks

The support case has a natural baseline: a fixed workflow can handle direct order lookups, exact policy questions, and refund eligibility checks. The model-directed loop may help with mixed or ambiguous requests, but it costs additional model turns and creates a larger action surface.

To decide whether the agent is worth that cost, compare a single-agent implementation with the fixed workflow on the same versioned cases. Use the same synthetic state and grade the same outcomes. Track task success, unsafe actions, handoffs, tool calls, latency, and token use. Add mixed-intent and ambiguous cases where dynamic sequencing might help; otherwise the dataset unfairly favors the workflow. Keep the simpler design unless the agent shows a measurable improvement on the cases that matter.

The fixed workflow passes **10/10** cases in `support-agent-live-v4`, using twelve tool calls and no model calls. It passes **12/15** in v5 and **13/16** in v6, where the additional scenario confirms that a revoked subject cannot receive data fetched earlier in the run. It still misses the multi-order comparison, the request requiring two policy articles, and the payment-ledger abstention. These authored cases now provide useful discriminators; they do not establish that a live model agent will pass them or outperform the workflow. Run both architectures against the same v6 data, synthetic state, and graders before making that decision.

The policy retriever has a separate eleven-query set with Hit@1, Recall@2, MRR, precision, and no-result accuracy. It currently scores 100% exact coverage on its authored synthetic queries. Keep retrieval metrics separate from end-to-end answer success; a retriever can return the right article while the model still misstates it.

## Improve the dataset responsibly

1. Add a case for every distinct failure mode; record why it exists and which requirement it protects.
2. Keep ordinary, ambiguous, boundary, adversarial, and regression cases separate by tags as the suite grows.
3. Use synthetic or properly sanitized inputs. Do not put customer data or credentials in version control.
4. For variable model behavior, run multiple trials and record model alias, prompt/tool version, dataset version, full trace, latency, token usage, and the rate card used for cost. `run_live_evals.py --trials N` repeats each case with a fresh runtime/task ID and summarizes pass rate, 95% Wilson score intervals, recurring failures, and average usage/latency with sample counts. An optional `--rate-card PATH` estimates model-token cost and cost per successful trial from user-supplied current rates. Reports fingerprint the system prompt, tool schema, dataset, and rate card. The intervals describe trial outcomes on this fixed suite; they do not establish generalization to a different task population.
5. Keep a holdout set for final design comparisons so prompt tuning does not silently overfit the only benchmark.
6. Inspect false positives and false negatives in graders. Require human calibration for tone, helpfulness, and other subjective judgments.

The sixteen v6 cases are enough to expose several workflow limitations, not enough to establish production reliability. The live runner and its multi-trial aggregation have only been checked with scripted decisions; no Anthropic API calls have been made from this workspace. Live results should be interpreted as a development signal, not a release certificate.

## Design exercise

Before adding cases, write a one-page evaluation contract for this assistant:

- What counts as resolving the task?
- Which tool paths are allowed or required for each task type?
- Which violations are automatic release blockers?
- What latency, token, and cost budgets should apply, and how will you set them from observed data?
- Which quality dimensions require human review?
- What evidence would show that the agent is better than the fixed workflow?

Avoid choosing numeric quality gates before you have representative cases and a baseline. Set thresholds based on the impact of failures and measured system behavior.

## Senior engineering extension: evaluation validity

Treat dataset, labels, grader, execution harness, and model configuration as versioned software artifacts. Keep a regression suite for known failures and a held-out set for model/prompt/architecture comparisons. Record case provenance and risk class; use production-derived cases only after privacy review and sanitization. Track coverage gaps as explicitly as score changes.

For stochastic behavior, report trial counts and distributions or intervals, not a best run. The runner uses Wilson score intervals for pass proportions; repeated trials on fixed prompts quantify variability for those cases but do not estimate performance on an unrepresentative population. Stratify by intent, ambiguity, language, tenant/data scope, and impact. Zero failures in a small sample still permits a material true failure rate; size trials to rule out the rate the risk owner cares about. Repeated tuning against the same holdout converts it into training data, so preserve an untouched final set.

Calibrate an LLM grader against blind human labels, inspect disagreements and class-specific error, and keep code-based checks authoritative for observable state and security invariants. For online experiments, define eligible traffic, assignment unit, exposure, contamination risk, success and guardrail metrics, stopping rule, and rollback before launch. Never use aggregate success to hide a regression in a high-risk slice.

## Next module

Continue with the security threat model in [Module 7](agentic-ai-module-07-agent-security-threat-model.md), then design the production architecture and operating plan. The baseline comparison is available in `run_workflow_baseline.py`; a live model comparison remains an open experiment.
