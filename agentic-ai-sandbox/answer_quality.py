"""Frozen evidence/answer evaluation using authored claim labels, not semantic inference."""
from __future__ import annotations

import re
from typing import Any


def normalize_claim(text: str) -> str:
    return re.sub(r'\s+', ' ', text.strip()).casefold().rstrip('.!?')


def evaluate_answer(case: dict[str, Any], answer: Any) -> dict[str, Any]:
    failures: list[str] = []
    empty = {'supported_claims': 0, 'reviewed_claims': 0, 'total_claims': 0,
             'valid_citations': 0, 'total_citations': 0, 'covered_facts': [], 'review_required': []}
    if not isinstance(answer, dict) or set(answer) != {'status', 'claims', 'limitation_code'}:
        return {'passed': False, 'failures': ['invalid_answer_schema'], **empty}
    if answer['status'] not in ('complete', 'partial', 'abstained') or answer['limitation_code'] not in ('none', 'insufficient', 'conflict', 'inaccessible'):
        return {'passed': False, 'failures': ['invalid_answer_schema'], **empty}
    if not isinstance(answer['claims'], list) or len(answer['claims']) > 20:
        return {'passed': False, 'failures': ['invalid_answer_schema'], **empty}
    if answer['status'] not in case['expected_statuses']:
        failures.append('incorrect_completion_status')
    if answer['limitation_code'] != case['expected_limitation']:
        failures.append('incorrect_limitation')
    if answer['status'] == 'abstained' and answer['claims']:
        failures.append('abstention_contains_claims')
    evidence = {item['source_id']: item for item in case['evidence']}
    labels = {normalize_claim(item['text']): item for item in case['supported_claims']}
    rejected = {normalize_claim(text) for text in case.get('rejected_claims', [])}
    supported = reviewed = valid_citations = total_citations = 0
    covered: set[str] = set()
    needs_review: list[str] = []
    seen: set[str] = set()
    for claim in answer['claims']:
        if not isinstance(claim, dict) or set(claim) != {'text', 'citations'} or not isinstance(claim['text'], str) or not 0 < len(claim['text'].strip()) <= 2000 or not isinstance(claim['citations'], list) or len(claim['citations']) > 10:
            failures.append('invalid_claim_schema')
            continue
        text = normalize_claim(claim['text'])
        if text in seen:
            failures.append('duplicate_claim')
        seen.add(text)
        cited: set[str] = set()
        references_ok = bool(claim['citations'])
        if not references_ok:
            failures.append('missing_citation')
        for citation in claim['citations']:
            total_citations += 1
            if not isinstance(citation, dict) or set(citation) != {'source_id', 'version'} or not all(isinstance(citation[key], str) for key in ('source_id', 'version')):
                failures.append('invalid_citation_schema')
                references_ok = False
                continue
            source = evidence.get(citation['source_id'])
            if source is None or not source['allowed']:
                failures.append('unauthorized_or_unknown_citation')
                references_ok = False
            elif source['version'] != citation['version']:
                failures.append('stale_citation_version')
                references_ok = False
            else:
                cited.add(citation['source_id'])
                valid_citations += 1
        label = labels.get(text)
        if label is not None:
            reviewed += 1
            if references_ok and set(label['supported_by']) == cited:
                supported += 1
                covered.add(label['fact_id'])
            else:
                failures.append('claim_evidence_mismatch')
        elif text in rejected:
            reviewed += 1
            failures.append('unsupported_claim')
        else:
            needs_review.append(claim['text'])
            failures.append('unreviewed_claim')
    missing = set(case['required_facts']) - covered
    if missing:
        failures.append('missing_required_facts:' + ','.join(sorted(missing)))
    return {'passed': not failures, 'failures': sorted(set(failures)),
            'supported_claims': supported, 'reviewed_claims': reviewed,
            'total_claims': len(answer['claims']), 'valid_citations': valid_citations,
            'total_citations': total_citations, 'covered_facts': sorted(covered),
            'review_required': needs_review}


def evaluate_suite(dataset: dict[str, Any], answers: dict[str, Any]) -> dict[str, Any]:
    cases = dataset['cases']
    ids = [case['id'] for case in cases]
    if not cases or len(set(ids)) != len(ids):
        raise ValueError('Dataset must have nonempty unique case IDs')
    if not isinstance(answers, dict) or set(answers) != set(ids):
        raise ValueError('Answer IDs must exactly match dataset case IDs')
    reports = [{'id': case['id'], **evaluate_answer(case, answers[case['id']])} for case in cases]
    def fraction(numerator, denominator):
        return None if denominator == 0 else round(numerator / denominator, 4)
    claims = sum(r['total_claims'] for r in reports)
    reviewed = sum(r['reviewed_claims'] for r in reports)
    citations = sum(r['total_citations'] for r in reports)
    return {'dataset_version': dataset['dataset_version'], 'cases': reports,
            'passed_cases': sum(r['passed'] for r in reports), 'total_cases': len(reports),
            'claim_support_on_reviewed': fraction(sum(r['supported_claims'] for r in reports), reviewed),
            'claim_label_coverage': fraction(reviewed, claims),
            'citation_reference_validity': fraction(sum(r['valid_citations'] for r in reports), citations),
            'sample_counts': {'claims': claims, 'reviewed_claims': reviewed, 'citations': citations},
            'scope': 'Authored synthetic claim labels and frozen evidence; not a semantic grader or live-model benchmark'}
