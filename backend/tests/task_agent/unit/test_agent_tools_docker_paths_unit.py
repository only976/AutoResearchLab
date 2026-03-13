import anyio

from task_agent import agent_tools


async def _run_command_path_check(monkeypatch):
    captured = {}

    async def fake_run_command_in_container(*, container_name, command, workdir, timeout_seconds=None):
        captured["container_name"] = container_name
        captured["command"] = command
        captured["workdir"] = workdir
        captured["timeout_seconds"] = timeout_seconds
        return {"code": 0, "stdout": "ok", "stderr": ""}

    monkeypatch.setattr(agent_tools, "run_command_in_container", fake_run_command_in_container)

    result = await agent_tools.run_run_command(
        "python script.py",
        "1_1",
        docker_container_name="maars-task-exec-1_1",
        timeout_seconds=33,
    )

    assert result == "ok"
    assert captured["container_name"] == "maars-task-exec-1_1"
    assert captured["workdir"] == "/workdir/src"
    assert captured["timeout_seconds"] == 33


def test_run_command_uses_src_workdir(monkeypatch):
    anyio.run(_run_command_path_check, monkeypatch)


async def _run_list_files_path_check(monkeypatch):
    captured = {}

    async def fake_run_command_in_container(*, container_name, command, workdir, timeout_seconds=None):
        captured["container_name"] = container_name
        captured["command"] = command
        captured["workdir"] = workdir
        captured["timeout_seconds"] = timeout_seconds
        return {"code": 0, "stdout": "a.txt\nsub/b.txt\n", "stderr": ""}

    monkeypatch.setattr(agent_tools, "run_command_in_container", fake_run_command_in_container)

    result = await agent_tools.run_list_files(
        idea_id="idea_x",
        plan_id="plan_y",
        path="sandbox/",
        task_id="1_1",
        execution_run_id="exec_1",
        docker_container_name="maars-task-exec-1_1",
        max_entries=50,
        max_depth=2,
    )

    assert '"items": [' in result
    assert '"a.txt"' in result
    assert captured["container_name"] == "maars-task-exec-1_1"
    assert captured["workdir"] == "/workdir/src"
    assert "find . -mindepth 1 -maxdepth 2" in captured["command"]


def test_list_files_uses_src_workdir(monkeypatch):
    anyio.run(_run_list_files_path_check, monkeypatch)
