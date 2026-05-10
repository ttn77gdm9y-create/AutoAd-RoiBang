from __future__ import annotations

from pathlib import Path
from typing import Any

from roibang_v2.runs import write_run_artifact


def _report_config(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("create_chain_final_report")
    return dict(value) if isinstance(value, dict) else dict(request)


def _summary_dict(artifact: dict[str, Any]) -> dict[str, Any]:
    value = artifact.get("summary")
    return dict(value) if isinstance(value, dict) else {}


def _blocking_reasons(*, readiness: dict[str, Any], phase_gate: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    for artifact in (readiness, phase_gate):
        rows = artifact.get("blocking_reasons")
        if not isinstance(rows, list):
            continue
        for row in rows:
            reason = str(row)
            if reason and reason not in reasons:
                reasons.append(reason)
    return reasons


def _overall_status(*, chain_index: dict[str, Any], readiness: dict[str, Any], phase_gate: dict[str, Any]) -> str:
    if not bool(chain_index.get("ok", False)) or str(chain_index.get("status") or "") != "indexed":
        return "invalid_chain_artifacts"
    if bool(phase_gate.get("live_execute_allowed", False)):
        return "unsafe_live_execute_allowed"
    if bool(readiness.get("ready_for_live_execute", False)) and bool(
        phase_gate.get("live_execute_development_allowed", False)
    ):
        return "ready_for_live_execute_development"
    return "not_ready_for_live_create"


def _business_summary(overall_status: str) -> str:
    if overall_status == "invalid_chain_artifacts":
        return "创建链路产物存在缺失或安全违规，必须先修复本地链路。"
    if overall_status == "unsafe_live_execute_allowed":
        return "创建链路出现真实执行放行配置，必须立即关闭并修复策略。"
    if overall_status == "ready_for_live_execute_development":
        return "创建链路本地关卡已准备好进入后续真实创建开发评审，但仍不代表可以真实执行。"
    return (
        "创建链路本地产物已索引完成，Phase 1 仍保持真实创建阻断；"
        "当前主要卡点是字段映射、模板槽位和阶段闸门。"
    )


def _execute_manual_summary(create_execute: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(create_execute, dict):
        return {}
    review_pack = create_execute.get("execute_review_pack")
    if not isinstance(review_pack, dict):
        return {}
    summary = review_pack.get("manual_review_summary")
    return dict(summary) if isinstance(summary, dict) else {}


def _creation_boundary_summary(create_execute: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(create_execute, dict):
        return {
            "status": "missing_create_execute_review",
            "plain_language": "最终报告未收到 create_execute 复核产物，无法汇总真实创建前最后边界。",
            "checks": {
                "execute_hard_blocked": False,
                "external_api_calls_zero": False,
                "actions_empty": False,
                "no_live_payloads": False,
                "no_executable_payloads": False,
                "approved_for_execute": False,
            },
            "payload_counts": {"create_project": 0, "create_unit": 0, "bind_material": 0, "total": 0},
            "counts": {
                "payload_count": 0,
                "executable_true_count": 0,
                "live_payload_count": 0,
                "unresolved_lookup_placeholder_count": 0,
            },
            "next_focus": "run_create_execute",
            "execution_enabled": False,
            "external_api_calls": 0,
            "actions": [],
        }
    contract = create_execute.get("chain_boundary_contract")
    contract = contract if isinstance(contract, dict) else {}
    manual_summary = _execute_manual_summary(create_execute)
    counts = manual_summary.get("counts") if isinstance(manual_summary.get("counts"), dict) else {}
    payload_counts = manual_summary.get("payload_counts") if isinstance(manual_summary.get("payload_counts"), dict) else {}
    unresolved_count = int(counts.get("unresolved_lookup_placeholder_count") or 0)
    status = str(contract.get("status") or manual_summary.get("status") or "unknown")
    if unresolved_count:
        plain_language = (
            "真实创建仍被 create_execute 硬阻断；"
            f"当前 execute 复核包还有 {unresolved_count} 个 lookup 占位符未解析。"
        )
        next_focus = "provider_id_ledger"
    else:
        plain_language = (
            "真实创建仍被 create_execute 硬阻断；execute 复核包已可人工核对 resolved payload。"
        )
        next_focus = "manual_payload_review"
    return {
        "status": status,
        "plain_language": plain_language,
        "checks": {
            "execute_hard_blocked": bool(contract.get("execute_hard_blocked", False)),
            "external_api_calls_zero": bool(contract.get("external_api_calls_zero", False)),
            "actions_empty": bool(contract.get("actions_empty", False)),
            "no_live_payloads": bool(contract.get("no_live_payloads", False)),
            "no_executable_payloads": bool(contract.get("no_executable_payloads", False)),
            "approved_for_execute": bool(contract.get("approved_for_execute", False)),
        },
        "payload_counts": {
            "create_project": int(payload_counts.get("create_project") or 0),
            "create_unit": int(payload_counts.get("create_unit") or 0),
            "bind_material": int(payload_counts.get("bind_material") or 0),
            "total": int(payload_counts.get("total") or 0),
        },
        "counts": {
            "payload_count": int(counts.get("payload_count") or 0),
            "executable_true_count": int(counts.get("executable_true_count") or 0),
            "live_payload_count": int(counts.get("live_payload_count") or 0),
            "unresolved_lookup_placeholder_count": unresolved_count,
        },
        "next_focus": next_focus,
        "execution_enabled": False,
        "external_api_calls": 0,
        "actions": [],
    }


def _summary(
    *,
    chain_index: dict[str, Any],
    readiness: dict[str, Any],
    phase_gate: dict[str, Any],
    blocking_reasons: list[str],
) -> dict[str, Any]:
    index_summary = _summary_dict(chain_index)
    return {
        "artifact_count": int(index_summary.get("artifact_count") or 0),
        "missing_artifact_count": int(index_summary.get("missing_artifact_count") or 0),
        "unsafe_artifact_count": int(index_summary.get("unsafe_artifact_count") or 0),
        "ready_for_live_execute": bool(readiness.get("ready_for_live_execute", False)),
        "live_execute_development_allowed": bool(phase_gate.get("live_execute_development_allowed", False)),
        "live_execute_allowed": bool(phase_gate.get("live_execute_allowed", False)),
        "blocking_reason_count": len(blocking_reasons),
    }


def _completed_sections() -> list[str]:
    return [
        "创建请求到本地预演链路已成型",
        "字段映射审阅包和模板槽位审阅包已生成",
        "链路回放、清单、索引和安全契约已覆盖",
        "真实执行和真实请求体仍保持硬阻断",
    ]


def _pending_confirmations(overall_status: str) -> list[str]:
    if overall_status == "invalid_chain_artifacts":
        return ["修复本地创建链路产物缺失或安全违规"]
    return [
        "确认 provider field map（渠道字段映射）",
        "确认 template slots（固定模板槽位）",
        "确认是否进入 Phase 2（真实创建开发阶段）",
    ]


def _recommended_next_steps(overall_status: str, creation_boundary: dict[str, Any] | None = None) -> list[str]:
    if overall_status == "invalid_chain_artifacts":
        return ["先修复本地链路产物", "重新跑创建链路索引", "继续保持 create_execute 硬阻断"]
    if isinstance(creation_boundary, dict):
        next_focus = str(creation_boundary.get("next_focus") or "")
        if next_focus == "provider_id_ledger":
            return [
                "保持 create_execute 硬阻断",
                "补齐 provider ID ledger（平台 ID 台账）后重新复核 execute payload",
                "审阅字段映射、模板槽位和 execute_review_pack",
            ]
        if next_focus == "manual_payload_review":
            return [
                "保持 create_execute 硬阻断",
                "人工复核 execute_review_pack 的 resolved payload",
                "准备后续由你单独确认是否进入真实执行开发阶段",
            ]
    return [
        "保持 create_execute 硬阻断",
        "审阅字段映射和模板槽位",
        "准备后续由你确认是否参考老项目成熟模板",
    ]


def _violations(chain_index: dict[str, Any], phase_gate: dict[str, Any]) -> list[str]:
    violations: list[str] = []
    for artifact in (chain_index, phase_gate):
        rows = artifact.get("violations")
        if isinstance(rows, list):
            violations.extend(str(item) for item in rows if str(item))
    return violations


def build_create_chain_final_report(
    *,
    create_chain_index_artifact: dict[str, Any],
    create_readiness_matrix_artifact: dict[str, Any],
    create_live_execute_phase_gate_artifact: dict[str, Any],
    create_adapter_review_pack_artifact: dict[str, Any],
    create_execute_artifact: dict[str, Any] | None = None,
) -> dict[str, Any]:
    blocking = _blocking_reasons(
        readiness=create_readiness_matrix_artifact,
        phase_gate=create_live_execute_phase_gate_artifact,
    )
    overall = _overall_status(
        chain_index=create_chain_index_artifact,
        readiness=create_readiness_matrix_artifact,
        phase_gate=create_live_execute_phase_gate_artifact,
    )
    violations = _violations(create_chain_index_artifact, create_live_execute_phase_gate_artifact)
    creation_boundary = _creation_boundary_summary(create_execute_artifact)
    source_workflows = [
        str(create_chain_index_artifact.get("workflow") or ""),
        str(create_readiness_matrix_artifact.get("workflow") or ""),
        str(create_live_execute_phase_gate_artifact.get("workflow") or ""),
        str(create_adapter_review_pack_artifact.get("workflow") or ""),
    ]
    if isinstance(create_execute_artifact, dict):
        source_workflows.append(str(create_execute_artifact.get("workflow") or ""))
    return {
        "ok": overall not in {"invalid_chain_artifacts", "unsafe_live_execute_allowed"} and not violations,
        "workflow": "create_chain_final_report",
        "phase": "phase1",
        "execution_enabled": False,
        "external_api_calls": 0,
        "status": "reported" if overall != "invalid_chain_artifacts" else "invalid",
        "overall_status": overall,
        "business_summary": _business_summary(overall),
        "summary": _summary(
            chain_index=create_chain_index_artifact,
            readiness=create_readiness_matrix_artifact,
            phase_gate=create_live_execute_phase_gate_artifact,
            blocking_reasons=blocking,
        ),
        "completed_sections": _completed_sections(),
        "pending_confirmations": _pending_confirmations(overall),
        "blocking_reasons": blocking,
        "recommended_next_steps": _recommended_next_steps(overall, creation_boundary),
        "creation_boundary_summary": creation_boundary,
        "source_workflows": source_workflows,
        "adapter_review_status": str(create_adapter_review_pack_artifact.get("status") or ""),
        "required_user_input_now": False,
        "violations": violations,
        "actions": [],
    }


def run_create_chain_final_report_request(
    request: dict[str, Any],
    *,
    runs_dir: str | Path,
) -> dict[str, Any]:
    cfg = _report_config(request)
    required = [
        "create_chain_index_artifact",
        "create_readiness_matrix_artifact",
        "create_live_execute_phase_gate_artifact",
        "create_adapter_review_pack_artifact",
    ]
    missing = [key for key in required if not isinstance(cfg.get(key), dict)]
    if missing:
        raise ValueError(f"create chain final report requires artifacts: {', '.join(missing)}")
    payload = build_create_chain_final_report(
        create_chain_index_artifact=cfg["create_chain_index_artifact"],
        create_readiness_matrix_artifact=cfg["create_readiness_matrix_artifact"],
        create_live_execute_phase_gate_artifact=cfg["create_live_execute_phase_gate_artifact"],
        create_adapter_review_pack_artifact=cfg["create_adapter_review_pack_artifact"],
        create_execute_artifact=cfg.get("create_execute_artifact")
        if isinstance(cfg.get("create_execute_artifact"), dict)
        else None,
    )
    artifact_path = write_run_artifact(runs_dir, "create_chain_final_report", payload)
    return {**payload, "artifact_path": str(artifact_path)}
