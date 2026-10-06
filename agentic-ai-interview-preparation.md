# Agentic AI Interview Preparation

This guide is a senior-level interview companion to the [mastery roadmap](agentic-ai-mastery-roadmap.md) and [architecture practicum](agentic-ai-module-12-senior-architecture-practicum.md). It covers system design, agent runtimes, orchestration, unstructured data and RAG, evaluation, security, reliability, and optimization.

The answers are models for clear reasoning, not scripts to memorize. In an interview, state assumptions, compare a simpler baseline, name the failure modes, and say what evidence would change your design. Be explicit about what you have implemented and measured versus what you have only designed.

## Practice beyond the model answer

Each question below has a follow-up and an expected artifact in the [interview workbook](agentic-ai-interview-workbook.md). Explain the answer in two minutes, defend a changed assumption, and show a diagram, calculation or failure trace. Use [LLM foundations](agentic-ai-llm-engineering-foundations.md) for model mechanics and [worked sizing](agentic-ai-worked-capacity-and-cost.md) for numerical system design. The [preparation plan](agentic-ai-mastery-and-interview-plan.md) supplies six-week and fourteen-day practice routes.

For deeper preparation, use [coding practice](agentic-ai-coding-interview-practice.md), [numerical worked answers](agentic-ai-numerical-workbook.md), [architecture comparisons](agentic-ai-architecture-decision-cases.md), and [leadership scenarios](agentic-ai-leadership-interview-practice.md). [Completed reference solutions](agentic-ai-completed-reference-solutions.md) show failed traces, controls, observed checks and limitations.

## A strong answer structure

For an architecture or system-design question, work through this sequence:

1. **Clarify the task:** users, inputs, success criteria, risk, traffic, latency, and cost constraints.
2. **Choose the least complex viable design:** direct model call, deterministic workflow, one bounded agent, or orchestration.
3. **Draw the runtime:** identity and policy, model adapter, tool broker, state, retrieval, external systems, and human review.
4. **Trace one normal run and failures:** timeout, malformed tool arguments, stale data, retry, model refusal, and partial side effect.
5. **Define evidence and operations:** representative evaluation, release gates, telemetry, rollback, and ownership.
6. **Name the trade-off:** quality, latency, cost, autonomy, security surface, and operational burden.

## 1. Agentic system design

### Q1. What makes a system agentic, and how is it different from a workflow?

**Strong answer:** An agentic runtime lets a model choose among bounded next steps based on the task and observations, often in a loop of model decision, tool execution, result, and another decision. A workflow encodes the control flow in application code. The distinction is about who chooses the next step, not whether the system uses an LLM. Many useful products combine both: code owns the lifecycle and policy while the model handles a narrow judgment step. I would call the design agentic only where that dynamic choice adds value.

### Q2. When would you avoid an agent?

**Strong answer:** I would start with a direct call or deterministic workflow when the task has stable inputs, known branches, and consequential actions that can be expressed as rules. A model loop adds latency, cost, nondeterminism, and a larger security surface. I would compare it with the simplest baseline on the same representative cases and keep the agent only if it materially improves a task metric without breaching safety, latency, or cost limits.

### Q3. Describe a production agent architecture.

**Strong answer:** I would separate request handling and identity, policy and task contract, orchestration/runtime, model-provider adapter, tool broker, retrieval, durable run state, and external systems. The model proposes actions; deterministic services authenticate the actor, enforce permissions, validate arguments, apply budgets, persist state, and decide whether an action may execute. I would trace the run end to end with versioned prompt, model, tool, policy, and dataset identifiers. The exact service boundaries depend on scale and team ownership; they need not all be separate deployables.

### Q4. How do you set an agent's autonomy boundary?

**Strong answer:** Define which requests it can handle, what data it may read, which tools it may call, what writes it may propose, and what requires human approval. Enforce those limits in runtime authorization and tool implementations, not only in instructions. Use explicit stop conditions, deadlines, turn and token budgets, and a safe fallback. I would test attempts to cross each boundary, including adversarial user text and hostile retrieved content.

## 2. Tools, model adapters, and orchestration

### Q5. What makes a good agent tool contract?

**Strong answer:** A tool should have one narrow purpose, a clear name and description, a typed schema, bounded input and output sizes, and documented errors and side effects. The runtime validates model-produced arguments, but the tool independently checks trusted identity, scope, and authorization. Read and write capabilities should be separate where practical. Mutations need idempotency and audit information; the model's choice to call a tool is never itself permission.

### Q6. The model requested a refund tool. What must happen before the refund is issued?

**Strong answer:** The application validates the tool name and arguments, retrieves the authenticated actor and current order facts from trusted services, checks policy and limits, and determines whether approval is required. For an approval flow, bind the approval to the exact proposal and recheck the relevant facts when committing it, so a stale proposal cannot be approved. Queue delivery durably and use the provider's idempotency mechanism. If the provider times out after a request, record an unknown outcome and reconcile before retrying.

### Q7. How should the runtime handle multiple tool calls in one model response?

**Strong answer:** First validate every call and determine whether calls are truly independent and read-only. Execute independent safe calls with bounded concurrency; serialize calls with ordering or shared-state dependencies. Preserve each provider call ID when returning results, and validate each result against limits and schema. Treat partial failure explicitly: retry only safe operations, retain successful results, and ask the model or user for the next step without duplicating side effects.

### Q8. Why isolate the model-provider adapter?

**Strong answer:** It keeps provider-specific request, response, streaming, error, and usage details out of business logic. The rest of the runtime can depend on an internal contract for messages, tool requests, stop reasons, and token usage. This improves testability and makes provider changes more contained, but it does not make models behaviorally interchangeable. I would retain provider-specific evaluation and capability checks, and avoid pretending that a common interface removes differences in semantics or quality.

### Q9. When is a multi-agent design justified?

**Strong answer:** When distinct subtasks benefit from genuinely different context, tools, policies, or independent parallel work—and evaluation shows a meaningful improvement over a single agent or workflow. A manager with specialist tools keeps the manager in charge of the user-facing conversation; a handoff transfers ownership to the specialist. Both need bounded contracts, deadlines, scoped tools, structured results, cancellation, and partial-failure rules. Parallel work can reduce critical-path latency while increasing total calls, spend, and merge risk.

### Q10. What belongs in a delegation contract?

**Strong answer:** A task ID and objective, trusted actor scope, allowed sources and tools, input/output schema, deadline, token or cost budget, maximum depth and fan-out, cancellation behavior, and data-retention expectations. Do not let the parent model widen a child’s permissions by editing text. A child result is untrusted evidence: validate its schema, provenance, and claims before using it. Measure the whole tree, not just the parent run.

## 3. State, durability, and human review

### Q11. Distinguish context, run state, and memory.

**Strong answer:** Context is the selected information sent to the model for this decision. Durable run state records workflow progress and facts needed to resume correctly. Cross-run memory is information intentionally retained for future tasks under an explicit policy. They have different access, consistency, and retention requirements. A compact model summary is not a replacement for authoritative state, and a vector store should not silently become the system of record.

### Q12. How do you make retries safe?

**Strong answer:** Use stable operation and idempotency keys, persist intent before delivery, make state transitions explicit, and distinguish retryable errors from permanent errors and unknown outcomes. For an external write, a timeout does not prove the provider rejected the request. Query or reconcile using the original operation key before retrying. A transactional outbox can atomically record approval and delivery intent in one database transaction, but it does not create a distributed transaction with an external provider.

### Q13. How would you make long-running agent jobs recoverable?

**Strong answer:** Persist a run record with state version, inputs or references, completed tool results, and the next expected transition. Workers claim jobs with expiring leases; fencing tokens or compare-and-swap prevent a stale worker from committing after its lease is superseded. On restart, resume from durable state rather than blindly replaying the entire conversation and repeating effects. Test crashes around each write boundary and around external calls.

### Q14. How do you design human approval for consequential actions?

**Strong answer:** Show the reviewer the exact action, amount or scope, subject, supporting facts, and policy version. Bind approval to a canonical proposal digest and an expiry. At commit time, reauthorize the operator and revalidate current facts and policy; reject or regenerate a stale proposal. Record the decision and enqueue the action atomically where the datastore allows it, then deliver through an idempotent outbox and reconcile provider outcomes.

## 4. Unstructured data and RAG

### Q15. Walk through a production document-to-answer pipeline.

**Strong answer:** At ingestion, authenticate the source, validate file type and size, scan or sandbox parsers, extract text and structure, normalize encoding, preserve heading/table/page provenance, and record source, tenant, classification, version, and timestamps. Apply redaction or policy checks before indexing. Chunk according to document structure, embed, and store vectors with metadata and a source reference. At query time, apply trusted access filters, retrieve candidates, optionally rerank, assemble a token-bounded evidence set, and require the answer to distinguish supported facts from missing evidence. Track ingestion failures and freshness as well as query quality.

### Q16. How do you choose chunking strategy and size?

**Strong answer:** Preserve semantic units first: headings, sections, paragraphs, tables, and page boundaries. Use fixed token windows with overlap only as a fallback or a deliberate baseline; overlap can improve boundary recall but increases index size and duplicated evidence. Keep parent and child identifiers so small retrieval units can be expanded to useful context. Compare strategies on a development set and holdout using retrieval and answer metrics, latency, and token cost rather than choosing a universal chunk size.

### Q17. What would you store alongside each vector?

**Strong answer:** A stable chunk ID and source ID, source version and content hash, tenant and classification, ACL or policy reference, document/section/page provenance, ingestion timestamp, and embedding model/version. Store enough text or a resolvable reference to render evidence and support deletion. Keep authoritative authorization outside model-readable free text. A vector database is not automatic: lexical or relational search may be enough. Choose storage based on corpus and query scale, filtering, update/deletion behavior, consistency, latency, and operational skills, then test those requirements.

### Q18. Describe a robust retrieval query path.

**Strong answer:** Normalize the question and infer required filters from trusted request context, not from a model-provided tenant ID. Run lexical retrieval for exact terms and dense retrieval for semantic matches when useful; combine rankings with a method such as reciprocal-rank fusion, then rerank a bounded candidate set if the quality/latency trade-off warrants it. Enforce ACL and freshness constraints before evidence reaches the model. Return source IDs and excerpts, and abstain or ask a clarifying question when evidence is insufficient.

### Q19. What are the important RAG evaluation metrics?

**Strong answer:** Evaluate retrieval separately from generation. Retrieval measures can include Recall@k, MRR or nDCG, exact coverage, freshness, and forbidden-source leakage. Answer checks can include factual support, citation correctness, completeness, abstention on unanswerable questions, and task success. Use labeled development and holdout queries with hard negatives, paraphrases, multi-source questions, stale versions, and access-scope cases. Inspect failures; a strong average score can hide a critical authorization failure.

### Q20. How do you handle document updates and deletions?

**Strong answer:** Treat the index as a derived, versioned view of authoritative sources. Use content hashes and source versions to avoid unnecessary re-embedding, publish new versions atomically or through a clear active-version pointer, and remove superseded chunks from retrieval. Propagate deletion and permission changes through caches and derived indexes with measurable SLAs. Test a query during update, after revocation, and after deletion; a stale vector must not keep granting access.

## 5. Context, memory, and prompt injection

### Q21. What should go into the model context?

**Strong answer:** Only the task-relevant instructions, current state summary, necessary recent turns, and evidence needed for the next decision. Keep permissions, budgets, canonical facts, and workflow state in trusted application state; expose only scoped, minimal representations. Set an explicit token budget and prioritize current authoritative evidence over stale conversation history. Measure whether context selection improves task quality and reduces unnecessary tokens.

### Q22. How do you decide whether to persist memory?

**Strong answer:** Start with a concrete future use case and define what may be written, by whom, for how long, and how it can be reviewed or deleted. Separate durable user preferences from task state and derived summaries. Do not let the model write unrestricted memory from arbitrary text; validate candidate writes and enforce tenant and user scope at read time. Evaluate memory precision, stale-memory harm, privacy, and deletion behavior.

### Q23. How do you defend against prompt injection in retrieved documents?

**Strong answer:** Treat retrieved text, tool results, and user content as untrusted data even when relevant. Tell the model to use them as evidence rather than instructions, but rely on deterministic controls for actual protection: least-privilege tools, server-side authorization, strict output validation, network or code sandboxing where needed, and approval gates. Test direct and indirect injection attempts, including instructions to reveal secrets or bypass policy. Do not assume a prompt delimiter or classifier alone creates a security boundary.

### Q24. What is prompt caching, and when is it useful?

**Strong answer:** It reuses processing for a repeated prompt prefix, which can reduce repeated input work and latency when the prefix is large and stable; it is not a response cache and does not replace context budgeting. Put reusable tool definitions, system instructions, and stable reference content before request-specific material, and place the cache boundary before dynamic user data. For Anthropic, the current prefix hierarchy is tools, system, then messages; deferred tool loading can also keep rarely used definitions out of the initial prompt. Check provider-specific semantics, instrument cache-read and cache-write usage, and evaluate privacy and retention requirements.

### Q25. How do you diagnose poor cache hit rates or decide whether caching saves money?

**Strong answer:** Compare consecutive serialized requests and identify what changed in the prefix: tool order/schema, system text, timestamps, user-specific data, or model settings. Confirm writes and reads from provider usage fields instead of inferring hits from code. Model write cost, read cost, TTL, request frequency, and invalidation rate using current provider pricing. Cache only stable content shared under the correct security boundary; avoid caching per-user secrets just to improve a token metric. For Anthropic, current cache behavior and tool-loading interactions are documented in its [tool-use caching guide](https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-use-with-prompt-caching).

### Q26. How do you control context growth over a long run?

**Strong answer:** First remove unnecessary context: defer large tool definitions, return bounded tool results, and avoid repeating retrieved evidence. Then compact old conversation when needed, preserving a concise summary, unresolved questions, key decisions, and links to authoritative durable state. Keep recent turns verbatim where they affect the next decision. Treat provider-managed compaction as a versioned capability, verify current availability and behavior, and never make a generated summary the sole record of a consequential action. See the current [Anthropic compaction overview](https://platform.claude.com/docs/en/build-with-claude/compaction).

## 6. Evaluation, observability, and optimization

### Q27. How would you build an agent evaluation program?

**Strong answer:** Start from task requirements and a fixed-workflow baseline. Create versioned, representative cases across normal, ambiguous, adversarial, unanswerable, and failure scenarios. Grade outcomes and trajectories: final task success, tool choice and arguments, policy compliance, evidence use, escalation, and side effects. Use deterministic checks for invariants and model or human graders for subjective quality; calibrate graders against reviewed examples. Keep a holdout set, run repeated trials for stochastic behavior, and make critical safety failures release blockers.

### Q28. What does an offline pass rate prove?

**Strong answer:** Only that this implementation passed the specific tested cases under the recorded harness and configuration. It does not prove live-provider quality, generalization, production reliability, or security. Report dataset provenance and hash, model/prompt/tool versions, trial count, confidence intervals where relevant, and untested assumptions. Add failures to the regression set without contaminating the holdout used for final comparison.

### Q29. What should you log and trace?

**Strong answer:** Record a correlation/run ID, actor and tenant references with appropriate privacy controls, model and prompt versions, tool name and validated argument summary, tool result status, state transitions, retrieval source IDs, latency, token/cache usage, budgets, and escalation or approval outcomes. Capture enough redacted detail to debug decisions, but avoid raw secrets and unnecessary personal data. Define access controls, retention, deletion, and incident procedures for traces before production.

### Q30. How would you optimize cost and latency without degrading quality?

**Strong answer:** Establish a representative baseline by task slice first, measuring cost per successful task as well as raw token spend. Then test targeted changes: remove unnecessary turns and context, improve retrieval, cache a stable prefix, defer rarely used tools, route simpler requests to a cheaper model, bound outputs, batch offline work, or parallelize independent reads. Track quality and safety alongside p50/p95 latency, total tokens, cache reads/writes, tool calls, retries, and total cost. Roll out incrementally and revert a change if it shifts errors into a critical slice, even when average cost improves.

### Q31. What should happen during a model-provider outage?

**Strong answer:** Use deadlines, bounded retries with jitter for retryable errors, and a circuit breaker or rate limit to prevent a retry storm. Continue only deterministic paths that remain correct and authorized; otherwise return a clear handoff or degraded response. Preserve durable run state, do not repeat consequential effects, and expose provider and fallback status to operators. Test recovery and queued-work behavior, not just a mocked single timeout.

### Q32. How would you roll out a new prompt, model, or retrieval version?

**Strong answer:** Version the complete behavior bundle, run offline regression and security suites, then shadow or canary traffic where policy permits. Compare task slices, traces, safety outcomes, cost, latency, and fallback rates against the previous version. Keep kill switches for model decisions and external action delivery separate. Define rollback thresholds and preserve compatibility with durable state and queued work before deployment.

## 7. System-design practice prompts

For each prompt, clarify constraints first. Then draw the architecture, walk through a normal and failed run, define release evidence, and identify what you would deliberately leave out of the first version.

### Prompt A: Customer-support resolution assistant

**Question:** Design an assistant that answers policy questions, looks up a customer's order, and can propose a refund.

**Example answer:** I would use a deterministic identity and authorization layer, policy/order read tools with narrow schemas, and a model only for ambiguous intent and answer composition. Policy retrieval would use versioned, provenance-preserving chunks with tenant and classification filters derived from trusted context; order access would go to the authoritative service. A refund remains a proposal until a human approves the exact amount and order. The approval path rechecks current order and policy state, records approval and an outbox event atomically in one datastore, then calls the payment provider with idempotency and reconciliation. I would compare against a fixed workflow on the same support cases, with zero unauthorized reads/writes as a release gate. I would not claim that a local SQLite simulation proves multi-service atomicity or production readiness.

### Prompt B: Internal engineering knowledge assistant

**Question:** Design a RAG assistant over runbooks, incident reports, and source documentation.

**Example answer:** I would inventory source owners, classification, update frequency, and access policy before choosing an index. A sandboxed ingestion pipeline would parse formats, preserve headings and provenance, chunk by structure, version embeddings, and support deletion. Query-time authorization would filter before snippets reach the model; hybrid retrieval and reranking would be evaluated against a labeled holdout with stale docs, hard negatives, and unanswerable requests. Answers would cite source versions and hand off when evidence conflicts or is missing. I would monitor freshness, access denials, retrieval quality, answer support, and token/latency cost.

### Prompt C: Long-running research task with specialists

**Question:** A research task spans many sources and could be parallelized. How would you design it?

**Example answer:** First compare a single agent and a fixed search/review workflow. If parallel specialists add measured evidence coverage or reduce critical-path time, have a bounded parent split independent questions into children with distinct source scopes, budgets, deadlines, and a structured evidence schema. Run only independent work concurrently; validate citations and contradictions during merge. Bound fan-out and retries, cancel or label partial results, and measure the full tree's cost, latency, and merge errors. The parent must treat worker output as untrusted and retain responsibility for the final answer.

## 8. Behavioral and experience questions

Use real examples. Do not present this repository's synthetic sandbox or unrun live evaluation as production experience.

### Q33. Tell me about a time you changed an architecture after seeing evaluation results.

**Answer framework:** Give the task and initial hypothesis, name the baseline and evaluation, explain which failure changed your view, describe the design change, and report what improved and what remains unverified. A strong senior answer includes the holdout or regression plan and why the new complexity was justified. If the work is from this repository, identify it as a design or synthetic demonstration.

### Q34. Describe a failure mode you designed for that was not solved by prompting.

**Answer framework:** Pick a concrete boundary such as revoked access, a stale refund proposal, duplicate delivery after timeout, or hostile retrieved text. Explain the system invariant, the deterministic control that enforces it, the test that exercises the failure, the telemetry that would detect it, and the recovery path. Separate the control from any model instruction that may reduce the chance of triggering it.

### Q35. How have you balanced product value against autonomy and risk?

**Answer framework:** Describe the user's job and harm from an incorrect action, the lower-autonomy baseline, and the evidence for adding model judgment. Explain which actions remain read-only, proposed, or approval-gated, and who owns the decision. Include a measurable kill criterion and explain what evidence would make you narrow or disable the agent.

## Interviewer scorecard and common weak answers

| Strong signal | Weak signal |
| --- | --- |
| Starts with task requirements and a simpler baseline | Starts by selecting an agent framework or model |
| Separates model suggestions from identity, policy, and authority | Treats a prompt or vector filter as the authorization boundary |
| Explains retries, unknown outcomes, state, and recovery | Claims an external side effect can be made exactly once by retrying |
| Evaluates retrieval and generation separately, including abstention and access scope | Assumes embeddings or larger chunks automatically solve RAG quality |
| Uses traces and slice-level metrics with privacy and retention controls | Reports only one aggregate pass rate or a demo transcript |
| Quantifies quality, cost, latency, and risk before keeping optimization | Caches every prompt or adds parallel agents without measuring invalidation and total spend |
| Labels implemented evidence, design assumptions, and gaps honestly | Describes synthetic tests as proof of production readiness |

## Suggested practice loop

1. Pick one question and answer it aloud in two minutes.
2. Add a diagram or state transition for questions about runtime or recovery.
3. Ask what fails under timeout, stale data, concurrency, or malicious input.
4. State the metric and test that would validate the design.
5. Review the related course module and revise the answer without claiming more evidence than it provides.

## Related course material

- [Harper Enterprise Knowledge and Code Intelligence Agent — Worked Project Example](agentic-ai-project-example-harper.md)
- [Module 1 — System Boundaries](agentic-ai-module-01-system-boundaries.md)
- [Module 4 — Agent Evaluation](agentic-ai-module-04-agent-evaluation.md)
- [Module 5 — Durable Runs and Recovery](agentic-ai-module-05-durable-runs-and-recovery.md)
- [Module 7 — Security Threat Model](agentic-ai-module-07-agent-security-threat-model.md)
- [Module 8 — Production Architecture and Operations](agentic-ai-module-08-production-architecture-and-operations.md)
- [Module 9 — Orchestration and Multi-Agent Design](agentic-ai-module-09-orchestration-and-multi-agent-design.md)
- [Module 10 — Context, Retrieval, and Memory](agentic-ai-module-10-context-retrieval-and-memory.md)
- [Module 11 — Unstructured Data, RAG, and Optimization](agentic-ai-module-11-data-rag-and-optimization.md)
- [Module 12 — Senior Architecture Practicum](agentic-ai-module-12-senior-architecture-practicum.md)
- [Anthropic: Tool Use with Prompt Caching](https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-use-with-prompt-caching)
- [Anthropic: Compaction Overview](https://platform.claude.com/docs/en/build-with-claude/compaction)
- [Anthropic: Manage Tool Context](https://platform.claude.com/docs/en/agents-and-tools/tool-use/manage-tool-context)
