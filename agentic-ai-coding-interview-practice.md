# Coding Interview Practice: Contracts Before Implementations

These exercises practice runtime engineering without requiring a provider account. Attempt them in a copy of [coding_exercises.py](agentic-ai-sandbox/coding_exercises.py) before opening [coding_solutions.py](agentic-ai-sandbox/coding_solutions.py). Run `python3 run_coding_checks.py` from the sandbox to examine the reference acceptance checks. Point equivalent tests at your implementation when practicing; passing the reference tests alone does not grade your own code.

## Exercise 1: Dependency scheduling, concurrency and cancellation

**Time:** 40 minutes. Implement `run_dag(steps, work, concurrency, timeout)` for read-only callbacks. Each step has an ID, dependencies and effect. A callback receives only its step and completed dependency values. Return per-step complete/value, failed/error type, or blocked outcomes.

Before any callback starts, reject duplicate IDs, unknown dependencies, cycles, non-read effects and excessive plan/concurrency limits. Start only dependency-ready work. Bound active tasks; retain independent successes when another task fails. Do not execute descendants of a failed dependency. On caller cancellation or total deadline, cancel and await local tasks so resources are cleaned up.

**Reference walkthrough:** `validate_plan` performs a Kahn-style dependency pass before effects. The executor keeps pending, running and outcomes maps. Completed callbacks free slots; failure propagates to blocked descendants. A `finally` block cleans up outstanding local tasks. Callback exceptions expose a type rather than internal messages.

**Acceptance:** Independent A/B may overlap; join starts after both. A failing branch does not stop unrelated success. Its descendants never run. A cycle makes zero callbacks. Cancellation and timeout execute cleanup.

**Trade-off:** This implementation scans pending dependencies and caps the plan at twenty steps; it is readable, not an optimized large-DAG engine. It has no distributed queue, durable state or retries. Callback code must authorize every read. Cancelling a local task cannot undo an already-issued external request.

**Follow-up:** How would you add per-tool quotas without deadlock? Acquire global/tool permits in a consistent order, bound waiting by the remaining deadline, and release in `finally`. Retry only classified safe reads; preserve identity scope and total budgets.

## Exercise 2: Assemble streamed tool calls safely

**Time:** 30 minutes. The input is a normalized provider-independent stream: begin(id,name), delta(id,text), end(id). Calls can interleave. Build complete argument objects while preserving call IDs. Return nothing executable from `feed`; output is available only at `finish`.

Reject duplicate begins, events without a begin, events after end, unknown fields/kinds, too many calls, oversized UTF-8 arguments, incomplete calls and non-object JSON. Invalid input poisons the batch. After parsing, the tool broker still validates the registered name, exact schema, identity and business authority.

**Reference walkthrough:** Keep one buffer per ID and separate ended flags. Count UTF-8 bytes, not characters. `finish` validates every buffer before returning the list; the caller must not execute incrementally while another call remains invalid. This is a normalized protocol exercise; a real adapter maps vendor events and handles refusal/disconnect/stop reasons separately.

**Acceptance:** Interleaved A/B succeed with correct IDs. `ééé` exceeds a four-byte limit. An unfinished stream executes nothing. Duplicate IDs or a JSON array are rejected.

**Follow-up:** A disconnected stream has one complete call and one partial call. Our atomic-batch policy discards the batch. A different policy needs explicit authorization, execution journal and missing-result semantics; do not make that decision accidentally.

## Exercise 3: Select evidence under a token budget

**Time:** 25 minutes. Each item has ID, actual rendered-token count, priority, allowed and required flags. Reserve output space, include required authorized evidence, then add optional evidence in deterministic priority order when it fits.

Reject duplicate IDs, invalid counts, forbidden required evidence, or required evidence that cannot fit. Do not truncate a policy condition silently. Return IDs and used tokens; the caller fetches a smaller authoritative section or hands off on required-budget failure.

**Reference result:** Budget 100, reserve 30, required item 40 tokens, optional items 100 and 20: select required plus the 20-token item, using 60. A forbidden ten-token item is never included. Required 40 with only 30 available fails.

**Trade-off:** Greedy priority selection is simple and deterministic; it is not optimal knapsack packing, semantic deduplication or retrieval scoring. Scope and counts come from trusted code. Selection does not make source statements true.

## Exercise 4: Idempotent local results and unknown external outcomes

**Time:** 35 minutes. Use a durable store keyed by namespace and operation key. Same request/key returns the original result; different request under the same key is rejected. Reopen the database and demonstrate replay.

**Reference:** [SQLiteIdempotencyStore](agentic-ai-sandbox/durable_state.py) commits a canonical request and result under a unique key. A local transaction prevents two stored results for that key. `run_durability_checks.py` and `run_approval_checks.py` demonstrate restart and provider-mock deduplication.

**Crash question:** A network payment is accepted before a local result is stored. The result table cannot make that external call atomic. Persist intent first, use the provider's idempotency/lookup contract, keep unknown outcome, and reconcile. Do not perform an external action before `put_if_absent` and claim this makes it exactly once.

**Acceptance:** Same-key replay survives reopen; different payload fails; two claimants cannot both hold one active lease; lost acknowledgement reuses the provider key. State which invariant is local and which needs downstream support.

## Exercise 5: Index lifecycle and security metadata

**Time:** 40 minutes. Implement a tenant/source-scoped index with monotonic source revision, conditional index revision, content hash and processing versions. Test unchanged text with changed ACL/classification, an embedding-version rebuild, deletion, older events, and the same source ID in two tenants.

**Reference:** [IndexSimulator](agentic-ai-sandbox/index_lifecycle_reference.py) and `run_index_lifecycle_checks.py` are complete synthetic answers. Metadata refresh does not increment the simulated embedding-build count; an embedding-version change does. Reads recheck a separate authoritative snapshot, so a stale derived index cannot grant access. Deletion plus older replay remains inaccessible.

**Trade-off:** This simulator has no actual embeddings, concurrent database transactions, connectors or network identity. It specifies the behavior a production implementation must enforce with authoritative revisions and integration tests.

## Exercise 6: Recover an interrupted evaluation trial

**Time:** 30 minutes. Persist completed answers and attempt usage. A failed/unfinished read-only generation may already have incurred charges; skip successes on resume and require an explicit retry flag for failed work. Reject resume against a changed dataset, model or prompt.

**Reference:** `run_trial` in [the optional generator](agentic-ai-sandbox/generate_answer_candidates.py) checkpoints before and after each call. `run_generation_recovery_checks.py` uses a fake client: case one succeeds, case two fails, and resume calls only case two. Malformed response usage is retained when available; transport-failure usage is unknown, not zero.

The checkpoint is for one process and path, not distributed leasing. An interrupted trial remains incomplete; the answer evaluator rejects missing case IDs rather than silently scoring a favorable subset.

## Scoring a coding attempt

Allocate 0–4 each for contract clarity, correctness, failure handling, resource bounds, relevant tests and explanation. A solution that starts writes before authorization, executes partial arguments, ignores cancellation or silently drops required evidence cannot pass on style points. Explain complexity and one unsupported requirement. Then change the input assumptions and extend a test without looking at the reference.
