from __future__ import annotations

from pathlib import Path
from typing import Any

from roibang_v2.runs import write_run_artifact


def _checklist_config(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("create_phase1_acceptance_checklist")
    return dict(value) if isinstance(value, dict) else dict(request)


def _summary_dict(artifact: dict[str, Any]) -> dict[str, Any]:
    value = artifact.get("summary")
    return dict(value) if isinstance(value, dict) else {}


def _safety_contract(chain_index: dict[str, Any]) -> dict[str, Any]:
    value = chain_index.get("safety_contract")
    return dict(value) if isinstance(value, dict) else {}


def _violations(*artifacts: dict[str, Any]) -> list[str]:
    rows: list[str] = []
    for artifact in artifacts:
        value = artifact.get("violations")
        if not isinstance(value, list):
            continue
        for item in value:
            text = str(item)
            if text and text not in rows:
                rows.append(text)
    return rows


def _row(check_id: str, label: str, accepted: bool, evidence: str) -> dict[str, Any]:
    return {
        "check_id": check_id,
        "label": label,
        "accepted": accepted,
        "evidence": evidence,
    }


def _build_checklist(*, final_report: dict[str, Any], chain_index: dict[str, Any]) -> list[dict[str, Any]]:
    final_summary = _summary_dict(final_report)
    index_summary = _summary_dict(chain_index)
    safety = _safety_contract(chain_index)

    artifact_count = int(index_summary.get("artifact_count") or final_summary.get("artifact_count") or 0)
    missing_count = int(index_summary.get("missing_artifact_count") or final_summary.get("missing_artifact_count") or 0)
    unsafe_count = int(index_summary.get("unsafe_artifact_count") or final_summary.get("unsafe_artifact_count") or 0)

    chain_complete = (
        bool(chain_index.get("ok", False))
        and str(chain_index.get("status") or "") == "indexed"
        and artifact_count >= 16
        and missing_count == 0
    )
    safety_passed = (
        str(safety.get("status") or "") == "passed"
        and bool(safety.get("execution_enabled_false", False))
        and bool(safety.get("external_api_calls_zero", False))
        and bool(safety.get("actions_empty", False))
        and bool(safety.get("no_live_execute_allowed", False))
        and bool(safety.get("no_live_payloads", False))
        and unsafe_count == 0
    )
    final_report_generated = (
        str(final_report.get("workflow") or "") == "create_chain_final_report"
        and str(final_report.get("status") or "") == "reported"
    )
    live_execute_allowed = bool(final_summary.get("live_execute_allowed", False))
    real_create_blocked = (
        str(final_report.get("overall_status") or "") != "unsafe_live_execute_allowed"
        and not live_execute_allowed
        and bool(safety.get("no_live_execute_allowed", False))
    )
    no_human_input_now = bool(final_report.get("required_user_input_now", True)) is False
    phase1_closeable = all(
        [
            chain_complete,
            safety_passed,
            final_report_generated,
            real_create_blocked,
            no_human_input_now,
        ]
    )

    return [
        _row(
            "create_chain_complete",
            "创建链路本地产物完整",
            chain_complete,
            f"artifact_count={artifact_count}, missing_artifact_count={missing_count}",
        ),
        _row(
            "phase1_safety_contract_passed",
            "创建链路安全契约通过",
            safety_passed,
            f"safety_contract={safety.get('status') or 'missing'}, unsafe_artifact_count={unsafe_count}",
        ),
        _row(
            "final_report_generated",
            "最终报告已生成",
            final_report_generated,
            f"status={final_report.get('status') or ''}, overall_status={final_report.get('overall_status') or ''}",
        ),
        _row(
            "real_create_blocked",
            "真实创建保持阻断",
            real_create_blocked,
            f"live_execute_allowed={live_execute_allowed}",
        ),
        _row(
            "no_human_input_now",
            "当前不要求人工临场输入",
            no_human_input_now,
            f"required_user_input_now={final_report.get('required_user_input_now')}",
        ),
        _row(
            "phase1_closeable",
            "Phase 1 可作为安全前半段收尾",
            phase1_closeable,
            "all previous acceptance checks passed" if phase1_closeable else "one or more previous checks failed",
        ),
    ]


def _recommended_next_steps(blocking_items: list[str]) -> list[str]:
    if blocking_items:
        return [
            "修复阻塞验收项",
            "重新生成创建链路最终报告",
            "继续保持真实创建执行脚本硬阻断",
        ]
    return [
        "冻结 Phase 1 创建链路安全基线",
        "由你决定是否进入 Phase 2 字段和模板确认",
        "继续保持真实创建执行脚本硬阻断",
    ]


def build_create_phase1_acceptance_checklist(
    *,
    create_chain_final_report_artifact: dict[str, Any],
    create_chain_index_artifact: dict[str, Any],
) -> dict[str, Any]:
    checklist = _build_checklist(
        final_report=create_chain_final_report_artifact,
        chain_index=create_chain_index_artifact,
    )
    accepted_items = [str(row["label"]) for row in checklist if bool(row["accepted"])]
    blocking_items = [str(row["label"]) for row in checklist if not bool(row["accepted"])]
    violations = _violations(create_chain_final_report_artifact, create_chain_index_artifact)
    accepted = not blocking_items and not violations

    return {
        "ok": accepted,
        "workflow": "create_phase1_acceptance_checklist",
        "phase": "phase1",
        "execution_enabled": False,
        "external_api_calls": 0,
        "status": "accepted_with_phase1_blockers" if accepted else "blocked",
        "phase1_acceptance_status": "accepted" if accepted else "blocked",
        "summary": {
            "check_count": len(checklist),
            "accepted_check_count": len(accepted_items),
            "blocking_check_count": len(blocking_items),
            "phase1_real_create_blocked": "真实创建保持阻断" in accepted_items,
            "ready_for_phase2_review": accepted,
        },
        "checklist": checklist,
        "accepted_items": accepted_items,
        "blocking_items": blocking_items,
        "recommended_next_steps": _recommended_next_steps(blocking_items),
        "source_workflows": [
            str(create_chain_final_report_artifact.get("workflow") or ""),
            str(create_chain_index_artifact.get("workflow") or ""),
        ],
        "required_user_input_now": False,
        "violations": violations,
        "actions": [],
    }


def run_create_phase1_acceptance_checklist_request(
    request: dict[str, Any],
    *,
    runs_dir: str | Path,
) -> dict[str, Any]:
    cfg = _checklist_config(request)
    required = [
        "create_chain_final_report_artifact",
        "create_chain_index_artifact",
    ]
    missing = [key for key in required if not isinstance(cfg.get(key), dict)]
    if missing:
        raise ValueError(f"create phase1 acceptance checklist requires artifacts: {', '.join(missing)}")
    payload = build_create_phase1_acceptance_checklist(
        create_chain_final_report_artifact=cfg["create_chain_final_report_artifact"],
        create_chain_index_artifact=cfg["create_chain_index_artifact"],
    )
    artifact_path = write_run_artifact(runs_dir, "create_phase1_acceptance_checklist", payload)
    return {**payload, "artifact_path": str(artifact_path)}
