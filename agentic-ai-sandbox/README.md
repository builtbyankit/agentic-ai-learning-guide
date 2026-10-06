# Agentic AI sandbox: support-resolution system

This is the hands-on build for the mastery roadmap. The deterministic harness uses Python’s standard library and synthetic data. A live Anthropic adapter is included separately.

## Run the evaluation scenarios

From this folder, run:

```sh
python3 run_evals.py
```

The latest run (2026-10-07) passed **9/9 scenarios**. They cover policy grounding, authorized and unauthorized order lookup, refund proposal review, idempotency, malformed-argument recovery, data minimization, and the run budget. A passing result means the harness and tool boundary satisfy these scripted scenarios.

Check the provider message/tool-result round trip without making an API request:

```sh
python3 run_adapter_checks.py
```

The adapter checks passed **3/3** locally. They use a fake Anthropic client and cover the tool round trip, safe handling of multiple requested tools, and optional prompt-cache request/usage metrics.

Check durable restart and idempotency behavior without making an API request:

```sh
python3 run_durability_checks.py
```

The thirteen recovery/coordination checks use temporary SQLite files and clean them up after the run. They include an earlier-schema migration, a two-thread claim race, lease takeover, stale-worker fencing, state-version compare-and-swap, heartbeat renewal during a slow tool call, and recovery after heartbeat failure.

Check the human approval and retry-safe outbox path without making an API request:

```sh
python3 run_approval_checks.py
```

The nine checks cover the shared-database invariant, separation of model authority from operator approval, exact-proposal binding, duplicate approval, leased delivery, expiry, rejection, retry after simulated provider success, and rejection of stale policy/order facts. The current synthetic authority state, proposal/review records, approval, and outbox share one SQLite database; a race check verifies policy updates serialize against approval. The payment provider is a local SQLite-backed mock; no real refund is issued.

Check adversarial input handling and deterministic security boundaries without making an API request:

```sh
python3 run_security_checks.py
```

The eleven check groups cover capability separation, request and argument bounds, tenant denial behavior, data minimization, subject revocation, identity-provider failure, proposal task/expiry checks, stale policy/order rejection, fail-closed tool dispatch, and a simulated planner following hostile retrieved text that must not bypass runtime authorization. This is not a live-model prompt-injection evaluation.

Check policy retrieval ranking, freshness, and output minimization without an API request:

```sh
python3 run_retrieval_checks.py
```

The eight checks cover catalog fingerprinting, paraphrased damage and delivery queries, active-policy ranking, archived-policy exclusion, bounded excerpts, source provenance, irrelevant queries, and an ingestion-only instruction that must not leave the catalog.

Measure retrieval quality on a separate versioned query set:

```sh
python3 run_retrieval_evals.py
```

The `policy-retrieval-v1` set has eleven synthetic paraphrase, multi-policy, stale-policy, and no-result queries. It reports Hit@1, Recall@2, reciprocal rank, precision, exact coverage, and no-result accuracy. These scores describe only this small authored set.

## Run the unstructured-data and vector retrieval lab

The RAG lab uses synthetic Markdown policies and supports static HTML plus bounded `.docx` extraction. Optional PDF support uses `pypdf` for selectable text and accepts an injected OCR adapter for pages with no selectable text. It preserves page markers, records OCR confidence in the page heading, and rejects low-confidence OCR, encrypted, malformed, or over-limit input. No PDF renderer or OCR engine is bundled; mixed pages that contain selectable text plus scanned images are not OCRed. Install the optional parser dependency and run its focused fixture checks with:

```sh
python3 -m pip install -r requirements-pdf.txt
python3 run_pdf_checks.py
```

HTML extraction preserves headings/tables and omits common script/style/navigation/footer boilerplate. The bounded DOCX parser maps common heading styles, turns directly marked list paragraphs into bullets, keeps basic table rows and page-break markers, rejects DTD/entity declarations, and enforces package size/member limits. It does not resolve list numbering, extract images/OCR, headers/footers, slides, or spreadsheets. The lab normalizes text, chunks with overlap, creates stable chunk IDs and source hashes, writes vectors plus metadata to SQLite, and supports dense, BM25-style lexical, and reciprocal-rank-fused hybrid retrieval. Every retrieval path applies trusted tenant and classification filters:

```sh
python3 run_rag_demo.py
python3 run_rag_demo.py --query "Are delivery dates promised?" --top-k 2
python3 run_rag_demo.py --tenant another-tenant
```

The demo creates `rag-demo.sqlite` in the current directory. The default `HashingEmbedder` is deterministic feature hashing for demonstrating the plumbing; it is not a semantic embedding model. The SQLite store scans eligible rows for exact cosine similarity, so this is not an ANN production database. `run_rag_checks.py` exercises DOCX structure preservation, PII redaction, DTD rejection, HTML cleanup, idempotency, provenance, and access filters. `run_pdf_checks.py` exercises synthetic selectable-text pages and a fake OCR adapter through confidence checks, redaction, chunking, indexing, and retrieval, plus malformed and over-limit rejection. This verifies the adapter contract only; it does not execute OCR on an image. `run_embedding_checks.py` uses a fake transport to check batching, query/document modes, response validation, error redaction, and atomic ingestion failure without an API key or network access. Parser fixtures are synthetic; parse real uploaded files inside a resource-limited isolated worker. See [Module 11](../agentic-ai-module-11-data-rag-and-optimization.md) for preprocessing guidance, chunking trade-offs, retrieval evaluation, production embedding/vector-store choices, and current optimization techniques.

Run the storage/access checks and compare the retrievers on the labeled development and holdout sets:

```sh
python3 run_rag_checks.py
python3 run_embedding_checks.py
python3 run_rag_evals.py --retriever dense
python3 run_rag_evals.py --retriever lexical
python3 run_rag_evals.py --retriever hybrid
python3 run_rag_evals.py --retriever lexical --output rag-eval.json
python3 run_rag_evals.py --dataset evals/rag_scenarios.json --retriever hybrid
python3 run_rag_evals.py --manifest knowledge/advanced/manifest.json --dataset evals/advanced_dev_scenarios.json --retriever lexical
python3 run_rag_evals.py --manifest knowledge/advanced/manifest.json --dataset evals/advanced_holdout_scenarios.json --retriever lexical
python3 run_rag_evals.py --manifest knowledge/advanced/manifest.json --dataset evals/advanced_holdout_scenarios.json --retriever hybrid
```

To compare a real embedding provider on the development set, configure `VOYAGE_API_KEY` through your local secret manager or shell environment, then explicitly opt into Voyage:

```sh
python3 run_rag_evals.py --manifest knowledge/advanced/manifest.json --dataset evals/advanced_dev_scenarios.json --retriever dense --embedding-provider voyage --embedding-model voyage-4 --output voyage-dev.json
python3 run_rag_evals.py --manifest knowledge/advanced/manifest.json --dataset evals/advanced_dev_scenarios.json --retriever hybrid --embedding-provider voyage --embedding-model voyage-4 --output voyage-hybrid-dev.json
```

Anthropic provides the agent/model adapter in this curriculum; its current documentation points to a separate embeddings provider. The optional `VoyageEmbedder` uses Python's standard library, sends separate `document` and `query` input types, batches requests, skips unchanged document chunks, and reports request/token counts. The default endpoint is Voyage's native API; if using a MongoDB Atlas model API key, set `VOYAGE_API_URL=https://ai.mongodb.com/v1/embeddings` (or pass `--embedding-endpoint`) and follow region-specific endpoint guidance. The default embedder remains offline hashing. Voyage calls can incur charges and transmit the supplied text to that provider; check current provider terms and model availability first. No live embedding call has been run in this repository yet. Do not tune on the holdout; choose settings on development data and preserve a fresh independent holdout.

The default evaluator uses the small holdout dataset and the dense placeholder, and reports known relevance gaps (nonzero exit). Its 10 queries over two short documents are retained as the minimal plumbing example. On this set, lexical retrieval passes all scenarios with 100% positive-source coverage and no-answer accuracy; hybrid passes 90% of scenarios with 100% source coverage and 75% no-answer accuracy. The expanded benchmark uses 15 manifest entries (including one superseded version) and separate 20-query development and holdout sets. It tests paraphrases, multi-source questions, stale versions, no-answer hard negatives, classification filters, and tenant isolation. The evaluator accepts `--manifest` to point at a different synthetic or sanitized corpus.

The advanced holdout currently reports, for dense feature hashing / lexical / hybrid feature hashing respectively: scenario pass 50% / 95% / 90%; required positive-source coverage 50% / 100% / 100%; no-answer accuracy 0% / 50% / 0%; and authorization leaks 0/2 for each. These authored synthetic results are diagnostic, not generalization or production evidence. Lexical retrieval currently fails the investment-return hard negative; dense and hybrid return too much irrelevant material and fail both no-answer examples. A Voyage adapter is available for explicit live development-set experiments, but it has not been called and these metrics do not evaluate semantic embeddings. Use the separate `authorization leaks` metric to distinguish forbidden-source disclosure from ordinary relevance false positives. See [Module 11](../agentic-ai-module-11-data-rag-and-optimization.md) and the [evaluation data guide](evals/README.md) for limitations and interpretation.

On the advanced development set, dense / lexical / hybrid scenario pass was 65% / 90% / 90%; positive-source coverage 67% / 93% / 100%; Hit@1 40% / 80% / 67%; and no-answer accuracy 0% / 50% / 0%. Lexical misses one damage case and retrieves the investment hard negative. Hybrid finds every positive source but fails to abstain. Use this split for tuning; do not use it to claim generalization.

Check repeated-trial aggregation without making an API request:

```sh
python3 run_eval_runner_checks.py
python3 run_cost_model_checks.py
```

`run_eval_runner_checks.py` uses the normal grader with scripted decisions to verify unique task IDs, read-only eligibility/authorization, exact tool-argument grading, Wilson interval and per-case aggregation, failure counts, and metric sample counts. `run_cost_model_checks.py` validates explicit rate cards, TTL-specific pricing, cost coverage, and unavailable estimates without provider calls.

## Run against Anthropic

Install the SDK and configure credentials and a model that your account can use:

```sh
python3 -m pip install -r requirements.txt
export ANTHROPIC_API_KEY="your-key"
export ANTHROPIC_MODEL="your-enabled-model"
python3 run_live_evals.py
```

The live runner makes real API requests and may incur usage charges. It reads the ten versioned cases in [evals/live_scenarios.json](evals/live_scenarios.json) (`support-agent-live-v4`), then reports the final answer, tools used, pending-review state, payment-side-effect count, regular and cache token usage, and elapsed model-call time. Use `--trials 3` to run each case three times; the allowed range is 1–10. To test Anthropic prompt caching, pass `--prompt-caching` (and optionally `--prompt-cache-ttl 1h` after checking current pricing). The cache marker is off by default. This small sandbox prefix may be below the active model's minimum cacheable length; verify nonzero cache read/write metrics before claiming a benefit. The report summarizes per-case pass rates, 95% Wilson intervals, failure frequencies, and average metrics with sample counts, and records the configured model plus system-prompt, tool-schema, and policy-catalog fingerprints. These intervals describe repeats on the selected suite and do not establish production reliability or generalization. Add `--rate-card ~/.config/agentic-ai/rate-card.json` to estimate model-token costs with current user-supplied rates; keep this file outside the repository if it contains commercial terms. The report excludes non-model charges. Without a rate card, the runner reports no currency estimate. Add `--output eval-results.json` to save a JSON report; reports contain answers and traces, so store them securely. No live API evaluation has been run from this workspace.

For the expanded architecture comparison, select [evals/live_scenarios_v5.json](evals/live_scenarios_v5.json) (`support-agent-live-v5`). It adds clarification, multiple orders, read-only refund eligibility, multiple policy topics, and an unsupported payment-ledger request. [V6](evals/live_scenarios_v6.json) preserves those cases and adds synthetic mid-run session revocation after a private order read. [V7](evals/live_scenarios_v7.json) preserves v6 and changes the return-policy version after refund proposal creation. Before queuing human review, the runtime checks that policy version, current eligibility, amount, and currency still match the proposal. A stale proposal fails closed and the workflow hands off; the scripted evaluator also catches a planner that claims review succeeded anyway. This agent-side check is in-process. The later operator approval transaction separately rechecks current policy/order terms in SQLite while writing approval and outbox rows atomically. That demonstrates serialization in one local database, not atomicity across production services. A production implementation should use an authoritative datastore transaction or versioned compare-and-swap at each consequential boundary. Reports include dataset path and SHA-256 plus pass rates by tag. The v4 dataset remains unchanged as a regression set.

Run the fixed-workflow baseline on either dataset. To reproduce the expanded comparison:

```sh
python3 run_workflow_baseline.py --dataset evals/live_scenarios_v5.json
python3 run_workflow_baseline.py --dataset evals/live_scenarios_v6.json
python3 run_workflow_baseline.py --dataset evals/live_scenarios_v7.json
python3 run_live_evals.py --dataset evals/live_scenarios_v7.json --trials 3 --output live-v7.json
# Add --rate-card ~/.config/agentic-ai/rate-card.json to estimate model-token charges from current rates.
```

The v4 baseline passes **10/10**, using twelve tool calls and zero model calls. The v5 baseline passes **12/15**; v6 passes **13/16**; v7 passes **14/17**, using twenty tool calls and zero model calls. The three remaining gaps are the two-order comparison, the two-policy-topic request, and explicit abstention on card-ledger status. These runs are synthetic architecture discriminators, not measures of live-agent performance. Run the live agent suite against the same v7 dataset before comparing quality, latency, and operating cost.

## What the prototype demonstrates

- A model-facing planner interface is separate from the application-owned tool gateway.
- The authenticated subject and task ID come from trusted runtime context, not the planner’s arguments.
- Order access is checked by the data service.
- The planner can prepare a refund proposal and request human review; it cannot issue a refund.
- Read-only refund eligibility is a separate tool from creating a proposal or requesting review.
- A small deterministic workflow baseline can be run on the same evaluation cases.
- Review requests are idempotent for a task and proposal.
- SQLite run journaling supports restart/replay, expiring worker leases, fencing tokens, and state-version compare-and-swap in a local teaching setup.
- An operator approval and an outbox action are committed together; a mock provider uses a stable idempotency key during retries.
- The loop has explicit turn and tool-call limits, and records a trace.

## What it does not demonstrate yet

`ScriptedPlanner` supplies predetermined choices so the scenarios are deterministic. It exercises the orchestration and authorization envelope, but it does not measure model reasoning. `run_live_evals.py` can measure a small amount of actual model behavior, including ownership override and private-note extraction requests, but it has not been run from this workspace. The private note is filtered before model context, so this checks data minimization rather than the model's response to a poisoned retrieved document. This narrow set is not broad prompt-injection assurance. The live runner can estimate model-token charges with an optional explicit rate card, but does not estimate tool, infrastructure, tax, or other provider costs.

`AnthropicPlanner` implements the provider adapter using the Messages API. The application keeps tool execution in `ToolRuntime`, rechecks permissions, and applies its own turn and tool budgets. The adapter asks for one tool per response; if Claude returns several tool calls in one response, the run hands off without executing them. This keeps the first implementation serial and bounded; a later design can add safe batch handling if measured tasks benefit from it.

The code is a teaching prototype, not a production service. The run journal uses SQLite transactions for local claims and rejects expired or stale journal writes. A background heartbeat renews the lease while calls are in flight and journal writes fail closed after heartbeat loss. A lease cannot revoke an external request already in flight, so consequential downstream writes still need idempotency or fencing and reconciliation. The prototype does not demonstrate multi-host database behavior, heartbeat behavior under provider/network failures, an identity provider, a real payment integration, production-grade trace redaction, or operational recovery workflows. The mock payment provider has its own local idempotency ledger; a real provider must offer equivalent idempotency or a reconciliation strategy. Review traces before storing them in a real service.

## Official implementation references

- [Anthropic tool use overview](https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview)
- [Anthropic tool-call handling](https://platform.claude.com/docs/en/agents-and-tools/tool-use/handle-tool-calls)
- [Anthropic Python SDK example](https://github.com/anthropics/anthropic-sdk-python/blob/main/examples/tools.py)

## Senior engineer / architect completion path

Use [Module 12 — Senior AI Engineer and Architect Practicum](../agentic-ai-module-12-senior-architecture-practicum.md) after Modules 1–11. It provides the architecture-dossier structure, versioned contract checklist, reliability and security review, evaluation gates, cost model, rollout stages, and readiness rubric. For each claim in the dossier, label it as implemented and measured, designed but unverified, or an assumption. The sandbox is a learning prototype; it does not establish production readiness.
