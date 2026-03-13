from pathlib import Path

import anyio

from task_agent import docker_runtime


async def _run_ensure(tmp_path, monkeypatch):
    import db

    monkeypatch.setattr(db, "SANDBOX_DIR", tmp_path / "sandbox")
    monkeypatch.setattr(docker_runtime, "_docker_bin", lambda: "docker")

    async def fake_status(*, enabled=True, container_name=None):
        return {
            "enabled": enabled,
            "available": True,
            "connected": True,
            "containerRunning": False,
            "containerName": container_name or "",
        }

    captured = {"run_cmd": None}

    async def fake_run(args, timeout=120):
        if args[:3] == ["docker", "image", "inspect"]:
            return {"ok": True, "code": 0, "stdout": "[]", "stderr": "", "args": args}
        if args[:2] == ["docker", "inspect"]:
            return {"ok": False, "code": 1, "stdout": "", "stderr": "not found", "args": args}
        if args[:2] == ["docker", "ps"]:
            return {"ok": True, "code": 0, "stdout": "", "stderr": "", "args": args}
        if len(args) >= 3 and args[1] == "run":
            captured["run_cmd"] = args
            return {"ok": True, "code": 0, "stdout": "container-id", "stderr": "", "args": args}
        return {"ok": True, "code": 0, "stdout": "", "stderr": "", "args": args}

    monkeypatch.setattr(docker_runtime, "get_local_docker_status", fake_status)
    monkeypatch.setattr(docker_runtime, "_run_docker_cmd", fake_run)

    skills_dir = tmp_path / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)

    runtime = await docker_runtime.ensure_execution_container(
        execution_run_id="exec_test",
        idea_id="idea_fixture",
        plan_id="plan_fixture",
        task_id="1_1",
        skills_dir=skills_dir,
        image="python:3.11-slim",
    )

    run_cmd = captured["run_cmd"]
    assert run_cmd is not None
    run_cmd_text = " ".join(str(x) for x in run_cmd)

    assert runtime["taskId"] == "1_1"
    assert runtime["containerName"].startswith("maars-task-exec_test-1_1")
    assert "dst=/workdir/src" in run_cmd_text
    assert "dst=/workdir/step" in run_cmd_text
    assert "--workdir /workdir/src" in run_cmd_text
    expected_src = (tmp_path / "sandbox" / "exec_test" / "src").resolve()
    expected_step = (tmp_path / "sandbox" / "exec_test" / "step" / "1_1").resolve()
    assert Path(runtime["srcDir"]).resolve() == expected_src
    assert Path(runtime["stepDir"]).resolve() == expected_step

    metadata_path = expected_step / "container-meta.json"
    assert metadata_path.exists()


def test_ensure_execution_container_uses_per_task_src_and_step_mounts(tmp_path, monkeypatch):
    anyio.run(_run_ensure, tmp_path, monkeypatch)


async def _run_image_race(monkeypatch):
    from task_agent import docker_runtime

    monkeypatch.setattr(docker_runtime, "_docker_bin", lambda: "docker")

    calls = {"inspect": 0, "build": 0}

    async def fake_run(args, timeout=120):
        if args[:3] == ["docker", "image", "inspect"]:
            calls["inspect"] += 1
            if calls["inspect"] == 1:
                return {"ok": False, "code": 1, "stdout": "", "stderr": "not found", "args": args}
            return {"ok": True, "code": 0, "stdout": "[{\"Id\":\"sha256:test\"}]", "stderr": "", "args": args}
        if args[:2] == ["docker", "build"]:
            calls["build"] += 1
            return {
                "ok": False,
                "code": 1,
                "stdout": "",
                "stderr": 'ERROR: failed to build: failed to solve: image "docker.io/library/maars-task-python:latest": already exists',
                "args": args,
            }
        return {"ok": True, "code": 0, "stdout": "", "stderr": "", "args": args}

    monkeypatch.setattr(docker_runtime, "_run_docker_cmd", fake_run)

    image = await docker_runtime.ensure_execution_image("maars-task-python:latest")
    assert image == "maars-task-python:latest"
    assert calls["build"] == 1


def test_ensure_execution_image_handles_already_exists_race(monkeypatch):
    anyio.run(_run_image_race, monkeypatch)
