import time

import anyio


def _wait_for_research_terminal(client, headers, research_id: str, timeout_s: float = 15.0):
    started = time.time()
    last = None
    while time.time() - started < timeout_s:
        r = client.get(f"/api/research/{research_id}", headers=headers)
        assert r.status_code == 200
        last = r.json()
        research = last.get('research') or {}
        st = research.get('stageStatus')
        if st in ('completed', 'failed'):
            return last
        time.sleep(0.2)
    return last


def test_create_list_get_research(client, session_headers):
    # create
    c = client.post('/api/research', headers=session_headers, json={'prompt': 'Test prompt'})
    assert c.status_code == 200
    rid = c.json().get('researchId')
    assert rid and rid.startswith('research_')

    # list
    lst = client.get('/api/research', headers=session_headers)
    assert lst.status_code == 200
    items = lst.json().get('items')
    assert isinstance(items, list)
    assert any(it.get('researchId') == rid for it in items)

    # get
    g = client.get(f'/api/research/{rid}', headers=session_headers)
    assert g.status_code == 200
    data = g.json()
    assert 'research' in data
    assert data['research']['researchId'] == rid


def test_run_research_pipeline_mock(client, session_headers, use_mock_agents):
    c = client.post('/api/research', headers=session_headers, json={'prompt': 'Mock pipeline prompt'})
    rid = c.json()['researchId']

    # Reduce flakiness: force validation to pass.
    from api import state as api_state

    sid = session_headers['X-MAARS-SESSION-ID']
    session = api_state.sessions.get(sid)
    if session and getattr(session, 'runner', None):
        session.runner.VALIDATION_PASS_PROBABILITY = 1.0
        session.runner.MAX_FAILURES = 1

    run = client.post(f'/api/research/{rid}/run', headers=session_headers, json={'format': 'markdown'})
    assert run.status_code in (200, 409)

    final = _wait_for_research_terminal(client, session_headers, rid, timeout_s=20.0)
    assert final is not None
    research = final.get('research') or {}
    assert research.get('researchId') == rid
    assert research.get('currentIdeaId')
    if str(research.get('stage') or '').strip().lower() in ('plan', 'execute', 'paper'):
        assert research.get('currentPlanId')

    # We don't strictly require completion here (execution may take longer on slower machines),
    # but response must be well-formed.
    assert 'idea' in final
    assert 'plan' in final
    assert 'execution' in final
    assert 'outputs' in final
    assert 'paper' in final


def test_stop_and_retry_research_pipeline(client, session_headers, use_mock_agents):
    c = client.post('/api/research', headers=session_headers, json={'prompt': 'Stop/retry prompt'})
    assert c.status_code == 200
    rid = c.json()['researchId']

    run = client.post(f'/api/research/{rid}/run', headers=session_headers, json={'format': 'markdown'})
    assert run.status_code in (200, 409)

    stop = client.post(f'/api/research/{rid}/stop', headers=session_headers)
    assert stop.status_code == 200
    stop_payload = stop.json() or {}
    assert stop_payload.get('success') is True

    # Retry should be accepted (may finish fast in mock mode).
    retry = client.post(f'/api/research/{rid}/retry', headers=session_headers, json={'format': 'markdown'})
    assert retry.status_code in (200, 409)

    # Ensure research can still be fetched and is well-formed.
    g = client.get(f'/api/research/{rid}', headers=session_headers)
    assert g.status_code == 200
    data = g.json()
    assert (data.get('research') or {}).get('researchId') == rid


def test_stage_run_blocks_when_predecessor_not_completed(client, session_headers):
    c = client.post('/api/research', headers=session_headers, json={'prompt': 'Prerequisite gating prompt'})
    assert c.status_code == 200
    rid = c.json()['researchId']

    # Fresh research is at refine/idle; execute must be blocked.
    run_execute = client.post(
        f'/api/research/{rid}/stage/execute/run',
        headers=session_headers,
        json={'format': 'markdown'},
    )
    assert run_execute.status_code == 400
    err = (run_execute.json() or {}).get('error', '')
    assert 'Cannot start' in err
    assert 'plan' in err

    # Paper must also be blocked while execute is not completed.
    run_paper = client.post(
        f'/api/research/{rid}/stage/paper/run',
        headers=session_headers,
        json={'format': 'markdown'},
    )
    assert run_paper.status_code == 400


def test_delete_research_cleans_execution_sandbox_and_volume(client, session_headers, monkeypatch):
    create_resp = client.post('/api/research', headers=session_headers, json={'prompt': 'Cleanup delete prompt'})
    assert create_resp.status_code == 200
    research_id = create_resp.json()['researchId']

    idea_id = 'idea_cleanup_case'
    plan_id = 'plan_cleanup_case'
    run_id = 'exec_cleanup_case'

    from db import (
        get_execution_task_step_dir,
        list_task_attempt_memories,
        save_task_attempt_memory,
        update_research_stage,
    )

    async def _seed_research_links() -> None:
        await update_research_stage(
            research_id,
            stage='execute',
            stage_status='completed',
            current_idea_id=idea_id,
            current_plan_id=plan_id,
            error=None,
        )

    anyio.run(_seed_research_links)

    anyio.run(
        save_task_attempt_memory,
        research_id,
        "1_1",
        1,
        {
            "attempt": 1,
            "phase": "execution",
            "error": "max turns",
            "willRetry": True,
            "ts": int(time.time() * 1000),
        },
    )
    before_mem = anyio.run(list_task_attempt_memories, research_id)
    assert len(before_mem) == 1

    step_dir = get_execution_task_step_dir(run_id, '1_1')
    step_dir.mkdir(parents=True, exist_ok=True)
    (step_dir / 'container-meta.json').write_text(
        '{"ideaId":"idea_cleanup_case","planId":"plan_cleanup_case","taskId":"1_1","executionRunId":"exec_cleanup_case"}',
        encoding='utf-8',
    )
    sandbox_root = step_dir.parent.parent
    assert sandbox_root.exists()

    delete_resp = client.delete(f'/api/research/{research_id}', headers=session_headers)
    assert delete_resp.status_code == 200
    assert delete_resp.json().get('success') is True

    assert not sandbox_root.exists(), 'research delete should remove execution sandbox root'
    after_mem = anyio.run(list_task_attempt_memories, research_id)
    assert after_mem == []


def test_retry_cleans_data_but_resume_does_not(client, session_headers, monkeypatch):
    create_resp = client.post('/api/research', headers=session_headers, json={'prompt': 'Retry resume distinction'})
    assert create_resp.status_code == 200
    rid = create_resp.json()['researchId']

    from db import update_research_stage

    async def _seed_state() -> None:
        await update_research_stage(
            rid,
            stage='execute',
            stage_status='stopped',
            current_idea_id='idea_rr_distinct',
            current_plan_id='plan_rr_distinct',
            error=None,
        )

    anyio.run(_seed_state)

    from api.routes import research as research_route

    cleanup_calls = []
    started = []

    async def fake_cleanup(idea_id, plan_id, stage):
        cleanup_calls.append((idea_id, plan_id, stage))
        return {'success': True}

    def fake_start(**kwargs):
        started.append(kwargs)

    monkeypatch.setattr(research_route, 'clear_research_stage_data_for_retry', fake_cleanup)
    monkeypatch.setattr(research_route, '_start_stage_pipeline_task', fake_start)

    retry_resp = client.post(f'/api/research/{rid}/stage/execute/retry', headers=session_headers, json={'format': 'markdown'})
    assert retry_resp.status_code == 200
    assert cleanup_calls and cleanup_calls[-1] == ('idea_rr_distinct', 'plan_rr_distinct', 'execute')
    assert started and started[-1].get('reset_start_stage') is True

    cleanup_calls.clear()
    resume_resp = client.post(f'/api/research/{rid}/stage/execute/resume', headers=session_headers, json={'format': 'markdown'})
    assert resume_resp.status_code == 200
    assert cleanup_calls == []
    assert started and started[-1].get('reset_start_stage') is False


def test_resume_requires_same_stage_and_stopped_or_failed(client, session_headers):
    create_resp = client.post('/api/research', headers=session_headers, json={'prompt': 'Resume guard'})
    assert create_resp.status_code == 200
    rid = create_resp.json()['researchId']

    from db import update_research_stage

    async def _seed_completed_state() -> None:
        await update_research_stage(
            rid,
            stage='execute',
            stage_status='completed',
            current_idea_id='idea_resume_guard',
            current_plan_id='plan_resume_guard',
            error=None,
        )

    anyio.run(_seed_completed_state)

    resp = client.post(f'/api/research/{rid}/stage/execute/resume', headers=session_headers, json={'format': 'markdown'})
    assert resp.status_code == 409
    err = (resp.json() or {}).get('error', '')
    assert 'Resume only applies' in err
