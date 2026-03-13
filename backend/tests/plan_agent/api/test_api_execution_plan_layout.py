def test_plan_layout_and_generate_execution_from_real_fixture(
    client,
    session_headers,
    use_mock_agents,
    seed_real_refine_plan,
):
    idea_id = seed_real_refine_plan["ideaId"]
    plan_id = seed_real_refine_plan["planId"]

    plan_resp = client.get(f"/api/plan?ideaId={idea_id}&planId={plan_id}", headers=session_headers)
    assert plan_resp.status_code == 200
    plan = (plan_resp.json() or {}).get("plan") or {}
    assert isinstance(plan.get("tasks"), list)
    assert len(plan["tasks"]) >= 5

    ex = client.post(
        "/api/execution/generate-from-plan",
        headers=session_headers,
        json={"ideaId": idea_id, "planId": plan_id},
    )
    assert ex.status_code == 200
    execution = (ex.json() or {}).get("execution") or {}
    assert isinstance(execution.get("tasks"), list)
    assert len(execution["tasks"]) >= 5

    layout = client.post(
        "/api/plan/layout",
        headers=session_headers,
        json={"execution": execution, "ideaId": idea_id, "planId": plan_id},
    )
    assert layout.status_code == 200
    assert (layout.json() or {}).get("layout")
