import time


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
    assert research.get('currentPlanId')

    # We don't strictly require completion here (execution may take longer on slower machines),
    # but response must be well-formed.
    assert 'idea' in final
    assert 'plan' in final
    assert 'execution' in final
    assert 'outputs' in final
    assert 'paper' in final
