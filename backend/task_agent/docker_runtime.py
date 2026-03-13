"""Local Docker runtime helpers for Task Agent execution."""

from __future__ import annotations

import asyncio
import json
import os
import re
import shlex
import shutil
from pathlib import Path
from typing import Any

from loguru import logger

from db import get_execution_sandbox_root, get_execution_src_dir, get_execution_task_step_dir

DEFAULT_DOCKER_IMAGE = os.getenv("MAARS_DOCKER_IMAGE", "maars-task-python:latest")
DOCKER_COMMAND_TIMEOUT = int(os.getenv("MAARS_DOCKER_COMMAND_TIMEOUT", "120"))
_DOCKER_KEEPALIVE_CMD = "trap : TERM INT; while sleep 3600; do :; done"
_MANAGED_LABEL = "maars.managed=true"
_MANAGED_KIND_LABEL = "maars.kind=task-execution"
_DOCKERFILE_PATH = Path(__file__).resolve().parent / "docker" / "Dockerfile"
_IMAGE_BUILD_LOCK = asyncio.Lock()


def _bootstrap_keepalive_cmd() -> str:
    return _DOCKER_KEEPALIVE_CMD


def _docker_bin() -> str:
    return shutil.which("docker") or ""


def _sanitize_name(value: str) -> str:
    raw = re.sub(r"[^a-zA-Z0-9_.-]+", "-", str(value or "").strip())
    raw = raw.strip("-._") or "run"
    return raw[:63]


async def _run_docker_cmd(args: list[str], timeout: int = DOCKER_COMMAND_TIMEOUT) -> dict[str, Any]:
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return {
            "ok": False,
            "code": -1,
            "stdout": "",
            "stderr": f"Timed out after {timeout}s",
            "args": args,
        }
    return {
        "ok": proc.returncode == 0,
        "code": proc.returncode,
        "stdout": stdout.decode("utf-8", errors="replace"),
        "stderr": stderr.decode("utf-8", errors="replace"),
        "args": args,
    }


async def get_local_docker_status(*, enabled: bool = True, container_name: str | None = None) -> dict[str, Any]:
    docker = _docker_bin()
    base: dict[str, Any] = {
        "enabled": bool(enabled),
        "available": bool(docker),
        "connected": False,
        "image": DEFAULT_DOCKER_IMAGE,
        "dockerPath": docker,
        "containerName": container_name or "",
        "containerRunning": False,
    }
    if not docker:
        base["error"] = "Docker CLI not found in PATH"
        return base

    info = await _run_docker_cmd([docker, "info", "--format", "{{.ServerVersion}}"], timeout=20)
    if not info["ok"]:
        base["error"] = (info.get("stderr") or info.get("stdout") or "Docker daemon unavailable").strip()
        return base

    base["connected"] = True
    base["serverVersion"] = (info.get("stdout") or "").strip()

    if container_name:
        inspect = await _run_docker_cmd(
            [docker, "inspect", "-f", "{{.State.Running}}", container_name],
            timeout=10,
        )
        if inspect["ok"]:
            base["containerRunning"] = (inspect.get("stdout") or "").strip().lower() == "true"
    return base


def build_container_name(execution_run_id: str, task_id: str) -> str:
    return f"maars-task-{_sanitize_name(execution_run_id)}-{_sanitize_name(task_id)}"


async def cleanup_stale_execution_containers() -> None:
    docker = _docker_bin()
    if not docker:
        raise RuntimeError("Docker CLI not found in PATH")

    args = [
        docker,
        "ps",
        "-aq",
        "--filter",
        f"label={_MANAGED_LABEL}",
        "--filter",
        "status=created",
        "--filter",
        "status=exited",
        "--filter",
        "status=dead",
    ]
    listed = await _run_docker_cmd(args, timeout=20)
    if not listed["ok"]:
        raise RuntimeError(listed.get("stderr") or listed.get("stdout") or "Failed to list stale Docker containers")

    container_ids = [line.strip() for line in (listed.get("stdout") or "").splitlines() if line.strip()]
    for container_id in container_ids:
        removed = await _run_docker_cmd([docker, "rm", "-f", container_id], timeout=20)
        if removed["ok"]:
            logger.info("Removed stale managed Docker container {}", container_id)


async def ensure_execution_image(image: str | None = None) -> str:
    docker = _docker_bin()
    if not docker:
        raise RuntimeError("Docker CLI not found in PATH")

    image_name = (image or DEFAULT_DOCKER_IMAGE).strip() or DEFAULT_DOCKER_IMAGE
    async with _IMAGE_BUILD_LOCK:
        inspect = await _run_docker_cmd([docker, "image", "inspect", image_name], timeout=20)
        if inspect["ok"]:
            return image_name

        if not _DOCKERFILE_PATH.exists():
            raise RuntimeError(f"Dockerfile not found: {_DOCKERFILE_PATH}")

        build_cmd = [
            docker,
            "build",
            "--progress=plain",
            "-f",
            str(_DOCKERFILE_PATH),
            "-t",
            image_name,
            "--label",
            _MANAGED_LABEL,
            "--label",
            _MANAGED_KIND_LABEL,
            str(_DOCKERFILE_PATH.parent),
        ]
        built = await _run_docker_cmd(build_cmd, timeout=max(DOCKER_COMMAND_TIMEOUT, 600))
        if built["ok"]:
            return image_name

        err_text = (built.get("stderr") or built.get("stdout") or "").strip()
        if "already exists" in err_text.lower():
            inspect_after = await _run_docker_cmd([docker, "image", "inspect", image_name], timeout=20)
            if inspect_after["ok"]:
                logger.info("Docker image build raced but image now exists: {}", image_name)
                return image_name

        raise RuntimeError(err_text or "Failed to build Docker image")


async def prepare_execution_runtime(*, enabled: bool, image: str | None = None) -> dict[str, Any]:
    status = await get_local_docker_status(enabled=enabled)
    if not enabled:
        return status
    if not status.get("connected"):
        raise RuntimeError(status.get("error") or "Docker daemon unavailable")
    await cleanup_stale_execution_containers()
    image_name = (image or DEFAULT_DOCKER_IMAGE).strip() or DEFAULT_DOCKER_IMAGE
    status["image"] = image_name
    return status


async def ensure_execution_container(
    *,
    execution_run_id: str,
    idea_id: str,
    plan_id: str,
    task_id: str,
    skills_dir: Path,
    image: str | None = None,
) -> dict[str, Any]:
    docker = _docker_bin()
    if not docker:
        raise RuntimeError("Docker CLI not found in PATH")

    plan_meta = {
        "ideaId": idea_id,
        "planId": plan_id,
        "taskId": task_id,
        "executionRunId": execution_run_id,
    }

    sandbox_root = get_execution_sandbox_root(execution_run_id).resolve()
    src_dir = get_execution_src_dir(execution_run_id).resolve()
    step_dir = get_execution_task_step_dir(execution_run_id, task_id).resolve()
    skills_dir = skills_dir.resolve()
    src_dir.mkdir(parents=True, exist_ok=True)
    step_dir.mkdir(parents=True, exist_ok=True)
    sandbox_root.mkdir(parents=True, exist_ok=True)

    image_name = await ensure_execution_image(image=image)
    container_name = build_container_name(execution_run_id, task_id)

    metadata_path = step_dir / "container-meta.json"
    metadata_path.write_text(json.dumps(plan_meta, ensure_ascii=False, indent=2), encoding="utf-8")

    status = await get_local_docker_status(enabled=True, container_name=container_name)
    if not status.get("connected"):
        raise RuntimeError(status.get("error") or "Docker daemon unavailable")
    if status.get("containerRunning"):
        return {
            **status,
            "containerName": container_name,
            "image": image_name,
            "taskId": task_id,
            "srcDir": str(src_dir),
            "stepDir": str(step_dir),
            "sandboxRoot": str(sandbox_root),
        }

    inspect = await _run_docker_cmd([docker, "inspect", container_name], timeout=10)
    if inspect["ok"]:
        started = await _run_docker_cmd([docker, "start", container_name], timeout=20)
        if not started["ok"]:
            raise RuntimeError(started.get("stderr") or started.get("stdout") or "Failed to start Docker container")
        return {
            **status,
            "connected": True,
            "containerRunning": True,
            "containerName": container_name,
            "image": image_name,
            "taskId": task_id,
            "srcDir": str(src_dir),
            "stepDir": str(step_dir),
            "sandboxRoot": str(sandbox_root),
        }
    
    run_cmd = [
        docker,
        "run",
        "-d",
        "--name",
        container_name,
        "--label",
        _MANAGED_LABEL,
        "--label",
        _MANAGED_KIND_LABEL,
        "--label",
        f"maars.execution_run_id={_sanitize_name(execution_run_id)}",
        "--label",
        f"maars.task_id={_sanitize_name(task_id)}",
        "--workdir",
        "/workdir/src",
        "--mount",
        f"type=bind,src={src_dir},dst=/workdir/src",
        "--mount",
        f"type=bind,src={step_dir},dst=/workdir/step",
        "--mount",
        f"type=bind,src={skills_dir},dst=/skills,readonly",
        "--mount",
        "type=tmpfs,dst=/tmp",
        image_name,
        "sh",
        "-lc",
        _bootstrap_keepalive_cmd(),
    ]
    created = await _run_docker_cmd(run_cmd, timeout=40)
    if not created["ok"]:
        raise RuntimeError(created.get("stderr") or created.get("stdout") or "Failed to create Docker execution container")

    logger.info(
        "Docker task container ready run_id={} task_id={} container={} image={} src_dir={} step_dir={}",
        execution_run_id,
        task_id,
        container_name,
        image_name,
        src_dir,
        step_dir,
    )
    return {
        "enabled": True,
        "available": True,
        "connected": True,
        "containerRunning": True,
        "containerName": container_name,
        "image": image_name,
        "taskId": task_id,
        "srcDir": str(src_dir),
        "stepDir": str(step_dir),
        "sandboxRoot": str(sandbox_root),
    }


async def run_command_in_container(
    *,
    container_name: str,
    command: str,
    workdir: str,
    timeout_seconds: int | None = None,
) -> dict[str, Any]:
    docker = _docker_bin()
    if not docker:
        raise RuntimeError("Docker CLI not found in PATH")
    if not container_name:
        raise RuntimeError("Docker container is not initialized")
    timeout = max(1, int(timeout_seconds or DOCKER_COMMAND_TIMEOUT))
    args = [docker, "exec", "-w", workdir, container_name, "sh", "-lc", command]
    result = await _run_docker_cmd(args, timeout=timeout)
    logger.info(
        "Docker exec container={} workdir={} timeout_s={} exit_code={} command={}",
        container_name,
        workdir,
        timeout,
        result.get("code"),
        command,
    )
    return result


async def run_skill_script_in_container(
    *,
    container_name: str,
    task_id: str,
    skill: str,
    script_rel_path: str,
    args: list[str] | None = None,
    timeout_seconds: int | None = None,
) -> dict[str, Any]:
    ext = Path(script_rel_path).suffix.lower()
    script_path = f"/skills/{skill}/{script_rel_path.lstrip('/')}"
    workspace_dir = "/workdir/src"
    resolved_args = [
        str(a).replace("[[sandbox]]", workspace_dir).replace("{{sandbox}}", workspace_dir)
        for a in (args or [])
    ]
    if ext == ".py":
        command = "python " + " ".join(shlex.quote(part) for part in [script_path, *resolved_args])
    elif ext == ".sh":
        command = "sh " + " ".join(shlex.quote(part) for part in [script_path, *resolved_args])
    elif ext == ".js":
        command = "node " + " ".join(shlex.quote(part) for part in [script_path, *resolved_args])
    else:
        raise RuntimeError(f"Unsupported script extension: {ext}")
    return await run_command_in_container(
        container_name=container_name,
        command=command,
        workdir=f"/skills/{skill}",
        timeout_seconds=timeout_seconds,
    )


async def stop_execution_container(container_name: str) -> None:
    docker = _docker_bin()
    if not docker or not container_name:
        return
    result = await _run_docker_cmd([docker, "rm", "-f", container_name], timeout=20)
    if result["ok"]:
        logger.info("Docker execution container removed container={}", container_name)
    else:
        logger.warning(
            "Failed to remove Docker execution container {}: {}",
            container_name,
            (result.get("stderr") or result.get("stdout") or "").strip(),
        )
