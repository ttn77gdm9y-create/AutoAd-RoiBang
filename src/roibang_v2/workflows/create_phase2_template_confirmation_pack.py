from __future__ import annotations

from pathlib import Path
from typing import Any

from roibang_v2.runs import write_run_artifact


def _pack_config(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("create_phase2_template_confirmation_pack")
    return dict(value) if isinstance(value, dict) else dict(request)


def _safe_source_artifact(artifact: dict[str, Any]) -> list[str]:
    violations: list[str] = []
    if str(artifact.get("workflow") or "") != "create_phase2_template_slot_prep":
        violations.append("template slot prep artifact workflow mismatch")
    if str(artifact.get("phase") or "") != "phase2_preparation":
        violations.append("template slot prep artifact phase must be phase2_preparation")
    if bool(artifact.get("execution_enabled", False)):
        violations.append("template slot prep artifact execution_enabled must be false")
    if int(artifact.get("external_api_calls") or 0) != 0:
        violations.append("template slot prep artifact external_api_calls must be 0")
    if artifact.get("actions"):
        violations.append("template slot prep artifact actions must be empty")
    return violations


def _confirmation_records(artifact: dict[str, Any]) -> list[dict[str, Any]]:
    rows = artifact.get("template_confirmation_checklist")
    checklist = rows if isinstance(rows, list) else []
    records: list[dict[str, Any]] = []
    for item in checklist:
        if not isinstance(item, dict):
            continue
        records.append(
            {
                "item_no": int(item.get("item_no") or len(records) + 1),
                "section": str(item.get("section") or ""),
                "field": str(item.get("field") or ""),
                "current_value": str(item.get("current_value") or ""),
                "source": str(item.get("source") or ""),
                "suggested_action": str(item.get("suggested_action") or ""),
                "question": str(item.get("question") or ""),
                "confirmation_status": "pending",
                "confirmed_value": "",
                "user_note": "",
            }
        )
    return records


def _confirmation_contract() -> dict[str, Any]:
    return {
        "review_only": True,
        "writes_policy": False,
        "execution_enabled": False,
        "external_api_calls": 0,
        "create_execute_hard_block_required": True,
    }


def _summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    confirmed = [record for record in records if str(record.get("confirmation_status") or "") == "confirmed"]
    changed = [
        record
        for record in confirmed
        if str(record.get("confirmed_value") or "") and str(record.get("confirmed_value") or "") != str(record.get("current_value") or "")
    ]
    return {
        "source_workflow": "create_phase2_template_slot_prep",
        "confirmation_item_count": len(records),
        "pending_confirmation_count": len(records) - len(confirmed),
        "confirmed_count": len(confirmed),
        "changed_count": len(changed),
        "ready_for_live_payload_development": False,
        "ready_for_live_execute": False,
    }


def build_create_phase2_template_confirmation_pack(
    *,
    create_phase2_template_slot_prep_artifact: dict[str, Any],
) -> dict[str, Any]:
    records = _confirmation_records(create_phase2_template_slot_prep_artifact)
    violations = _safe_source_artifact(create_phase2_template_slot_prep_artifact)
    if not records:
        violations.append("template confirmation checklist is empty")
    return {
        "ok": not violations,
        "workflow": "create_phase2_template_confirmation_pack",
        "phase": "phase2_preparation",
        "execution_enabled": False,
        "external_api_calls": 0,
        "required_user_input_now": True,
        "status": "blocked" if violations else "needs_user_confirmation",
        "summary": _summary(records),
        "confirmation_contract": _confirmation_contract(),
        "confirmation_records": records,
        "violations": violations,
        "actions": [],
    }


def run_create_phase2_template_confirmation_pack_request(
    request: dict[str, Any],
    *,
    runs_dir: str | Path,
) -> dict[str, Any]:
    cfg = _pack_config(request)
    artifact = cfg.get("create_phase2_template_slot_prep_artifact")
    if not isinstance(artifact, dict):
        raise ValueError("template confirmation pack requires template slot prep artifact")
    payload = build_create_phase2_template_confirmation_pack(
        create_phase2_template_slot_prep_artifact=artifact,
    )
    artifact_path = write_run_artifact(runs_dir, "create_phase2_template_confirmation_pack", payload)
    return {**payload, "artifact_path": str(artifact_path)}
