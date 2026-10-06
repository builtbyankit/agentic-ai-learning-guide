"""Reproduce the numerical workbook using small, deterministic calculations."""
import json,math


def softmax(logits,temperature=1.0):
    if temperature <= 0 or not logits or not all(math.isfinite(value) for value in logits):
        raise ValueError('Finite logits and positive temperature required')
    scaled=[value/temperature for value in logits]
    maximum=max(scaled)
    values=[math.exp(value-maximum) for value in scaled]
    return [value/sum(values) for value in values]


def cosine(a,b):
    if len(a)!=len(b) or not a or not all(math.isfinite(value) for value in a+b):
        raise ValueError('Compatible finite nonempty vectors required')
    denominator=math.sqrt(sum(value*value for value in a)*sum(value*value for value in b))
    if denominator==0:
        raise ValueError('Cosine is undefined for a zero vector')
    return sum(x*y for x,y in zip(a,b))/denominator



def nucleus(probabilities, p):
    if not 0 < p <= 1:
        raise ValueError('top-p must be in (0, 1]')
    selected=[]
    mass=0.0
    for index in sorted(range(len(probabilities)),key=lambda i:(-probabilities[i],i)):
        selected.append(index)
        mass+=probabilities[index]
        if mass>=p:
            break
    return selected,[probabilities[index]/mass for index in selected]


def ranking_metrics(ranked, relevant, k):
    if not relevant or len(ranked)!=len(set(ranked)) or k<1:
        raise ValueError('Use unique labeled sources and positive k')
    top=ranked[:k]
    hits=sum(item in relevant for item in top)
    reciprocal=next((1/rank for rank,item in enumerate(ranked,1) if item in relevant),0.0)
    dcg=sum(1/math.log2(rank+1) for rank,item in enumerate(top,1) if item in relevant)
    ideal=sum(1/math.log2(rank+1) for rank in range(1,min(len(relevant),k)+1))
    return hits/k,hits/len(relevant),reciprocal,dcg/ideal


def calculate():
    probabilities=softmax([math.log(4),math.log(2),0])
    colder=softmax([math.log(4),math.log(2),0],0.5)
    assert all(math.isclose(a,b) for a,b in zip(probabilities,[4/7,2/7,1/7]))
    assert all(math.isclose(a,b) for a,b in zip(colder,[16/21,4/21,1/21]))
    weights=softmax([1/math.sqrt(2),0])
    output=[weights[0]*10,weights[1]*20]
    assert math.isclose(cosine([1,1],[1,0]),1/math.sqrt(2))
    try:
        cosine([0,0],[1,0])
    except ValueError:
        pass
    else:
        raise AssertionError('Zero-vector similarity should not be fabricated')
    idf=math.log(1+(10-2+0.5)/(2+0.5))
    bm25=idf*(3*2.2)/(3+1.2*(1-0.75+0.75*100/100))
    selected,filtered=nucleus(probabilities,0.8)
    precision,recall,reciprocal,ndcg=ranking_metrics(["B","A","D","C"],{"A","C"},3)
    assert selected==[0,1] and math.isclose(filtered[0],2/3)
    assert math.isclose(precision,1/3) and math.isclose(recall,1/2)
    lora=8*(4096+4096)
    base=4096*4096
    kv_bytes=2*32*8*128*4096*4*2
    assert lora==65536 and kv_bytes==2**31
    return {'decoding_T1':probabilities,'decoding_T05':colder,
            'top_p_08_selected':selected,'top_p_08_renormalized':filtered,
            'attention_weights':weights,'attention_output':output,
            'cosine_example':cosine([1,1],[1,0]),'bm25_one_term':bm25,
            'ranking_P_at_3':precision,'ranking_Recall_at_3':recall,'ranking_MRR':reciprocal,'ranking_nDCG_at_3':ndcg,
            'lora_parameters_one_matrix':lora,'lora_fraction_one_matrix':lora/base,
            'lora_32_layers_two_matrices':lora*32*2,'KV_cache_GiB':kv_bytes/2**30,
            'vector_GB_primary_two_replicas':1200000*1024*4*3*3/10**9,
            'scope':'Illustrative arithmetic only; no training, retrieval benchmark or accelerator run'}


if __name__=='__main__':
    print(json.dumps(calculate(),indent=2))
