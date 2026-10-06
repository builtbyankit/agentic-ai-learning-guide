# Advanced Labs: Build Evidence for Mastery

These labs close the gap between architectural vocabulary and a defensible implementation. They specify experiments, not unmeasured results. Use approved or synthetic data and keep provider credentials and private traces outside Git. API experiments are optional and must be explicitly configured; offline work remains useful.

## Lab 1: Improve the baseline before adding an agent

From the sandbox:

```sh
python3 run_workflow_baseline.py --baseline original --dataset evals/live_scenarios_v7.json
python3 run_workflow_baseline.py --baseline improved --dataset evals/live_scenarios_v7.json
python3 run_workflow_checks.py
```

The original returns exit 1 for its three expected evaluation gaps; the improved passes 17/17 with 22 tool calls and no model calls. The eight additional authored regression challenges test reversed ownership, repeated IDs, two policies, read-only eligibility, negated refund, multi-refund clarification, oversized plans, and unknown orders. They were created during improvement, so are not an independent holdout.

**Experiment:** Ask another person to label a fresh task sample without looking at router code. Include implicit references, negation, multi-turn ambiguity, mixed read/write intent, languages, and misleading unsupported requests. Freeze it and run the improved workflow and live planner under identical budgets and graders. Do not route by scenario IDs or add holdout-specific phrase rules.

**Deliverable:** Compare useful task completion, safe handoff, trajectory correctness, user-intent errors, live cost and tail latency. Keep an agent only where its improvement pays for its failure/operational surface. The new 17/17 score is evidence that these authored cases do not require a model, not that the whole product never will.

## Lab 2: Evaluate answers separately from retrieval

```sh
python3 run_answer_eval_checks.py
python3 run_answer_evals.py
python3 run_answer_evals.py --answers evals/answer_quality_bad.json
```

The good fixture accepts eight authored cases. The deliberately bad fixture fails all eight and returns exit 1. Cases cover incorrect claims with valid citations, missing facts, unanswerable finance questions, conflicting sources, inaccessible sources, stale versions, and poisoned evidence. Inspect `answer_quality.py` and the JSON fixtures.

**What the grader establishes:** Valid envelope and citation/version references; coverage of authored required facts; support against explicit exact-claim labels; appropriate abstention/limitation. Unknown paraphrases are queued for human review, not automatically judged false or true. Report reviewed-claim support together with label coverage and sample counts. `citation_reference_validity` measures IDs and versions, not semantic entailment. These frozen packets isolate generation from retrieval and do not exercise production authorization.

**Optional live generation:** Install the sandbox's existing provider dependency, configure your account-enabled model and secret outside Git, then explicitly opt in:

```sh
python3 generate_answer_candidates.py --live --output /tmp/answer-trial-1.json
python3 run_answer_evals.py --answers /tmp/answer-trial-1.json --output /tmp/answer-review-1.json
```

The generator sends questions and allowed evidence only, without gold labels; fake-client checks cover that boundary. It makes no tool calls, records usage/model/prompt/dataset fingerprints, and rejects abnormal completion. No live run has been performed for the repository's results. The provider can paraphrase claims outside the authored labels; an initial failure then means review is required, not automatically that the model hallucinated.

**Human review protocol:** Split answers into atomic claims; label supported, contradicted, or insufficient evidence and supporting source/version. Independently review a sample with two reviewers, adjudicate disagreement, and record label revision. Freeze accepted claim/citation mappings before scoring that trial. Do not expose evaluation labels to generation or use holdout answers to tune a prompt. The simple exact-label evaluator does not replace a calibrated semantic or human grader.

**End-to-end extension:** Run the real retriever first, record its authorized source/version packets, and label what the task requires separately from what was retrieved. Feed only that evidence to generation. A missing source should count as retrieval failure even when the generator appropriately abstains. An unsupported answer with all sources present is generation failure. Track both along with useful overall completion, abstention on negatives, and access failures.

## Lab 3: Retrieval relevance and calibrated abstention

Reproduce the expanded development benchmark with lexical, dense and hybrid methods. The default dense path is hashing, not learned semantics. Use the optional real embedder on development data if configured. Add a reranker only after candidate recall is understood.

Construct a larger negative set: shared financial words, negation, near-duplicate policies, conflicting current sources, stale versions, exact code identifiers, and unfamiliar phrasing. Choose a confidence/abstention rule on development data; never use a raw RRF score as an unexamined probability. Plot the false-answer/false-abstention trade-off. Measure source and chunk precision/recall separately, then label answer support.

**Gate:** Present numerator/denominator for every slice; compare against unchanged lexical search and a new frozen holdout. Zero access leaks is a tested invariant, not a small-sample security certification. Improvements in recall do not excuse a false high-impact answer.

## Lab 4: Index lifecycle and security metadata

Build a connector simulator with monotonic source revisions and independent text, ACL, classification and deletion changes. Test unchanged text with changed ACL/classification; unchanged text with a new chunker/embedder; a deletion arriving during rebuild; and an older event arriving after a newer one.

Require tenant/source namespacing, revision-aware conditional publication, security metadata refresh without unnecessary embedding, and an active-version pointer. A stale event cannot reactivate deleted or restricted content. Authorization rechecks must precede disclosure even if physical removal is asynchronous. Compare with the corrected Harper pseudocode.

**Gate:** Demonstrate the classification bug with the guard removed and the denied result with it restored. Explain how source metadata and ACL snapshots are acquired consistently; separate that contract from atomic index publication.

## Lab 5: Recovery under interacting failures

Run existing durability and approval checks. Then add cancellation during a slow call, duplicate queue delivery, schema compatibility across worker versions, database restore, and provider acceptance with lost acknowledgement. Use a fake external service with configurable idempotency retention and operation lookup.

**Gate:** One stable approved intent, no unexplained duplicate financial effect, explicit unknown outcomes, stale-worker writes rejected, and a reproducible recovery trace. State that an in-flight request cannot be cancelled merely by expiring a lease. Record recovery time and backlog, not just a Boolean check.

## Lab 6: Orchestration as an experiment

Choose a task with genuinely independent investigations. Compare fixed search/review, one agent, and bounded manager/workers. Keep source scope, task labels, provider configuration and output contract fixed. Record full-tree calls, tokens, cost, critical-path latency, duplicate work, contradictions, missing evidence, cancellations and merge errors.

**Gate:** A measured improvement in quality or elapsed time with acceptable total spend and scoped permissions. If all workers inherit the same assumption, more votes do not establish independent evidence. Explain why support order/policy lookups do not automatically need specialist agents.

## Lab 7: Load and operations game day

Start with the capacity exercise's assumptions. Generate synthetic traffic with slow-provider, retry-burst, restrictive-filter and long-context slices. Enforce provider quotas and deadline-aware admission. Measure queue age, useful completion, p95/p99 task latency and per-route cost.

Run an incident: provider outage, identity failure, stale index, unknown payment outcome, sensitive trace exposure, or review backlog. Demonstrate detection, kill switch, safe fallback, reconciliation, named owner and recovery. Record what a rollback does to pending work and deleted sources.

## Lab 8: Adaptation decision and serving experiment

Collect governed examples for a consistent behavioral error after prompting and retrieval baselines. Split by source/time or user where leakage is plausible. Compare prompt-only, RAG, and a small adaptation experiment if hardware/data permit. Evaluate normal tasks, refusal, grounding, rare slices and held-out drift. Document trainable parameters, memory, training/serving cost and rollback.

For a serving experiment, measure prefill, decode, first-token time, throughput and memory at varied context lengths and concurrency. Compare a floating-point baseline with quantization only on compatible hardware. A managed-API candidate can instead build the experimental plan and distinguish unobserved hardware claims. Keep permissions in the runtime under every model route.

## Report template

For every lab, record objective, hypothesis, baseline, versioned inputs, configuration, command, labels/graders, results by slice with sample counts, failure trace, confounders, decision and next falsifying experiment. Label status as measured offline, measured live, designed, or unverified. Link this report from your capstone rather than repeating claims across every module.
