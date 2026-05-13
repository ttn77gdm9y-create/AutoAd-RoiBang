from __future__ import annotations

from pathlib import Path
from typing import Any

from roibang_v2.runs import write_run_artifact
from roibang_v2.workflows.create_phase2_yzt_account_pool_check import (
    build_create_phase2_yzt_account_pool_check,
)
from roibang_v2.workflows.create_phase2_yzt_config_check import build_create_phase2_yzt_config_check
from roibang_v2.workflows.create_phase2_yzt_material_pool_check import (
    build_create_phase2_yzt_material_pool_check,
)


def _check_config(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("create_phase2_yzt_preparation_check")
    return dict(value) if isinstance(value, dict) else dict(request)


def _step(step: str, artifact: dict[str, Any]) -> dict[str, Any]:
    return {
        "step": step,
        "workflow": str(artifact.get("workflow") or ""),
        "ok": bool(artifact.get("ok")),
        "status": str(artifact.get("status") or ""),
    }


def _dedupe(rows: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for row in rows:
        if row in seen:
            continue
        seen.add(row)
        result.append(row)
    return result


DEFAULT_PREVIEW_CONFIG_PATH = "configs/create/yzt-wx-mini-game.preview.example.json"


def _preparation_command(*, preview_config_path: str = DEFAULT_PREVIEW_CONFIG_PATH) -> str:
    return (
        "PYTHONPATH=src python3 scripts/run_create_phase2_yzt_preparation_check.py "
        "--config configs/runtime.example.json "
        f"--preview-config {preview_config_path} "
        "--policy policies/create-policy.example.json"
    )


def _dry_chain_command(*, preview_config_path: str = DEFAULT_PREVIEW_CONFIG_PATH) -> str:
    return (
        "PYTHONPATH=src python3 scripts/run_create_phase2_yzt_dry_chain.py "
        "--config configs/runtime.example.json "
        f"--preview-config {preview_config_path} "
        "--policy policies/create-policy.example.json"
    )


def _operator_guide(*, ok: bool, next_steps: list[str], preview_config_path: str = DEFAULT_PREVIEW_CONFIG_PATH) -> dict[str, Any]:
    if ok:
        return {
            "status": "ready_for_dry_chain",
            "title": "准备检查已通过",
            "ordered_steps": [
                "运行完整预演命令。",
                "检查完整预演产物里的项目名、账户、素材数量。",
            ],
            "next_command": _dry_chain_command(preview_config_path=preview_config_path),
        }
    return {
        "status": "needs_fix",
        "title": "当前不能进入完整预演",
        "ordered_steps": [*next_steps, "修完后重新运行一键准备检查。"],
        "next_command": _preparation_command(preview_config_path=preview_config_path),
    }


def build_create_phase2_yzt_preparation_check(
    *,
    preview_config: dict[str, Any],
    policy: dict[str, Any],
    db_path: str | Path,
    preview_config_path: str = DEFAULT_PREVIEW_CONFIG_PATH,
) -> dict[str, Any]:
    config_check = build_create_phase2_yzt_config_check(preview_config=preview_config, policy=policy)
    account_pool_check = build_create_phase2_yzt_account_pool_check(
        preview_config=preview_config,
        policy=policy,
        db_path=db_path,
    )
    material_pool_check = build_create_phase2_yzt_material_pool_check(
        preview_config=preview_config,
        policy=policy,
        db_path=db_path,
    )
    checks = [config_check, account_pool_check, material_pool_check]
    check_steps = [
        _step("config_check", config_check),
        _step("account_pool_check", account_pool_check),
        _step("material_pool_check", material_pool_check),
    ]
    violations = _dedupe([str(item) for check in checks for item in (check.get("violations") or [])])
    ok = all(bool(check.get("ok")) for check in checks) and not violations
    next_steps = _dedupe([str(item) for check in checks for item in (check.get("human_next_steps") or [])])
    if ok:
        next_steps = ["准备检查都通过；下一步可以跑完整预演。"]
    operator_guide = _operator_guide(ok=ok, next_steps=next_steps, preview_config_path=preview_config_path)
    return {
        "ok": ok,
        "workflow": "create_phase2_yzt_preparation_check",
        "phase": "phase2_preparation",
        "execution_enabled": False,
        "external_api_calls": 0,
        "status": "passed" if ok else "needs_fix",
        "summary": {
            "check_count": len(checks),
            "passed_check_count": len([check for check in checks if bool(check.get("ok"))]),
            "failed_check_count": len([check for check in checks if not bool(check.get("ok"))]),
            "ready_for_dry_chain": ok,
        },
        "check_steps": check_steps,
        "config_check": config_check,
        "account_pool_check": account_pool_check,
        "material_pool_check": material_pool_check,
        "violations": violations,
        "human_next_steps": next_steps,
        "operator_guide": operator_guide,
        "actions": [],
    }


def run_create_phase2_yzt_preparation_check_request(
    request: dict[str, Any],
    *,
    db_path: str | Path,
    runs_dir: str | Path,
) -> dict[str, Any]:
    cfg = _check_config(request)
    payload = build_create_phase2_yzt_preparation_check(
        preview_config=cfg.get("preview_config") if isinstance(cfg.get("preview_config"), dict) else {},
        policy=cfg.get("policy") if isinstance(cfg.get("policy"), dict) else {},
        db_path=db_path,
        preview_config_path=str(cfg.get("preview_config_path") or DEFAULT_PREVIEW_CONFIG_PATH),
    )
    artifact_path = write_run_artifact(runs_dir, "create_phase2_yzt_preparation_check", payload)
    return {**payload, "artifact_path": str(artifact_path)}
