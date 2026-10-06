# Agentic AI and System Design: Mastery Roadmap

## Learning objective

Become able to take a real problem from requirements to a reliable agentic system: choose the right level of autonomy, design its tools and state, control risk and cost, measure behavior, and explain the trade-offs.

The central design rule throughout this roadmap is: **use the least autonomous architecture that reliably meets the requirement**. A fixed workflow is often better for a predictable task; a model-directed agent is useful when the steps genuinely depend on what it discovers. Add complexity only when evaluation shows a benefit.

## Course progress

- **Module 1 — system boundaries:** Worked design for a bounded support-resolution assistant is available in [Module 1](agentic-ai-module-01-system-boundaries.md).
- **Module 2 — tool loop and evaluation:** A provider-neutral harness and nine scripted scenarios are available in the [sandbox](agentic-ai-sandbox/README.md), with interpretation notes in [Module 2](agentic-ai-module-02-tool-loop-and-evaluation.md). All nine pass; live-model behavior remains unevaluated.
- **Module 3 — live-model adapter:** The sandbox now includes an Anthropic Messages API adapter and a ten-scenario live evaluator. Three fake-client adapter checks cover tool wiring and optional prompt-cache instrumentation; the live evaluator has not been run. See [Module 3](agentic-ai-module-03-anthropic-adapter.md).
- **Module 4 — evaluation design:** The live cases are now versioned data; [Module 4](agentic-ai-module-04-agent-evaluation.md) covers outcome and trajectory graders, human trace review, production monitoring, and comparison against a fixed-workflow baseline.
- **Module 5 — durable execution:** The sandbox now journals runs and idempotent review writes in SQLite; five crash/restart checks pass. See [Module 5](agentic-ai-module-05-durable-runs-and-recovery.md). Multi-worker coordination and payment execution remain out of scope for this teaching prototype.
- **Module 6 — human approval and retry-safe actions:** The sandbox binds operator approval to an exact refund proposal, atomically queues the approved action, and simulates leased outbox delivery with provider idempotency. Six approval/outbox checks pass; the provider is mocked. See [Module 6](agentic-ai-module-06-human-approval-outbox.md).
- **Module 7 — agent security threat model:** Added bounded requests and tool inputs, task/expiry checks for review enqueueing, and seven groups of adversarial security assertions. The shared live dataset is now v4 with ten cases; the deterministic workflow passes 10/10, while the live model evaluation remains unrun. See [Module 7](agentic-ai-module-07-agent-security-threat-model.md).
- **Module 8 — production architecture and operations:** The architecture, lifecycle, release gates, observability, incident response, rollout/rollback, and readiness review are documented in [Module 8](agentic-ai-module-08-production-architecture-and-operations.md). This is a design artifact; it is not deployed, load-tested, or ready for a production launch.
- **Supplemental Module 9 — orchestration and multi-agent design:** Compares workflows, a single agent, handoffs, manager/specialist, and parallel fan-out; provides a delegation contract and evaluation plan. Its support-case recommendation is to retain the workflow until evidence supports added orchestration. See [Module 9](agentic-ai-module-09-orchestration-and-multi-agent-design.md).
- **Supplemental Module 10 — context, retrieval, and memory:** Separates trusted runtime scope, working context, durable run state, and cross-run memory. The sandbox implements a fingerprinted lexical policy catalog, eight retrieval contract checks, and an eleven-query retrieval evaluation scoring 100% exact coverage on its authored cases. See [Module 10](agentic-ai-module-10-context-retrieval-and-memory.md).
- **Supplemental Module 11 — unstructured data, RAG, and optimization:** Adds Markdown/static-HTML preprocessing, structure-aware and table-preserving chunking, a persistent SQLite vector-search lab with trusted tenant/classification filters, BM25-style lexical search, RRF, separate development/holdout evaluations, and current agent optimizations including Anthropic prompt caching, deferred tool loading, compaction, and context editing. The expanded 15-entry synthetic corpus and 20-query holdout compare dense placeholder, lexical, and hybrid retrieval; lexical covers the required positive sources but fails one hard negative, while dense and hybrid fail no-answer abstention. The optional batched Voyage adapter passes eight fake-transport checks but has not been called live; PDF/OCR and Office ingestion remain unimplemented, the offline embedder is not semantic, and the two authorization cases do not establish tenant isolation. See [Module 11](agentic-ai-module-11-data-rag-and-optimization.md).
- **Evaluation refinement:** The live runner now supports 1–10 trials per case with isolated task IDs and aggregated pass rates, failure counts, regular/cache token usage, and model latency. Reports record prompt/tool hashes. Three runner checks pass using a scripted planner; no provider API calls were made.

## Capstone status

The sandbox currently demonstrates a bounded Python harness, an Anthropic Messages API adapter with optional cache instrumentation, deterministic evaluations, SQLite run recovery, a mocked approval/outbox delivery path, versioned lexical policy retrieval, and an offline SQLite-backed vector/lexical/hybrid lab. The fixed workflow passes all ten cases in `support-agent-live-v4` without model calls. The RAG holdout shows that retrieval quality and no-answer rejection need work; the vector lab does not claim semantic relevance or production-scale ANN performance.

The objective is still in progress. The most important remaining evidence is a multi-trial live Anthropic evaluation with trace review, a real embedding-provider comparison on a larger labeled corpus, representative mixed/ambiguous tasks that establish whether an agent improves on the workflow, and agreed real-world identity, traffic, SLO, and budget requirements. Real operator authentication, provider integration, load tests, and operational drills would also be needed before any production claim.

## The system model to learn

An agentic system is more than a prompt and a model. Treat it as a probabilistic controller inside a deterministic envelope:

```text
User / event
    ↓
Policy + task contract ──→ context and state
    ↓                          ↑
Model decision → tool broker → external systems
    ↑                   ↓
    └── observation / result ──┘
    ↓
Stop, ask a person, or return a result

Across the whole path: permissions, budgets, tracing, evaluations, recovery
```

The model can propose the next step. Application code should own identity, permissions, validation, durable state, approval gates, budgets, and whether a consequential action is allowed to happen.

## Curriculum

Work through the modules in order. Each module ends with an artifact or demonstration; those artifacts become the capstone design.

### Senior engineer / AI architect depth

This track is for engineers who need to own a system across model behavior, APIs, data, reliability, security, and operations. A successful prompt demo is not mastery. For every design decision, name the assumption, failure mode, deterministic control, evaluation evidence, operational signal, and owner.

The sequence is Modules 1–8 for foundations, Module 9 for orchestration, Module 10 for context and memory, Module 11 for unstructured data/RAG/optimization, and Module 12 for the architecture practicum. The final artifact is a reviewable dossier with a launch-stage recommendation. See [Module 12 — Senior AI Engineer and Architect Practicum](agentic-ai-module-12-senior-architecture-practicum.md).

| Area | Design artifact | Evidence artifact |
|---|---|---|
| Product fit | Task taxonomy, autonomy boundary, baseline | Same-case workflow/agent comparison and kill criterion |
| Agent interface | Versioned tool contracts, schemas, permissions | Contract, malformed-input and trace checks |
| Data/context | Provenance, ACLs, memory lifecycle, retrieval design | Retrieval holdout, stale/deleted/cross-tenant checks |
| Execution | Run state machine, idempotency, leases, recovery | Crash/retry/concurrency and unknown-outcome drills |
| Evaluation | Grader contract, dataset governance, release thresholds | Calibrated outcomes/trajectories with sample counts |
| Security | Threat model, trust boundaries, data lifecycle | Red-team cases and deterministic invariant checks |
| Operations | SLOs, capacity/cost envelope, owners, runbooks | Load/failure drills, canary/rollback evidence |

Review each module with these questions: Is the model deciding only what requires judgment? Is identity or permission inferred from text? Can derived state be stale or leak across tenants? What breaks under retries or concurrent workers? Does evaluation exercise the actual model and full tool path? What signal tells an operator to disable or recover the feature?

### 1. Foundations: what makes a system agentic?

Learn the difference between a normal model call, a workflow, and an agent. Learn the basic loop: receive a task, choose an action, call a tool, observe the result, and continue or stop. Understand where model judgment helps and where deterministic code is safer.

**Checkpoint:** Given three use cases, justify whether each needs a single model call, a fixed workflow, or a dynamic agent. State the quality target and what evidence would change your decision.

### 2. Tool use and the agent-computer interface

Design tools with narrow purpose, clear names and descriptions, typed inputs, bounded outputs, explicit errors, and observable side effects. Learn function calling and MCP as ways to connect models to capabilities. Separate tool discovery and data access from permission to perform an action.

**Checkpoint:** Specify five tools for a mock support assistant. For each, define inputs, output shape, failure modes, required permission, and whether it changes external state. Include a read-only lookup and a consequential action.

### 3. Context, retrieval, and memory

Learn context selection, retrieval, summarization, conversation state, and durable task state. Distinguish information that belongs in the current model context from information that should live in a database or event log. Account for stale, irrelevant, sensitive, and untrusted content.

**Checkpoint:** Draw the data flow for a long-running task. Mark what is persisted, for how long, who can access it, and how the agent retrieves only what it needs.

Use [Supplemental Module 10](agentic-ai-module-10-context-retrieval-and-memory.md) for the current sandbox’s state map and context/retrieval evaluation checklist.

Use [Supplemental Module 11](agentic-ai-module-11-data-rag-and-optimization.md) to build the unstructured-data ingestion path and study chunking, vector retrieval, prompt caching, tool discovery, context compaction, and cost/latency optimization.

### 4. Orchestration and system architecture

Learn sequential workflows, routing, parallel work, evaluator loops, and orchestrator-worker patterns. Compare one agent with specialist agents. Use multiple agents only when separate context, independent work, or clear specialization improves quality, latency, or control enough to justify coordination overhead.

**Checkpoint:** Design two architectures for the same task—one single-agent and one multi-agent. Compare failure modes, latency, cost, traceability, and control. Recommend one with evidence you would gather.

Use [Supplemental Module 9](agentic-ai-module-09-orchestration-and-multi-agent-design.md) for the worked comparison and delegation contract.

### 5. Reliability and runtime behavior

Design the run loop, deadlines, iteration and token budgets, retries, idempotency, cancellation, durable checkpoints, resume behavior, and graceful degradation. Define what happens when a tool times out, returns malformed data, or partially completes an action. Make stopping conditions explicit.

**Checkpoint:** Walk through a failed tool call and a process restart. Show how the system avoids duplicate side effects and either resumes safely or asks a person.

### 6. Evaluation and observability

Build a representative task set before tuning. Measure outcomes as well as trajectories: task success, correct tool choice and arguments, policy compliance, unsupported claims, escalation quality, latency, and cost. Inspect traces to understand failures; use automated graders as aids and validate them against human judgments.

**Checkpoint:** Create a small evaluation plan with normal cases, edge cases, adversarial cases, and regression cases. For every metric, define how it is scored and what threshold blocks release.

### 7. Security, privacy, and human control

Study prompt injection through user content, retrieved documents, and tool outputs; excessive permissions; data exposure; confused-deputy behavior; unsafe code execution; and unbounded loops. Apply least privilege, input/output validation, sandboxing where relevant, action-specific approvals, audit logs, and explicit data retention rules.

**Checkpoint:** Threat-model the capstone. For each important asset, identify a threat, a preventive control, a detection signal, and a recovery path. Make the approval boundary concrete: what can happen automatically, and what requires a person?

### 8. Production system design

Design the service boundary, model/provider interface, tool broker, state store, queue or worker model, observability, access control, rollout, rollback, and operational ownership. Estimate cost and latency from measured traces. Plan how you will detect drift and turn production failures into evaluation cases.

**Checkpoint:** Present an architecture and an operations plan that another engineer could implement and operate. Include load assumptions, service-level targets, cost controls, alerts, and rollback criteria.

## Capstone: a support-resolution agent in a sandbox

Build or blueprint an agent that can answer questions using a mock knowledge base, look up an order, draft a response, and propose a refund or account change. Keep the system in a sandbox. Require explicit approval before consequential actions.

The final submission should include:

1. A problem statement, user journey, success measures, and a reason for choosing the architecture.
2. A component diagram and sequence for a successful run and at least two failure cases.
3. Tool contracts, state model, permissions, approval points, and stopping rules.
4. An evaluation set and results, including safety and regression cases.
5. A threat model, deployment outline, monitoring plan, and cost/latency estimate.
6. A short design review explaining the trade-offs and the next experiment you would run.

For senior-level completion, use the [Module 12 dossier](agentic-ai-module-12-senior-architecture-practicum.md) and include workload/SLO assumptions, versioned API/event contracts, retry/concurrency behavior, retrieval lifecycle, calibrated evaluations, a cost model, rollout stages, runbooks, owners, and evidence gaps. Label each claim as **implemented and measured**, **designed but unverified**, or **assumption**.

## Mastery rubric

You are approaching mastery when you can consistently:

- Choose between a direct model call, workflow, single agent, and multi-agent design using task evidence.
- Specify tool contracts and permissions clearly enough that another engineer can implement them.
- Explain where state lives and how runs recover from interruptions and partial failure.
- Measure behavior with representative evaluations and connect traces to concrete fixes.
- Identify security boundaries and prevent an agent from granting itself authority.
- Estimate operational costs and latency, define release criteria, and explain how the system will be monitored.
- Defend the architecture, including what you deliberately kept simple.
- Trace a requirement from source of truth through enforcement, evaluation, telemetry, and recovery ownership.
- Explain consistency, replay, idempotency, concurrency, deletion, and cache invalidation across service boundaries.
- Quantify cost and capacity from measured distributions; set per-run and per-tenant limits and safe degradation behavior.
- Distinguish an authored benchmark pass rate from a statistically meaningful reliability estimate.
- Give a staged launch recommendation that matches the evidence, with rollback criteria and named owners.

The final review rubric and dossier template are in [Module 12](agentic-ai-module-12-senior-architecture-practicum.md). A high average score does not compensate for an unaddressed authorization, privacy, or consequential-action failure.

## Recommended reading and implementation references

Read for stable design ideas first; use SDK documentation when implementing because APIs evolve.

- [Anthropic: Building effective agents](https://www.anthropic.com/engineering/building-effective-agents) — workflows, agents, and common composition patterns.
- [Anthropic: Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) — context selection and just-in-time retrieval.
- [OpenAI Agents SDK guide](https://developers.openai.com/api/docs/guides/agents/sdk) — code-first agent runtime, tools, orchestration, guardrails, state, and tracing.
- [OpenAI: Orchestration and handoffs](https://developers.openai.com/api/docs/guides/agents/orchestration) — choosing how specialists cooperate.
- [OpenAI: Evaluate agent workflows](https://developers.openai.com/api/docs/guides/agent-evals) — traces, graders, datasets, and evaluation runs.
- [Model Context Protocol architecture](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/docs/docs/2026-07-28/learn/architecture.mdx) — protocol roles and primitives.
- [OWASP Top 10 for Agentic Applications, 2026](https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/) — agent-specific security risks.

## First lesson: make the autonomy decision

For any proposed agent, answer these questions before choosing a framework:

1. What outcome does the user need, and how will we know it is correct?
2. Are the steps predictable enough to encode as a workflow?
3. What must the model decide dynamically, and what should ordinary code decide?
4. Which tools can read data, and which can change the world?
5. What is the maximum allowed spend, run time, and number of actions?
6. At what point must the system stop or ask a person?

**Exercise:** Pick a real task you want an agent to handle. Write a one-paragraph task definition, answer the six questions, then sketch the smallest architecture that could meet the goal. The next lesson can use that task as the running example.

## Senior-level completion note

The advanced track includes a final architecture dossier, review rubric, architecture decision record template, and launch-stage recommendation in [Module 12](agentic-ai-module-12-senior-architecture-practicum.md). Modules 1–11 also include senior engineering extensions so the deeper requirements are carried through the curriculum rather than isolated in the final practicum.
