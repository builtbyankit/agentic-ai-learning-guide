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

The unstructured RAG lab has a 10-query development set in [rag_scenarios.json](rag_scenarios.json) and a separate 10-query authored holdout set in [rag_holdout_scenarios.json](rag_holdout_scenarios.json). `run_rag_evals.py` compares exact cosine over the demo feature hash, BM25-style lexical search, and RRF hybrid ranking. Reports fingerprint the corpus metadata/content and query dataset, and include required-source coverage, Hit@1, source Recall@k, MRR, positive-query precision, no-answer accuracy, and retrieved chunk IDs with source/version/section provenance. Use `--output report.json` to save the full report for trace review. The currently measured holdout results are recorded in Module 11. They expose the fake dense embedder's shortcomings; do not treat them as a semantic-embedding benchmark or generalization estimate.
