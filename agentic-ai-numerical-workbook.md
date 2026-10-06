# Numerical Workbook: LLMs, Retrieval and Serving

Attempt each question before reading its solution. Explain the units, assumptions and what the result does not establish. These are small mathematical examples, not provider settings or measured hardware performance. Reproduce them with `python3 run_numerical_exercises.py` from the sandbox.

## 1. Token budget

**Question:** A hypothetical model accepts a combined 16,000-token input/output budget. Instructions use 1,000, tools 1,500, history 2,000, and output reserve 2,000. Each rendered evidence chunk is 700 tokens. How many fit?

**Solution:** Evidence allowance is `16,000 − 1,000 − 1,500 − 2,000 − 2,000 = 9,500`. At most `floor(9,500/700) = 13` chunks fit, using 9,100 tokens and leaving 400. Count the actual rendered citation metadata and separators. Provider limits may separate input/output or impose a lower output ceiling; this example assumes a combined limit explicitly.

**Follow-up:** The required policy exception is in chunk 14. Do not silently drop it. Fetch a smaller authoritative section, reduce reconstructible history, or hand off. The `pack_evidence` solution implements the required-evidence budget boundary.

## 2. Temperature and top-p

**Question:** Three token logits are `[ln(4), ln(2), 0]`. Calculate softmax at temperatures 1 and 0.5. At temperature 1, apply top-p 0.8.

**Solution:** At T=1, exponentials are `[4,2,1]`, so probabilities are `[4/7,2/7,1/7]`, approximately `[0.5714,0.2857,0.1429]`. At T=0.5, logits double: `[16,4,1]/21`, approximately `[0.7619,0.1905,0.0476]`. For top-p 0.8, the first token alone has mass 0.5714, and the first two reach 0.8571. Keep those two and renormalize to `[2/3,1/3]`.

**Failure analysis:** Sharper sampling makes the most probable token more likely, not more truthful. Changing both temperature and top-p obscures which change affected behavior. Check actual provider semantics and supported controls. Use a numerically stable softmax by subtracting the maximum scaled logit.

## 3. One attention calculation

**Question:** Query `q=[1,0]`; keys `k1=[1,0]`, `k2=[0,1]`; values `v1=[10,0]`, `v2=[0,20]`. Use scaled dot-product attention with key dimension 2.

**Solution:** Scores are `[1/√2,0]`. Softmax gives weights approximately `[0.66976,0.33024]`. The weighted value output is `[6.69762,6.60477]`. If the second position is masked, its score is excluded from the softmax and the output becomes `[10,0]`.

This illustrates one attention head, not the whole Transformer, training cost or production context behavior. The attention mechanism is described in [Attention Is All You Need](https://arxiv.org/abs/1706.03762).

**Follow-up:** A large attention weight is not proof of causal explanation, factual support, or authorization. Those require other evidence and system controls.

## 4. Cosine versus inner product

**Question:** Compare query `[1,1]` with documents A=`[1,0]`, B=`[10,0]`, C=`[0,1]`.

**Solution:** All have cosine `1/√2 ≈ 0.7071` with the query. Raw dot products are 1, 10 and 1, so B ranks higher by magnitude. Unit normalization makes dot-product and cosine ordering agree for nonzero vectors. A zero vector has undefined cosine; reject it or use a documented fallback rather than inventing a score.

**Follow-up:** Similarity 0.7071 is not a 70.71% chance of answer correctness. Calibrate answerability using labeled positives/negatives and the full retrieval/generation path.

## 5. BM25 and rank fusion

**Question:** For one term, use N=10 documents, document frequency n=2, term frequency tf=3, document length=average length=100, k1=1.2, b=0.75. Use the positive-IDF convention `ln(1+(N−n+0.5)/(n+0.5))`.

**Solution:** IDF is `ln(4.4) ≈ 1.48160`. Length normalization equals 1; the term-frequency factor is `3×2.2/(3+1.2) ≈ 1.57143`. The contribution is approximately 2.32824. Implementations can use different conventions; state the formula rather than comparing unqualified scores across engines.

**RRF question:** Document A ranks 1 lexically and 4 densely; B ranks 3 and 1. With fusion constant 60, A scores `1/61+1/64 ≈ 0.03202`, B scores `1/63+1/61 ≈ 0.03227`. B wins. Neither value is a cosine score or calibrated probability.

## 6. Ranking and abstention metrics

**Question:** Relevant source set is `{A,C}`; distinct-source results are `[B,A,D,C]`. Calculate Precision@3, Recall@3, reciprocal rank and binary nDCG@3.

**Solution:** Top three contain one relevant source. Precision@3=`1/3`; Recall@3=`1/2`; reciprocal rank=`1/2`. DCG@3 is `1/log2(3) ≈ 0.63093`. Ideal DCG puts both relevant sources first: `1+1/log2(3) ≈ 1.63093`. nDCG@3 is approximately 0.38685. MRR averages reciprocal rank over queries; one query's value is not a dataset estimate.

If raw chunks are `[B,A,A,D,C]`, do not silently treat the duplicated A as two relevant sources. State chunk/source rank and deduplication before reporting k.

**Abstention question:** On 100 answerable and 40 unanswerable questions, a system answers 90 of the former and abstains on 30 of the latter. Abstention precision is `30/(30+10)=75%`; abstention recall on unanswerable questions is `30/40=75%`. Ten unsupported answer attempts remain. The 90 answerable responses still need correctness and support evaluation; answerability alone does not prove they succeeded.

## 7. LoRA parameter count

**Question:** A frozen dense matrix is 4,096×4,096. A LoRA update uses rank 8. How many parameters are trainable for that matrix? What if query/value projections are adapted across 32 layers?

**Solution:** Low-rank factors contain `r×din + dout×r = 8×(4,096+4,096) = 65,536` parameters. The original matrix has 16,777,216, so the update is 0.390625% of that matrix's count. Two such projections across 32 layers have 4,194,304 adapter parameters. This excludes biases, other target modules and trainable output heads; it is not the percentage of the entire model.

LoRA freezes base weights and learns low-rank updates; see [the original paper](https://arxiv.org/abs/2106.09685). Trainable-parameter count alone does not determine total training memory: optimizer state, activations, base representation, batching and sharding also matter.

## 8. KV cache and weight memory

**Question:** Assume 32 layers, 8 KV heads, head dimension 128, sequence length 4,096, batch size 4, and two bytes per cached scalar. Estimate unsharded K/V cache bytes.

**Solution:** `2 × layers × KV heads × head dimension × sequence length × batch × bytes = 2×32×8×128×4,096×4×2 = 2,147,483,648 bytes = 2 GiB`. The leading 2 accounts for keys and values. Use KV heads rather than query heads for grouped-query attention. Allocation, padding, parallelism, cache precision and runtime overhead can change actual resident memory.

An 8-billion-parameter model at two bytes/weight has 16 GB decimal raw weight memory. Adding the illustrative KV cache alone raises the subtotal to approximately 18.15 GB decimal, before workspaces, activations, runtime and safety headroom. Four-bit raw weights would be about 4 GB before scale/metadata overhead; this is not a throughput prediction.

## 9. Capacity calculation correction

The capacity companion's 1.2 million 1,024-dimensional float32 vectors occupy 4.9152 GB raw. With an assumed index factor of 3 and **one primary plus two replicas**, total modeled allocation is `4.9152×3×3 = 44.2368 GB`. Two total copies would instead be 29.4912 GB. State whether replicas include or exclude the primary. The factor is hypothetical and excludes other stores and rebuild space.

## Self-check

For each solution, explain a changed assumption, a likely mistake, and a validation method. Numerical mastery means choosing the correct model and denominators, not memorizing these values. Complete the capacity exercise next and defend the effect of route mix, token quotas, retry tails and reviewer throughput.
