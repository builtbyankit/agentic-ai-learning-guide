"""Grade supplied answers separately from retrieval using frozen labeled evidence."""
import argparse
import hashlib
import json
from pathlib import Path
from answer_quality import evaluate_suite


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', default='evals/answer_quality_scenarios.json')
    parser.add_argument('--answers', default='evals/answer_quality_good.json')
    parser.add_argument('--output')
    args = parser.parse_args()
    base = Path(__file__).parent
    def resolve(name):
        path = Path(name)
        return path if path.is_absolute() else base / path
    dataset_path, answers_path = resolve(args.dataset), resolve(args.answers)
    report = evaluate_suite(json.loads(dataset_path.read_text()), json.loads(answers_path.read_text()))
    report['dataset_sha256'] = hashlib.sha256(dataset_path.read_bytes()).hexdigest()
    report['answers_sha256'] = hashlib.sha256(answers_path.read_bytes()).hexdigest()
    print(json.dumps(report, indent=2))
    if args.output:
        target = Path(args.output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, indent=2) + '\n')
    return 0 if report['passed_cases'] == report['total_cases'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
