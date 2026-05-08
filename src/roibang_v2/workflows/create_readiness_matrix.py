from __future__ import annotations

from pathlib import Path
from typing import Any

from roibang_v2.runs import write_run_artifact


_ARTIFACT_KEYS = {
    "create_provider_field_map_check": "create_provider_field_map_check_artifact",
    "create_field_mapping_review_pack": "create_field_mapping_review_pack_artifact",
    "create_template_slot_review_pack": "create_template_slot_review_pack_artifact",
    "create_preflight": "create_preflight_artifact",
    "create_dry_run": "create_dry_run_artifact",
    "create_chain_replay": "create_chain_replay_artifact",
    "create_chain_manifest": "create_chain_manifest_artifact",
}


def _matrix_config(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("create_readiness_matrix")
    return dict(value) if isinstance(value, dict) else dict(request)


def _status(artifact: dict[str, Any]) -> str:
    return str(artifact.get("status") or "")


def _ok(artifact: dict[str, Any]) -> bool:
    return bool(artifact.get("ok", False))


def _row(*, gate: str, workflow: str, artifact: dict[str, Any], ready: bool, reason: str) -> dict[str, Any]:
    return {
        "gate": gate,
        "workflow": workflow,
        "artifact_status": _status(artifact),
        "ready": ready,
        "blocking": not ready,
        "reason": "" if ready else reason,
    }


def _provider_field_map_ready(artifact: dict[str, Any]) -> bool:
    readiness = artifact.get("provider_readiness_contract") if isinstance(artifact.get("provider_readiness_contract"), dict) else {}
    return _ok(artifact) and _status(artifact) == "verified" and bool(readiness.get("ready_for_live_execute", False))


def _field_mapping_review_ready(artifact: dict[str, Any]) -> bool:
    return _ok(artifact) and _status(artifact) == "verified"


def _template_slot_review_ready(artifact: dict[str, Any]) -> bool:
    return _ok(artifact) and _status(artifact) in {"reviewed", "verified"}


def _preflight_ready(artifact: dict[str, Any]) -> bool:
    return _ok(artifact) and _status(artifact) == "passed"


def _dry_run_ready(artifact: dict[str, Any]) -> bool:
    return _ok(artifact) and _status(artifact) == "simulated"


def _replay_ready(artifact: dict[str, Any]) -> bool:
    return _ok(artifact) and _status(artifact) == "passed"


def _manifest_ready(artifact: dict[str, Any]) -> bool:
    return _ok(artifact) and _status(artifact) == "ready"


def _matrix(
    *,
    field_map_check: dict[str, Any],
    field_mapping_review_pack: dict[str, Any],
    template_slot_review_pack: dict[str, Any],
    preflight: dict[str, Any],
    dry_run: dict[str, Any],
    replay: dict[str, Any],
    manifest: dict[str, Any],
) -> list[dict[str, Any]]:
    return [
        _row(
            gate="provider_field_map",
            workflow="create_provider_field_map_check",
            artifact=field_map_check,
            ready=_provider_field_map_ready(field_map_check),
            reason="provider field map must be verified before live execute",
        ),
        _row(
            gate="field_mapping_review_pack",
            workflow="create_field_mapping_review_pack",
            artifact=field_mapping_review_pack,
            ready=_field_mapping_review_ready(field_mapping_review_pack),
            reason="field mapping review pack still needs review",
        ),
        _row(
            gate="template_slot_review_pack",
            workflow="create_template_slot_review_pack",
            artifact=template_slot_review_pack,
            ready=_template_slot_review_ready(template_slot_review_pack),
            reason="template slot review pack still needs review",
        ),
        _row(
            gate="create_preflight",
            workflow="create_preflight",
            artifact=preflight,
            ready=_preflight_ready(preflight),
            reason="create preflight must pass",
        ),
        _row(
            gate="create_dry_run",
            workflow="create_dry_run",
            artifact=dry_run,
            ready=_dry_run_ready(dry_run),
            reason="create dry-run must complete",
        ),
        _row(
            gate="create_chain_replay",
            workflow="create_chain_replay",
            artifact=replay,
            ready=_replay_ready(replay),
            reason="create chain replay must pass",
        ),
        _row(
            gate="create_chain_manifest",
            workflow="create_chain_manifest",
            artifact=manifest,
            ready=_manifest_ready(manifest),
            reason="create chain manifest must be ready",
        ),
    ]


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    passed = sum(1 for row in rows if bool(row.get("ready", False)))
    blocking = sum(1 for row in rows if bool(row.get("blocking", False)))
    return {
        "gate_count": len(rows),
        "passed_gate_count": passed,
        "blocking_gate_count": blocking,
        "ready_for_live_execute": blocking == 0,
    }


def build_create_readiness_matrix(
    *,
    create_provider_field_map_check_artifact: dict[str, Any],
    create_field_mapping_review_pack_artifact: dict[str, Any],
    create_template_slot_review_pack_artifact: dict[str, Any],
    create_preflight_artifact: dict[str, Any],
    create_dry_run_artifact: dict[str, Any],
    create_chain_replay_artifact: dict[str, Any],
    create_chain_manifest_artifact: dict[str, Any],
) -> dict[str, Any]:
    rows = _matrix(
        field_map_check=create_provider_field_map_check_artifact,
        field_mapping_review_pack=create_field_mapping_review_pack_artifact,
        template_slot_review_pack=create_template_slot_review_pack_artifact,
        preflight=create_preflight_artifact,
        dry_run=create_dry_run_artifact,
        replay=create_chain_replay_artifact,
        manifest=create_chain_manifest_artifact,
    )
    summary = _summary(rows)
    ready = bool(summary["ready_for_live_execute"])
    return {
        "ok": True,
        "workflow": "create_readiness_matrix",
        "phase": "phase1",
        "execution_enabled": False,
        "external_api_calls": 0,
        "status": "ready" if ready else "not_ready",
        "ready_for_live_execute": ready,
        "summary": summary,
        "readiness_matrix": rows,
        "blocking_reasons": [str(row.get("reason") or "") for row in rows if bool(row.get("blocking", False))],
        "violations": [],
        "actions": [],
    }


def run_create_readiness_matrix_request(
    request: dict[str, Any],
    *,
    runs_dir: str | Path,
) -> dict[str, Any]:
    cfg = _matrix_config(request)
    missing = [key for key in _ARTIFACT_KEYS.values() if not isinstance(cfg.get(key), dict)]
    if missing:
        raise ValueError(f"create readiness matrix requires artifacts: {', '.join(missing)}")
    payload = build_create_readiness_matrix(
        create_provider_field_map_check_artifact=cfg["create_provider_field_map_check_artifact"],
        create_field_mapping_review_pack_artifact=cfg["create_field_mapping_review_pack_artifact"],
        create_template_slot_review_pack_artifact=cfg["create_template_slot_review_pack_artifact"],
        create_preflight_artifact=cfg["create_preflight_artifact"],
        create_dry_run_artifact=cfg["create_dry_run_artifact"],
        create_chain_replay_artifact=cfg["create_chain_replay_artifact"],
        create_chain_manifest_artifact=cfg["create_chain_manifest_artifact"],
    )
    artifact_path = write_run_artifact(runs_dir, "create_readiness_matrix", payload)
    return {**payload, "artifact_path": str(artifact_path)}
