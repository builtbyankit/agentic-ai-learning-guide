# Content and Implementation Gap Fixes — Validation

Date: 2026-10-07. This report supplements the initial upgrade snapshot. Results are from synthetic local checks. No paid provider, real OCR, accelerator, distributed database, or production integration was run.

## Review finding to deliverable

| Gap | Delivered correction | Verification or practice gate |
| --- | --- | --- |
| Labs lacked completed solutions | Five completed failure-to-fix case studies with code, traces, results and limitations | Reproduce each command, then change an assumption |
| Coding preparation was shallow | Six coding contracts; separate attempt file; runnable scheduler, stream/evidence, lifecycle and checkpoint references | Failure-focused acceptance suites, not output-only demos |
| Numerical depth was limited | Nine worked sections covering tokens, decoding, attention, similarity, BM25/RRF, metrics, LoRA, KV/weights and replication | Deterministic calculation script plus units/assumptions defense |
| Architecture comparison was narrow | Existing-vs-dedicated storage, scale change, runtime/workflow, hosting economics and provider contracts | Workload-constrained decisions with falsifying benchmarks and migration triggers |
| Leadership practice was limited | Ten scenarios and a verifiable personal narrative/scoring method | Ownership, collaboration, impact and uncertainty probes |
| Workflow misread negation/mixed intent | Explicit bounded action grammar, conservative negation, clarification, separate read outcomes and damage-refund handling | Sixteen authored challenge cases plus unchanged v7 |
| Failed live trial discarded evidence | Per-attempt checkpoint, partial exports, usage history, fingerprinted resume and explicit failed-call retry | Fake-provider partial failure/resume and malformed-response tests |
| Replica arithmetic was ambiguous | One primary plus two replicas explicitly means three total copies; 44.2368 GB in the illustrative model | Numerical workbook/script; no hardware sizing claim |

## Observed results

- Seventeen dependency-free suites pass, including all existing ten, workflow/answer checks and five added coding/lifecycle/generation/reference/numerical suites.
- Workflow checks pass 33/33 authored cases: unchanged v7 17 plus sixteen challenge regressions. The original v7 remains 14/17, while the corrected workflow remains 17/17 with 22 tools and zero model calls.
- Three reproduced intent counterexamples fail the original router's outcome contracts and pass the corrected router's contracts. No payment tool is added; review remains separate from execution.
- The synthetic scheduler respects dependency order and a concurrency cap of two, blocks failed descendants, rejects invalid plans before work and cleans up on cancellation/deadline. No latency benchmark was performed.
- The lifecycle simulator refreshes changed classification/ACL independently of content, rebuilds for a changed embedding version, preserves tenant namespace, rejects stale source/writer revisions and denies against current authority during index lag/deletion.
- A failed fake-provider trial retains its completed first case. Resume without explicit retry performs no new calls; explicit retry performs only the unfinished case. Known malformed-response usage survives; transport-failure usage remains unknown.
- Existing eight good answer fixtures are accepted and eight deliberately bad fixtures rejected. The grader remains authored exact-claim matching with unknown paraphrases pending review, not a semantic judge.

These cases were developed in response to failures and are regression data, not an independent holdout. The router remains a narrow English grammar and may over-abstain or miss other phrasing; this is disclosed in the case study. Current-provider generalization and production authorization remain separate evidence requirements.

## Reproduce

From `agentic-ai-sandbox/`:

```sh
python3 run_offline_checks.py
python3 run_reference_cases.py
python3 run_workflow_checks.py
python3 run_coding_checks.py
python3 run_index_lifecycle_checks.py
python3 run_generation_recovery_checks.py
python3 run_numerical_exercises.py
python3 run_workflow_baseline.py --baseline improved --dataset evals/live_scenarios_v7.json
```

`run_offline_checks.py` includes all these checks and runs in the Pages build workflow. Attempt your own coding answers before studying references; the reference suite's green result does not grade your implementation.

For live read-only generation, an incomplete output cannot be graded as a complete suite. Use the same output path and model/prompt/dataset when resuming:

```sh
python3 generate_answer_candidates.py --live --output /tmp/answer-trial-1.json
python3 generate_answer_candidates.py --live --resume --retry-failed --output /tmp/answer-trial-1.json
```

The second command explicitly authorizes another call for failed/unfinished attempts. It may incur charges again; no such calls were made for this report. One process owns a checkpoint path. A crash between remote response and checkpoint commit remains an ambiguous read-only attempt.

## Documentation validation

The source staging command and strict MkDocs website build pass with the repository-pinned documentation dependency. Local Markdown targets and Python source syntax were checked. Numerical answers are reproduced by the deterministic workbook script; no training or hardware result is inferred from their arithmetic.

## Completion status

The content gaps now have concrete lessons, worked answers, reference implementations and interview probes. Actual mastery still requires independent practice, representative labels, live trials if relevant, and truthful personal project evidence. Real provider/identity/payment integration, adaptation, accelerator/load benchmarks and operations exercises are not represented as completed merely because the learning material covers them.
