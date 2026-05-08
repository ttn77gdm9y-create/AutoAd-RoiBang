from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from roibang_v2.runs import write_run_artifact


BASELINE_ID = "phase1-create-safe-baseline-v1"


def _freeze_config(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("create_phase1_baseline_freeze")
    return dict(value) if isinstance(value, dict) else dict(request)


def _summary_dict(artifact: dict[str, Any]) -> dict[str, Any]:
    value = artifact.get("summary")
    return dict(value) if isinstance(value, dict) else {}


def _safety_contract(chain_index: dict[str, Any]) -> dict[str, Any]:
    value = chain_index.get("safety_contract")
    return dict(value) if isinstance(value, dict) else {}


def _list_field(artifact: dict[str, Any], field: str) -> list[str]:
    value = artifact.get(field)
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item)]


def _violations(*artifacts: dict[str, Any]) -> list[str]:
    rows: list[str] = []
    for artifact in artifacts:
        for item in _list_field(artifact, "violations"):
            if item not in rows:
                rows.append(item)
    return rows


def _source_paths(*, acceptance: dict[str, Any], final_report: dict[str, Any], chain_index: dict[str, Any]) -> dict[str, str]:
    return {
        "create_phase1_acceptance_checklist": str(acceptance.get("artifact_path") or ""),
        "create_chain_final_report": str(final_report.get("artifact_path") or ""),
        "create_chain_index": str(chain_index.get("artifact_path") or ""),
    }


def _baseline_digest(payload: dict[str, Any]) -> dict[str, Any]:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {
        "algorithm": "sha256",
        "value": hashlib.sha256(encoded).hexdigest(),
    }


def _freeze_contract(*, acceptance: dict[str, Any], final_report: dict[str, Any], chain_index: dict[str, Any]) -> dict[str, Any]:
    acceptance_summary = _summary_dict(acceptance)
    final_summary = _summary_dict(final_report)
    safety = _safety_contract(chain_index)
    accepted = (
        bool(acceptance.get("ok", False))
        and str(acceptance.get("phase1_acceptance_status") or "") == "accepted"
        and int(acceptance_summary.get("blocking_check_count") or 0) == 0
    )
    live_execute_allowed = bool(final_summary.get("live_execute_allowed", False))
    execution_enabled_false = bool(safety.get("execution_enabled_false", False))
    external_api_calls_zero = bool(safety.get("external_api_calls_zero", False))
    actions_empty = bool(safety.get("actions_empty", False))
    no_live_execute_allowed = bool(safety.get("no_live_execute_allowed", False)) and not live_execute_allowed
    no_live_payloads = bool(safety.get("no_live_payloads", False))
    frozen = all(
        [
            accepted,
            execution_enabled_false,
            external_api_calls_zero,
            actions_empty,
            no_live_execute_allowed,
            no_live_payloads,
        ]
    )
    return {
        "status": "frozen" if frozen else "blocked",
        "acceptance_required": True,
        "acceptance_status": str(acceptance.get("phase1_acceptance_status") or ""),
        "execution_enabled_false": execution_enabled_false,
        "external_api_calls_zero": external_api_calls_zero,
        "actions_empty": actions_empty,
        "no_live_execute_allowed": no_live_execute_allowed,
        "no_live_payloads": no_live_payloads,
    }


def _recommended_next_steps(frozen: bool) -> list[str]:
    if frozen:
        return [
            "保留 Phase 1 安全基线产物",
            "进入 Phase 2 前先确认字段映射和模板槽位",
            "真实创建执行仍保持关闭",
        ]
    return [
        "修复阻塞验收项",
        "重新生成 Phase 1 验收清单",
        "真实创建执行仍保持关闭",
    ]


def build_create_phase1_baseline_freeze(
    *,
    create_phase1_acceptance_checklist_artifact: dict[str, Any],
    create_chain_final_report_artifact: dict[str, Any],
    create_chain_index_artifact: dict[str, Any],
) -> dict[str, Any]:
    acceptance = create_phase1_acceptance_checklist_artifact
    final_report = create_chain_final_report_artifact
    chain_index = create_chain_index_artifact
    acceptance_summary = _summary_dict(acceptance)
    final_summary = _summary_dict(final_report)
    contract = _freeze_contract(acceptance=acceptance, final_report=final_report, chain_index=chain_index)
    violations = _violations(acceptance, final_report, chain_index)
    blocking_reasons = _list_field(acceptance, "blocking_items")
    frozen = contract["status"] == "frozen" and not violations
    digest_source = {
        "baseline_id": BASELINE_ID,
        "acceptance_status": acceptance.get("phase1_acceptance_status"),
        "acceptance_summary": acceptance_summary,
        "final_report_summary": final_summary,
        "chain_index_summary": _summary_dict(chain_index),
        "source_artifact_paths": _source_paths(
            acceptance=acceptance,
            final_report=final_report,
            chain_index=chain_index,
        ),
    }

    return {
        "ok": frozen,
        "workflow": "create_phase1_baseline_freeze",
        "phase": "phase1",
        "execution_enabled": False,
        "external_api_calls": 0,
        "status": "frozen" if frozen else "blocked",
        "phase1_baseline_status": "frozen" if frozen else "blocked",
        "baseline_id": BASELINE_ID,
        "baseline_digest": _baseline_digest(digest_source),
        "summary": {
            "accepted": str(acceptance.get("phase1_acceptance_status") or "") == "accepted",
            "artifact_count": int(final_summary.get("artifact_count") or _summary_dict(chain_index).get("artifact_count") or 0),
            "accepted_check_count": int(acceptance_summary.get("accepted_check_count") or 0),
            "blocking_check_count": int(acceptance_summary.get("blocking_check_count") or 0),
            "real_create_blocked": bool(acceptance_summary.get("phase1_real_create_blocked", False)),
            "ready_for_phase2_review": frozen,
        },
        "freeze_contract": contract,
        "frozen_workflows": [
            "create_phase1_acceptance_checklist",
            "create_chain_final_report",
            "create_chain_index",
        ],
        "source_artifact_paths": _source_paths(
            acceptance=acceptance,
            final_report=final_report,
            chain_index=chain_index,
        ),
        "blocking_reasons": blocking_reasons,
        "recommended_next_steps": _recommended_next_steps(frozen),
        "required_user_input_now": False,
        "violations": violations,
        "actions": [],
    }


def run_create_phase1_baseline_freeze_request(
    request: dict[str, Any],
    *,
    runs_dir: str | Path,
) -> dict[str, Any]:
    cfg = _freeze_config(request)
    required = [
        "create_phase1_acceptance_checklist_artifact",
        "create_chain_final_report_artifact",
        "create_chain_index_artifact",
    ]
    missing = [key for key in required if not isinstance(cfg.get(key), dict)]
    if missing:
        raise ValueError(f"create phase1 baseline freeze requires artifacts: {', '.join(missing)}")
    payload = build_create_phase1_baseline_freeze(
        create_phase1_acceptance_checklist_artifact=cfg["create_phase1_acceptance_checklist_artifact"],
        create_chain_final_report_artifact=cfg["create_chain_final_report_artifact"],
        create_chain_index_artifact=cfg["create_chain_index_artifact"],
    )
    artifact_path = write_run_artifact(runs_dir, "create_phase1_baseline_freeze", payload)
    return {**payload, "artifact_path": str(artifact_path)}
