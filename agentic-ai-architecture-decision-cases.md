# Architecture Decision Cases: Compare Viable Alternatives

These hypothetical cases practice choosing under constraints rather than reciting a stack. For each, attempt a five-minute decision before reading the reference. Current framework details should be verified against pinned versions; the principles and workload assumptions matter more than product names.

## 1. Existing database or dedicated retrieval service?

**Scenario:** Two engineers maintain an internal assistant over 50,000 documents. The business already operates Postgres, needs tenant filters and frequent source updates, and expects two peak queries/second. No retrieval benchmark exists yet.

| Option | Potential advantage | Evidence or cost to examine |
| --- | --- | --- |
| Existing relational database plus vector/full-text capability | Reuse operational ownership and transactional metadata | Filtered recall, query/index contention, index build, restore and deletion |
| Dedicated vector/search service | Separate retrieval scaling and operations | Dual-write consistency, ACL/delete propagation, reconciliation, cost and ownership |
| Lexical/direct search only | Less machinery for exact identifiers and small policies | Semantic paraphrase recall and answer-quality gaps |

**Reference decision:** Start with lexical/exact baselines and test a vector-capable existing store when semantic coverage needs it. Under these assumed constraints, operational simplicity favors the existing store for a pilot. This is a decision hypothesis, not evidence that two QPS or this corpus always fits. Query selectivity, document length, update patterns and hardware must be measured.

Postgres's pgvector extension supports exact and approximate search, including HNSW and IVFFlat. Approximate search/filter behavior needs testing on the actual query path. [Primary documentation](https://github.com/pgvector/pgvector)

**Benchmark design:** Same embeddings, authorized queries and labeled corpus across stores. Compare exact-search ground truth with filtered ANN recall, p95/p99 at expected concurrency, update/delete visibility, rebuild time, backup/restore and cost. A rechecked ACL is still required before disclosure. Do not pick a universal chunk/QPS cutoff from intuition.

**Reconsider:** Material contention or retrieval-SLO failure after tuning and capacity analysis; a dedicated service must justify its consistency and operating cost.

## 2. When retrieval should be separated

**Changed scenario:** Thirty million chunks, 200 peak queries/second, several independent tenant classes, and heavy ingestion. The relational service also owns critical transactional writes.

**Reference decision:** Evaluate a separately operated retrieval tier to isolate workload and failure domains. Preserve authoritative identity/security revisions outside the derived index. Compare partitioning in the existing database with a dedicated service; neither wins without filtered-recall and load evidence. Make publication, tombstones, out-of-order events and rollback part of the contract, not follow-up work.

**Failure walk:** A permission update arrives while a new index generation is staged. Current-source authorization denies revoked content immediately; staged publication cannot overwrite a newer security revision. Rollback must not restore old entitlements. A missing authorization service causes fail-closed retrieval, not unfiltered fallback.

**Follow-up:** Exact scan, HNSW, IVF and compression offer different recall/memory/build trade-offs. Use an exact baseline and verify filter selectivity; see [Faiss index documentation](https://github.com/facebookresearch/faiss/wiki/Faiss-indexes). This case does not claim a particular service's scale limit.

## 3. Explicit loop, graph runtime or durable workflow engine?

**Scenario:** A seven-tool assistant mostly completes in seconds, with occasional parallel read branches. Later, approvals may wait days and resume across worker deployments.

| Option | Good reason to investigate | Responsibilities it does not remove |
| --- | --- | --- |
| Explicit loop/custom bounded executor | Small inspectable surface, narrow current requirements | Protocol mapping, persistence, budgets, cancellation, contracts, testing |
| Graph orchestration runtime | Branching state, checkpoints, interrupts and joins | Domain authority, safe replay, downstream effects, deployment compatibility |
| Durable workflow engine | Timers, long waits, reliable event history and worker recovery | Activity idempotency, deterministic replay rules, approval identity and reconciliation |

LangGraph is a low-level stateful orchestration runtime with persistence and human-in-the-loop capabilities. [Primary overview](https://docs.langchain.com/oss/python/langgraph/overview)

Temporal workflow execution uses recorded history and replay; environment interactions occur through Activities. [Primary overview](https://docs.temporal.io/workflow-execution)

**Reference decision:** Keep the bounded explicit runtime for the present short pilot if its contracts are sufficient. Evaluate a graph runtime when branching/state complexity increases. For a days-long business process, evaluate durable workflow infrastructure and put model/network calls behind recorded effect boundaries. A graph and a durable workflow engine can coexist at different layers, but that adds operations and integration contracts.

**Migration test:** Replay recorded tool histories; upgrade event schemas; crash after an external effect; cancel during a call; resume an expired identity; retry after an approval wait. Verify actual semantics rather than assuming framework checkpointing makes a payment exactly once.

**Follow-up:** Which state belongs to conversation, graph, workflow history and domain system of record? Draw their ownership and retention separately.

## 4. Managed model API or self-hosted inference?

**Scenario A:** Variable traffic, small platform team, approved external processing, fast model experimentation. **Reference:** A managed API is a useful initial option; measure task quality, quotas, tail latency, retention controls, availability, fallback and total cost. Model switching requires behavioral evaluation, not just an identical client interface.

**Scenario B:** Approved data cannot leave a designated environment, utilization is predictable, and a serving team owns accelerator operations. **Reference:** Evaluate an eligible self-hosted model/runtime inside that boundary, with task-quality, memory, throughput and operating evidence. Lower token price or “open weights” alone does not establish suitability, licensing, privacy or security. Check each model and deployment contract.

**Hypothetical economics:** One million monthly tasks at $0.01/task costs $10,000 for managed model calls. Assume two accelerator instances at $2/hour each for 730 hours: $2,920. Add $6,000 allocated engineering/on-call and $1,000 runtime/storage/observability: $9,920. This apparent $80 saving is inconclusive: availability replicas, utilization, quality differences, migration, energy/egress and growth may reverse it. All rates are invented. Compare cost per successful authorized task and compliance with the required boundary.

**Serving experiment:** Sweep input lengths, output lengths and concurrency; measure prefill/first-token/decode times, throughput, KV/workspace memory, errors and recovery. Compare quantization only with compatible kernels and actual task-quality checks. Do not extrapolate from raw weight memory or a single benchmark.

## 5. Provider-neutral agent integration

Keep an internal decision/result contract, but retain provider call IDs, original protocol events, usage categories and stop reasons for diagnosis. Maintain a capability matrix: client/server tools, parallel-call behavior, streaming, constrained output, refusal, continuation/replay, caching and data handling. Mark unsupported capabilities explicitly.

**Reference fallback design:** Router selects a provider only from allowed configurations. Each provider has its own normalizer and contract tests. A fallback can answer read-only cases only after equivalent task/security evaluation; an in-flight side effect cannot be retried through another provider under a new operation key. Use a deterministic safe path or handoff when equivalence is absent.

**Acceptance artifact:** Two fake providers producing the same semantic tool request in different event shapes, a normalized trace with original IDs, and failure cases for duplicate/missing results, truncation and refusal. The repo's real live adapter remains Anthropic; this exercise does not claim a second integration was deployed.

## Interview defense checklist

State the assumed workload and hard constraints. Name two viable alternatives, explain the first-release choice and omitted complexity, then provide a falsifying benchmark and migration trigger. “We use framework X” is not the decision; explain what requirement it fulfills and what your team must still own.
