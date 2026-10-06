# Interview and Mastery Upgrade — Validation

This is the initial upgrade snapshot. The later [gap-fix validation](agentic-ai-gap-fix-validation.md) records additional content, intent corrections, sixteen workflow challenges and seventeen offline suites.

Date: 2026-10-07. This report records the curriculum and offline engineering upgrade. It does not certify interview outcomes, live model quality, or production readiness. The earlier evaluation report remains the historical snapshot of the original implementation.

## Material added

- A role-aware six-week mastery plan and fourteen-day interview sprint with deliverables and practice gates.
- LLM engineering foundations: tokens, attention/context, decoding, structured output, embeddings/reranking, indexes, adaptation, quantization, inference and MCP boundaries.
- Follow-ups for all 35 core interview questions, four timed mocks, a six-dimension rubric and truthful project narrative template.
- A worked numerical capacity/cost exercise with invented workload and prices, provider quotas, latency allocation, storage/rebuild estimates, sensitivity and reviewer capacity.
- Eight advanced labs covering baseline fairness, answer support, abstention, security metadata, recovery, orchestration, operations and adaptation.

## Implementation changes

The improved fixed workflow collects multiple unique order references and policy topics, checks each order independently, explains unsupported ledger access, defaults eligibility questions to reads, respects explicit no-submission phrases, and asks for clarification on multiple refund targets or an oversized read plan. The original router is preserved under `--baseline original`. The default is now `--baseline improved`. Evaluation gaps return exit 1 instead of an unconditional success exit.

The router is still bounded lexical logic. It does not establish robust handling of arbitrary negation, mixed mutation intent, dialogue, languages, or implicit identifiers. Both v7 and the added challenges are authored synthetic regression data. A fresh independently labeled set is needed before generalization or model-value claims.

The answer-quality lab evaluates frozen evidence and submitted answer envelopes separately from retrieval. It distinguishes citation-reference validity from labeled support, required-fact coverage, completion/abstention and unknown claims needing review. It uses explicit authored exact-claim labels, not a semantic inference model. The optional live generator filters forbidden evidence, excludes gold labels, records usage/configuration fingerprints and requires explicit `--live` configuration. No live run was made during this upgrade.

Harper's synchronization pseudocode now handles classification and ACL updates independently of unchanged text; includes chunking/embedding-version invalidation, tenant namespacing, consistent source snapshots and revision-aware publication; and distinguishes content version from policy/ACL revision. These methods are proposed contracts, not deployed connector code.

## Reproduced offline results

| Check | Result | Interpretation |
| --- | --- | --- |
| Existing ten dependency-free suites | All pass | Scripted harness, adapter, durability, approval, security, retrieval, RAG, embedding adapter, evaluator and cost-model regression behavior preserved |
| Original workflow on unchanged v7 | 14/17; 20 tools; 0 model calls | Historical gaps preserved; exit 1 intentionally reports grading gaps |
| Improved workflow on unchanged v7 | 17/17; 22 tools; 0 model calls | Existing cases can be covered with explicit bounded branches |
| Additional workflow challenges | 8/8 | Authored regressions, including mutation boundary and multi-target clarification |
| Good answer fixtures | 8/8 | Grader accepts expected authored answers and abstentions |
| Deliberately bad answer fixtures | 0/8 | Grader rejects unsupported claims, missing facts, wrong abstention, forbidden/stale citations and poisoned claims |
| Answer evaluator and fake generation boundaries | Pass | Unknown paraphrases require review; malformed answers rejected; forbidden evidence and labels do not enter generation packet |

`run_offline_checks.py` runs the twelve dependency-free suites. The Pages workflow runs this gate before the documentation build. The optional PDF checks also passed 3/3 using the bundled `pypdf` runtime. The documentation staging command and `mkdocs build --strict` passed using the repository-pinned Material dependency in a temporary directory. No documentation-link warnings were reported. The PDF fixtures still exercise a fake OCR adapter, not an image OCR engine.

## Reproduce

From the sandbox:

```sh
python3 run_offline_checks.py
python3 run_workflow_baseline.py --baseline original --dataset evals/live_scenarios_v7.json
python3 run_workflow_baseline.py --baseline improved --dataset evals/live_scenarios_v7.json
python3 run_answer_evals.py
python3 run_answer_evals.py --answers evals/answer_quality_bad.json
```

The original workflow and deliberately bad answers intentionally exit 1. Good fixtures and improved workflow exit 0. Preserve dataset hashes and do not tune on a holdout. Optional PDF checks require `pypdf`; no real OCR engine is evaluated.

## Evidence still to build through the labs

Representative independent labels, live model trials, semantic embeddings/reranking, end-to-end generated answer review, distributed/identity/payment integrations, load/fault exercises, actual project economics and personal ownership narratives remain work for the learner. The course now gives concrete exercises and review gates for these tasks; it does not invent their results.
