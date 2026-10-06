# Evaluation data

`live_scenarios.json` is a small, versioned starter dataset. Each scenario includes:

- A user request and an authenticated synthetic subject.
- Required answer phrases or one acceptable outcome phrase.
- Sensitive values that must not appear in the answer or tool trace.
- Tool calls that must or must not appear.
- Expected number of pending human-review requests.

Add a new case when a failure is found. Keep the task inputs synthetic, label the reason for the case, and preserve older cases as regressions. Before treating an answer phrase as a reliable semantic grader, review false positives and false negatives against human judgments.

This ten-case `support-agent-live-v4` dataset is not statistically sufficient to establish production reliability. It now includes paraphrased policy-retrieval cases and a private-note minimization case. It is a specification seed that should grow from product requirements, edge cases, red-team work, and sanitized production failures. The live runner accepts `--trials N` (1–10), assigns each attempt a distinct task ID, and aggregates per-case pass rates, failure frequencies, and mean model metrics. Repeats can reveal nondeterminism; the small sample and phrase-based graders do not support a production reliability claim or a meaningful confidence interval. A production evaluation should also use separate quality and regression suites, human calibration for subjective graders, and end-state checks for consequential actions. See Anthropic’s [agent evaluation guidance](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents).

Policy retrieval also has a separate eleven-query set in [retrieval_scenarios.json](retrieval_scenarios.json). `run_retrieval_evals.py` computes Hit@1, Recall@k, MRR, precision, exact coverage, and accuracy on queries whose expected result is empty. Its report includes the policy-catalog version and content hash. Review the labeled expected article IDs whenever the source catalog or ranking policy changes; a perfect score on this small synthetic set does not imply retrieval quality on a real policy corpus.

The minimal unstructured RAG lab has ten-query development and holdout sets in [rag_scenarios.json](rag_scenarios.json) and [rag_holdout_scenarios.json](rag_holdout_scenarios.json), over two short Markdown sources.

The larger offline lab uses [advanced_dev_scenarios.json](advanced_dev_scenarios.json) and [advanced_holdout_scenarios.json](advanced_holdout_scenarios.json) with the separate [advanced corpus manifest](../knowledge/advanced/manifest.json). It contains 20 queries per split and covers multiple policy topics, one superseded version, answerable and unanswerable paraphrases, multi-source queries, hard negatives, and tenant/classification filters. `expected_versions` requires a current source version on selected cases. `case_type: authorization` with `forbidden_source_ids` grades forbidden-source exposure separately from ordinary irrelevant retrieval; an unrelated accessible result can still fail relevance without being counted as an ACL leak.

The v1 holdout has been run and reviewed, so it is now a regression set. Create a fresh holdout before tuning retriever thresholds or choosing an embedding/reranker from these results.

`run_rag_evals.py` compares exact cosine over the demo feature hash, BM25-style lexical ranking, and reciprocal-rank-fused hybrid search. Reports fingerprint corpus metadata/content and the query dataset. They include source coverage, Hit@1, source Recall@k, MRR, unique-source precision, no-answer accuracy, authorization-isolation rate/leak count, embedding request/token counts, and retrieved source/version/chunk provenance. Use `--manifest` to select the corpus and `--output report.json` to preserve the full report. For a real embedding experiment, configure `VOYAGE_API_KEY` and explicitly pass `--embedding-provider voyage`; the provider is intended for development-set runs and has not been called in this workspace. Check current provider pricing/data policies. Reports can contain original query text. These synthetic evaluations do not estimate production generalization.
