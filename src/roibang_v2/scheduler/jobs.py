from __future__ import annotations

import shlex
from pathlib import Path
from typing import Any

from roibang_v2.config import load_json


FORBIDDEN_JOB_KEYS = {"prompt", "agentId", "agent_id", "operator_task"}
LIVE_MUTATION_CATEGORIES = {"live_mutation", "execute", "create", "pause", "delete", "bid_apply"}


def load_job_registry(path: str | Path) -> dict[str, Any]:
    return load_json(path)


def _require(condition: bool, message: str, violations: list[str]) -> None:
    if not condition:
        violations.append(message)


def _validate_job(job: dict[str, Any], index: int) -> list[str]:
    violations: list[str] = []
    prefix = f"jobs[{index}]"
    job_id = str(job.get("id") or "").strip()
    for key in FORBIDDEN_JOB_KEYS:
        if key in job:
            violations.append(f"{prefix} {job_id} uses forbidden AI execution key: {key}")
    _require(bool(job_id), f"{prefix} missing id", violations)
    _require(bool(str(job.get("name") or "").strip()), f"{prefix} missing name", violations)

    schedule = job.get("schedule")
    _require(isinstance(schedule, dict), f"{prefix} missing schedule", violations)
    if isinstance(schedule, dict):
        _require(schedule.get("type") == "cron", f"{prefix} schedule.type must be cron", violations)
        _require(bool(str(schedule.get("expr") or "").strip()), f"{prefix} missing schedule.expr", violations)
        _require(bool(str(schedule.get("tz") or "").strip()), f"{prefix} missing schedule.tz", violations)

    script = job.get("script")
    _require(isinstance(script, dict), f"{prefix} missing script", violations)
    if isinstance(script, dict):
        command = script.get("command")
        has_command = bool(_script_command_argv(command)) if command is not None else False
        has_path = bool(str(script.get("path") or "").strip())
        _require(has_command or has_path, f"{prefix} missing script.command or script.path", violations)
        _require(str(script.get("mode") or "") in {"foreground", "background"}, f"{prefix} invalid script.mode", violations)

    policy = job.get("policy")
    _require(isinstance(policy, dict), f"{prefix} missing policy", violations)
    result_contract = job.get("result_contract")
    _require(isinstance(result_contract, dict), f"{prefix} missing result_contract", violations)
    if isinstance(result_contract, dict):
        _require(bool(str(result_contract.get("workflow") or "").strip()), f"{prefix} missing result_contract.workflow", violations)
        _require(bool(str(result_contract.get("artifact_dir") or "").strip()), f"{prefix} missing result_contract.artifact_dir", violations)

    category = str(job.get("category") or "").strip()
    if category in LIVE_MUTATION_CATEGORIES:
        _require(isinstance(policy, dict) and bool(policy.get("approval_policy")), f"{prefix} live mutation missing approval policy", violations)
        _require(isinstance(result_contract, dict) and bool(result_contract.get("execution_result")), f"{prefix} live mutation missing execution result contract", violations)

    return violations


def _script_command_argv(command: Any) -> list[str]:
    if isinstance(command, str):
        return shlex.split(command)
    if isinstance(command, list):
        return [str(arg) for arg in command if str(arg).strip()]
    return []


def validate_job_registry(registry: dict[str, Any]) -> dict[str, Any]:
    jobs = registry.get("jobs")
    if not isinstance(jobs, list):
        raise ValueError("registry must contain jobs list")
    violations: list[str] = []
    for index, job in enumerate(jobs):
        if not isinstance(job, dict):
            violations.append(f"jobs[{index}] must be object")
            continue
        violations.extend(_validate_job(job, index))
    if violations:
        message = "; ".join(violations)
        if "prompt" in message:
            raise ValueError(f"prompt-driven jobs are forbidden: {message}")
        if "policy" in message:
            raise ValueError(f"policy validation failed: {message}")
        raise ValueError(message)
    enabled_jobs = sum(1 for job in jobs if bool(job.get("enabled", False)))
    return {
        "ok": True,
        "jobs": len(jobs),
        "enabled_jobs": enabled_jobs,
        "disabled_jobs": len(jobs) - enabled_jobs,
        "violations": [],
    }
