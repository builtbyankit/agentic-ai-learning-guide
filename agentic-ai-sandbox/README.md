# Agentic AI sandbox: support-resolution system

This is the hands-on build for the mastery roadmap. The deterministic harness uses Python’s standard library and synthetic data. A live Anthropic adapter is included separately.

## Run the evaluation scenarios

From this folder, run:

```sh
python3 run_evals.py
```

The latest run (2026-10-06) passed **9/9 scenarios**. They cover policy grounding, authorized and unauthorized order lookup, refund proposal review, idempotency, malformed-argument recovery, data minimization, and the run budget. A passing result means the harness and tool boundary satisfy these scripted scenarios.

Check the provider message/tool-result round trip without making an API request:

```sh
python3 run_adapter_checks.py
```

The adapter checks passed **3/3** locally. They use a fake Anthropic client and cover the tool round trip, safe handling of multiple requested tools, and optional prompt-cache request/usage metrics.

Check durable restart and idempotency behavior without making an API request:

```sh
python3 run_durability_checks.py
```

The five recovery checks use temporary SQLite files and clean them up after the run.

Check the human approval and retry-safe outbox path without making an API request:

```sh
python3 run_approval_checks.py
```

The six checks cover separation of model authority from operator approval, exact-proposal binding, duplicate approval, leased delivery, expiry, rejection, and retry after simulated provider success. The payment provider is a local SQLite-backed mock; no real refund is issued.

Check adversarial input handling and deterministic security boundaries without making an API request:

```sh
python3 run_security_checks.py
```

The seven check groups cover capability separation, request and argument bounds, tenant denial behavior, prompt-injection resistance through runtime controls and data minimization, proposal task/expiry checks, and fail-closed tool dispatch.

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

The new RAG lab uses only the Python standard library and synthetic Markdown policies. It normalizes and parses heading structure, chunks with overlap, creates stable chunk IDs and source hashes, writes vectors plus metadata to SQLite, and supports dense, BM25-style lexical, and reciprocal-rank-fused hybrid retrieval. Every path applies the requested tenant and classification filters:

```sh
python3 run_rag_demo.py
python3 run_rag_demo.py --query "Are delivery dates promised?" --top-k 2
python3 run_rag_demo.py --tenant another-tenant
```

The demo creates `rag-demo.sqlite` in the current directory. The default `HashingEmbedder` is deterministic feature hashing for demonstrating the plumbing; it is not a semantic embedding model. The SQLite store scans eligible rows for exact cosine similarity, so this is not an ANN production database. See [Module 11](../agentic-ai-module-11-data-rag-and-optimization.md) for preprocessing guidance, chunking trade-offs, retrieval evaluation, production embedding/vector-store choices, and current optimization techniques.

Run the storage/access checks and compare the retrievers on the labeled development and holdout sets:

```sh
python3 run_rag_checks.py
python3 run_rag_evals.py --retriever dense
python3 run_rag_evals.py --retriever lexical
python3 run_rag_evals.py --retriever hybrid
python3 run_rag_evals.py --retriever lexical --output rag-eval.json
python3 run_rag_evals.py --dataset evals/rag_scenarios.json --retriever hybrid
```

The default evaluator uses the holdout dataset with the dense placeholder and currently reports known relevance gaps (nonzero exit). On the authored 10-query set, the lexical baseline reached 100% required-source coverage and 100% empty-query accuracy, while hybrid RRF reached 90% and 75%, respectively. See Module 11 for all metrics and limits; these are instructional results on two short synthetic documents, not production evidence.

Check repeated-trial aggregation without making an API request:

```sh
python3 run_eval_runner_checks.py
```

These checks use the normal grader with scripted decisions and verify unique task IDs, per-case pass-rate aggregation, failure counts, and metric sample counts.

## Run against Anthropic

Install the SDK and configure credentials and a model that your account can use:

```sh
python3 -m pip install -r requirements.txt
export ANTHROPIC_API_KEY="your-key"
export ANTHROPIC_MODEL="your-enabled-model"
python3 run_live_evals.py
```

The live runner makes real API requests and may incur usage charges. It reads the ten versioned cases in [evals/live_scenarios.json](evals/live_scenarios.json) (`support-agent-live-v4`), then reports the final answer, tools used, pending-review state, payment-side-effect count, regular and cache token usage, and elapsed model-call time. Use `--trials 3` to run each case three times; the allowed range is 1–10. To test Anthropic prompt caching, pass `--prompt-caching` (and optionally `--prompt-cache-ttl 1h` after checking current pricing). The cache marker is off by default. This small sandbox prefix may be below the active model's minimum cacheable length; verify nonzero cache read/write metrics before claiming a benefit. The report summarizes per-case pass rates, failure frequencies, and average metrics with sample counts, and records the configured model plus system-prompt, tool-schema, and policy-catalog fingerprints. Repeated trials help reveal variability but do not establish production reliability or a confidence interval. The runner does not estimate money cost because model rates vary. Add `--output eval-results.json` to save a JSON report; reports contain answers and traces, so store them securely. No live API evaluation has been run from this workspace.

Run the fixed-workflow baseline on exactly the same ten cases:

```sh
python3 run_workflow_baseline.py
```

The latest local run (2026-10-06) passed **10/10**, using twelve tool calls and zero model calls. This shows the hand-built workflow covers the current small dataset; it does not show that a keyword router covers the full range of real support requests. Run the live agent suite against the same dataset before comparing quality and operating cost.

## What the prototype demonstrates

- A model-facing planner interface is separate from the application-owned tool gateway.
- The authenticated subject and task ID come from trusted runtime context, not the planner’s arguments.
- Order access is checked by the data service.
- The planner can prepare a refund proposal and request human review; it cannot issue a refund.
- A small deterministic workflow baseline can be run on the same evaluation cases.
- Review requests are idempotent for a task and proposal.
- SQLite run journaling supports restart and replay in a single-worker teaching setup.
- An operator approval and an outbox action are committed together; a mock provider uses a stable idempotency key during retries.
- The loop has explicit turn and tool-call limits, and records a trace.

## What it does not demonstrate yet

`ScriptedPlanner` supplies predetermined choices so the scenarios are deterministic. It exercises the orchestration and authorization envelope, but it does not measure model reasoning. `run_live_evals.py` can measure a small amount of actual model behavior, including ownership override and private-note extraction requests, but it has not been run from this workspace. The private note is filtered before model context, so this checks data minimization rather than the model's response to a poisoned retrieved document. This narrow set is not broad prompt-injection assurance. The live runner captures latency and tokens, but not currency cost.

`AnthropicPlanner` implements the provider adapter using the Messages API. The application keeps tool execution in `ToolRuntime`, rechecks permissions, and applies its own turn and tool budgets. The adapter asks for one tool per response; if Claude returns several tool calls in one response, the run hands off without executing them. This keeps the first implementation serial and bounded; a later design can add safe batch handling if measured tasks benefit from it.

The code is a teaching prototype, not a production service. The application can use SQLite for durable runs and approval/outbox state, but the demonstration assumes one active worker and does not implement worker leases across the run journal, an identity provider, a real payment integration, production-grade trace redaction, or operational recovery workflows. The mock payment provider has its own local idempotency ledger; a real provider must offer equivalent idempotency or a reconciliation strategy. Review traces before storing them in a real service.

## Official implementation references

- [Anthropic tool use overview](https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview)
- [Anthropic tool-call handling](https://platform.claude.com/docs/en/agents-and-tools/tool-use/handle-tool-calls)
- [Anthropic Python SDK example](https://github.com/anthropics/anthropic-sdk-python/blob/main/examples/tools.py)

## Senior engineer / architect completion path

Use [Module 12 — Senior AI Engineer and Architect Practicum](../agentic-ai-module-12-senior-architecture-practicum.md) after Modules 1–11. It provides the architecture-dossier structure, versioned contract checklist, reliability and security review, evaluation gates, cost model, rollout stages, and readiness rubric. For each claim in the dossier, label it as implemented and measured, designed but unverified, or an assumption. The sandbox is a learning prototype; it does not establish production readiness.
