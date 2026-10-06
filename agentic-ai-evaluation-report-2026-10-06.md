# Offline System Evaluation — 2026-10-06

## Decision summary

The current sandbox demonstrates useful control and data-path mechanics under synthetic, offline conditions. The deterministic harness, approval/outbox simulation, security boundaries, and local retrieval contracts pass their authored checks. The fixed workflow passes all ten shared support cases without model calls.

The evidence does **not** establish that a live model is useful or reliable, that the system meets production SLOs, or that RAG works on a representative corpus. The Anthropic adapter was tested with a fake client. The RAG dense path uses feature hashing, and the SQLite search scans eligible rows rather than exercising a production ANN service. Hybrid retrieval produced a false positive on a no-answer holdout query.

**Current recommendation:** continue the work as an offline prototype. Do not describe it as production-ready or as validated live-agent behavior.

## Environment and method

- Date: 2026-10-06.
- Repository: this curriculum repository's `agentic-ai-sandbox/` directory.
- Data: authored synthetic support cases and two short synthetic policy documents.
- API access: `ANTHROPIC_API_KEY` and `ANTHROPIC_MODEL` were not configured; no paid model or embedding API calls were made.
- Commands were run offline. The dense and hybrid RAG evaluators returned exit code 1 because their graders found relevance gaps; this is the expected signal for those gaps, not a Python execution failure.

## Results

| Area | Result | What it establishes |
|---|---:|---|
| Scripted agent scenarios | 9/9 | The tested harness/tool outcomes satisfy the hand-authored deterministic expectations. |
| Anthropic adapter checks | 3/3 | Fake-client tool round trip, optional prompt-cache instrumentation, and safe handoff for multi-tool responses work in the checked paths. No live provider behavior was measured. |
| Durable-run checks | 5/5 | Tested single-worker SQLite restart, replay, subject binding, and idempotency paths work. No multi-worker lease/consistency claim follows. |
| Approval/outbox checks | 6/6 | Tested exact-proposal approval and mocked retry/deduplication behavior works. No real operator identity or payment provider was exercised. |
| Security check groups | 7/7 | Tested bounded inputs, capability separation, tenant-denial behavior, minimized data, expiry/task checks, and fail-closed dispatch pass. This is not a live-model prompt-injection assessment. |
| Policy retrieval contract checks | 8/8 | The small policy catalog meets its current authored ranking, freshness, provenance, and minimization checks. |
| Policy retrieval eval | 11/11 | Hit@1 100%, Recall@2 100%, MRR 1.000, exact coverage 100%, and empty-query accuracy 100% on `policy-retrieval-v1`. This dataset is small and written alongside the retriever. |
| RAG storage/access checks | 5/5 groups | SQLite ingestion, metadata/provenance, access filters, supersede, persistence, and deletion work in the tested local paths. |
| RAG dense holdout (minimal set) | 60% scenario pass; 50% positive-source coverage; 83% Hit@1; 67% Recall@4; MRR .833; 75% no-answer accuracy; 100% unique-source precision | Feature hashing misses several authored relevant-source requirements and returned a result for the capital-city no-answer query. It is not a semantic embedding benchmark. |
| RAG lexical holdout (minimal set) | 100% scenario pass and positive-source coverage; 100% Hit@1/Recall@4; MRR 1.000; 100% no-answer accuracy; 89% unique-source precision | Lexical retrieval is strongest on this tiny, keyword-oriented synthetic holdout. The precision gap shows extra sources remain. It does not establish generalization. |
| RAG hybrid holdout (minimal set) | 90% scenario pass; 100% positive-source coverage/Hit@1/Recall@4; MRR 1.000; 75% no-answer accuracy; 89% unique-source precision | RRF recovered required sources in positive cases but carried a false positive for the capital-city no-answer query. It underperforms lexical retrieval on abstention. |
| Repeated-trial evaluator checks | 3/3 | Scripted checks confirm aggregation/task isolation mechanics; they do not measure model variability. |
| Fixed-workflow baseline | 10/10; 12 tool calls; 0 model calls | The baseline covers these ten cases. The set does not prove it covers real support traffic or that an agent could not help on representative ambiguous cases. |

The RAG holdout contains ten queries over two short policy documents. A zero or perfect score here has little statistical power and must not be interpreted as a production reliability estimate.

## Expanded RAG evaluation

To test the evaluator on more than the original two-document demo, I added 15 manifest entries (including an archived/superseded version) across 14 source IDs, 20 development queries, and a separate 20-query holdout. Cases cover paraphrases, multiple required sources, source-version constraints, answerable and unanswerable queries, hard negatives, tenant scope, and classification filters. The evaluator now accepts `--manifest`, checks `expected_versions`, and separates `authorization` cases with forbidden source IDs from ordinary relevance/abstention cases.

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

The positive-source coverage is not the whole story: lexical search retrieved all labeled positive sources but also returned irrelevant sources and failed a hard-negative investment query. Dense and hybrid paths returned results for both no-answer queries. The authorization cases found no forbidden source in these two authored checks; they do not establish access-control security. The expanded set improves diagnostic value but remains synthetic, manually authored, and too small for a production reliability claim.

## Failure review

1. **Feature-hashing dense retrieval:** misses `return-window-new-phrase`, one source in a two-policy evidence question, and one source in the multi-source holdout. The feature hash preserves token overlap signals but does not represent semantic similarity.
2. **Hybrid no-answer behavior:** the `no-answer-capital` query retrieves `returns-policy`. Lexical terms or dense noise can enter the RRF candidate set, and fusion does not apply a calibrated relevance threshold. The current design needs an explicit abstention policy calibrated on labeled negatives.
3. **Lexical extra results:** positive-case source coverage is high, but precision is 89%. Measure the trade-off between candidate breadth and context noise before using the retriever in an answer path.
4. **Workflow-versus-agent value:** the fixed baseline solves every case in the shared ten-case set without inference. Current evidence does not show an agent benefit; the missing experiment is an expanded set with realistic mixed, ambiguous, and changing-context tasks, followed by a live comparison.

## Production-readiness evidence still missing

| Requirement | Current evidence | Still needed |
|---|---|---|
| Live model behavior | Fake Anthropic client only | Account-enabled multi-trial run, full trace review, grader calibration, and workflow comparison on representative cases |
| Prompt caching savings | Request block and usage parsing tested with fake client | Repeated live calls with nonzero cache read/write tokens, current rate card, and controlled cost/latency comparison |
| Semantic RAG quality | Deterministic feature-hashing path | Real embedding provider(s), representative labeled corpus, fresh held-out queries, filtered Recall@k and answer-grounding evaluation |
| Vector scale/performance | SQLite exact scan over eligible rows | Chosen vector service/database, filtered recall, p95/p99 latency, concurrency, backup/rebuild, deletion and rollback drills |
| Identity and tenant isolation | Synthetic subject IDs and local ownership rules | Real identity propagation plus service-boundary integration tests, revocation and replay cases |
| Concurrent durable work | Single-worker simulated restarts and outbox leases | Multi-worker run claims, fencing/CAS, queue duplicate delivery, stale lease, and race tests |
| External action | Local payment mock | Real provider idempotency contract, ambiguous-outcome reconciliation, authenticated approval, audit, and operational exercise |
| Production objectives | Architecture plan only | Approved task mix, traffic/concurrency, SLOs, spend envelope, retention policy, and named on-call owners |
| Privacy/observability | Synthetic data; no production trace controls | Redaction, access/retention/deletion controls, incident runbook, cost attribution and sensitive-data tests |

## Recommended next experiments

1. **Improve the RAG benchmark before tuning:** the expanded set now covers multiple topics, one superseded version, paraphrases, hard negatives, multi-source questions, and tenant/classification filters. Add longer layout-rich sources, near-duplicates, conflicting active sources, more languages/modalities, and more independent labels. Freeze a new holdout before tuning chunking or thresholds.
2. **Add real embeddings as a separate adapter:** keep ingestion, metadata filters, and evaluators constant. Compare a chosen provider's model with lexical search using relevance, filtered recall, no-answer precision/recall, answer grounding, latency, and cost.
3. **Add calibrated abstention:** set thresholds on a development set; report false answer vs abstention trade-offs on holdout. Keep access control separate from relevance scoring.
4. **Expand support-agent cases:** create mixed-intent and ambiguous tasks, current-state changes, stale evidence, access revocation during a run, and incomplete tool responses. Run the workflow baseline first; then run the Anthropic planner on the identical cases when credentials/account access are available.
5. **Only then test live prompt caching:** repeat a fixed case order, compare disabled/enabled requests and cache metrics, price the cache writes/reads from the active rate card, and include full task quality and latency.
6. **Harden distributed execution:** implement or prototype multi-worker lease/fencing semantics and fault-injection cases before scaling the run journal.

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
python3 run_rag_evals.py --retriever dense
python3 run_rag_evals.py --retriever lexical
python3 run_rag_evals.py --retriever hybrid
python3 run_rag_evals.py --manifest knowledge/advanced/manifest.json --dataset evals/advanced_dev_scenarios.json --retriever lexical
python3 run_rag_evals.py --manifest knowledge/advanced/manifest.json --dataset evals/advanced_holdout_scenarios.json --retriever dense
python3 run_rag_evals.py --manifest knowledge/advanced/manifest.json --dataset evals/advanced_holdout_scenarios.json --retriever lexical
python3 run_rag_evals.py --manifest knowledge/advanced/manifest.json --dataset evals/advanced_holdout_scenarios.json --retriever hybrid
python3 run_eval_runner_checks.py
python3 run_workflow_baseline.py
```

The live model evaluator was not run because credentials/model configuration were absent. See the [sandbox README](agentic-ai-sandbox/README.md) for its live-run requirements and limitations.
