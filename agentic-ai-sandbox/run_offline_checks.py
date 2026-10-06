"""Run dependency-free contract/regression checks; no live calls or demo databases."""
from pathlib import Path
import subprocess,sys

CHECKS = (
    'run_evals.py', 'run_adapter_checks.py', 'run_durability_checks.py',
    'run_approval_checks.py', 'run_security_checks.py', 'run_retrieval_checks.py',
    'run_rag_checks.py', 'run_embedding_checks.py', 'run_eval_runner_checks.py',
    'run_cost_model_checks.py', 'run_workflow_checks.py', 'run_answer_eval_checks.py',
)


def main():
    base=Path(__file__).parent
    for name in CHECKS:
        result=subprocess.run([sys.executable,'-B',str(base/name)],cwd=base,
                              capture_output=True,text=True,timeout=90)
        if result.returncode:
            print(result.stdout+result.stderr)
            print(f'FAIL {name}: exit {result.returncode}')
            return 1
        print(f'PASS {name}',flush=True)
    print(f'{len(CHECKS)}/{len(CHECKS)} offline suites passed; live providers, optional PDF, and load tests excluded')
    return 0


if __name__=='__main__':
    raise SystemExit(main())
