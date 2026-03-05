import time


def _seed_idea(client, idea_id: str, text: str):
    from db import save_idea

    # direct DB write to keep API tests focused
    import anyio

    anyio.run(save_idea, {"idea": text, "keywords": [], "papers": []}, idea_id)


def test_plan_layout_and_generate_execution(client, session_headers, use_mock_agents):
    idea_id = 'idea_test'
    plan_id = 'plan_test'
    _seed_idea(client, idea_id, 'Test idea')

    # Kick plan generation (background)
    r = client.post('/api/plan/run', headers=session_headers, json={'ideaId': idea_id, 'skipQualityAssessment': True})
    assert r.status_code == 200
    pid = r.json()['planId']

    # Poll until plan exists
    started = time.time()
    plan = None
    while time.time() - started < 10:
        g = client.get(f'/api/plan?ideaId={idea_id}&planId={pid}')
        assert g.status_code == 200
        plan = g.json().get('plan')
        if plan and plan.get('tasks') and len(plan['tasks']) > 1:
            break
        time.sleep(0.2)

    assert plan is not None
    assert isinstance(plan.get('tasks'), list)

    # Generate execution from plan
    ex = client.post('/api/execution/generate-from-plan', json={'ideaId': idea_id, 'planId': pid})
    assert ex.status_code == 200
    execution = ex.json().get('execution')
    assert execution and isinstance(execution.get('tasks'), list)

    # Build layout via plan/layout
    layout = client.post('/api/plan/layout', headers=session_headers, json={'execution': execution, 'ideaId': idea_id, 'planId': pid})
    assert layout.status_code == 200
    assert layout.json().get('layout')
