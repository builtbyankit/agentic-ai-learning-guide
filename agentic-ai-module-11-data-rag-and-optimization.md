# Module 11 — Unstructured Data, RAG, and Agent Optimization

## Learning objective

Build the data path that gives an agent reliable evidence: ingest unstructured sources, clean and preserve their structure, split them into useful retrieval units, embed and store them with provenance, retrieve with authorization filters, and evaluate whether the evidence helps. Then reduce context, latency, and cost without weakening quality or safety.

Use this module with [Module 10](agentic-ai-module-10-context-retrieval-and-memory.md). Module 10's small policy catalog is the deliberately simple baseline; this module adds a data pipeline for larger and less structured corpora.

The executable lab supports Markdown/plain text, static `.html`/`.htm`, a bounded standard-library `.docx` extractor, and optional PDF parsing through `pypdf`. The Word path reads the main OOXML body, maps common heading styles, turns directly marked list paragraphs into bullets, preserves basic tables and page-break markers, and honors configured basic PII redaction downstream. It rejects DTD/entity declarations and limits package size/member counts. It does not resolve list numbering/styles, extract headers/footers, comments, images, text-box reading order, tracked-change history, or spreadsheet/slide content. The PDF path preserves page boundaries and uses layout-mode extraction for selectable text. For pages with no text, callers may inject a `PDFOCRAdapter` that returns page text and confidence; results below the caller's threshold are rejected for review, while accepted text keeps page and confidence provenance and follows normal redaction/chunking. This repository defines and tests that adapter contract with synthetic output only—it contains no renderer or OCR engine, does not OCR mixed text/image pages, and does not guarantee table/column reconstruction. Confidence thresholds must be calibrated for the actual engine, language, and document class. `pypdf` notes that PDFs lack a semantic layer, image-only pages need OCR, and page-content parsing can consume substantial memory. The size checks here are input guards, not a parser sandbox; process untrusted PDFs in a resource-limited worker. See the [pypdf text-extraction guide](https://pypdf.readthedocs.io/en/stable/user/extract-text.html). The HTML path retains headings, lists, image alt text, and table rows while stripping common script/style/navigation/footer elements; it does not render JavaScript or guarantee removal of site-specific boilerplate. Treat each parser as a versioned source-specific component with fixtures, not a universal document parser.

## The knowledge pipeline

```mermaid
flowchart LR
    S[Source systems] --> X[Extract text and layout]
    X --> P[Normalize, classify, redact, deduplicate]
    P --> C[Structure-aware chunks + provenance]
    C --> E[Embedding model]
    E --> V[(Vector index + metadata)]
    Q[Question + trusted scope] --> F[Authorization and metadata filters]
    F --> R[Hybrid retrieval]
    V --> R
    R --> RR[Optional reranking]
    RR --> B[Bounded evidence with citations]
    B --> A[Agent answer or tool decision]
    A --> G[Retrieval and answer evaluation]
```

Keep source records as the authority. A vector index is a derived, rebuildable search structure. Search results are evidence candidates, not permission grants and not instructions. Check access from trusted application identity before content reaches the model.

## 1. Preprocess unstructured sources

Treat extraction as its own quality stage. A document pipeline should retain the original object and create a normalized, traceable representation rather than overwriting the source.

| Source | Extraction concerns | Useful metadata |
|---|---|---|
| HTML and web pages | Boilerplate, navigation, tables, canonical URL, crawl time | URL, page title, fetched time, content hash |
| PDF | Reading order, page breaks, headers/footers, tables, scanned pages, OCR confidence | File ID, page number, parser version, OCR status |
| Word and slides | Headings, lists, speaker notes, tables, slide/page boundaries | File ID, section/slide, author if approved |
| Email and tickets | Quoted replies, signatures, attachments, participant privacy | Conversation ID, message time, tenant, access group |
| Audio/video | ASR errors, speaker turns, timestamps, language | Asset ID, time range, transcript model/version |
| Code and logs | Syntax boundaries, stack traces, secrets, timestamps | Repository/service, path, commit, environment |

Apply a repeatable sequence:

1. **Extract** with a parser suited to the source. Preserve page, heading, table, and timestamp boundaries; record parser/OCR version and extraction errors.
2. **Normalize** Unicode and line endings, remove control characters and known boilerplate, and make whitespace consistent. Preserve meaningful list/table structure and the original alongside normalized text.
3. **Classify and scope** by tenant, access group, sensitivity, jurisdiction, retention, and source status. Derive these from trusted metadata, not from text or a model-generated label alone.
4. **Redact or exclude** fields that should never be embedded or passed to a model. Basic regex redaction catches only obvious patterns; it is not a complete PII or secret scanner. Keep redaction policy and parser versions in the ingestion record.
5. **Deduplicate** exact duplicates by normalized content hash. Detect near-duplicates where repeated content would crowd the top results; preserve source links for citations and choose a canonical representation.
6. **Attach provenance**: stable source ID, version, content hash, effective date, owner/tenant, classification, page/section, and ingestion time. Keep a path back to the authoritative source.
7. **Validate** extracted text length, encoding, empty pages, OCR confidence, chunk coverage, and source counts. Quarantine malformed documents instead of silently indexing partial data.

Retrieved text is untrusted input. A document may contain prompt injection, stale instructions, private fields, or misleading content. Treat it as quoted evidence, separate it from agent policy, restrict tool authority independently, and test poisoned documents.

## 2. Choose a chunking strategy

Chunk boundaries affect both what can be found and whether a retrieved result makes sense by itself. There is no universally best chunk size; tune it on representative queries with retrieval and downstream answer metrics.

| Strategy | Strength | Cost or failure mode | Good starting use |
|---|---|---|---|
| Fixed token windows with overlap | Simple, predictable, easy to bound | Cuts tables, clauses, or narrative at arbitrary points; overlap duplicates content | Baseline for plain text |
| Recursive/structure-aware | Respects headings, paragraphs, lists, pages, code blocks, and table rows | Requires good parsers; a large section still needs splitting | Policies, manuals, HTML, code |
| Semantic boundary splitting | Splits when topic changes rather than at a fixed count | Adds an analysis step, can be unstable, and may create uneven lengths | Long mixed-topic prose where boundaries matter |
| Parent-child chunks | Small child chunks retrieve precisely; larger parent section restores context | More storage and a second fetch; deduplicate parents | Dense manuals or long policies |
| Sentence/late chunking | Can preserve broader context for token representations before making smaller retrieval units | Depends on embedding model and pipeline support; more complexity | Test only where standard chunking misses contextual links |

Practical rules:

- Keep a heading path or compact document context with every chunk so a fragment such as “within 30 days” remains interpretable.
- Split on natural structure first, then split oversized sections to meet a measured model-token budget. The sandbox uses whitespace-word counts only to stay dependency-free; production limits should use the embedding/model tokenizer.
- Use overlap to protect boundary-spanning facts, then measure duplicate results and redundant prompt tokens. More overlap is not automatically better.
- Keep tables as coherent rows with repeated column headers; preserve code blocks and speaker turns; do not flatten layout-heavy sources blindly.
- Make chunk IDs stable from source/version/section/content so re-ingestion is idempotent and updates can be traced. Keep embedding model/version separately.
- Store the source location and version for every chunk. Cite the actual source, not an opaque vector ID.

## 3. Embed, store, and refresh

The embedding model and vector store are separate parts of the system. Keep an `Embedder` interface so you can compare providers or models without changing ingestion, authorization, or agent code. Anthropic's documentation currently says Anthropic does not offer its own embedding model and demonstrates a separate embeddings provider; evaluate model quality, language/domain coverage, latency, privacy, and cost for the actual corpus. See [Anthropic's embeddings guide](https://platform.claude.com/docs/en/build-with-claude/embeddings).

Choose by measured workload rather than model name alone. Anthropic's current provider guide describes `voyage-4-large` for highest general retrieval quality, `voyage-4` as a quality/efficiency balance, `voyage-4-lite` for lower latency/cost, `voyage-code-4` for code, and `voyage-context-4` for contextualized chunk embeddings; it also lists a multimodal option for text, images, and video. Compare query classes, languages, latency, and cost on your own data. The normal text adapter here uses `voyage-4` with `input_type="document"` and `input_type="query"`. The provider currently supports configurable output dimensions for several models; dimension is part of the index contract, so record model and dimension and rebuild a separate index when either changes. See [the current model/API guide](https://platform.claude.com/docs/en/build-with-claude/embeddings).

The sandbox includes an optional standard-library HTTP adapter for Voyage. It sends document and query inputs with distinct `input_type` values, batches changed chunks before the SQLite write transaction, restores response order from provider indices, checks dimensions and finite values, and records document/query request and input-token counts separately. The adapter caps a request at 64 texts; the lab's 90-word chunks keep its requests small, but this is not a provider tokenizer or a general token-budget guarantee. Production ingestion should enforce per-input and per-request token budgets using the selected model's tokenizer. The default path remains local feature hashing. See the provider's [text embeddings API](https://docs.voyageai.com/reference/embeddings-api-1) for request and model details. To run an actual semantic comparison, set `VOYAGE_API_KEY` in the environment and opt in explicitly:

```sh
export VOYAGE_API_KEY="your-key"
python3 run_rag_evals.py --manifest knowledge/advanced/manifest.json \
  --dataset evals/advanced_dev_scenarios.json --retriever dense \
  --embedding-provider voyage --embedding-model voyage-4 --output voyage-dev.json
```

Then evaluate the chosen configuration on a holdout only after model/chunking decisions are set. `voyage-4` is the adapter default; verify model availability, endpoint, data terms, and current pricing with the provider. The default endpoint is Voyage's native API; when using a MongoDB Atlas model API key, set `VOYAGE_API_URL=https://ai.mongodb.com/v1/embeddings` or pass `--embedding-endpoint` (use region-specific endpoint guidance when applicable). The adapter makes real billable requests only with the explicit `--embedding-provider voyage` flag, does not retry automatically, and never writes the API key to a report. Do not commit keys or reports containing sensitive queries. No live Voyage call has been made in this workspace, so existing retrieval metrics remain feature-hashing/lexical baselines.

Store each vector with filterable metadata, not as a detached float array. Common fields are `tenant_id`, access groups, classification, source ID, version, effective date, status, content hash, section/page, embedding model ID, and vector. Apply tenant/access/version filters inside the retrieval boundary before evidence is returned. Do not ask the model to enforce access control after retrieval.

The local lab uses SQLite to persist vectors and metadata and computes exact cosine similarity over the rows allowed by trusted tenant and classification filters. It also implements a small BM25-style lexical ranker and reciprocal-rank fusion (RRF) so you can compare dense, lexical, and hybrid paths. This makes the mechanics inspectable and runnable without an API key. Its deterministic feature-hashing embedder is **not** a semantic embedding model, and exact scanning is not a production-scale approximate-nearest-neighbor index. Replace it with a real embedding model and an appropriate vector-capable database when scale and relevance evaluations justify it. A database might combine vector search with full-text search, metadata indexes, tenant policy, backups, deletion workflows, and index-version management.

One concrete production-style option is PostgreSQL with [pgvector](https://github.com/pgvector/pgvector). The sketch below shows the important shape; use the selected embedding model's actual dimension and your database driver's vector adaptation:

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE document_chunks (
    chunk_id text PRIMARY KEY,
    tenant_id text NOT NULL,
    classification text NOT NULL,
    status text NOT NULL,
    source_id text NOT NULL,
    source_version text NOT NULL,
    content text NOT NULL,
    embedding vector(1536) NOT NULL
);

CREATE INDEX document_chunks_scope ON document_chunks (tenant_id, status, classification);
CREATE INDEX document_chunks_embedding ON document_chunks
    USING hnsw (embedding vector_cosine_ops);

SELECT chunk_id, source_id, source_version, content,
       embedding <=> $2::vector AS cosine_distance
FROM document_chunks
WHERE tenant_id = $1
  AND status = 'active'
  AND classification = ANY($3)
ORDER BY embedding <=> $2::vector
LIMIT 10;
```

`$1` and `$3` come from trusted authorization state, never agent-generated arguments. Add database row-level security or stronger tenant isolation if required by the threat model. pgvector performs exact search by default; HNSW and IVFFlat trade some recall for speed. With approximate indexes, selective SQL filters can leave too few candidates because filtering may happen after the index scan; benchmark filtered recall and latency, and tune iterative scans or choose a scoped/exact plan where needed. See the [pgvector indexing and filtering guidance](https://github.com/pgvector/pgvector#filtering).

Refresh lifecycle:

- Re-ingest changed source versions idempotently; mark or remove superseded chunks according to retention policy.
- When the embedding model or chunking logic changes, version it and re-embed/reindex the corpus consistently. Do not compare vectors from incompatible spaces.
- Propagate source deletion and access revocation into derived indexes and caches. Record completion and retry failures.
- Keep a small canary corpus and query set; compare new parser/chunker/embedder versions before a full rebuild.
- Batch offline embedding calls where the provider supports them. Use content hashes to skip unchanged inputs and avoid duplicate embedding work.

## 4. Query and assemble evidence

Start with the cheapest effective query path and add complexity only when errors show a need:

1. Apply hard tenant, classification, status, version/effective-date, and ACL filters from trusted runtime state.
2. Retrieve candidates using lexical search (for exact terms and identifiers), dense vector similarity (for paraphrases), or both.
3. For hybrid retrieval, merge ranks with a measured method such as reciprocal-rank fusion; normalize scores only when there is a meaningful calibration set.
4. Optionally rerank a bounded candidate set with a stronger model or cross-encoder. Measure its quality lift against added latency/cost.
5. Deduplicate overlapping chunks, cap results and total evidence tokens, and preserve source/page/section/version citations.
6. If evidence is weak or conflicting, retrieve more, ask a question, or abstain. Do not make the model fill evidence gaps from plausible-sounding guesses.

Useful modern retrieval experiments include query rewriting for ambiguous user language, contextualizing chunks with concise parent headings before embedding, BM25+dense hybrid retrieval, parent-child retrieval, and reranking. The demo implements RRF over its two ranked lists; the resulting RRF score is a rank-fusion score, not a cosine similarity and not comparable to BM25 or cosine values. Anthropic reported gains from contextual embeddings plus contextual BM25 and reranking in its [Contextual Retrieval article](https://www.anthropic.com/engineering/contextual-retrieval); treat those reported gains as a hypothesis to reproduce on your own corpus, not a promised result. For small corpora, direct lookup or just-in-time reads may remain better than embeddings; see [Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents).

## 5. Evaluate the retrieval system separately

Use human-checked query → relevant source/chunk labels. Keep training/tuning queries separate from a holdout set and include paraphrases, exact identifiers, multilingual inputs if needed, no-answer cases, stale versions, conflicting documents, cross-tenant attempts, and injection-bearing content.

| Question | Example metric or review |
|---|---|
| Did the relevant source appear? | Recall@k, Hit@k, answerable-query coverage |
| Was it near the top? | MRR, nDCG@k, rank of first relevant result |
| Did irrelevant chunks crowd the prompt? | Precision@k, duplicate rate, evidence token count |
| Did permissions and freshness hold? | Unauthorized-result count (must be zero), stale-source rate |
| Did the answer use the evidence correctly? | Claim-to-source support, faithfulness review, citation precision |
| Was the whole system worth the cost? | End-to-end success, p50/p95 latency, embedding/rerank/model cost per successful task |

Inspect the retrieved chunks and complete agent trace, not only the final response. Break metrics down by document type and query class so a strong average does not hide failed tables, OCR, or tenant filters.

## Hands-on: local ingestion and vector query

The [sandbox lab](agentic-ai-sandbox/README.md) includes `knowledge/` Markdown sources, a manifest, a preprocessing/chunking pipeline, a SQLite vector store, and an offline feature-hashing embedder. The manifest loader also accepts static HTML and synthetic `.docx`/`.pdf` fixtures, preserving basic heading/table/page provenance. PDF support is optional: install `requirements-pdf.txt` and run `run_pdf_checks.py`. A confidence-gated OCR adapter contract is implemented, but no real OCR engine, scanned-document corpus, `.pptx`, or `.xlsx` parser is included. Real hostile documents should be parsed in a resource-limited isolated worker.

```sh
cd agentic-ai-sandbox
python3 run_rag_demo.py
python3 run_rag_demo.py --query "Are delivery dates promised?" --top-k 2
python3 run_rag_demo.py --tenant another-tenant
python3 run_rag_checks.py
python3 run_embedding_checks.py
python3 -m pip install -r requirements-pdf.txt
python3 run_pdf_checks.py
python3 run_rag_evals.py --retriever dense
python3 run_rag_evals.py --retriever lexical
python3 run_rag_evals.py --retriever hybrid
python3 run_rag_evals.py --retriever lexical --output rag-eval.json
python3 run_rag_evals.py --dataset evals/rag_scenarios.json --retriever hybrid
python3 run_rag_evals.py --manifest knowledge/advanced/manifest.json --dataset evals/advanced_dev_scenarios.json --retriever dense --embedding-provider voyage
```

The first demo run creates `rag-demo.sqlite` in the current directory. The demo derives a stable chunk ID, preserves heading path and policy version, embeds the chunk, stores vector plus metadata, and runs tenant-scoped cosine search. The sample classifier is synthetic. The `another-tenant` query returns no evidence because its trusted scope does not match. `run_rag_checks.py` exercises the local storage and access contract. `run_rag_evals.py` defaults to the holdout set and supports `dense`, `lexical`, or `hybrid`; the development set is selectable by path. Its optional JSON output includes corpus/dataset fingerprints and retrieved chunk IDs with source metadata for trace review. A `GAP` and nonzero exit code show retrieval misses or false positives, not a code crash.

On `rag-retrieval-holdout-v2` (ten synthetic queries, two short policy documents, and a feature-hashing placeholder), dense scored 60% overall scenario pass, 50% positive-source coverage, and 75% no-answer accuracy; BM25-style lexical scored 100% on scenario pass and positive-source coverage, 100% no-answer accuracy, and 89% unique-source precision; hybrid RRF scored 90% scenario pass, 100% positive-source coverage, 75% no-answer accuracy, and 89% unique-source precision. This demonstrates threshold and retrieval trade-offs on this tiny authored set only. It does not establish performance on real data or evaluate a semantic embedding model. In particular, the placeholder dense path returned a false positive for an unrelated capital-city query, and RRF carried that false positive through.

### Expanded corpus evaluation

To make retrieval review more representative, the sandbox now also includes 15 manifest entries over multiple support topics, one superseded policy version, three classifications, and two tenants. The advanced development and holdout sets each have 20 queries. They cover paraphrase, multi-source retrieval, current-version requirements, hard negatives, no-answer behavior, and access-scope checks. `run_rag_evals.py --manifest knowledge/advanced/manifest.json` selects this corpus. The evaluator grades expected source versions and records forbidden-source leakage separately from relevance false positives.

On the `agentic-rag-advanced-dev-v1` tuning split, dense / lexical / hybrid produced scenario pass rates 65% / 90% / 90%, positive-source coverage 67% / 93% / 100%, Hit@1 40% / 80% / 67%, and no-answer accuracy 0% / 50% / 0%. Lexical misses the damaged-in-transit case and returns a result for the investment hard negative. Hybrid retrieves all required positive sources but does not abstain on negative cases. Tune on this development set, preserve the current holdout as regression, and create a new holdout before making model or threshold claims.

The separate `agentic-rag-advanced-holdout-v1` comparison is:

| Metric | Dense feature hash | BM25-style lexical | Hybrid RRF |
|---|---:|---:|---:|
| Scenario pass | 50% | 95% | 90% |
| Required positive-source coverage | 50% | 100% | 100% |
| Hit@1 | 25% | 81% | 69% |
| Recall@5 sources | 50% | 100% | 100% |
| MRR | .339 | .877 | .804 |
| No-answer accuracy | 0% | 50% | 0% |
| Unique-source precision | 31% | 34% | 31% |
| Forbidden-source leaks | 0/2 | 0/2 | 0/2 |

The lexical baseline ranked every required source in this authored holdout but returned irrelevant sources and failed one hard-negative query. Dense and hybrid retrieval failed to abstain on the two no-answer cases; hybrid inherited lexical and dense candidates. The authorization cases showed no forbidden-source leakage under the tested filters, but two cases are far too few to establish tenant isolation. The runnable Voyage adapter enables the next experiment, but a provider call, representative corpus, and independently labeled holdout are still required. Improve negative-query threshold calibration and compare answer grounding as well as retrieval metrics. The feature-hashing dense result remains a plumbing diagnostic, not semantic retrieval evidence.

`advanced_holdout_v1` has now been inspected and should be treated as a regression set, not an untouched benchmark for future tuning. Preserve a new holdout version for the next retrieval-model or threshold decision.

Explore the code in [rag_pipeline.py](agentic-ai-sandbox/rag_pipeline.py). Then extend the exercise:

1. Add a long document and compare 40/8, 90/18, and structure-aware chunking (maximum words / overlap words in this lab). Inspect boundaries and duplicate retrieval.
2. Add one superseded version and confirm that only the active version is returned.
3. Add one internal-only and one confidential source; vary the trusted allowlist and verify each result set.
4. Replace `HashingEmbedder` with a real embedding adapter and re-run a labeled query set. Keep the same metadata and filters.
5. Compare the included BM25-style lexical and RRF hybrid paths against the dense placeholder. Explain the holdout's false positive and missed paraphrases. Add a real semantic embedder or reranker only when a new labeled evaluation can show the quality lift against added latency and cost.
6. Add an adversarial instruction inside a document and verify it is treated as quoted data, never as system policy.

## Current optimization techniques for agentic systems

Optimize measured end-to-end quality and cost per successful task, not tokens in isolation. Preserve application-side authorization, budgets, and approvals as fixed invariants.

### Prompt caching (Anthropic + Python)

Prompt caching reuses an identical prompt prefix. Anthropic builds that prefix in `tools → system → messages` order. Put stable tool schemas and instructions first, then dynamic evidence and the current request. Mark the last stable block; edits before it invalidate that cache point and later points. The API supports up to four explicit breakpoints, while its prefix lookback covers the most recent 20 block positions. Use multiple points only when sections change at different rates or long histories would push reuse out of the lookback window. Keep serialization and ordering deterministic and remove timestamps/request IDs from reusable blocks. Anthropic offers 5-minute and 1-hour ephemeral TTLs; verify current model minimums, pricing, platforms, and SDK behavior in the [Prompt Caching guide](https://platform.claude.com/docs/en/build-with-claude/prompt-caching).

```python
response = client.messages.create(
    model=model,
    max_tokens=800,
    # Stable tools + stable system prefix are cacheable. Keep user-specific data below.
    system=[{
        "type": "text",
        "text": STABLE_SYSTEM_POLICY,
        "cache_control": {"type": "ephemeral"},
    }],
    tools=STABLE_TOOL_SCHEMAS,
    messages=[{"role": "user", "content": request_and_fresh_evidence}],
)

usage = response.usage
cache_reads = getattr(usage, "cache_read_input_tokens", 0)
cache_writes = getattr(usage, "cache_creation_input_tokens", 0)
```

The system marker above caches the prefix through the system block, including preceding tools. A short prompt may not satisfy the model-specific minimum (which currently varies by model from hundreds to several thousand tokens); marked prompts below the minimum are processed without caching. Check both `cache_creation_input_tokens` and `cache_read_input_tokens`. Anthropic's standard pricing uses a 1.25× base-input multiplier for 5-minute writes and 2× for 1-hour writes; cache reads are usually 0.1× but have model-specific exceptions. The TTL clock starts when the request begins, so generation time consumes part of the cache lifetime. For total input, add `input_tokens + cache_creation_input_tokens + cache_read_input_tokens`. Compare actual reuse, latency, and the applicable rate card rather than assuming caching saves money. Keep tenant-specific/private evidence out of shared or broadly reused cache prefixes unless the provider and your data-handling design explicitly support that scope. These mechanics and prices can change; check the current provider guide before an experiment.

The sandbox's `AnthropicPlanner` supports opt-in stable-prefix caching through `enable_prompt_caching=True`; `run_live_evals.py` exposes `--prompt-caching` and `--prompt-cache-ttl`. Fake-client checks verify the request shape and metric capture without making a request. The current support prompt/tool set is intentionally small and may be below the active model's cache minimum. A live comparison requires repeated requests and may incur charges; the runner keeps caching off by default.

### Other high-value optimizations

- **Just-in-time context:** pass identifiers and retrieve the needed record only when required. Avoid stuffing the full corpus and full run history into every turn.
- **Tool discovery / deferred loading:** Anthropic's server-side [tool search](https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool) can keep specialized schemas out of the model's initial context until discovered. You still send every full schema in the request's `tools` array; deferral reduces what enters the active model context, not the request payload. Discovery adds a planning step and a tool-selection failure mode. Anthropic recommends it for larger catalogs (for example, ten or more tools or definitions consuming over 10k tokens); compare total input tokens, discovery errors, selection quality, latency, and cost. Keep common tools immediately available.
- **Bounded context compaction:** keep durable state outside the model. Compact older conversation history when needed, preserve recent critical turns, and reload authoritative records before consequential actions. Anthropic offers on-demand and token-threshold compaction, both currently beta with separate compatibility constraints; its [compaction overview](https://platform.claude.com/docs/en/build-with-claude/compaction) explains the trade-offs. Treat generated summaries as lossy, non-authoritative state.
- **Choose compaction or context editing deliberately:** compaction summarizes old turns; server-side context editing selectively clears old tool results or thinking blocks. Context editing currently requires its beta header and has different cache effects: clearing tool results invalidates later cache prefixes. The API keeps the client's original conversation history unmodified, so preserve your durable journal and inspect `context_management.applied_edits`. Check current [context-editing](https://platform.claude.com/docs/en/build-with-claude/context-editing) and compaction compatibility before adoption; never treat a summary as authoritative state.
- **Cache embeddings and retrieval carefully:** cache document embeddings by normalized-content hash plus embedding model/version. Cache query results only with query normalization, tenant/ACL scope, corpus/index version, and freshness in the key; invalidate on permission or source changes.
- **Batch independent work:** batch document embeddings and independent read-only tool calls. Parallelism can reduce wall time while preserving total token/API spend; do not parallelize dependent writes or bypass idempotency, approval, or rate limits.
- **Route by task difficulty:** use deterministic code for validation and known branches, a smaller/cheaper model for classification or extraction only if it meets the eval threshold, and a stronger model for genuinely difficult reasoning. Measure routing mistakes and fallback cost.
- **Trim tool outputs:** return only fields needed for the next decision, cap rows and characters, and keep large payloads in storage with handles for follow-up reads.
- **Use structured outputs and schemas:** validate tool arguments and final machine-readable results at application boundaries; schema conformance does not establish authorization or factual accuracy.
- **Stop loops early:** bound model turns, tool calls, output tokens, retries, deadline, and total spend. Use deterministic calculations and direct APIs for work that does not need model judgment.
- **Compare safe cache keys:** prompt and semantic caches can cross users or tenants if keyed poorly. Bind access scope, policy/index version, model version, and relevant personalization into keys; never rely on a cache hit as an authorization check.

### Senior optimization discipline

Treat optimization as controlled experimentation. Start with quality/cost/latency by task class, then change one variable at a time on the same versioned cases. Include tail metrics and safety guardrails, not only average tokens. Use cache diagnostics when expected prefix reuse is absent; deterministic serialization/order and recent repeated prefixes matter. Prompt caching reuses a prefix; it does not remove tokens from the logical prompt or make mutable data safe to share.

Anthropic's deferred tool definitions are excluded from the rendered model prefix until discovered; the full definitions are still sent to the API, and discovered definitions are inserted into the conversation. Tool search therefore reduces upfront context and preserves the existing prefix cache, but does not shrink the request body. A deferred tool cannot carry its own `cache_control`; cache stable, immediately loaded tools instead. Verify current API/model compatibility and compare discovery accuracy and total token use. See [Tool search](https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool) and [Tool use with prompt caching](https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-use-with-prompt-caching).

For cache or compaction experiments, include isolation tests: tenant crossing, policy/index version change, source deletion, stale authorization, changed tool schema, and provider cache miss. Revalidate authorization at retrieval time. Measure quality, retrieval support, cache reads/writes, tokens, provider/tool calls, p50/p95/p99, errors, and estimated cost per successful task. Roll back if savings shift risk into stale evidence, missed tools, unsupported answers, or tail latency.

For retrieval, compare chunk size/overlap, parser version, lexical/dense/hybrid candidates, reranker depth, context budget, and citations as separate factors. Tune on development data, report the untouched holdout once, and preserve a fresh challenge set before release. A good retrieval score does not guarantee grounded answers, and a lower token count does not mean better retrieval.


### Optimization scorecard

For each change, compare the same versioned cases and trace graders before and after. Track task success, policy/security failures, retrieval Recall@k and citation support, model calls, prompt/cache-read/cache-write tokens, tool calls, embedding/reranking calls, p50/p95 latency, and estimated cost per successful task. Reject an optimization that saves average tokens but increases critical errors, stale evidence, unauthorized disclosure, or tail latency beyond the task's target.

## Mastery checkpoint

Draw the source-to-answer pipeline for one real unstructured dataset. For every field, identify its source of truth, tenant/ACL scope, sensitivity, retention, version, and deletion path. Pick one chunk strategy and one retrieval baseline, define a labeled holdout set, and set release thresholds. Then choose two optimizations—one data/retrieval optimization and one agent/runtime optimization—and state what evidence would make you keep or revert each.

## References

- [Anthropic embeddings guide](https://platform.claude.com/docs/en/build-with-claude/embeddings)
- [Anthropic Prompt Caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)
- [Anthropic Contextual Retrieval](https://www.anthropic.com/engineering/contextual-retrieval)
- [Anthropic Effective Context Engineering for AI Agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- [Anthropic Tool Search Tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool)
- [Anthropic Compaction](https://platform.claude.com/docs/en/build-with-claude/compaction)
