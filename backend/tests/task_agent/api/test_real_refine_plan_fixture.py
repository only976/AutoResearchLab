def test_real_refine_plan_fixture_can_seed_and_generate_execution(client, session_headers, seed_real_refine_plan):
    idea_id = seed_real_refine_plan["ideaId"]
    plan_id = seed_real_refine_plan["planId"]

    idea_resp = client.get(f"/api/idea?ideaId={idea_id}", headers=session_headers)
    assert idea_resp.status_code == 200
    idea = (idea_resp.json() or {}).get("idea") or {}
    assert isinstance(idea.get("refined_idea"), str)
    assert idea.get("refined_idea", "").strip()

    plan_resp = client.get(f"/api/plan?ideaId={idea_id}&planId={plan_id}", headers=session_headers)
    assert plan_resp.status_code == 200
    plan = (plan_resp.json() or {}).get("plan") or {}
    tasks = plan.get("tasks") or []
    assert isinstance(tasks, list)
    assert len(tasks) >= 5

    ex_resp = client.post(
        "/api/execution/generate-from-plan",
        headers=session_headers,
        json={"ideaId": idea_id, "planId": plan_id},
    )
    assert ex_resp.status_code == 200
    execution = (ex_resp.json() or {}).get("execution") or {}
    assert isinstance(execution.get("tasks"), list)
    assert len(execution["tasks"]) >= 5

    layout_resp = client.post(
        "/api/plan/layout",
        headers=session_headers,
        json={"ideaId": idea_id, "planId": plan_id, "execution": execution},
    )
    assert layout_resp.status_code == 200
    layout = (layout_resp.json() or {}).get("layout") or {}
    assert isinstance(layout.get("treeData"), list)
    assert len(layout["treeData"]) >= 5
