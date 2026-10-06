"""Dependency-free reference answers for bounded read scheduling, streams and evidence."""
from __future__ import annotations

import asyncio
import json
import math
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class Step:
    step_id: str
    depends_on: tuple[str, ...] = ()
    effect: str = 'read'


def validate_plan(steps: list[Step], concurrency: int):
    if not isinstance(concurrency, int) or isinstance(concurrency, bool) or not 1 <= concurrency <= 8 or len(steps) > 20:
        raise ValueError('Invalid plan limits')
    ids = {step.step_id for step in steps}
    if len(ids) != len(steps) or any(not step.step_id or step.effect != 'read' for step in steps):
        raise ValueError('Only uniquely named read steps are supported')
    if any(not set(step.depends_on) <= ids for step in steps):
        raise ValueError('Unknown dependency')
    remaining = {step.step_id: set(step.depends_on) for step in steps}
    resolved = set()
    while remaining:
        ready = {key for key, deps in remaining.items() if deps <= resolved}
        if not ready:
            raise ValueError('Dependency cycle')
        resolved.update(ready)
        remaining = {key: deps for key, deps in remaining.items() if key not in ready}


async def run_dag(steps: list[Step], work: Callable, *, concurrency=2, timeout=5.0):
    """Execute authorized read callbacks; skip descendants of failed dependencies.

    work(step, dependency_values) must perform its own authorization. Deadline and
    caller cancellation stop local tasks; they cannot revoke already-issued remote calls.
    """
    validate_plan(steps, concurrency)
    if timeout <= 0:
        raise ValueError('Deadline must be positive')

    async def execute():
        pending = {step.step_id: step for step in steps}
        running = {}
        outcomes = {}

        async def invoke(step):
            deps = {key: outcomes[key]['value'] for key in step.depends_on}
            try:
                return {'status': 'complete', 'value': await work(step, deps)}
            except Exception as exc:
                return {'status': 'failed', 'error_type': type(exc).__name__}

        try:
            while pending or running:
                for key, step in list(pending.items()):
                    if any(dep in outcomes and outcomes[dep]['status'] != 'complete' for dep in step.depends_on):
                        outcomes[key] = {'status': 'blocked'}
                        del pending[key]
                    elif len(running) < concurrency and all(dep in outcomes for dep in step.depends_on):
                        running[asyncio.create_task(invoke(step))] = key
                        del pending[key]
                if running:
                    done, _ = await asyncio.wait(running, return_when=asyncio.FIRST_COMPLETED)
                    for task in done:
                        outcomes[running.pop(task)] = task.result()
                elif pending:
                    # Blocked chains may require another propagation pass.
                    continue
            return outcomes
        finally:
            for task in running:
                task.cancel()
            await asyncio.gather(*running, return_exceptions=True)
    return await asyncio.wait_for(execute(), timeout=timeout)


class ToolCallAssembler:
    """Normalized begin/delta/end events. Never yields executable partial arguments."""

    def __init__(self, max_calls=8, max_bytes=4096):
        if not 1 <= max_calls <= 8 or not 1 <= max_bytes <= 65536:
            raise ValueError('Invalid stream limits')
        self.max_calls, self.max_bytes = max_calls, max_bytes
        self.calls = {}
        self.failed = False

    def feed(self, event):
        if self.failed:
            raise ValueError('Stream previously failed')
        try:
            if not isinstance(event, dict) or event.get('kind') not in ('begin', 'delta', 'end'):
                raise ValueError('Unknown event')
            key = event.get('id')
            if not isinstance(key, str) or not 0 < len(key) <= 128:
                raise ValueError('Invalid call ID')
            kind = event['kind']
            if kind == 'begin':
                if set(event) != {'kind', 'id', 'name'} or not isinstance(event['name'], str) or not 0 < len(event['name']) <= 128 or key in self.calls or len(self.calls) >= self.max_calls:
                    raise ValueError('Invalid or duplicate begin')
                self.calls[key] = {'name': event['name'], 'text': '', 'ended': False}
            else:
                call = self.calls.get(key)
                if call is None or call['ended']:
                    raise ValueError('Missing begin or already ended')
                if kind == 'delta':
                    if set(event) != {'kind', 'id', 'text'} or not isinstance(event['text'], str):
                        raise ValueError('Invalid delta')
                    if len((call['text'] + event['text']).encode('utf-8')) > self.max_bytes:
                        raise ValueError('Arguments exceed byte budget')
                    call['text'] += event['text']
                else:
                    if set(event) != {'kind', 'id'}:
                        raise ValueError('Invalid end')
                    call['ended'] = True
        except Exception:
            self.failed = True
            raise

    def finish(self):
        if self.failed or any(not call['ended'] for call in self.calls.values()):
            raise ValueError('Stream failed or incomplete')
        result = []
        for key, call in self.calls.items():
            try:
                arguments = json.loads(call['text'])
                if not isinstance(arguments, dict):
                    raise ValueError('Tool arguments must be an object')
            except (ValueError, TypeError):
                self.failed = True
                raise ValueError('Invalid complete arguments') from None
            result.append({'id': key, 'name': call['name'], 'arguments': arguments})
        return result


@dataclass(frozen=True)
class Evidence:
    evidence_id: str
    tokens: int  # Actual tokenizer count supplied by the caller, including formatting.
    priority: float
    allowed: bool = True
    required: bool = False


def pack_evidence(items: list[Evidence], *, budget: int, reserve: int = 0):
    """Required evidence first, then greedy relevance; never silently drop required facts."""
    if not isinstance(budget, int) or not isinstance(reserve, int) or budget < 0 or reserve < 0 or reserve > budget:
        raise ValueError('Invalid token budget')
    ids = [item.evidence_id for item in items]
    if len(ids) != len(set(ids)) or any(not item.evidence_id or not isinstance(item.tokens, int) or isinstance(item.tokens, bool) or item.tokens <= 0 or not math.isfinite(item.priority) for item in items):
        raise ValueError('Invalid evidence IDs or token counts')
    if any(item.required and not item.allowed for item in items):
        raise ValueError('Required evidence inaccessible; hand off')
    limit = budget - reserve
    selected = [item for item in items if item.required]
    used = sum(item.tokens for item in selected)
    if used > limit:
        raise ValueError('Required evidence cannot fit; fetch smaller authoritative evidence or hand off')
    for item in sorted((item for item in items if item.allowed and not item.required), key=lambda item: (-item.priority, item.evidence_id)):
        if used + item.tokens <= limit:
            selected.append(item)
            used += item.tokens
    return [item.evidence_id for item in selected], used
