# Mastery and Interview Preparation Plan

Use this as the starting page for the expanded course. Default track: senior AI engineer / architect. A study schedule creates practice opportunities; completing readings alone does not establish mastery or guarantee an interview result.

## Completed practice material

Attempt the [coding prompts](agentic-ai-coding-interview-practice.md) and [numerical questions](agentic-ai-numerical-workbook.md) before reading the answers. The [completed reference case studies](agentic-ai-completed-reference-solutions.md) demonstrate actual offline failure/correction checks. Use [architecture decision cases](agentic-ai-architecture-decision-cases.md) to compare platforms under constraints and [leadership practice](agentic-ai-leadership-interview-practice.md) for personal ownership and organizational judgment.

## Choose your route

| Track | Prioritize | Demonstration |
| --- | --- | --- |
| Senior AI engineer / architect | All core modules, foundations, baseline comparison, RAG quality, sizing | Defend a design and implement one failure control |
| Hands-on agentic AI engineer | Tool protocol, typed contracts, RAG pipeline, adapter and evaluator debugging | Modify runtime behavior, inspect traces, run meaningful checks |
| Staff / principal architect | Task economics, governance, service boundaries, organizational ownership, migration and rollout | Capacity model, decision records, game day, residual-risk recommendation |

Start with a 45-minute mock from the workbook. Score it before reading. Spend more time on weak dimensions rather than treating every chapter equally.

## Six-week mastery path

Assume roughly 10–12 focused hours/week. Adapt to your existing experience. Each week has one primary deliverable and a gate; avoid producing several unfinished artifacts.

| Week | Read and build | Primary deliverable | Gate |
| --- | --- | --- | --- |
| 1 | LLM foundations; Modules 1–3; trace policy and order requests | Task contract plus annotated provider/tool trace | Explain tokens/decoding, trusted actor scope, refusal and malformed-call handling without notes |
| 2 | Modules 4–6; run workflow, durability, approval checks | Crash-window and approval state-machine dossier | Demonstrate duplicate delivery, lease takeover, stale action rejection; distinguish local evidence from distributed guarantees |
| 3 | Modules 7, 10, 11; retrieval benchmark; answer-quality lab | Labeled evidence and claim-support review | Explain precision/recall unit, false answer vs abstention, revocation and malicious content; preserve a fresh holdout |
| 4 | Modules 8–9; capacity exercise; orchestration experiment design | Numerical architecture and cost worksheet | Recompute for a doubled route share and a quota reduction; defend simpler baseline |
| 5 | Harper, Module 12, advanced labs | Versioned capstone dossier and experiment report | Map each requirement to control, evidence, signal, owner; label implemented, proposed, assumed |
| 6 | All four mock rounds; two personal narratives; weak-area retakes | Interview evidence pack | Three changed-scenario mocks >=18/24, no dimension below 2, no unsafe or fabricated claims |

Daily block: 20 minutes explain aloud, 45 minutes build/debug using the coding exercises, 20 minutes evaluate, 15 minutes write the failure and next decision. Reserve longer sessions for design and load/fault experiments.

## Fourteen-day interview sprint

For candidates with prior engineering experience, compress practice rather than claim a two-week mastery shortcut.

| Days | Focus | Output |
| --- | --- | --- |
| 1–2 | Diagnostic mock, LLM foundations, autonomy and tools | Gap list and two-minute explanations |
| 3–4 | Durability, approval and unknown outcomes | Two state machines and a crash trace |
| 5–6 | RAG metrics, evidence support, abstention and ACL changes | Failure analysis using actual sandbox results |
| 7–8 | Capacity, cost, quota limits, latency budgets | Recomputed worksheet and bottleneck explanation |
| 9–10 | Harper end-to-end design; orchestration alternatives | 45-minute system-design recording and scored review |
| 11–12 | Coding/debugging and incident mocks | Working change with a relevant regression check |
| 13 | Two personal project narratives | Verified contribution, numbers and limitations |
| 14 | New complete mock; targeted retake | Readiness score and remaining weak areas |

## Evidence pack

Keep seven compact artifacts: task/autonomy contract, runtime/trust diagram, failure state machine, evaluation report, numerical capacity/cost sheet, threat/operations decision record, and personal project narratives. Each should name its date/configuration and distinguish measurements from assumptions. Link to code or trace evidence where available.

The new workflow passes 17/17 existing v7 cases and 16/16 additional authored challenges. This shows explicit branches can solve those cases; it does not establish general intent understanding or production reliability. The answer-quality fixtures demonstrate grader behavior, not live model quality. Live-provider experiments are separate and optional until configured and budgeted.

## Completion gates

**Conceptual:** Explain tokens/context, tools, orchestration, RAG, state, approval, retries, evaluation and serving without memorized vendor names.

**Implementation:** Implement one bounded runtime or retrieval change, handle error paths, and demonstrate a relevant regression that fails without the control. Read the existing code before reaching for a framework.

**Evidence:** Build representative labels, distinguish tuning from holdout, review answer support and trajectories, record latency/cost and limitations. If API access is unavailable, complete offline work and explicitly mark live behavior unverified.

**Architecture:** Size the system, find a provider or human-process bottleneck, trace permission changes, define graceful degradation, and explain rollback with pending work.

**Interview:** Answer in two minutes, defend under follow-up, adapt to changed assumptions, and state what you personally shipped or measured.

## Suggested first session

1. Read the interview guide's answer structure and take Mock A in the workbook.
2. Run `python3 run_workflow_checks.py` from the sandbox and inspect why the improved workflow passes cases the original misses.
3. Run `python3 run_answer_eval_checks.py`, then inspect the deliberately bad answer fixtures.
4. Choose the lowest-scoring mock dimension as tomorrow's focus.

Use [advanced labs](agentic-ai-advanced-labs.md) for evidence-building work and [the workbook](agentic-ai-interview-workbook.md) for repeated defense.
