import asyncio


def test_experiments_generate_plan_and_status(client, monkeypatch):
    import backend.api.experiments as exp_api

    saved = {"plan": None, "execution": None}

    async def list_plan_ids():
        return ["exp1"]

    async def get_plan(plan_id: str):
        return {"idea": "hello", "tasks": [{"task_id": "0", "description": "d", "dependencies": []}]}

    async def save_plan(plan: dict, plan_id: str):
        saved["plan"] = (plan_id, plan)

    async def get_effective_config():
        return {"useMock": True}

    async def run_plan(plan, *_args, **_kwargs):
        # mimic planner output
        return {"tasks": plan.get("tasks")}

    def build_execution_from_plan(plan: dict):
        return {"tasks": [{"task_id": "0", "status": "done"}]}

    async def save_execution(execution: dict, plan_id: str):
        saved["execution"] = (plan_id, execution)

    async def get_execution(plan_id: str):
        # used by /status
        if saved["execution"]:
            return saved["execution"][1]
        return {"tasks": []}

    async def list_plan_outputs(plan_id: str):
        return {"0": {"content": "ok"}}

    async def get_task_artifact(plan_id: str, task_id: str):
        return {"content": "ok"}

    def build_layout_from_execution(execution: dict):
        return {"nodes": []}

    class DummyRunner:
        is_running = False
        plan_id = None

        def set_layout(self, *args, **kwargs):
            return None

        async def start_execution(self, *args, **kwargs):
            await asyncio.sleep(0)

    class DummyState:
        runner = DummyRunner()

    def _load_maars_stub():
        return {
            "state": DummyState(),
            "get_effective_config": get_effective_config,
            "get_execution": get_execution,
            "get_plan": get_plan,
            "get_task_artifact": get_task_artifact,
            "list_plan_ids": list_plan_ids,
            "list_plan_outputs": list_plan_outputs,
            "save_execution": save_execution,
            "save_plan": save_plan,
            "build_execution_from_plan": build_execution_from_plan,
            "build_layout_from_execution": build_layout_from_execution,
            "run_plan": run_plan,
        }

    monkeypatch.setattr(exp_api, "_load_maars", _load_maars_stub, raising=True)

    # list experiments
    r0 = client.get("/api/experiments")
    assert r0.status_code == 200
    assert r0.json()[0]["id"] == "exp1"

    # generate plan
    r1 = client.post("/api/experiments/exp1/plan", json={"idea": {"title": "T"}, "topic": {}})
    assert r1.status_code == 200
    assert saved["plan"] is not None

    # run experiment (starts async task)
    r2 = client.post("/api/experiments/exp1/run", json={})
    assert r2.status_code == 200

    # status should be completed (task done)
    r3 = client.get("/api/experiments/exp1/status")
    assert r3.status_code == 200
    assert r3.json()["experiment_status"] == "completed"

    # artifacts listing + fetch
    r4 = client.get("/api/experiments/exp1/artifacts")
    assert r4.status_code == 200
    manifest = r4.json()["manifest"]
    assert len(manifest) >= 1

    r5 = client.get("/api/experiments/exp1/artifacts/task_0.json")
    assert r5.status_code == 200
    assert r5.json()["content"] == "ok"
