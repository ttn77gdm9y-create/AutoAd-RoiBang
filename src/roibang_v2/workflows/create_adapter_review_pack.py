from __future__ import annotations

from pathlib import Path
from typing import Any

from roibang_v2.runs import write_run_artifact


def _review_pack_config(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("create_adapter_review_pack")
    return dict(value) if isinstance(value, dict) else dict(request)


def _summary(scaffold: dict[str, Any], review_contract: dict[str, Any], sections: list[dict[str, Any]]) -> dict[str, Any]:
    summary = scaffold.get("summary") if isinstance(scaffold.get("summary"), dict) else {}
    return {
        "provider": str(summary.get("provider") or ""),
        "field_mapping_version": str(summary.get("field_mapping_version") or ""),
        "adapter_status": str(scaffold.get("status") or ""),
        "provider_payload_draft_count": int(summary.get("provider_payload_draft_count") or 0),
        "live_payload_count": int(summary.get("live_payload_count") or 0),
        "executable_payload_count": int(summary.get("executable_payload_count") or 0),
        "review_item_count": len(sections),
        "blocking_reason_count": len(scaffold.get("blocking_reasons") if isinstance(scaffold.get("blocking_reasons"), list) else []),
    }


def _adapter_interface(scaffold: dict[str, Any]) -> dict[str, Any]:
    value = scaffold.get("adapter_interface")
    return dict(value) if isinstance(value, dict) else {}


def _safety_contract(scaffold: dict[str, Any]) -> dict[str, Any]:
    value = scaffold.get("safety_contract")
    return dict(value) if isinstance(value, dict) else {}


def _provider_payload_draft_digest(scaffold: dict[str, Any]) -> dict[str, Any]:
    digest = scaffold.get("provider_payload_draft_digest")
    if isinstance(digest, dict):
        return {
            "algorithm": str(digest.get("algorithm") or ""),
            "value": str(digest.get("value") or ""),
            "provider_payload_draft_count": int(digest.get("provider_payload_draft_count") or 0),
        }
    return {"algorithm": "sha256", "value": "", "provider_payload_draft_count": 0}


def _items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"key": str(key), "value": value} for key, value in payload.items()]


def _review_sections(scaffold: dict[str, Any]) -> list[dict[str, Any]]:
    interface = _adapter_interface(scaffold)
    input_contract = interface.get("input_contract") if isinstance(interface.get("input_contract"), dict) else {}
    output_contract = interface.get("output_contract") if isinstance(interface.get("output_contract"), dict) else {}
    safety = _safety_contract(scaffold)
    blocking_reasons = scaffold.get("blocking_reasons") if isinstance(scaffold.get("blocking_reasons"), list) else []
    return [
        {
            "section": "input_contract",
            "status": "present" if input_contract else "missing",
            "items": _items(input_contract),
        },
        {
            "section": "output_contract",
            "status": "disabled",
            "items": _items(output_contract),
        },
        {
            "section": "safety_contract",
            "status": str(safety.get("status") or "unknown"),
            "items": [
                {"key": "phase_gate_allows_development", "value": bool(safety.get("phase_gate_allows_development", False))},
                {"key": "phase_gate_allows_live_execute", "value": bool(safety.get("phase_gate_allows_live_execute", False))},
                {"key": "live_payload_generation_enabled", "value": bool(safety.get("live_payload_generation_enabled", False))},
            ],
        },
        {
            "section": "blocking_reasons",
            "status": "blocked" if blocking_reasons else "clear",
            "items": [{"key": "reason", "value": str(item)} for item in blocking_reasons],
        },
    ]


def _review_contract(scaffold: dict[str, Any]) -> dict[str, Any]:
    live_payloads_empty = scaffold.get("live_payloads") == []
    executable_payloads_empty = scaffold.get("executable_payloads") == []
    external_api_calls_zero = int(scaffold.get("external_api_calls") or 0) == 0
    actions_empty = scaffold.get("actions") in (None, [], {})
    safe = live_payloads_empty and executable_payloads_empty and external_api_calls_zero and actions_empty
    return {
        "status": "needs_review" if safe else "invalid",
        "safe_to_review": safe,
        "live_payloads_empty": live_payloads_empty,
        "executable_payloads_empty": executable_payloads_empty,
        "external_api_calls_zero": external_api_calls_zero,
        "actions_empty": actions_empty,
    }


def _violations(contract: dict[str, Any]) -> list[str]:
    violations: list[str] = []
    if not bool(contract.get("live_payloads_empty", False)):
        violations.append("adapter scaffold live_payloads must be empty")
    if not bool(contract.get("executable_payloads_empty", False)):
        violations.append("adapter scaffold executable_payloads must be empty")
    if not bool(contract.get("external_api_calls_zero", False)):
        violations.append("adapter scaffold external_api_calls must be 0")
    if not bool(contract.get("actions_empty", False)):
        violations.append("adapter scaffold actions must be empty")
    return violations


def build_create_adapter_review_pack(
    *,
    create_live_payload_adapter_scaffold_artifact: dict[str, Any],
) -> dict[str, Any]:
    contract = _review_contract(create_live_payload_adapter_scaffold_artifact)
    sections = _review_sections(create_live_payload_adapter_scaffold_artifact)
    violations = _violations(contract)
    return {
        "ok": not violations,
        "workflow": "create_adapter_review_pack",
        "phase": "phase1",
        "execution_enabled": False,
        "external_api_calls": 0,
        "status": "invalid" if violations else "needs_review",
        "required_user_input_now": False,
        "summary": _summary(create_live_payload_adapter_scaffold_artifact, contract, sections),
        "review_contract": contract,
        "review_sections": sections,
        "provider_payload_draft_digest": _provider_payload_draft_digest(
            create_live_payload_adapter_scaffold_artifact
        ),
        "violations": violations,
        "actions": [],
    }


def run_create_adapter_review_pack_request(
    request: dict[str, Any],
    *,
    runs_dir: str | Path,
) -> dict[str, Any]:
    cfg = _review_pack_config(request)
    scaffold = cfg.get("create_live_payload_adapter_scaffold_artifact")
    if not isinstance(scaffold, dict):
        raise ValueError("create adapter review pack requires create_live_payload_adapter_scaffold_artifact")
    payload = build_create_adapter_review_pack(create_live_payload_adapter_scaffold_artifact=scaffold)
    artifact_path = write_run_artifact(runs_dir, "create_adapter_review_pack", payload)
    return {**payload, "artifact_path": str(artifact_path)}
