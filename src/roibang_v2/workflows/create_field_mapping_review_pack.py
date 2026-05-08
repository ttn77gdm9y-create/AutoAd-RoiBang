from __future__ import annotations

from pathlib import Path
from typing import Any

from roibang_v2.runs import write_run_artifact
from roibang_v2.workflows.create_payload_schema import disabled_create_payload_schema
from roibang_v2.workflows.create_provider_adapter import disabled_provider_adapter, provider_adapter_contract
from roibang_v2.workflows.create_provider_field_map import (
    load_provider_field_map,
    provider_field_map_contract,
    provider_field_map_digest,
)
from roibang_v2.workflows.create_provider_readiness import provider_readiness_contract


def _review_pack_config(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("create_field_mapping_review_pack")
    return dict(value) if isinstance(value, dict) else dict(request)


def _field_map_path(policy: dict[str, Any]) -> str:
    return str(policy.get("provider_field_map_path") or "").strip()


def _review_status(entry: dict[str, Any]) -> str:
    if not str(entry.get("provider_field") or "").strip():
        return "needs_provider_field"
    if not bool(entry.get("verified", False)):
        return "needs_verification"
    return "verified"


def _review_sections(
    *,
    field_map: dict[str, Any],
    payload_schema: dict[str, Any],
) -> list[dict[str, Any]]:
    operations = field_map.get("operations") if isinstance(field_map.get("operations"), dict) else {}
    endpoints = payload_schema.get("endpoints") if isinstance(payload_schema.get("endpoints"), dict) else {}
    field_sources = payload_schema.get("field_sources") if isinstance(payload_schema.get("field_sources"), dict) else {}
    sections: list[dict[str, Any]] = []
    for operation, rows in operations.items():
        fields: list[dict[str, Any]] = []
        for entry in rows if isinstance(rows, list) else []:
            if not isinstance(entry, dict):
                continue
            fields.append(
                {
                    "internal_field": str(entry.get("internal_field") or ""),
                    "provider_field": str(entry.get("provider_field") or ""),
                    "required": bool(entry.get("required", False)),
                    "verified": bool(entry.get("verified", False)),
                    "purpose": str(entry.get("purpose") or ""),
                    "source": str(entry.get("source") or ""),
                    "review_status": _review_status(entry),
                }
            )
        sections.append(
            {
                "operation": str(operation),
                "endpoint": str(endpoints.get(operation) or ""),
                "field_source": str(field_sources.get(operation) or ""),
                "fields": fields,
            }
        )
    return sections


def _review_contract(field_contract: dict[str, Any], sections: list[dict[str, Any]]) -> dict[str, Any]:
    fields = [
        field
        for section in sections
        for field in section.get("fields", [])
        if isinstance(field, dict)
    ]
    needs_provider = sum(1 for field in fields if field.get("review_status") == "needs_provider_field")
    needs_verification = sum(1 for field in fields if field.get("review_status") in {"needs_provider_field", "needs_verification"})
    verified = sum(1 for field in fields if field.get("review_status") == "verified")
    status = "verified" if str(field_contract.get("status") or "") == "verified" else "needs_review"
    return {
        "status": status,
        "field_count": len(fields),
        "needs_provider_field_count": needs_provider,
        "needs_verification_count": needs_verification,
        "verified_field_count": verified,
        "missing_required_field_count": int(field_contract.get("missing_required_field_count") or 0),
        "duplicate_internal_field_count": int(field_contract.get("duplicate_internal_field_count") or 0),
        "duplicate_provider_field_count": int(field_contract.get("duplicate_provider_field_count") or 0),
        "unknown_internal_field_count": int(field_contract.get("unknown_internal_field_count") or 0),
    }


def _summary(
    *,
    policy: dict[str, Any],
    field_map: dict[str, Any],
    review_contract: dict[str, Any],
    readiness_contract: dict[str, Any],
) -> dict[str, Any]:
    return {
        "provider": str(field_map.get("provider") or ""),
        "field_mapping_version": str(field_map.get("field_mapping_version") or ""),
        "field_map_path": _field_map_path(policy),
        "operation_count": len(field_map.get("operations") if isinstance(field_map.get("operations"), dict) else {}),
        "field_count": int(review_contract.get("field_count") or 0),
        "needs_provider_field_count": int(review_contract.get("needs_provider_field_count") or 0),
        "needs_verification_count": int(review_contract.get("needs_verification_count") or 0),
        "ready_for_live_execute": bool(readiness_contract.get("ready_for_live_execute", False)),
    }


def build_create_field_mapping_review_pack(*, policy: dict[str, Any]) -> dict[str, Any]:
    field_map = load_provider_field_map(policy)
    field_contract = provider_field_map_contract(field_map, policy)
    field_digest = provider_field_map_digest(field_map)
    payload_schema = disabled_create_payload_schema(policy)
    sections = _review_sections(field_map=field_map, payload_schema=payload_schema)
    review_contract = _review_contract(field_contract, sections)
    adapter = disabled_provider_adapter(policy)
    adapter_contract = provider_adapter_contract(adapter=adapter, provider_payload_drafts=[], tasks=[])
    draft_contract = {
        "status": "passed",
        "draft_count": 0,
        "live_payload_count": 0,
        "executable_draft_count": 0,
        "redacted": True,
    }
    readiness = provider_readiness_contract(
        provider_adapter_contract=adapter_contract,
        provider_field_map_contract=field_contract,
        payload_draft_contract=draft_contract,
    )
    invalid_config = str(field_map.get("source") or "") == "phase1_placeholder_invalid_provider_field_map_config"
    violations = ["provider field map config is missing or malformed"] if invalid_config else []
    return {
        "ok": not invalid_config,
        "workflow": "create_field_mapping_review_pack",
        "phase": "phase1",
        "execution_enabled": False,
        "external_api_calls": 0,
        "status": "invalid" if invalid_config else str(review_contract.get("status") or "needs_review"),
        "required_user_input_now": False,
        "summary": _summary(
            policy=policy,
            field_map=field_map,
            review_contract=review_contract,
            readiness_contract=readiness,
        ),
        "payload_schema": payload_schema,
        "provider_field_map": field_map,
        "provider_field_map_contract": field_contract,
        "provider_field_map_digest": field_digest,
        "provider_readiness_contract": readiness,
        "review_contract": review_contract,
        "review_sections": sections,
        "violations": violations,
        "actions": [],
    }


def run_create_field_mapping_review_pack_request(
    request: dict[str, Any],
    *,
    runs_dir: str | Path,
) -> dict[str, Any]:
    cfg = _review_pack_config(request)
    policy = cfg.get("policy") if isinstance(cfg.get("policy"), dict) else {}
    payload = build_create_field_mapping_review_pack(policy=policy)
    artifact_path = write_run_artifact(runs_dir, "create_field_mapping_review_pack", payload)
    return {**payload, "artifact_path": str(artifact_path)}
