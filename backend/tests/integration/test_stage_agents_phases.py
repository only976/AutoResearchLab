import os
import sqlite3
import time


def _wait_for(predicate, timeout_s: float = 15.0, interval_s: float = 0.1):
    start = time.time()
    last = None
    while time.time() - start < timeout_s:
        last = predicate()
        if last:
            return last
        time.sleep(interval_s)
    raise AssertionError(f"Timed out after {timeout_s}s waiting for condition")


def _get_paper_from_sqlite(idea_id: str, plan_id: str) -> dict | None:
    db_path = os.environ.get("MAARS_DB_PATH")
    assert db_path, "MAARS_DB_PATH must be set in tests"
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        try:
            cur.execute(
                "SELECT format, content, updated_at FROM papers WHERE idea_id = ? AND plan_id = ?",
                (idea_id, plan_id),
            )
        except sqlite3.OperationalError:
            return None
        row = cur.fetchone()
        if not row:
            return None
        return {"format": row[0], "content": row[1], "updated_at": row[2]}
    finally:
        conn.close()


def test_stage_agents_phases_mock_pipeline(client, session_headers, use_mock_agents):
    # ---- Phase 1: Idea (Refine) ----
    idea_resp = client.post(
        "/api/idea/collect",
        headers=session_headers,
        json={"idea": "Test idea for phase pipeline", "limit": 3},
    )
    assert idea_resp.status_code == 200
    idea_id = idea_resp.json()["ideaId"]
    assert idea_id.startswith("idea_")

    def idea_ready():
        r = client.get(f"/api/idea?ideaId={idea_id}")
        assert r.status_code == 200
        idea = (r.json() or {}).get("idea") or {}
        if not (idea.get("keywords") and idea.get("refined_idea")):
            return None
        return idea

    idea_data = _wait_for(idea_ready, timeout_s=20.0)
    assert isinstance(idea_data.get("keywords"), list)
    assert len(idea_data["keywords"]) > 0
    assert isinstance(idea_data.get("refined_idea"), str)
    assert idea_data["refined_idea"].strip()

    # ---- Phase 2: Plan ----
    plan_run = client.post(
        "/api/plan/run",
        headers=session_headers,
        json={"ideaId": idea_id, "skipQualityAssessment": True},
    )
    assert plan_run.status_code == 200
    plan_id = plan_run.json()["planId"]
    assert plan_id.startswith("plan_")

    def plan_ready():
        r = client.get(f"/api/plan?ideaId={idea_id}&planId={plan_id}")
        assert r.status_code == 200
        plan = (r.json() or {}).get("plan") or {}
        tasks = plan.get("tasks") or []
        if len(tasks) < 2:
            return None
        return plan

    plan = _wait_for(plan_ready, timeout_s=25.0)
    assert len(plan.get("tasks") or []) >= 2

    # ---- Phase 3: Execution (Generate -> Layout -> Run) ----
    gen = client.post(
        "/api/execution/generate-from-plan",
        headers=session_headers,
        json={"ideaId": idea_id, "planId": plan_id},
    )
    assert gen.status_code == 200
    execution = gen.json().get("execution")
    assert isinstance(execution, dict)
    assert isinstance(execution.get("tasks"), list)
    assert len(execution.get("tasks")) > 0

    layout = client.post(
        "/api/plan/layout",
        headers=session_headers,
        json={"ideaId": idea_id, "planId": plan_id, "execution": execution},
    )
    assert layout.status_code == 200

    # Reduce flakiness: force execution/validation to pass for mock runner.
    from api import state as api_state

    sid = session_headers["X-MAARS-SESSION-ID"]
    session = api_state.sessions.get(sid)
    assert session is not None
    assert getattr(session, "runner", None) is not None
    session.runner.EXECUTION_PASS_PROBABILITY = 1.0
    session.runner.VALIDATION_PASS_PROBABILITY = 1.0
    session.runner.MAX_FAILURES = 1

    run = client.post(
        "/api/execution/run",
        headers=session_headers,
        json={"ideaId": idea_id, "planId": plan_id},
    )
    assert run.status_code == 200

    def execution_finished():
        r = client.get(
            f"/api/execution/status?ideaId={idea_id}&planId={plan_id}",
            headers=session_headers,
        )
        assert r.status_code == 200
        data = r.json() or {}
        tasks = data.get("tasks") or []
        if not tasks:
            return None
        if data.get("running"):
            return None
        return data

    status = _wait_for(execution_finished, timeout_s=25.0)
    tasks = status.get("tasks") or []
    assert len(tasks) > 0
    # At least all tasks are no longer 'undone' once finished.
    assert all(t.get("status") in ("done", "execution-failed", "validation-failed") for t in tasks)

    # ---- Phase 4: Paper ----
    paper_run = client.post(
        "/api/paper/run",
        headers=session_headers,
        json={"ideaId": idea_id, "planId": plan_id, "format": "markdown"},
    )
    assert paper_run.status_code == 200

    paper = _wait_for(lambda: _get_paper_from_sqlite(idea_id, plan_id), timeout_s=20.0)
    assert paper is not None
    assert paper.get("format") == "markdown"
    assert isinstance(paper.get("content"), str)
    assert paper["content"].strip()
