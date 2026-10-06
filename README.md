# Agentic AI Mastery Guide

A senior-level, project-based learning path for agentic AI engineering and system architecture. It covers system boundaries, tool use, Anthropic with Python, evaluation, durable execution, human approval, security, production operations, orchestration, memory, unstructured data, RAG, optimization, and a senior architecture practicum.

The lessons, runnable exercises, synthetic datasets, and evaluation reports live together in this repository. The material emphasizes explicit control flow, measurable behavior, security boundaries, and honest reporting of what has and has not been validated.

## Start here

1. Read the [mastery roadmap](agentic-ai-mastery-roadmap.md) to understand the sequence and expected outcomes.
2. Work through the [12-module curriculum](#curriculum), in order or by topic.
3. Run the [Python sandbox](agentic-ai-sandbox/README.md) alongside the lessons. Its deterministic exercises use Python's standard library.
4. Review the [offline evaluation report](agentic-ai-evaluation-report-2026-10-07.md) for measured results, retrieval failure analysis, evidence gaps, and next experiments.

The support-agent sandbox uses synthetic data. Offline checks do not establish production reliability; live Anthropic calls are optional, require your own credentials, and may incur usage charges. The live provider evaluation has not been run for the results in this repository. See each report for its scope and limitations.

## Curriculum

| Module | Topic |
| --- | --- |
| [01](agentic-ai-module-01-system-boundaries.md) | System boundaries and agent design |
| [02](agentic-ai-module-02-tool-loop-and-evaluation.md) | Tool loops and evaluation |
| [03](agentic-ai-module-03-anthropic-adapter.md) | Anthropic adapter in Python |
| [04](agentic-ai-module-04-agent-evaluation.md) | Agent evaluation |
| [05](agentic-ai-module-05-durable-runs-and-recovery.md) | Durable runs and recovery |
| [06](agentic-ai-module-06-human-approval-outbox.md) | Human approval and transactional outbox |
| [07](agentic-ai-module-07-agent-security-threat-model.md) | Agent security and threat modeling |
| [08](agentic-ai-module-08-production-architecture-and-operations.md) | Production architecture and operations |
| [09](agentic-ai-module-09-orchestration-and-multi-agent-design.md) | Orchestration and multi-agent design |
| [10](agentic-ai-module-10-context-retrieval-and-memory.md) | Context, retrieval, and memory |
| [11](agentic-ai-module-11-data-rag-and-optimization.md) | Unstructured data, RAG, and optimization |
| [12](agentic-ai-module-12-senior-architecture-practicum.md) | Senior architecture practicum |

## Interview preparation

Use the [Agentic AI Interview Preparation guide](agentic-ai-interview-preparation.md) for senior-level questions and model answers on architecture, tools, durability, orchestration, unstructured data and RAG, security, evaluation, optimization, and system-design scenarios.

The [Harper worked project example](agentic-ai-project-example-harper.md) shows a complete enterprise knowledge and code assistant design, from problem framing and high-level architecture through ingestion, ACL-aware retrieval, typed orchestration, code sketches, evaluation, and rollout. It separates the attached notes' resume-backed scope from proposed implementation choices that need verification.

## Run the sandbox

From the repository root:

```bash
cd agentic-ai-sandbox
python3 run_evals.py
python3 run_retrieval_checks.py
python3 run_rag_checks.py
```

For the full set of offline checks, setup details, and optional provider integrations, see the [sandbox guide](agentic-ai-sandbox/README.md) and [evaluation guide](agentic-ai-sandbox/evals/README.md). PDF parsing is optional and uses `requirements-pdf.txt`. No API key is needed for the offline exercises.

## Preview the course website

The static course site is built from the Markdown already in this repository. To preview it locally, use Python 3.10 or newer:

```bash
python3 -m pip install -r requirements-docs.txt
python3 scripts/prepare_pages_docs.py
mkdocs serve
```

Open the local address printed by MkDocs. The preparation command refreshes the generated `.pages-docs/` folder from the repository sources; rerun it after changing course or sandbox files. To build the same site artifact used by CI:

```bash
python3 scripts/prepare_pages_docs.py
mkdocs build --strict
```

The generated documentation staging folder and site output (`site/`) are ignored by Git.

## Publish with GitHub Pages

A pull request runs a strict documentation build. Pushes to the repository's default branch build and deploy the site; the workflow can also be started manually from GitHub Actions on the default branch. The published Pages site is public, so keep credentials, private documents, and real customer data out of the repository.

To enable the first deployment:

1. Push this repository to GitHub.
2. In **Settings → Pages**, set **Build and deployment → Source** to **GitHub Actions**.
3. Push a change to the default branch, or choose the default branch and run **Build and deploy Pages** from the Actions tab.

The workflow uses GitHub's Pages artifact deployment flow and does not need a provider API key. See [GitHub's custom Actions publishing guide](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages) if repository settings or organization policies differ.


## Contributing

Issues and pull requests are welcome. Useful contributions include clearer explanations, reviewed technical references, additional synthetic evaluation cases, and reproducible improvements to the exercises.

- Keep examples and test data synthetic; never add real customer data, secrets, API keys, or private policy documents.
- Include the command and environment used when reporting evaluation results. Distinguish authored-case results from evidence of production performance.
- For behavior changes, update the relevant lesson or sandbox guide and explain security, reliability, and cost implications where applicable.
- Keep pull requests focused and describe how a reviewer can reproduce the change.

## License

This project is licensed under the [MIT License](LICENSE). Copyright © 2026 Ankit Kumar.
