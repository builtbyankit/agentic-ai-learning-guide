# Interview Workbook: Explain, Defend, Build

Pair this workbook with the [35 core questions](agentic-ai-interview-preparation.md), [LLM foundations](agentic-ai-llm-engineering-foundations.md), and [worked capacity exercise](agentic-ai-worked-capacity-and-cost.md). A polished paragraph is the start of an answer. A senior candidate must also draw the control flow, predict a failure, quantify the trade-off, and identify their evidence.

## Deep practice companions

Use the [coding exercises and reference solutions](agentic-ai-coding-interview-practice.md), [numerical workbook](agentic-ai-numerical-workbook.md), and [completed failure-to-fix case studies](agentic-ai-completed-reference-solutions.md) for implementation and calculations. Add the [architecture comparisons](agentic-ai-architecture-decision-cases.md) and [leadership scenarios](agentic-ai-leadership-interview-practice.md) for staff/principal depth. These are separate from personal production experience.

## How to practice

Answer the core question in two minutes without notes. Spend three minutes on the follow-up below. Draw or calculate the artifact in five minutes. Check your answer against the expected reasoning, then record a score and the next experiment. Use personal experience only where you can substantiate it.

The question numbers below match the interview guide. The prompts are practice probes, not a prediction of any employer's interview.

## Follow-ups for every core answer

| Q | Interviewer follow-up | Expected reasoning and artifact |
| --- | --- | --- |
| 1 | Your workflow uses an LLM router. Is the entire system an agent? | Mark exactly where the model chooses a next step; do not classify by framework name. Draw fixed and dynamic edges. |
| 2 | Your agent beats a router that only accepts one order ID. Is the comparison fair? | Improve the baseline, freeze cases/graders, compare quality and cost; explain where dynamic discovery remains useful. |
| 3 | Which boxes must be separate services on day one? | Separate logical boundaries first; choose deployable boundaries by scale, trust, ownership, and failure isolation. Draw a modular monolith and a later split. |
| 4 | A safe read tool returns an attacker-controlled URL. What may happen next? | A read can carry an injection or enable exfiltration through another tool; enforce destination policy and credentials at that next boundary. |
| 5 | Schema validation passes, but the refund reason contradicts the user. What now? | Separate syntax, authorization, business eligibility, and user intent; show why typed arguments alone are insufficient. |
| 6 | Policy changes after approval but before delivery. Is the approval still valid? | State the business rule, snapshot/reservation or revalidation contract, and pending-action cancellation/reapproval behavior. |
| 7 | One of three parallel reads fails after two succeed. Can you retry all three? | Preserve successful evidence, retry only within scope/deadline, label partial coverage, and avoid repeating mutations. Draw dependency and join logic. |
| 8 | Two providers implement the same schema but behave differently. How do you switch? | Capability checks, refusal/stop/stream mapping, provider-specific evals and canary; distinguish interface compatibility from behavior. |
| 9 | Four agents make the same mistaken assumption. Does voting fix it? | Correlated errors and shared context/model biases; require independent evidence and measured benefit over one agent. |
| 10 | A parent asks a child to broaden its tool permissions. Who decides? | Trusted runtime attenuation; the parent's prose cannot grant authority. Show an immutable child scope and cancellation contract. |
| 11 | A compact summary says approval exists, but the database disagrees. Which wins? | Authoritative state wins; refresh and halt an unauthorized transition. Label summary provenance and retention. |
| 12 | The provider's idempotency retention is shorter than your retry window. What changes? | Durable operation lookup/reservation or manual reconciliation; never assume a reused expired key deduplicates forever. Draw the unknown-outcome branch. |
| 13 | A worker loses its lease while a payment request is in flight. What does fencing stop? | Stops stale state commits only where enforced; cannot undo an issued request. Downstream fencing/idempotency plus reconciliation is required. |
| 14 | The reviewer approves twice in two tabs, one with old data. | Canonical display/digest, server-derived identity, expiry/current-state check, atomic decision/outbox, idempotent or conflicting decision response. |
| 15 | A scanned PDF has a table and misleading reading order. | Preserve page/table provenance, quantify OCR uncertainty, quarantine or hand off; parser success is not extraction accuracy. |
| 16 | Smaller chunks improve Recall@k but answers worsen. Why? | Missing conditions, duplicate overlap, inadequate parent context, changed ranking unit; evaluate support/completeness as well as recall. |
| 17 | A document's text is unchanged but its classification changes. | Refresh security metadata independently; rebuild on processing/model changes; current authorization must prevent stale-index exposure. |
| 18 | Hybrid returns all required sources and many irrelevant ones. | Candidate recall is useful but not sufficient; tune on development data, rerank, pack context, and calibrate abstention. |
| 19 | Your 95% scenario score hides 34% source precision. | Explain coverage-oriented pass semantics, metric denominators, no-answer failures, and downstream grounded-answer evaluation. |
| 20 | Deletion arrives while the old index is being restored. | Tombstone/revocation authority must survive rebuild/rollback; replay security updates before publication. Draw index and source revisions. |
| 21 | The most relevant result cannot fit the context budget. | Preserve essential evidence, fetch a smaller authoritative section or hand off; do not truncate a required condition silently. |
| 22 | A remembered preference came from hostile retrieved text. | Candidate-memory provenance, verified user intent, write policy, scope, expiry, correction/deletion; no unrestricted model memory writes. |
| 23 | Authorization blocks exfiltration, but the model still repeats a false policy. | Injection can damage answer integrity without crossing access boundaries; evaluate unsupported claims and poisoned evidence separately. |
| 24 | Prefix caching is enabled but cache-read tokens stay zero. | Check prefix stability, model-specific minimum, TTL and breakpoints; measure provider usage, never infer savings from a flag. |
| 25 | Cache hit rate improves but cost rises. | Include write premium, TTL, frequency, invalidation, and route mix; compute full cost per useful task. |
| 26 | Compaction drops an unresolved action. | Store canonical action/state outside summary; evaluate required-fact survival, re-fetch before write, and avoid transcript duplication. |
| 27 | The grader rewards a correct phrase in a fabricated answer. | Calibrate with human labels; adversarial grader cases, claim support, exact action outcomes, and inter-rater disagreements. |
| 28 | You observed zero failures in 100 trials. Is a one-in-a-million claim justified? | No; independent zero-event rule of three gives roughly 3% upper bound. Explain dependence and representativeness assumptions. |
| 29 | Traces help debugging but contain private data. | Minimized fields, scoped access, redaction, retention/deletion, and governed sampling; show a trace schema and incident response. |
| 30 | A cheaper route improves average spend but fails a rare critical class. | Slice metrics and hard safety gates; rollback that route regardless of average savings. Calculate cost per successful authorized task. |
| 31 | Provider outage causes queued jobs to retry together. | Deadline-aware jitter, retry budget, breaker, backpressure, queue-age limits, deterministic fallback, and separate write-delivery controls. |
| 32 | Old workers consume new events during a rollback. | Version contracts, expand/contract migration, compatibility/drain strategy, immutable behavior bundle, and separate action kill switch. |
| 33 | How do you know your improvement came from the design change? | Same tasks/configuration, paired comparison where possible, repeated trials and reviewed failures; expose confounders and untouched evidence. |
| 34 | Show the failure with the control removed. | An executable counterexample or trace; identify preventive control, detection, and recovery rather than a prompt-only claim. |
| 35 | Product wants more autonomy to reduce support volume. | Quantify value and harm, propose a bounded pilot, reviewer capacity, explicit risk owner, and criteria to narrow or disable. |

## Four complete mock interview rounds

### Round A: 45-minute system design

**Prompt:** Design Harper for 10,000 employees, 200,000 documents, permission changes, and a 5-task/second burst. Use the assumptions in the capacity exercise.

- Minutes 0–5: clarify users, useful outcome, ACL freshness, sources, target latency and unknowns.
- Minutes 5–15: draw ingestion and query planes, trust boundaries, authoritative ACLs, versioned indexes and direct-versus-planner routing.
- Minutes 15–25: calculate chunks/storage, token/call quotas, concurrency and monthly cost. State omitted terms.
- Minutes 25–35: walk revocation after retrieval, source deletion, provider throttling, and index rebuild/rollback.
- Minutes 35–45: define evidence and rollout gates, challenge one assumption, recommend first release.

**Strong answer:** authorization before disclosure; classification/ACL updates independent of content; versioned rebuild; targeted planning; explicit quota bottleneck; evidence-backed answers and measured abstention. **Weak answer:** picks a vector vendor first, promises exactly-once execution, or gives an unmeasured latency guarantee.

### Round B: 45-minute coding and debugging

**Prompt:** Extend the support workflow to compare two orders and retrieve two policy topics under one trusted identity. Keep four tool calls and six turns.

First define testable invariants. Each reference needs independent ownership enforcement. One denied read must not erase an allowed result or reveal hidden fields. A repeated ID should not duplicate work. Eligibility checks must not create proposals. Multiple refund targets and plans exceeding the budget require clarification.

Implement a bounded planner, then run `run_workflow_checks.py`. Inspect the runtime rather than putting trusted subject IDs in model arguments. Explain what the lexical router still misses: negation scope, mixed mutation requests, implicit IDs, unsupported languages, and conversational ambiguity. The included improved router is a small teaching baseline, not general natural-language understanding.

### Round C: 30-minute reliability incident

**Prompt:** An approved refund was accepted by a provider; the worker timed out, its lease expired, and another worker claimed the row.

Draw approval → outbox → claimed → submitted/unknown → confirmed. Reuse the original operation key within the provider's documented contract. Query authoritative operation status if available. Reject stale acknowledgements; preserve unknown outcomes when reconciliation is unavailable. Explain what happens if key retention expires and whether a policy change invalidates a pending approval. Define alerts, operator action, and safe replay.

**Probe:** Cancellation arrived after submit. Do not claim cancellation reversed the provider's action. Reconcile before telling the user the money moved or the action failed.

### Round D: 30-minute evaluation review

**Prompt:** Lexical retrieval scores 95% scenario pass but 50% no-answer accuracy; hybrid has better positive coverage but worse abstention. Choose a release experiment.

Explain metric units and labels, inspect hard negatives, and freeze a new holdout before tuning. Evaluate candidate retrieval separately from generated claim support. Compare a development-calibrated relevance/abstention approach against the unchanged baseline. Include abstention precision/recall, supported completeness, access failures, latency and cost. With only two negative holdout cases, 50% means one of two; it is not a stable production estimate.

## Scoring and retakes

Score six dimensions from 0 to 4: requirements, technical mechanism, trust/failure control, quantitative trade-offs, evaluation evidence, and communication/ownership.

- 0: missing or fundamentally unsafe.
- 1: vocabulary without a workable example.
- 2: coherent example, but weak failure or evidence reasoning.
- 3: defensible design with concrete controls and validation.
- 4: handles changed assumptions, numerical limits, failure interactions, and residual uncertainty.

Practice gate: at least 18/24 across three different mocks, no dimension below 2, and no unauthorized-action or fabricated-experience claim. This is a self-assessment target, not a hiring prediction. Retake the weakest dimension with a new scenario rather than rehearsing identical wording.

## Personal project narrative template

Prepare two real narratives: an architecture change after evidence and a failure you designed for. For each, write user/problem, constraints, your exact contribution, alternatives, key decision, failure, measurement/sample size, outcome, limitation, and what you would change now. Separate personal work from team results. If using this repo, say “synthetic learning prototype” and cite its measured checks.

A truthful opening could be: “I built a local support-agent prototype to study authorization and recovery. I compared a bounded workflow with authored scenarios and strengthened the workflow before evaluating model value. Live-provider quality and production load remain unmeasured.” Replace it with your actual experience when available.

## Daily practice log

| Date / question | First score | Failure I missed | Artifact or experiment | Retake score |
| --- | --- | --- | --- | --- |
| Fill after answering aloud | 0–24 | Concrete missed condition | Diagram, calculation, trace, or test | Use a changed scenario |

Keep the log outside public Git if it contains employer or customer information. Use [the mastery plan](agentic-ai-mastery-and-interview-plan.md) to sequence the drills and evidence.
