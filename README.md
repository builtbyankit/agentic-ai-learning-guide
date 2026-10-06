# Agentic AI Mastery

A senior-level learning path for agentic AI engineering and system architecture. It combines design lessons, a Python/Anthropic adapter, offline evaluations, and a sandboxed support-agent implementation.

## Learning path

1. Read the [Mastery Roadmap](agentic-ai-mastery-roadmap.md) and [Module 1: System Boundaries](agentic-ai-module-01-system-boundaries.md).
2. Work through Modules 2–8 for tool loops, Anthropic integration, evaluations, durable execution, approvals, security, and production operations.
3. Continue with [Module 9: Orchestration](agentic-ai-module-09-orchestration-and-multi-agent-design.md), [Module 10: Context and Memory](agentic-ai-module-10-context-retrieval-and-memory.md), and [Module 11: Unstructured Data, RAG, and Optimization](agentic-ai-module-11-data-rag-and-optimization.md).
4. Complete [Module 12: Senior Architecture Practicum](agentic-ai-module-12-senior-architecture-practicum.md) as the final design dossier and review.
5. Use the [Python sandbox](agentic-ai-sandbox/README.md) for hands-on exercises and evaluation workflows.

See the [latest offline evaluation report](agentic-ai-evaluation-report-2026-10-06.md) for executed results, retrieval failure analysis, production-evidence gaps, and the recommended next experiments. The RAG lab defaults to offline hashing and includes an explicitly enabled Voyage semantic-embedding adapter; live provider evaluation remains pending.

## Repository structure

```text
agentic-ai-mastery-roadmap.md
agentic-ai-module-*.md
agentic-ai-sandbox/
  support_agent.py
  durable_state.py
  approval_outbox.py
  policy_retrieval.py
  rag_pipeline.py
  voyage_embedder.py
  evals/
  run_*.py
```

## Sandbox setup

The deterministic and retrieval labs use Python's standard library. From `agentic-ai-sandbox/`, run the commands in its README. The live Anthropic evaluator needs the SDK and credentials and makes real API calls; it is optional and is not required for the offline exercises.

Evaluation data is synthetic. Passing authored cases demonstrates only those cases; it does not establish production reliability or readiness. The roadmap and Module 12 distinguish measured evidence from assumptions and unverified integrations.
