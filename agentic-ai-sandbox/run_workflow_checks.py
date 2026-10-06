"""Check stronger workflow safety and evidence collection on authored regressions."""
from evals.common import create_scenario_runtime, grade_result, load_dataset
from run_workflow_baseline import ImprovedWorkflowPlanner
from support_agent import AgentLoop, RunContext


def main():
    count = 0
    for dataset in ('evals/live_scenarios_v7.json', 'evals/workflow_challenge_scenarios.json'):
        _, scenarios = load_dataset(dataset)
        for scenario in scenarios:
            runtime = create_scenario_runtime(scenario)
            task_id = 'workflow-check-' + scenario.scenario_id
            result = AgentLoop(runtime).run(scenario.request, RunContext(subject_id=scenario.subject_id, task_id=task_id), ImprovedWorkflowPlanner(scenario.request))
            failures, _ = grade_result(scenario, result, runtime, task_id)
            assert not failures, (scenario.scenario_id, failures)
            if scenario.scenario_id == 'deduplicate-reference':
                assert len(result.tool_trace) == 1, 'Repeated identifiers must not multiply reads'
            count += 1
    print(f'PASS {count}/{count} workflow cases; authored regression data only, zero model calls')


if __name__ == '__main__':
    main()
