"""Reproduce the intent bug-to-fix case study with original and current workflows."""
from support_agent import AgentLoop,RunContext,ToolRuntime
from run_workflow_baseline import FixedWorkflowPlanner,ImprovedWorkflowPlanner


CASES = (
    ("I don't want a refund for ORD-100. Just tell me its status.", 'negation'),
    ('Please refund ORD-100 because the notebook arrived damaged.', 'damage'),
    ('Is ORD-100 eligible for a refund, and where is it now?', 'combined'),
)


def main():
    totals={}
    for label,planner_type in [('original',FixedWorkflowPlanner),('current',ImprovedWorkflowPlanner)]:
        passes=0
        for i,(request,kind) in enumerate(CASES):
            runtime=ToolRuntime()
            task_id=f'{label}-case-study-{i}'
            result=AgentLoop(runtime).run(request,RunContext(subject_id='customer-ada',task_id=task_id),planner_type(request))
            tools=[event['tool'] for event in result.tool_trace]
            reviews=runtime.review_count(task_id)
            if kind=='negation':
                passed=reviews==0 and 'prepare_refund_proposal' not in tools and 'shipped' in result.answer
            elif kind=='damage':
                passed=reviews==1 and 'request_human_review' in tools
            else:
                passed=reviews==0 and 'eligible' in result.answer and 'shipped' in result.answer and {'get_order','check_refund_eligibility'}<=set(tools)
            passes+=passed
            print(f'{label} {kind}: meets_outcomes={passed}; tools={tools}; reviews={reviews}')
        totals[label]=passes
    assert totals=={'original':0,'current':3},totals
    print('PASS reference case study: original 0/3; current 3/3; authored synthetic regressions, no live model')


if __name__=='__main__':
    main()
