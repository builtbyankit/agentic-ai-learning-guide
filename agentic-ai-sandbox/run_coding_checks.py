"""Failure-focused acceptance checks for the coding reference solutions."""
import asyncio
from coding_solutions import Evidence, Step, ToolCallAssembler, pack_evidence, run_dag


def must_raise(fn, exception=ValueError):
    try:
        fn()
    except exception:
        return
    raise AssertionError('Expected a rejected operation')


async def scheduler_checks():
    active = peak = 0
    trace = []
    async def work(step, dependencies):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        try:
            await asyncio.sleep(0)
            trace.append((step.step_id, sorted(dependencies)))
            if step.step_id == 'bad':
                raise RuntimeError('Sensitive internal details must not be returned')
            return step.step_id.upper()
        finally:
            active -= 1
    steps = [Step('a'), Step('b'), Step('join', ('a','b')), Step('bad'), Step('skip',('bad',)), Step('skip2',('skip',))]
    result = await run_dag(steps, work, concurrency=2)
    assert peak == 2 and active == 0
    assert result['join']['status'] == 'complete' and ('join',['a','b']) in trace
    assert result['bad'] == {'status':'failed','error_type':'RuntimeError'}
    assert result['skip']['status'] == result['skip2']['status'] == 'blocked'
    assert not any(key.startswith('skip') for key, _ in trace)
    before = len(trace)
    for invalid in ([Step('a',('b',)),Step('b',('a',))], [Step('a'),Step('a')], [Step('x',('missing',))], [Step('write',effect='write')]):
        try:
            await run_dag(invalid, work)
        except ValueError:
            pass
        else:
            raise AssertionError('Invalid plan launched work')
    assert len(trace) == before
    entered = asyncio.Event()
    cleaned = asyncio.Event()
    async def slow(step, deps):
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleaned.set()
    task = asyncio.create_task(run_dag([Step('slow')], slow))
    await entered.wait()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    assert cleaned.is_set()
    cleaned.clear()
    try:
        await run_dag([Step('slow')], slow, timeout=0.01)
    except asyncio.TimeoutError:
        pass
    else:
        raise AssertionError('Deadline was ignored')
    assert cleaned.is_set()
    print('PASS scheduler: dependency order, concurrency, partial failure, cycle/write rejection, cancellation and deadline')


def stream_checks():
    stream = ToolCallAssembler()
    events = [
        {'kind':'begin','id':'a','name':'get_order'}, {'kind':'begin','id':'b','name':'search_policy'},
        {'kind':'delta','id':'a','text':'{"order_'}, {'kind':'delta','id':'b','text':'{"topic":"returns"}'},
        {'kind':'delta','id':'a','text':'ref":"ORD-100"}'}, {'kind':'end','id':'b'}, {'kind':'end','id':'a'},
    ]
    for event in events:
        assert stream.feed(event) is None
    assert stream.finish()[0]['arguments'] == {'order_ref':'ORD-100'}
    for events in ([{'kind':'delta','id':'x','text':'{}'}],
                   [{'kind':'begin','id':'x','name':'tool'}]*2,
                   [{'kind':'begin','id':'x','name':'tool'}, {'kind':'delta','id':'x','text':'ééé'}]):
        broken = ToolCallAssembler(max_bytes=4)
        must_raise(lambda: [broken.feed(event) for event in events])
        must_raise(broken.finish)
    incomplete = ToolCallAssembler()
    incomplete.feed({'kind':'begin','id':'x','name':'tool'})
    must_raise(incomplete.finish)
    malformed = ToolCallAssembler()
    for event in [{'kind':'begin','id':'x','name':'tool'},{'kind':'delta','id':'x','text':'[]'},{'kind':'end','id':'x'}]:
        malformed.feed(event)
    must_raise(malformed.finish)
    print('PASS stream: interleaved calls, duplicate/unknown/incomplete rejection, object shape and UTF-8 bounds')


def evidence_checks():
    items = [Evidence('required',40,0,required=True), Evidence('large',100,10), Evidence('small',20,9), Evidence('forbidden',10,100,allowed=False)]
    assert pack_evidence(items,budget=100,reserve=30) == (['required','small'],60)
    must_raise(lambda: pack_evidence(items,budget=50,reserve=20))
    must_raise(lambda: pack_evidence([Evidence('private',1,1,allowed=False,required=True)],budget=10))
    must_raise(lambda: pack_evidence([Evidence('dup',1,1)]*2,budget=10))
    print('PASS evidence: reserve, required facts, oversized optional skip, denial and duplicate rejection')


def main():
    asyncio.run(scheduler_checks())
    stream_checks()
    evidence_checks()


if __name__ == '__main__':
    main()
