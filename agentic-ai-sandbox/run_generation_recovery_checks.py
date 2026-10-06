"""Fake-provider checks for partial trials, explicit retries and preserved usage."""
import copy,json,tempfile
from pathlib import Path
from types import SimpleNamespace
from generate_answer_candidates import run_trial


class FakeClient:
    def __init__(self, fail_on=None, malformed=False):
        self.messages=self
        self.calls=0
        self.fail_on=fail_on
        self.malformed=malformed
    def create(self,**kwargs):
        self.calls+=1
        if self.calls==self.fail_on:
            raise RuntimeError('Do not persist internal provider details')
        text='invalid JSON' if self.malformed else '{"status":"abstained","claims":[],"limitation_code":"insufficient"}'
        return SimpleNamespace(stop_reason='end_turn', content=[SimpleNamespace(type='text',text=text)],
                               usage=SimpleNamespace(input_tokens=20,output_tokens=10))


def main():
    base=Path(__file__).parent/'evals'
    dataset=json.loads((base/'answer_quality_scenarios.json').read_text())
    dataset['cases']=dataset['cases'][:2]
    with tempfile.TemporaryDirectory() as temporary:
        target=Path(temporary)/'trial.json'
        first=FakeClient(fail_on=2)
        assert run_trial(dataset,first,'fake-model',target) is False
        assert len(json.loads(target.read_text()))==1
        checkpoint=target.with_suffix('.json.checkpoint.json')
        saved=json.loads(checkpoint.read_text())
        assert saved['cases'][dataset['cases'][0]['id']]['attempts'][0]['usage']['input_tokens']==20
        assert saved['cases'][dataset['cases'][1]['id']]['attempts'][0]['usage'] is None
        no_retry=FakeClient()
        assert run_trial(dataset,no_retry,'fake-model',target,resume=True) is False and no_retry.calls==0
        resumed=FakeClient()
        assert run_trial(dataset,resumed,'fake-model',target,resume=True,retry_failed=True) is True
        assert resumed.calls==1, 'Completed case was repeated'
        saved=json.loads(checkpoint.read_text())
        assert len(saved['cases'][dataset['cases'][1]['id']]['attempts'])==2
        changed=copy.deepcopy(dataset)
        changed['cases'][0]['question']='Changed question'
        try:
            run_trial(changed,FakeClient(),'fake-model',target,resume=True)
        except ValueError:
            pass
        else:
            raise AssertionError('Changed trial resumed')
        broken=Path(temporary)/'malformed.json'
        assert run_trial(dataset,FakeClient(malformed=True),'fake-model',broken) is False
        state=json.loads(broken.with_suffix('.json.checkpoint.json').read_text())
        assert state['cases'][dataset['cases'][0]['id']]['attempts'][0]['usage']['output_tokens']==10
    print('PASS generation recovery: partial success retained, failed usage marked unknown, retry opt-in, completed cases skipped, signature checks and malformed-response usage')


if __name__=='__main__':
    main()
