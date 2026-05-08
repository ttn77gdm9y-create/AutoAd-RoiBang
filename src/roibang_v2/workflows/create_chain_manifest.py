from __future__ import annotations

from pathlib import Path
from typing import Any

from roibang_v2.runs import write_run_artifact
from roibang_v2.workflows.create_lineage import create_ref


_ARTIFACT_KEYS = {
    "create_request": "create_request_artifact",
    "create_strategy_plan": "create_strategy_plan_artifact",
    "create_preflight": "create_preflight_artifact",
    "create_dry_run": "create_dry_run_artifact",
    "create_approval": "create_approval_artifact",
    "create_plan_snapshot": "create_plan_snapshot_artifact",
    "create_execute": "create_execute_artifact",
    "create_chain_replay": "create_chain_replay_artifact",
}


def _manifest_config(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("create_chain_manifest")
    return dict(value) if isinstance(value, dict) else dict(request)


def _artifact_path(artifact: dict[str, Any]) -> str:
    return str(artifact.get("artifact_path") or "")


def _artifact_paths(artifacts: dict[str, dict[str, Any]]) -> dict[str, str]:
    return {workflow: _artifact_path(artifact) for workflow, artifact in artifacts.items()}


def _digest(artifact: dict[str, Any], key: str, *, count_key: str | None = None) -> dict[str, Any]:
    value = artifact.get(key)
    if isinstance(value, dict):
        result = {
            "algorithm": str(value.get("algorithm") or ""),
            "value": str(value.get("value") or ""),
        }
        if count_key:
            result[count_key] = int(value.get(count_key) or 0)
        return result
    result = {"algorithm": "sha256", "value": ""}
    if count_key:
        result[count_key] = 0
    return result


def _summary(*, plan: dict[str, Any], replay: dict[str, Any]) -> dict[str, Any]:
    plan_ref = create_ref(workflow="create_strategy_plan", artifact=plan)
    return {
        "plan_id": str(plan_ref.get("plan_id") or ""),
        "request_id": str(plan_ref.get("request_id") or ""),
        "target_date": str(plan_ref.get("target_date") or ""),
        "replay_status": str(replay.get("status") or ""),
        "artifact_count": len(_ARTIFACT_KEYS),
    }


def _replay_violations(replay: dict[str, Any]) -> list[str]:
    if str(replay.get("status") or "") == "passed" and bool(replay.get("ok", False)):
        return []
    return ["create chain replay must pass before manifest is ready"]


def build_create_chain_manifest(
    *,
    create_request_artifact: dict[str, Any],
    create_strategy_plan_artifact: dict[str, Any],
    create_preflight_artifact: dict[str, Any],
    create_dry_run_artifact: dict[str, Any],
    create_approval_artifact: dict[str, Any],
    create_plan_snapshot_artifact: dict[str, Any],
    create_execute_artifact: dict[str, Any],
    create_chain_replay_artifact: dict[str, Any],
) -> dict[str, Any]:
    artifacts = {
        "create_request": create_request_artifact,
        "create_strategy_plan": create_strategy_plan_artifact,
        "create_preflight": create_preflight_artifact,
        "create_dry_run": create_dry_run_artifact,
        "create_approval": create_approval_artifact,
        "create_plan_snapshot": create_plan_snapshot_artifact,
        "create_execute": create_execute_artifact,
        "create_chain_replay": create_chain_replay_artifact,
    }
    violations = _replay_violations(create_chain_replay_artifact)
    status = "ready" if not violations else "not_ready"
    return {
        "ok": not violations,
        "workflow": "create_chain_manifest",
        "phase": "phase1",
        "execution_enabled": False,
        "external_api_calls": 0,
        "status": status,
        "summary": _summary(plan=create_strategy_plan_artifact, replay=create_chain_replay_artifact),
        "artifact_paths": _artifact_paths(artifacts),
        "candidate_task_digest": _digest(
            create_approval_artifact,
            "candidate_task_digest",
            count_key="candidate_task_count",
        ),
        "provider_field_map_digest": _digest(create_dry_run_artifact, "provider_field_map_digest"),
        "provider_payload_draft_digest": _digest(
            create_dry_run_artifact,
            "provider_payload_draft_digest",
            count_key="provider_payload_draft_count",
        ),
        "replay_status": str(create_chain_replay_artifact.get("status") or ""),
        "phase1_safety_contract": create_chain_replay_artifact.get("phase1_safety_contract")
        if isinstance(create_chain_replay_artifact.get("phase1_safety_contract"), dict)
        else {"status": "unknown"},
        "violations": violations,
        "actions": [],
    }


def run_create_chain_manifest_request(
    request: dict[str, Any],
    *,
    runs_dir: str | Path,
) -> dict[str, Any]:
    cfg = _manifest_config(request)
    missing = [key for key in _ARTIFACT_KEYS.values() if not isinstance(cfg.get(key), dict)]
    if missing:
        raise ValueError(f"create chain manifest requires artifacts: {', '.join(missing)}")
    payload = build_create_chain_manifest(
        create_request_artifact=cfg["create_request_artifact"],
        create_strategy_plan_artifact=cfg["create_strategy_plan_artifact"],
        create_preflight_artifact=cfg["create_preflight_artifact"],
        create_dry_run_artifact=cfg["create_dry_run_artifact"],
        create_approval_artifact=cfg["create_approval_artifact"],
        create_plan_snapshot_artifact=cfg["create_plan_snapshot_artifact"],
        create_execute_artifact=cfg["create_execute_artifact"],
        create_chain_replay_artifact=cfg["create_chain_replay_artifact"],
    )
    artifact_path = write_run_artifact(runs_dir, "create_chain_manifest", payload)
    return {**payload, "artifact_path": str(artifact_path)}
