from __future__ import annotations

from pathlib import Path
from typing import Any

from roibang_v2.runs import write_run_artifact
from roibang_v2.workflows.create_dry_run import run_create_dry_run_request
from roibang_v2.workflows.create_phase2_yzt_create_preview import run_create_phase2_yzt_create_preview_request
from roibang_v2.workflows.create_preflight import run_create_preflight_request
from roibang_v2.workflows.create_provider_field_map_check import run_create_provider_field_map_check_request
from roibang_v2.workflows.create_request import run_create_request
from roibang_v2.workflows.create_strategy_plan import run_create_strategy_plan_request


def _chain_config(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("create_phase2_yzt_dry_chain")
    return dict(value) if isinstance(value, dict) else dict(request)


def _policy_section(policy: dict[str, Any], key: str) -> dict[str, Any]:
    value = policy.get(key)
    return dict(value) if isinstance(value, dict) else {}


def _status(artifact: dict[str, Any]) -> str:
    value = str(artifact.get("status") or "").strip()
    if value:
        return value
    workflow = str(artifact.get("workflow") or "")
    if workflow == "create_request":
        return "recorded"
    if workflow == "create_strategy_plan":
        return "planned"
    return "unknown"


def _step(step: str, artifact: dict[str, Any]) -> dict[str, Any]:
    return {
        "step": step,
        "workflow": str(artifact.get("workflow") or ""),
        "ok": bool(artifact.get("ok")),
        "status": _status(artifact),
    }


def _artifact_path(artifact: dict[str, Any]) -> str:
    return str(artifact.get("artifact_path") or "")


def _violations(*artifacts: dict[str, Any]) -> list[str]:
    violations: list[str] = []
    for artifact in artifacts:
        violations.extend(str(item) for item in artifact.get("violations") or [])
        plan = artifact.get("plan") if isinstance(artifact.get("plan"), dict) else {}
        violations.extend(str(item) for item in plan.get("violations") or [])
    return _dedupe(violations)


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    rows: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        rows.append(value)
    return rows


def _human_next_steps(violations: list[str]) -> list[str]:
    if not violations:
        return ["人工复核完整预演产物里的项目名、账户、预算和素材分配。"]
    joined = "\n".join(violations)
    steps: list[str] = []
    if "daily budget" in joined:
        steps.append("把预算改到策略允许范围内，或先调整策略里的预算上限。")
    if "not in account_pool" in joined:
        steps.append("把目标账户换成本地账户池里存在的账户，或先同步账户池。")
    if "source material account has 0 usable materials" in joined or "has 0 materials" in joined:
        steps.append("先同步源素材账户，确保素材数量够这次预演使用。")
    if "create preflight must pass before dry-run" in joined:
        steps.append("等前面的检查通过后，再重新跑完整预演。")
    return steps or ["查看 violations 里的失败原因，修配置或本地数据后重新跑完整预演。"]


def _blocking_summary(violations: list[str]) -> dict[str, Any]:
    if not violations:
        return {
            "blocked_reason_count": 0,
            "plain_language": "完整本地预演已通过，但真实创建仍然关闭。",
            "needs_real_create": False,
        }
    return {
        "blocked_reason_count": len(violations),
        "plain_language": "完整预演被本地检查拦住，没有进入真实创建。",
        "needs_real_create": False,
    }


def _failed_chain_payload(
    *,
    preview: dict[str, Any],
    runs_dir: str | Path,
) -> dict[str, Any]:
    violations = _violations(preview)
    payload = {
        "ok": False,
        "workflow": "create_phase2_yzt_dry_chain",
        "phase": "phase2_preparation",
        "execution_enabled": False,
        "external_api_calls": 0,
        "status": "blocked",
        "summary": {
            "template_name": preview.get("summary", {}).get("template_name") if isinstance(preview.get("summary"), dict) else "",
            "preview_project_count": preview.get("summary", {}).get("preview_project_count")
            if isinstance(preview.get("summary"), dict)
            else 0,
            "create_request_project_count": 0,
            "strategy_project_count": 0,
            "preflight_status": "not_run",
            "dry_run_status": "not_run",
            "ready_for_live_execute": False,
        },
        "chain_steps": [_step("preview", preview)],
        "artifacts": {"preview": _artifact_path(preview)},
        "preview_summary": preview.get("summary") if isinstance(preview.get("summary"), dict) else {},
        "dry_run_summary": {},
        "blocking_summary": _blocking_summary(violations),
        "human_next_steps": _human_next_steps(violations),
        "violations": violations,
        "actions": [],
    }
    artifact_path = write_run_artifact(runs_dir, "create_phase2_yzt_dry_chain", payload)
    return {**payload, "artifact_path": str(artifact_path)}


def run_create_phase2_yzt_dry_chain_request(
    request: dict[str, Any],
    *,
    db_path: str | Path,
    runs_dir: str | Path,
) -> dict[str, Any]:
    cfg = _chain_config(request)
    preview_config = cfg.get("preview_config") if isinstance(cfg.get("preview_config"), dict) else {}
    policy = cfg.get("policy") if isinstance(cfg.get("policy"), dict) else {}

    preview = run_create_phase2_yzt_create_preview_request(
        {
            "create_phase2_yzt_create_preview": {
                "preview_config": preview_config,
                "policy": policy,
            }
        },
        runs_dir=runs_dir,
    )
    if not bool(preview.get("ok")):
        return _failed_chain_payload(preview=preview, runs_dir=runs_dir)

    create_request_artifact = run_create_request(
        {"create_request": preview["standard_create_request"]},
        db_path=db_path,
        runs_dir=runs_dir,
    )
    strategy = run_create_strategy_plan_request(
        create_request_artifact,
        db_path=db_path,
        runs_dir=runs_dir,
        policy=_policy_section(policy, "create_strategy_plan"),
        create_request_artifact_path=create_request_artifact["artifact_path"],
    )
    preflight = run_create_preflight_request(
        {
            "create_preflight": {
                "create_strategy_plan_artifact": strategy,
                "create_strategy_plan_artifact_path": strategy["artifact_path"],
                "policy": _policy_section(policy, "create_preflight"),
            }
        },
        db_path=db_path,
        runs_dir=runs_dir,
    )
    field_map_check = run_create_provider_field_map_check_request(
        {
            "create_provider_field_map_check": {
                "policy": _policy_section(policy, "create_dry_run"),
            }
        },
        runs_dir=runs_dir,
    )
    dry_run = run_create_dry_run_request(
        {
            "create_dry_run": {
                "create_strategy_plan_artifact": strategy,
                "create_strategy_plan_artifact_path": strategy["artifact_path"],
                "create_preflight_artifact": preflight,
                "create_preflight_artifact_path": preflight["artifact_path"],
                "policy": _policy_section(policy, "create_dry_run"),
            }
        },
        runs_dir=runs_dir,
        db_path=db_path,
    )

    violations = _violations(preview, create_request_artifact, strategy, preflight, field_map_check, dry_run)
    ok = all(
        bool(artifact.get("ok"))
        for artifact in (preview, create_request_artifact, strategy, preflight, field_map_check, dry_run)
    ) and not violations
    preview_summary = preview.get("summary") if isinstance(preview.get("summary"), dict) else {}
    create_request_summary = (
        create_request_artifact.get("summary") if isinstance(create_request_artifact.get("summary"), dict) else {}
    )
    strategy_summary = strategy.get("summary") if isinstance(strategy.get("summary"), dict) else {}
    payload = {
        "ok": ok,
        "workflow": "create_phase2_yzt_dry_chain",
        "phase": "phase2_preparation",
        "execution_enabled": False,
        "external_api_calls": 0,
        "status": "simulated" if ok else "blocked",
        "summary": {
            "template_name": str(preview_summary.get("template_name") or ""),
            "preview_project_count": int(preview_summary.get("preview_project_count") or 0),
            "create_request_project_count": int(create_request_summary.get("planned_project_count") or 0),
            "strategy_project_count": int(strategy_summary.get("planned_project_count") or 0),
            "preflight_status": str(preflight.get("status") or ""),
            "dry_run_status": str(dry_run.get("status") or ""),
            "ready_for_live_execute": False,
        },
        "chain_steps": [
            _step("preview", preview),
            _step("create_request", create_request_artifact),
            _step("strategy_plan", strategy),
            _step("preflight", preflight),
            _step("provider_field_map_check", field_map_check),
            _step("dry_run", dry_run),
        ],
        "artifacts": {
            "preview": _artifact_path(preview),
            "create_request": _artifact_path(create_request_artifact),
            "strategy_plan": _artifact_path(strategy),
            "preflight": _artifact_path(preflight),
            "provider_field_map_check": _artifact_path(field_map_check),
            "dry_run": _artifact_path(dry_run),
        },
        "preview_summary": preview_summary,
        "dry_run_summary": dry_run.get("summary") if isinstance(dry_run.get("summary"), dict) else {},
        "blocking_summary": _blocking_summary(violations),
        "human_next_steps": _human_next_steps(violations),
        "violations": violations,
        "actions": [],
    }
    artifact_path = write_run_artifact(runs_dir, "create_phase2_yzt_dry_chain", payload)
    return {**payload, "artifact_path": str(artifact_path)}
