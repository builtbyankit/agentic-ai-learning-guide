# Completed Reference Solutions: Failure, Diagnosis, Correction, Evidence

These are completed offline case studies with runnable code and observed checks. They complement the advanced labs, whose live-provider, adaptation and production extensions still need your own experiments. Every result below is synthetic and local; none is a production performance claim.

## Case 1: Word routing is insufficient for action intent

**Task:** A customer may request status, refund eligibility or a refund proposal. Preserve independently requested outcomes and avoid proposals when intent is negative or unclear.

**Failed approach:** The original router treats the occurrence of “refund” as an action unless another policy keyword changes the route. A later short negation list still missed “I don't want a refund.” Damage wording could switch an explicit refund into a policy answer; eligibility could replace a separate status request.

**Diagnostic trace:** “I don't want a refund for ORD-100. Just tell me its status” previously produced `prepare_refund_proposal → request_human_review`, one review and no status. “Please refund ORD-100 because the notebook arrived damaged” produced only `get_order → search_policy`. These are user-intent failures even though no payment tool exists.

**Correction:** The current router requires a narrow explicit request grammar, treats recognized negation conservatively, clarifies unclear refund wording, and collects separate read outcomes. Damage as a reason no longer changes an explicit refund into a policy-only route. Multiple consequential targets or excessive planned calls still require narrowing.

**Reproduce:**

```sh
python3 run_reference_cases.py
python3 run_workflow_checks.py
```

**Observed result:** The original router meets none of the three case-study outcome contracts; the corrected router meets all three. The combined regression checker passes 33 cases: 17 existing v7 plus 16 improvement-time challenges. The unchanged v7 comparison remains 14/17 original versus 17/17 corrected; the improved baseline uses 22 tools and zero model calls.

**Limitations and decision:** This is bounded phrase routing, not general linguistic understanding. Conservative negation may over-abstain. Quoted requests, unusual word order, mixed conditions and multilingual dialogue need independent challenge data. A perfect score on these authored cases justifies explicit branches for them; it does not validate arbitrary action intent.

## Case 2: Schedule independent reads without losing failure semantics

**Task:** Run independent A/B, join their outputs, and retain success when a separate branch fails. Stop locally on timeout/cancellation.

**Failed approach:** Await every read sequentially, or launch every node simultaneously. The first leaves parallelism unused; the second starts dependent work before evidence exists. `gather` alone does not define blocked descendants or cleanup policy.

**Correction:** The reference validates the entire DAG before work, launches only ready nodes under a concurrency cap, records per-step outcomes, propagates blocked status and cancels outstanding tasks in `finally`.

**Reproduce:** `python3 run_coding_checks.py`.

**Observed result:** The synthetic scheduler reaches two active callbacks under a cap of two, joins only after A/B, preserves independent success, and never executes failed descendants. Invalid cycles/IDs/write effects start no work. Caller cancellation and total deadline execute callback cleanup. Stream and evidence checks also pass.

**Limitations and decision:** No latency speedup was benchmarked. This is local asyncio scheduling for twenty or fewer read steps; authorization belongs in callbacks. Remote requests may remain in flight after local cancellation. Use the same contract to assess a framework rather than claiming this toy executor provides distributed durability.

## Case 3: Text hashes cannot decide security freshness

**Task:** A policy's text stays unchanged while its classification or ACL changes; later its embedding version changes and then it is deleted.

**Failed approach:** Return “unchanged” whenever normalized content hashes match. This skips changed security metadata and processing versions. An old indexing event can also resurrect a deleted source without revision checks.

**Correction:** `IndexSimulator` namespaces by tenant/source, conditionally publishes against an index revision, rejects older source revisions, refreshes security metadata independently of text and rebuilds when processing versions change. Reads consult a separate current-authority snapshot before returning text.

**Reproduce:** `python3 run_index_lifecycle_checks.py`.

**Observed result:** Initial ingestion increments build count to one. Classification-only update refreshes metadata without another build and immediately denies an internal-only actor through current authority. An embedding-version change increments builds to two. ACL revocation/deletion deny reads; an old source event and stale publisher are rejected. Identical source IDs in different tenants remain separate.

**Limitations and decision:** This is an in-memory simulator with synthetic principals, not a vector service or multi-worker database. Source revisions must actually be comparable; same revision cannot encode changed content/security facts. Production needs connector snapshot semantics, transaction/CAS enforcement and identity integration tests.

## Case 4: Keep evaluation evidence when a later call fails

**Task:** Case one generates an answer; case two encounters a provider failure. Resume without repeating successful calls and without assuming failed calls cost zero.

**Failed approach:** Buffer all results and write only after the final case. Failure discards completed output/usage, and restart repeats earlier paid work.

**Correction:** The optional generator checkpoints before a call and after its outcome, exports partial candidates/metadata, preserves an attempt history, checks dataset/model/prompt fingerprints on resume, and requires explicit retry intent for failed or unfinished work. Malformed responses retain available token usage; transport failures record usage as unknown.

**Reproduce:** `python3 run_generation_recovery_checks.py` uses a fake provider; it makes no network calls.

**Observed result:** One completed case remains after case two fails. Resume without retry makes zero new calls. Explicit retry calls only the unfinished case. A changed dataset is rejected; the failed attempt remains in history. A malformed JSON response retains its known output-token count.

**Limitations and decision:** The checkpoint is a single-process teaching design, not a distributed lease protocol. A crash after the provider responds but before checkpoint commit still leaves an ambiguous attempt; an explicit retry may incur charges again. An incomplete trial cannot be scored as a full successful suite.

## Case 5: A valid citation can support the wrong statement

**Task:** Evaluate claim support separately from whether source IDs exist.

**Failed approach:** Accept any answer that cites an allowed current source. A “90 days” claim can cite a real “30 days” policy and still be false.

**Correction:** `answer_quality.py` checks exact authored support mappings, required facts, expected abstention and reference/version validity. Unknown paraphrases require human review. It never treats citation existence as semantic entailment.

**Reproduce:** `python3 run_answer_eval_checks.py`; inspect the good/bad JSON fixtures.

**Observed result:** Eight expected answer fixtures pass; eight deliberately bad fixtures fail. The bad set includes a valid citation attached to a contradicted claim, missing evidence, wrong abstention, inaccessible/stale references and a poisoned instruction. Fake generation excludes forbidden evidence and gold labels.

**Limitations and decision:** Exact claim labels are useful for grader mechanics, not open-ended semantic scoring. Human or calibrated semantic review is still needed. Retrieval is frozen here: connect actual authorized retrieval packets before making end-to-end RAG claims.

## How to use these solutions in an interview

Explain the requirement, show the failed trace, identify the enforcing control, state the test and result, then name the remaining uncertainty. Reproduce one result yourself and change its assumptions. The rejected approach and limitation are as important as the passing check. Pair these cases with the coding prompts before reading solutions and with the numerical workbook for quantitative defense.
