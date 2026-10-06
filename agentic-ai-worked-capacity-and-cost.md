# Worked Capacity, Latency, and Cost Design

This exercise uses invented workload, prices, and targets to practice numerical reasoning. None are measured Harper numbers, current provider prices, or production recommendations. Replace assumptions and validate distributions before deployment.

## Requirements and assumptions

Design a permission-aware internal knowledge assistant for 10,000 employees.

| Input | Hypothetical value |
| --- | --- |
| Documents | 200,000; average 3,000 model tokens each |
| Chunking baseline | 600 tokens, overlap 100, preserve structures where possible |
| Embeddings | 1,024 dimensions, float32 |
| Content changes | 2% of documents/day; ACL changes handled independently |
| Traffic | 40,000 tasks/day, 22 workdays/month; most traffic within 8 hours |
| Peak arrival rate | 5 tasks/second for 15 minutes |
| Routes | 60% search only, 30% one grounded generation, 10% bounded investigation |
| Generation route | One model call, 4,000 input and 500 output tokens, mean task time 6 seconds |
| Investigation route | Three calls, 18,000 total input and 1,500 total output tokens, mean task time 20 seconds |
| Search route | No generator; mean task time 0.5 seconds |
| Proposed response targets | Search p95 <= 1 second; generation <= 10 seconds; investigation <= 30 seconds |
| Proposed ACL boundary | Current access checked before any evidence is exposed; stale index is never authority |

The targets are hypotheses for this exercise. Measure under representative concurrency; do not derive p95 by multiplying averages.

## 1. Corpus and storage

For fixed windows, count approximately `1 + ceil((document_tokens - chunk_tokens) / stride)` when a document exceeds one chunk, where stride is 500 tokens. A 3,000-token document therefore creates six chunks. Real structure-aware parsing will change this count.

- Approximate chunks: `200,000 × 6 = 1,200,000`.
- Raw vectors: `1,200,000 × 1,024 × 4 = 4,915,200,000 bytes`, about 4.92 GB decimal or 4.58 GiB.
- Embedded chunk tokens: last window is 500 tokens; `5 × 600 + 500 = 3,500/document`, about 700 million total. Overlap costs more than the original 600 million tokens.
- Changed documents: `4,000/day`; approximate 24,000 replacement chunks and 14 million embedding input tokens/day.

Raw vectors exclude graph/index overhead, lexical postings, text, metadata, tombstones, staging, replicas, and backups. With an illustrative assumed planning factor of 3 and one primary plus two replicas (three total copies), provision approximately 44.2 GB just for that modeled vector/index allocation. Benchmark the factor; this is not a universal HNSW rule. Retain a separate budget for other data and a rebuild beside the active version.

If sustained ingestion is 100 chunks/second, a full 1.2-million-chunk rebuild takes at least 12,000 seconds, or 3 hours 20 minutes, excluding fetch, parse, retry, validation, and publication. That rate also consumes roughly 58,300 embedding input tokens/second on the assumed average chunk size. Provider quotas may dominate. A 15-minute rebuild promise needs at least 1,334 chunks/second before overhead.

## 2. Request and model capacity

The eight-hour active-period average arrival rate is `40,000 / 28,800 = 1.39 tasks/second`. Size the specified 5/second burst separately.

Weighted mean task duration is `0.6 × 0.5 + 0.3 × 6 + 0.1 × 20 = 4.1 seconds`. Little's Law predicts about `5 × 4.1 = 20.5` tasks in flight during a stable period at that arrival rate. It does not establish required worker count, p95, or safety margin. Blocking workers, async workers, provider quotas, and tool pools impose different constraints.

Model calls/task: `0.3 × 1 + 0.1 × 3 = 0.6`. Peak demand is about 3 calls/second, or 180 calls/minute, before retries.

Input tokens/task: `0.3 × 4,000 + 0.1 × 18,000 = 3,000`. Output tokens/task: `0.3 × 500 + 0.1 × 1,500 = 300`. Peak demand is approximately 900,000 input and 90,000 output tokens/minute. Compare both with provider-account quotas. A 10% retry factor produces 198 calls/minute, 990,000 input, and 99,000 output tokens/minute only if retries have the same route mix; failure-correlated retries can be worse.

If an account allows just 150 calls/minute, then even the no-retry peak is infeasible. At 0.6 calls/task, the call-limit ceiling is `150 / 60 / 0.6 = 4.17 tasks/second`; token or tool limits may reduce it further. Queue with bounded age, admit fewer investigations, and offer search-only fallback. Adding workers cannot remove the provider ceiling.

## 3. Latency budget and streaming

For a hypothetical 10-second generation p95 target, allocate an initial budget: auth/admission 0.2 seconds, queue 0.5, retrieval 0.5, rerank/evidence 0.3, model 7.5, validation/delivery 0.5, and reserve 0.5. These total 10 seconds and are budget allocations, not independently measured p95 values; summing component p95 values is not the true end-to-end p95.

Instrument stage spans and measure actual task latency. Track first-token time separately; never declare a completed answer merely because streaming started. Put deadlines on each stage and reserve time for a safe fallback. Parallel independent searches may help the critical path while increasing load and total cost.

## 4. Cost model

Use invented rates: input $2/million tokens, output $8/million, embeddings $0.10/million. No prompt-cache saving is assumed.

| Route | Token cost/task |
| --- | --- |
| Search only | $0 generator cost; still has query/retrieval/infrastructure cost |
| Grounded generation | `(4,000 × 2 + 500 × 8) / 1,000,000 = $0.012` |
| Investigation | `(18,000 × 2 + 1,500 × 8) / 1,000,000 = $0.048` |

Weighted generation cost is `0.3 × 0.012 + 0.1 × 0.048 = $0.0084/task`. For 880,000 tasks/month, generation spend is $7,392 before retries. Uniform 10% token overhead gives $8,131.20.

Initial corpus embeddings cost approximately $70; 22 days of changes cost $30.80. Query embeddings, reranking, connector APIs, storage, compute, telemetry, egress, human work, and tax are excluded and must be added. With an assumed 92% useful-completion rate and the illustrative retry spend, generation cost per useful task is `$8,131.20 / (880,000 × 0.92) ≈ $0.0100`. Compare useful, authorized outcomes, not just cheap calls.

**Sensitivity:** Doubling investigations from 10% to 20% while reducing search-only from 60% to 50% raises weighted token cost to $0.0132/task, a 57% increase. Uniform 10% retries then cost $12,777.60/month. Model calls rise to 0.9/task, or 270/minute at peak. Quality and rate-limit constraints can become the bottleneck before infrastructure cost.

## 5. Human review and incident load

Suppose 2% of 40,000 daily tasks require review: 800 reviews/day. At four minutes/review, that is 3,200 minutes, or 53.3 reviewer-hours/day. At six productive hours/reviewer/day, nine reviewers are a minimum average-capacity floor. This ignores bursts, absence, uneven service time, investigation escalations, and a review-time SLA. Model the queue and reserve headroom; never clear it by silently approving.

## 6. Defend the design

In five minutes, explain which assumptions dominate cost, which quota limits peak throughput, where ACL changes bypass content-hash skipping, and how a rebuild runs beside the active index. Change two assumptions and recompute. Submit a worksheet with units, formulas, measurement plan, and fallback policy. Load-test slow model calls, retry bursts, restricted-filter queries, revocations, and review backlog before accepting the targets.
