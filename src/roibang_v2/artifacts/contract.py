from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from roibang_v2.scheduler.jobs import validate_job_registry


def _find_job(registry: dict[str, Any], job_id: str) -> dict[str, Any]:
    validate_job_registry(registry)
    for job in registry["jobs"]:
        if str(job.get("id")) == job_id:
            return job
    raise ValueError(f"unknown scheduler job: {job_id}")


def _latest_artifact_path(job: dict[str, Any], repo_root: str | Path) -> Path:
    artifact_dir = Path(repo_root) / str(job["result_contract"]["artifact_dir"])
    candidates = sorted(artifact_dir.glob("*.json"))
    if not candidates:
        raise FileNotFoundError(f"no artifact json files found in {artifact_dir}")
    return candidates[-1]


def _load_artifact(path: str | Path) -> tuple[dict[str, Any] | None, list[str]]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, [f"artifact not found: {path}"]
    except json.JSONDecodeError as exc:
        return None, [f"artifact is not valid JSON: {exc.msg}"]
    if not isinstance(value, dict):
        return None, ["artifact root must be a JSON object"]
    return value, []


def validate_artifact_contract(
    registry: dict[str, Any],
    *,
    job_id: str,
    artifact_path: str | Path | None = None,
    repo_root: str | Path = ".",
) -> dict[str, Any]:
    job = _find_job(registry, job_id)
    contract = job["result_contract"]
    path = Path(artifact_path) if artifact_path is not None else _latest_artifact_path(job, repo_root)
    artifact, load_errors = _load_artifact(path)
    if artifact is None:
        return {
            "ok": False,
            "job_id": job_id,
            "workflow": contract["workflow"],
            "artifact_path": str(path),
            "missing_fields": [],
            "violations": load_errors,
        }

    violations: list[str] = []
    expected_workflow = str(contract["workflow"])
    actual_workflow = str(artifact.get("workflow") or "")
    if actual_workflow != expected_workflow:
        violations.append(f"workflow mismatch: expected {expected_workflow}, got {actual_workflow}")

    required_fields = [str(field) for field in contract.get("must_include", [])]
    missing_fields = [field for field in required_fields if field not in artifact]
    if missing_fields:
        violations.append(f"missing required fields: {', '.join(missing_fields)}")

    must_equal = contract.get("must_equal")
    if isinstance(must_equal, dict):
        for field, expected in must_equal.items():
            actual = artifact.get(str(field))
            if actual != expected:
                violations.append(f"field {field} must equal {expected!r}, got {actual!r}")

    must_be_empty = contract.get("must_be_empty")
    if isinstance(must_be_empty, list):
        for field in must_be_empty:
            actual = artifact.get(str(field))
            if actual not in (None, [], {}, ""):
                violations.append(f"field {field} must be empty")

    return {
        "ok": not violations,
        "job_id": job_id,
        "workflow": expected_workflow,
        "artifact_path": str(path),
        "missing_fields": missing_fields,
        "violations": violations,
    }
