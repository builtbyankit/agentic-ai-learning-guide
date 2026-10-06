# LLM Engineering Foundations for Agent Builders

Use this companion before Module 3 and revisit it before coding interviews. The goal is to explain mechanisms, predict failures, and choose experiments. The twelve modules cover the application around the model; this chapter supplies the model and retrieval vocabulary that application engineers must understand.

## 1. Tokens, attention, and context

A tokenizer maps text into model-specific token IDs. A token is not a word: identifiers, punctuation, languages, and whitespace can tokenize differently. Count the actual serialized request with the relevant tokenizer or provider tool, including instructions, schemas, history, evidence, and output reserve. Character/word limits are useful input guards but do not establish a token budget.

An autoregressive language model predicts a distribution over the next token given prior tokens. Repeating this process produces an answer or a serialized tool call. Training on plausible continuations does not guarantee truthful statements, correct citations, or permission-aware behavior.

Attention uses query/key compatibility to weight value representations; multiple heads can represent different relationships. A causal mask prevents a position from attending to future positions in decoder generation. Feed-forward layers, positional information, normalization, and residual paths also contribute. Conventional full attention has quadratic pairwise interactions in sequence length; optimized kernels can reduce memory traffic without making every architecture's total cost linear. The original Transformer is described in [Attention Is All You Need](https://arxiv.org/abs/1706.03762).

A large supported context window does not imply equally good use of every token. Evaluate distractors, evidence position, conflicting instructions, and long histories. More context can increase latency, spend, and irrelevant information. A model can emit a schema-valid tool call that is still incorrect or unauthorized.

**Interview drill:** A 100,000-token context model misses a refund condition. Test retrieval coverage, evidence placement, contradictory versions, and task wording before simply adding tokens. Keep the authoritative refund decision outside the model.

## 2. Decoding and structured output

Temperature changes the sharpness of the token distribution; top-p sampling restricts the sampled set by cumulative probability. These tune generation behavior, not factual correctness. A low-temperature run is not a universal reproducibility guarantee: runtime, model updates, tie-breaking, and backend execution can change outputs. Check which decoding controls the selected model actually supports.

Separate three checks: valid transport/protocol, valid JSON/schema, and valid business meaning. Constrained output can reduce structural failures, but cannot establish ownership or that a claim is supported. Test refusal, truncation, partial streaming, unexpected stop reason, and duplicate tool-call IDs. Never execute a partial streamed tool argument.

**Coding drill:** Given JSON with a valid amount and another customer's order ID, identify which checks belong to schema validation, domain authorization, approval, and execution. Build one failure case for each.

## 3. Embeddings, ranking, and indexes

An embedding maps an input to a vector trained for a particular objective. Retrieval quality depends on the model, domain, language, query/document encoding, and distance function. A feature-hashing vector preserves token signals; it is not a learned semantic embedding. Query and document vectors must use compatible models and dimensions.

For nonzero vectors, cosine similarity is their normalized dot product. Dot product on unit-normalized vectors gives the same ordering as cosine. Without normalization, vector magnitude affects inner product. A similarity value is not a calibrated probability that evidence answers a question.

A bi-encoder embeds candidates independently and permits precomputation. A cross-encoder-style reranker jointly scores a query and candidate, trading more query-time computation for a richer pairwise comparison. Keep candidate recall and reranking quality separate: a reranker cannot recover an absent source. Evaluate top-k at the unit you label: chunks, documents, or distinct sources.

BM25-style lexical retrieval captures term matches with term-frequency and document-length effects. Dense retrieval can help semantic paraphrases while missing exact identifiers or negation. RRF combines ranks rather than assuming raw lexical and dense scores share a scale. Fusion improves candidate discovery only if measured; it does not create an abstention rule.

Exact vector search is a useful correctness baseline. HNSW explores a graph; IVF limits search to selected partitions; PQ compresses representations. Search parameters change recall, memory, build time, and latency. Filter selectivity and deletion behavior require separate testing, and implementations differ. See [Faiss index documentation](https://github.com/facebookresearch/faiss/wiki/Faiss-indexes).

**Numerical drill:** Relevant sources are A and C; top results are B, A, A, D, C. At chunk rank 3, A is found but C is missing. If deduplicated source rank is used, the list becomes B, A, D, C. State the unit before reporting Recall@k. Do not silently compare source-level and chunk-level results.

## 4. Prompting, RAG, fine-tuning, and LoRA

| Requirement | First experiment | Why and what to measure |
| --- | --- | --- |
| Clear format or bounded reasoning behavior | Prompt/examples plus schema checks | Cheap to change; measure task and structural error |
| Frequently changing or permissioned knowledge | Retrieval from authoritative sources | Supports provenance, freshness, access, and deletion |
| Consistent specialized behavior on many examples | Supervised fine-tuning after a prompt baseline | Needs governed labels, stable targets, and held-out evaluation |
| Lower adaptation resource use | Parameter-efficient adaptation such as LoRA | Compare quality, trainable state, memory, and serving complexity |
| Lower serving memory | Quantization after a floating-point baseline | Check kernel/hardware compatibility and task regression |

Fine-tuning can teach behavior and domain patterns; it does not guarantee factual recall, citations, or immediate removal of learned private information. RAG and fine-tuning can be combined. Do not train on a holdout, embed inaccessible material into a broadly shared prompt, or use fine-tuning to replace authorization.

LoRA represents selected weight updates with low-rank factors while freezing base weights. Rank and target layers influence adaptation capacity and resource use. Merged and unmerged serving have different operational implications. QLoRA combines a quantized base with low-rank adaptation; base compression does not eliminate optimizer, activation, or adapter memory. See [LoRA](https://arxiv.org/abs/2106.09685), [QLoRA](https://arxiv.org/abs/2305.14314), and the [PEFT conceptual guide](https://huggingface.co/docs/peft/main/en/conceptual_guides/lora).

**Interview drill:** A company wants new policies reflected tomorrow and replies in a consistent support style. Start with RAG for policy updates and prompting for style; consider adaptation only after systematic residual behavior errors and suitable labeled data.

## 5. Inference and serving

Prefill processes the input; decode generates tokens incrementally. Measure time to first token, time per output token, and time to complete the task separately. Streaming can improve perceived responsiveness while leaving total compute unchanged. A response displayed early can still be wrong; consequential actions need verified complete arguments and authorization.

KV caches retain attention keys/values to avoid recomputing prior representations during decoding. Their memory grows with active sequences and retained length, with details depending on architecture, precision, and sharding. Continuous batching interleaves active work to improve utilization, but changes queueing and latency trade-offs. Paged allocation addresses cache management and fragmentation; see [vLLM's Paged Attention design](https://docs.vllm.ai/en/latest/design/paged_attention/).

Weight memory is only one part of serving capacity. Also budget KV cache, activations/workspaces, runtime overhead, replicas, and failure headroom. Quantization may improve footprint, but speed depends on supported kernels and workload. Compare managed and self-hosted inference on data requirements, workload, quality, engineering effort, and total cost rather than GPU prices alone.

**Sizing drill:** An 8-billion-parameter model at two bytes per weight needs approximately 16 GB for raw weights. This is neither total accelerator memory nor proof that it fits safely on a 16 GB device. Explain the missing terms and measure the actual serving footprint.

## 6. Tool protocols and MCP

Function calling expresses tool intent and results within a model-provider protocol. MCP standardizes interactions between hosts, clients, and servers for capabilities such as tools and resources. Protocol compatibility does not certify a server, its descriptions, or its authorization behavior. Identity, server trust, credentials, egress, output limits, and tool-level permissions remain application concerns.

For an interview, explain discovery versus invocation, trusted actor context versus model arguments, and what happens when a server changes its tool schema or returns malicious text. Use the [MCP authorization specification](https://modelcontextprotocol.io/specification/latest/basic/authorization) for transport-specific current requirements; pin the protocol version in an implementation review.

## Exit criteria

Without notes, explain one token budget, one embedding/reranking failure, the RAG-versus-adaptation decision, and a prefill/decode bottleneck. Implement cosine ranking with zero-vector handling and compare it with a lexical baseline. Write a model-change evaluation covering normal tasks, refusals, malformed output, stale sources, and authorization. Show how a low-temperature, schema-valid answer can still fail.
