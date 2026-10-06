# Offline System Evaluation — 2026-10-07

## Decision summary

The current sandbox demonstrates useful control and data-path mechanics under synthetic, offline conditions. The deterministic harness, approval/outbox simulation, security boundaries, and local retrieval contracts pass their authored checks. The fixed workflow passes all ten v4 support cases without model calls; the expanded v7 suite passes 14/17 without model calls.

The evidence does **not** establish that a live model is useful or reliable, that the system meets production SLOs, or that RAG works on a representative corpus. The Anthropic adapter was tested with a fake client. The RAG dense path uses feature hashing, and the SQLite search scans eligible rows rather than exercising a production ANN service. Hybrid retrieval produced a false positive on a no-answer holdout query.

**Current recommendation:** continue the work as an offline prototype. Do not describe it as production-ready or as validated live-agent behavior.

## Environment and method

- Date: 2026-10-07.
- Repository: this curriculum repository's `agentic-ai-sandbox/` directory.
- Data: authored synthetic support cases, a two-document minimal RAG corpus, a 15-entry expanded RAG corpus, and generated parser fixtures.
- API access: `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`, and the Anthropic SDK were unavailable; no paid model or embedding API calls were made.
- Commands were run offline. The dense and hybrid RAG evaluators returned exit code 1 because their graders found relevance gaps; this is the expected signal for those gaps, not a Python execution failure.
- The deterministic agent, recovery, approval, security, retrieval, and PDF checks were rerun on this date. The optional PDF check used bundled `pypdf` 6.10.0. An additional retrieved-content injection case was added and passed its 11th security check group.

## Results

| Area | Result | What it establishes |
|---|---:|---|
| Scripted agent scenarios | 9/9 | The tested harness/tool outcomes satisfy the hand-authored deterministic expectations. |
| Anthropic adapter checks | 3/3 | Fake-client tool round trip, optional prompt-cache instrumentation, and safe handoff for multi-tool responses work in the checked paths. No live provider behavior was measured. |
| Durable-run checks | 13/13 | Tests cover SQLite restart/replay, subject binding, idempotency, exclusive active claims, a two-thread claim race, expiry takeover, stale fencing/state-version rejection, terminal-run rejection, additive migration, slow-tool heartbeat renewal, and idempotent recovery after heartbeat loss. This is local SQLite evidence, not provider/network or multi-host validation. |
| Approval/outbox checks | 9/9 | Tested the shared-database invariant, exact-proposal approval, retry/deduplication, current-state rejection, and serialization against a concurrent policy update. Current state is a synthetic table in local SQLite; no real operator identity or payment provider was exercised. |
| Security check groups | 11/11 | Covers bounded inputs, capability separation, tenant-denial behavior, minimized data, expiry/task checks, session revocation, identity-provider failure, fail-closed dispatch, stale proposals, and a simulated planner following hostile retrieved policy text. Runtime authorization blocks the resulting cross-customer read. The planner is scripted; live-model resistance and multi-host datastore behavior remain untested. |
| Policy retrieval contract checks | 8/8 | The small policy catalog meets its current authored ranking, freshness, provenance, and minimization checks. |
| Policy retrieval eval | 11/11 | Hit@1 100%, Recall@2 100%, MRR 1.000, exact coverage 100%, and empty-query accuracy 100% on `policy-retrieval-v1`. This dataset is small and written alongside the retriever. |
| RAG preprocessing/storage/access checks | 7/7 groups | Markdown/static-HTML/DOCX fixture extraction, heading/table/page-break preservation, configured PII redaction, DTD rejection, SQLite idempotency, metadata/provenance, filters, supersede, persistence, and deletion pass synthetic local checks. Optional PDF handling has separate 3/3 checks for selectable text and the injected confidence-gated OCR contract; no real OCR engine or document corpus was evaluated. |
| Optional PDF parser/OCR adapter checks | 3/3 | Synthetic selectable-text pages preserve page markers through redaction, chunking, SQLite storage, and filtered retrieval. A fake OCR adapter preserves page/confidence provenance, passes text through redaction and retrieval, and rejects below-threshold results. Malformed and over-limit PDFs are rejected. Ran with bundled `pypdf` 6.10.0; no image OCR was performed. |
| Voyage adapter checks | 8/8, fake transport | Batching, query/document request types, response ordering/shape, dimension consistency, credential/error redaction, no-partial-write behavior after a later-batch failure, and end-to-end evaluator telemetry pass without network/API usage. |
| RAG dense holdout (minimal set) | 60% scenario pass; 50% positive-source coverage; 83% Hit@1; 67% Recall@4; MRR .833; 75% no-answer accuracy; 100% unique-source precision | Feature hashing misses several authored relevant-source requirements and returned a result for the capital-city no-answer query. It is not a semantic embedding benchmark. |
| RAG lexical holdout (minimal set) | 100% scenario pass and positive-source coverage; 100% Hit@1/Recall@4; MRR 1.000; 100% no-answer accuracy; 89% unique-source precision | Lexical retrieval is strongest on this tiny, keyword-oriented synthetic holdout. The precision gap shows extra sources remain. It does not establish generalization. |
| RAG hybrid holdout (minimal set) | 90% scenario pass; 100% positive-source coverage/Hit@1/Recall@4; MRR 1.000; 75% no-answer accuracy; 89% unique-source precision | RRF recovered required sources in positive cases but carried a false positive for the capital-city no-answer query. It underperforms lexical retrieval on abstention. |
| Repeated-trial evaluator checks | 7/7 | Scripted checks verify aggregation/task isolation, read-only eligibility, session revocation, stale proposals and misleading planner claims, exact tool arguments, allowed statuses, expected tool errors, tag summaries, and Wilson interval calculations; they do not measure live model variability. |
| Token rate-card estimator checks | 5/5 | Fake usage verifies model-bound rate cards, separate input/output/cache-read/5m-write/1h-write pricing, incomplete-usage handling, coverage rules, and invalid-price rejection. No live invoice comparison was performed. |
| Fixed-workflow baseline, v4 | 10/10; 12 tool calls; 0 model calls | Preserved unchanged as a simple regression set. |
| Fixed-workflow baseline, v5 | 12/15; 17 tool calls; 0 model calls | Expanded synthetic cases expose misses on comparing multiple orders, collecting two policy topics, and abstaining on unsupported payment-ledger details. This is a workflow limitation signal, not proof of live-agent superiority. |
| Fixed-workflow baseline, v6 | 13/16; 18 tool calls; 0 model calls | Adds a synthetic mid-run session revocation after an order read. The harness discards the stale result, records a safe denial, and hands off. Three existing mixed/out-of-scope cases still fail. |
| Fixed-workflow baseline, v7 | 14/17; 20 tool calls; 0 model calls | Adds a synthetic return-policy version change after proposal creation. The runtime rejects stale proposals before creating a review request; three existing mixed/out-of-scope cases still fail. |

The minimal RAG holdout contains ten queries over two short policy documents. The expanded holdout contains 20 queries over 15 manifest entries. Both were authored synthetically; neither provides an independent production reliability estimate.

## Expanded RAG evaluation

To test the evaluator on more than the original two-document demo, I added 15 manifest entries (including an archived/superseded version) across 14 source IDs, 20 development queries, and a separate 20-query holdout. Cases cover paraphrases, multiple required sources, source-version constraints, answerable and unanswerable queries, hard negatives, tenant scope, and classification filters. The evaluator now accepts `--manifest`, checks `expected_versions`, and separates `authorization` cases with forbidden source IDs from ordinary relevance/abstention cases.

The development split is for model, chunking, and threshold selection; do not treat it as a second holdout:

| Advanced development metric | Dense feature hash | BM25-style lexical | Hybrid RRF |
|---|---:|---:|---:|
| Scenario pass | 65% | 90% | 90% |
| Required positive-source coverage | 67% | 93% | 100% |
| Hit@1 | 40% | 80% | 67% |
| Recall@5 sources | 67% | 93% | 100% |
| MRR | .494 | .856 | .822 |
| No-answer accuracy | 0% | 50% | 0% |
| Unique-source precision | 31% | 41% | 33% |
| Forbidden-source leakage | 0/3 | 0/3 | 0/3 |

Lexical misses `damage-crushed-in-transit` and returns results for the investment hard negative. Hybrid retrieves every labeled positive source but still answers both no-answer examples. Dense misses several paraphrases and both negative checks. These are tuning signals on this synthetic set only.

| Advanced holdout metric | Dense feature hash | BM25-style lexical | Hybrid RRF |
|---|---:|---:|---:|
| Scenario pass | 50% | 95% | 90% |
| Required positive-source coverage | 50% | 100% | 100% |
| Hit@1 | 25% | 81% | 69% |
| Recall@5 sources | 50% | 100% | 100% |
| MRR | .339 | .877 | .804 |
| No-answer accuracy | 0% | 50% | 0% |
| Unique-source precision | 31% | 34% | 31% |
| Forbidden-source leakage | 0/2 | 0/2 | 0/2 |

The positive-source coverage is not the whole story: lexical search retrieved all labeled positive sources but also returned irrelevant sources and failed a hard-negative investment query. Dense and hybrid paths returned results for both no-answer queries. The authorization cases found no forbidden source in these two authored checks; they do not establish access-control security. The expanded set improves diagnostic value but remains synthetic, manually authored, and too small for a production reliability claim. A fresh run on 2026-10-07 reproduced these values and the specific lexical development miss (`damage-crushed-in-transit`) and holdout hard-negative false positive (`holdout-hard-negative-refund-finance`). Hybrid returned results for the holdout Moon and investment queries. The inspected v1 holdout is regression-only; threshold tuning requires a new frozen holdout.

## Expanded support-agent architecture comparison

I preserved `support-agent-live-v4` and added `support-agent-live-v5` with five mixed, ambiguous, and out-of-scope cases. The live and fixed-workflow runners now select the same dataset with `--dataset PATH`, fingerprint it, and grade allowed terminal statuses, exact required tool-argument subsets, optional expected tool-error counts, and per-case tags.

The v5 baseline scores **12/15** (80%), with 17 tool calls and no model calls. It passes the clarification case and the explicit read-only refund eligibility case. It fails to check the second order in a mixed-ownership comparison, misses the delivery article when asked for two policy topics, and answers an order lookup without acknowledging that card-ledger status is unavailable. The pass rate by selected tag is 0/2 for `mixed-intent`, 0/1 for `authorization`, 0/1 for `out-of-scope`, 1/1 for `ambiguity`, and 1/1 for `action-boundary`. Tags overlap across cases, so these are diagnostic slice counts, not independent test populations.

The read-only refund case exposed an API design ambiguity: the prior proposal tool combined eligibility inspection with proposal creation. I added `check_refund_eligibility`, which enforces order ownership and returns only eligibility and policy version; proposal creation and human review remain separate steps. Scripted checks confirm the read-only path does not create a proposal or review. The fixed workflow still passes the v4 regression suite.

I also strengthened the operator approval boundary. Proposals, reviews, current synthetic policy/order facts, approval decisions, and the outbox now share one SQLite database. `approve()` validates the current policy version and current owner/eligibility/amount/currency inside the same `BEGIN IMMEDIATE` transaction that records approval and creates the outbox row. The approval checks now reject a policy update or amount change before approval and race policy mutation against approval; the concurrent result must serialize into a valid order. This is stronger local evidence than the agent-side pre-review check, but it depends on a colocated synthetic authority table and does not establish multi-host behavior or atomicity with independent production services.

The SHA-256 of `support-agent-live-v5` is `720505047b0a12c3da49f2aa7c90882b6ccc9c53ca3b178456115f8348ec8089`. These authored synthetic requests are development discriminators, not a held-out production sample. The Anthropic runner has not been run because provider credentials/model configuration are unavailable; live quality, cost, and caching behavior remain unmeasured.

I added `support-agent-live-v6`, retaining all v5 cases and adding a deterministic intervention that revokes the authenticated subject immediately after a successful private order read. The runtime discards the returned order details before writing the observation to the run trace or asking the model for another turn. The fixed workflow passes **13/16** cases (18 tool calls, zero model calls); the added revocation case passes. Its SHA-256 is `808431fdac6f04d59d4555c31749ca190a1ae321cb068fdb8a8b482f4350ad9d`. The scenario-specific intervention is synthetic; it does not verify a real identity provider or atomic authorization with a data service.

I added `support-agent-live-v7`, retaining all v6 cases and changing the current return-policy version after an eligible proposal is prepared but before review is requested. `request_human_review` now compares the proposal's policy version and material order facts (eligibility, amount, currency) with current runtime state. It rejects stale proposals; a fresh proposal under the new policy receives a version-scoped idempotency key. Security checks also mutate the order amount and verify that the stale proposal cannot create a review. The scripted evaluator passes the safe-hand-off case and fails a deliberately misleading planner that claims review is pending. The fixed workflow passes **14/17** (20 tool calls, zero model calls), and the v7 SHA-256 is `cdd7dcaf50a9a1439a4ac414a460ab7fef0abceb453e20e341e175fbc1b636de`. This is an in-process state-transition test: it does not close the concurrency window between a database read and review persistence. Production should validate and enqueue within one transaction or use an authoritative revision with compare-and-swap.

The live evaluator now reports two-sided 95% Wilson score intervals for each scenario and the pooled selected suite. These intervals are conditional on repeated trials of the fixed authored cases; they do not address dataset representativeness, grader validity, or generalization. With at most ten trials per case, they remain intentionally wide and should be treated as a variability diagnostic.

## Failure review

1. **Feature-hashing dense retrieval:** misses `return-window-new-phrase`, one source in a two-policy evidence question, and one source in the multi-source holdout. The feature hash preserves token overlap signals but does not represent semantic similarity.
2. **Hybrid no-answer behavior:** the `no-answer-capital` query retrieves `returns-policy`. Lexical terms or dense noise can enter the RRF candidate set, and fusion does not apply a calibrated relevance threshold. The current design needs an explicit abstention policy calibrated on labeled negatives.
3. **Lexical extra results:** positive-case source coverage is high, but precision is 89%. Measure the trade-off between candidate breadth and context noise before using the retriever in an answer path.
4. **Workflow-versus-agent value:** v7 provides mixed, ambiguous, authorization, unsupported-domain, revocation, and stale-policy cases; the fixed baseline passes 14/17. The next experiment is a live multi-trial Anthropic run against this exact v7 file, followed by trace review and a fresh holdout before tuning.

## Production-readiness evidence still missing

| Requirement | Current evidence | Still needed |
|---|---|---|
| Live model behavior | Fake Anthropic client only | Account-enabled multi-trial run, full trace review, grader calibration, and workflow comparison on representative cases |
| Prompt caching savings | Request block and usage parsing tested with fake client | Repeated live calls with nonzero cache read/write tokens, current rate card, and controlled cost/latency comparison |
| Semantic RAG quality | Deterministic feature-hashing path; optional Voyage HTTP adapter added but not called | Provider run on development data, representative labeled corpus, fresh held-out queries, filtered Recall@k and answer-grounding evaluation |
| Vector scale/performance | SQLite exact scan over eligible rows | Chosen vector service/database, filtered recall, p95/p99 latency, concurrency, backup/rebuild, deletion and rollback drills |
| Identity and tenant isolation | Synthetic subject IDs, local ownership rules, and a mid-run revocation intervention | Real identity propagation plus service-boundary integration tests, atomic revocation during in-flight writes, and replay cases |
| Concurrent durable work | Local SQLite lease/fencing/CAS, two-thread claim race, slow-tool heartbeat, and heartbeat-loss recovery checks; outbox leases | Provider/network and multi-host behavior, queue duplicate delivery, event-schema rollout, cancellation, restore, and downstream reconciliation drills |
| External action | Local payment mock | Real provider idempotency contract, ambiguous-outcome reconciliation, authenticated approval, audit, and operational exercise |
| Production objectives | Architecture plan only | Approved task mix, traffic/concurrency, SLOs, spend envelope, retention policy, and named on-call owners |
| Privacy/observability | Synthetic data; no production trace controls | Redaction, access/retention/deletion controls, incident runbook, cost attribution and sensitive-data tests |

## Recommended next experiments

1. **Improve the RAG benchmark before tuning:** the expanded set now covers multiple topics, one superseded version, paraphrases, hard negatives, multi-source questions, and tenant/classification filters. Add longer layout-rich sources, near-duplicates, conflicting active sources, more languages/modalities, and more independent labels. Freeze a new holdout before tuning chunking or thresholds.
2. **Evaluate the optional real-embedding adapter:** the repository now includes a standard-library Voyage adapter with batched document/query modes. Configure credentials outside Git and run it on development data; keep ingestion, metadata filters, and evaluators constant. Compare the provider model with lexical search using relevance, filtered recall, no-answer precision/recall, answer grounding, latency, and cost, then freeze a new independent holdout.
3. **Add calibrated abstention:** set thresholds on a development set; report false answer vs abstention trade-offs on holdout. Keep access control separate from relevance scoring.
4. **Run the support-agent comparison:** configure an account-enabled Anthropic model and a current local rate card outside the repository, then run `python3 run_live_evals.py --dataset evals/live_scenarios_v7.json --rate-card ~/.config/agentic-ai/rate-card.json --trials 3 --output live-v7.json`. Review failures, complete tool traces, token costs, and costs per successful trial beside the fixed-workflow results. Then add incomplete-tool-response cases and preserve a fresh holdout before tuning.
5. **Only then test live prompt caching:** repeat a fixed case order, compare disabled/enabled requests and cache metrics, price the cache writes/reads from the active rate card, and include full task quality and latency.
6. **Harden distributed execution:** add heartbeat supervision and fault-injection for slow calls, duplicate queue delivery, schema rollout, cancellation, restore, and downstream reconciliation before scaling beyond the local SQLite journal.

## Reproduction commands

From `agentic-ai-sandbox/`:

```sh
python3 run_evals.py
python3 run_adapter_checks.py
python3 run_durability_checks.py
python3 run_approval_checks.py
python3 run_security_checks.py
python3 run_retrieval_checks.py
python3 run_retrieval_evals.py
python3 run_rag_checks.py
python3 -m pip install -r requirements-pdf.txt  # optional PDF dependency
python3 run_pdf_checks.py
python3 run_embedding_checks.py
python3 run_rag_evals.py --retriever dense
python3 run_rag_evals.py --retriever lexical
python3 run_rag_evals.py --retriever hybrid
python3 run_rag_evals.py --manifest knowledge/advanced/manifest.json --dataset evals/advanced_dev_scenarios.json --retriever lexical
python3 run_rag_evals.py --manifest knowledge/advanced/manifest.json --dataset evals/advanced_holdout_scenarios.json --retriever dense
python3 run_rag_evals.py --manifest knowledge/advanced/manifest.json --dataset evals/advanced_holdout_scenarios.json --retriever lexical
python3 run_rag_evals.py --manifest knowledge/advanced/manifest.json --dataset evals/advanced_holdout_scenarios.json --retriever hybrid
python3 run_eval_runner_checks.py
python3 run_workflow_baseline.py --dataset evals/live_scenarios.json
python3 run_workflow_baseline.py --dataset evals/live_scenarios_v5.json
python3 run_workflow_baseline.py --dataset evals/live_scenarios_v6.json
python3 run_workflow_baseline.py --dataset evals/live_scenarios_v7.json
```

The live model evaluator was not run because credentials/model configuration were absent. See the [sandbox README](agentic-ai-sandbox/README.md) for its live-run requirements and limitations.
