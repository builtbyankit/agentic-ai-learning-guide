"""Regression checks for answer correctness, review coverage, and citation boundaries."""
from pathlib import Path
import copy,json
from answer_quality import evaluate_answer,evaluate_suite


def main():
    base=Path(__file__).parent/'evals'
    dataset=json.loads((base/'answer_quality_scenarios.json').read_text())
    good=json.loads((base/'answer_quality_good.json').read_text())
    bad=json.loads((base/'answer_quality_bad.json').read_text())
    good_report=evaluate_suite(dataset,good)
    bad_report=evaluate_suite(dataset,bad)
    assert good_report['passed_cases']==8
    assert bad_report['passed_cases']==0
    failures={r['id']:r['failures'] for r in bad_report['cases']}
    assert 'unauthorized_or_unknown_citation' in failures['inaccessible']
    assert 'stale_citation_version' in failures['stale-citation']
    assert 'unsupported_claim' in failures['valid-citation-wrong-claim']
    assert bad_report['citation_reference_validity']>bad_report['claim_support_on_reviewed']
    answer=copy.deepcopy(good['supported-return'])
    answer['claims'][0]['text']='You can send eligible items back within a month.'
    review=evaluate_answer(dataset['cases'][0],answer)
    assert 'unreviewed_claim' in review['failures'] and review['review_required']
    assert review['reviewed_claims']==0, 'Unlabeled paraphrases require review, not invented semantic judgment'
    for malformed in (None,[],{}, {'status':'complete','claims':[],'limitation_code':'none','extra':'ignored'}):
        assert 'invalid_answer_schema' in evaluate_answer(dataset['cases'][0],malformed)['failures']
    answer=copy.deepcopy(good['supported-return'])
    answer['claims'][0]['citations'][0]['source_id']=['not','a','string']
    assert 'invalid_citation_schema' in evaluate_answer(dataset['cases'][0],answer)['failures']
    try:
        evaluate_suite(dataset,{})
    except ValueError:
        pass
    else:
        raise AssertionError('Missing cases must not silently improve scores')
    answer=copy.deepcopy(good['supported-return'])
    answer['claims'][0]['citations']=[]
    assert 'missing_citation' in evaluate_answer(dataset['cases'][0],answer)['failures']
    answer=copy.deepcopy(good['multi-source'])
    answer['claims'][0]['citations'].append({'source_id':'delivery','version':'v2'})
    assert 'claim_evidence_mismatch' in evaluate_answer(dataset['cases'][1],answer)['failures'], 'Permitted irrelevant sources cannot establish claim support'
    from types import SimpleNamespace
    from generate_answer_candidates import generate_answer
    class FakeClient:
        def __init__(self):
            self.messages = self
            self.request = None
        def create(self, **kwargs):
            self.request = kwargs
            return SimpleNamespace(stop_reason='end_turn', content=[SimpleNamespace(type='text', text=json.dumps(good['inaccessible']))], usage=SimpleNamespace(input_tokens=10, output_tokens=5))
    fake = FakeClient()
    generated, metrics = generate_answer(dataset['cases'][4], fake, 'fake-model')
    packet = json.loads(fake.request['messages'][0]['content'])
    assert packet['evidence'] == [], 'Forbidden evidence must not reach the generation provider'
    assert 'supported_claims' not in packet and 'required_facts' not in packet, 'Gold labels must not leak into generation'
    assert generated == good['inaccessible'] and metrics['output_tokens'] == 5
    print('PASS 8 good fixtures accepted; 8 bad fixtures rejected; review/schema/coverage and fake generation boundaries checked')


if __name__=='__main__':
    main()
