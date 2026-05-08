from __future__ import annotations

import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from roibang_v2.artifacts.contract import validate_artifact_contract
from roibang_v2.runs import write_run_artifact
from roibang_v2.scheduler.jobs import validate_job_registry


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _find_job(registry: dict[str, Any], job_id: str) -> dict[str, Any]:
    validate_job_registry(registry)
    for job in registry["jobs"]:
        if str(job.get("id")) == job_id:
            return job
    raise ValueError(f"unknown scheduler job: {job_id}")


def _script_argv(job: dict[str, Any]) -> list[str]:
    script = job["script"]
    script_path = str(script["path"])
    args = [str(arg) for arg in script.get("args", [])]
    if script_path.endswith(".py"):
        return ["python3", script_path, *args]
    return [script_path, *args]


def _artifact_failure(registry: dict[str, Any], job_id: str, repo_root: Path) -> dict[str, Any]:
    try:
        return validate_artifact_contract(registry, job_id=job_id, repo_root=repo_root)
    except FileNotFoundError as exc:
        return {
            "ok": False,
            "job_id": job_id,
            "artifact_path": "",
            "missing_fields": [],
            "violations": [str(exc)],
        }


def run_scheduler_job(
    registry: dict[str, Any],
    *,
    job_id: str,
    repo_root: str | Path = ".",
    execution_runs_dir: str | Path = "data/runs",
) -> dict[str, Any]:
    job = _find_job(registry, job_id)
    if str(job["script"].get("mode")) != "foreground":
        raise ValueError("Phase 1 scheduler runner only supports foreground scripts")

    root = Path(repo_root)
    argv = _script_argv(job)
    started_at = _now_iso()
    started = time.monotonic()
    env = os.environ.copy()
    env["PYTHONPATH"] = "src"
    completed = subprocess.run(
        argv,
        cwd=root,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    finished_at = _now_iso()
    duration_seconds = round(time.monotonic() - started, 3)
    script_result = {
        "path": str(job["script"]["path"]),
        "args": [str(arg) for arg in job["script"].get("args", [])],
        "argv": argv,
        "mode": "foreground",
        "exit_code": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }

    violations: list[str] = []
    if completed.returncode != 0:
        violations.append("script exited with non-zero status")

    if completed.returncode == 0:
        try:
            artifact_contract = validate_artifact_contract(registry, job_id=job_id, repo_root=root)
        except FileNotFoundError as exc:
            artifact_contract = {
                "ok": False,
                "job_id": job_id,
                "artifact_path": "",
                "missing_fields": [],
                "violations": [str(exc)],
            }
    else:
        artifact_contract = _artifact_failure(registry, job_id, root)
    violations.extend(str(item) for item in artifact_contract.get("violations", []))

    payload = {
        "ok": completed.returncode == 0 and bool(artifact_contract.get("ok")),
        "workflow": "scheduler_job",
        "phase": "phase1",
        "job_id": job_id,
        "job_name": job["name"],
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_seconds": duration_seconds,
        "script": script_result,
        "artifact_contract": artifact_contract,
        "violations": violations,
    }
    artifact_path = write_run_artifact(Path(root) / execution_runs_dir, f"scheduler/{job_id}", payload)
    return {**payload, "execution_result_path": str(artifact_path)}
