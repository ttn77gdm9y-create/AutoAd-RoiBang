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


def _prep_config(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("create_phase2_provider_mapping_prep")
    return dict(value) if isinstance(value, dict) else dict(request)


def _field_map_path(policy: dict[str, Any]) -> str:
    return str(policy.get("provider_field_map_path") or "").strip()


def _review_status(entry: dict[str, Any]) -> str:
    mapping_kind = str(entry.get("mapping_kind") or "").strip()
    if mapping_kind in {"local_lookup_key", "local_only"} and bool(entry.get("local_only_confirmed", False)):
        return "local_only_confirmed"
    if not str(entry.get("provider_field") or "").strip():
        return "needs_provider_field"
    evidence = entry.get("evidence_refs")
    if not isinstance(evidence, list) or not [item for item in evidence if str(item or "").strip()]:
        return "needs_evidence"
    if not bool(entry.get("verified", False)):
        return "needs_verification"
    return "verified"


def _field_row(entry: dict[str, Any]) -> dict[str, Any]:
    open_questions = entry.get("open_questions")
    evidence_refs = entry.get("evidence_refs")
    return {
        "internal_field": str(entry.get("internal_field") or ""),
        "provider_field": str(entry.get("provider_field") or ""),
        "provider_object": str(entry.get("provider_object") or ""),
        "mapping_kind": str(entry.get("mapping_kind") or ("direct" if str(entry.get("provider_field") or "").strip() else "")),
        "value_source": str(entry.get("value_source") or ""),
        "evidence_refs": [str(item) for item in evidence_refs if str(item or "").strip()]
        if isinstance(evidence_refs, list)
        else [],
        "open_questions": [str(item) for item in open_questions if str(item or "").strip()]
        if isinstance(open_questions, list)
        else [],
        "review_status": _review_status(entry),
    }


def _review_matrix(*, field_map: dict[str, Any], payload_schema: dict[str, Any]) -> list[dict[str, Any]]:
    operations = field_map.get("operations") if isinstance(field_map.get("operations"), dict) else {}
    endpoints = payload_schema.get("endpoints") if isinstance(payload_schema.get("endpoints"), dict) else {}
    field_sources = payload_schema.get("field_sources") if isinstance(payload_schema.get("field_sources"), dict) else {}
    sections: list[dict[str, Any]] = []
    for operation, rows in operations.items():
        fields = [
            _field_row(entry)
            for entry in rows
            if isinstance(entry, dict)
        ] if isinstance(rows, list) else []
        sections.append(
            {
                "operation": str(operation),
                "endpoint": str(endpoints.get(operation) or ""),
                "field_source": str(field_sources.get(operation) or ""),
                "fields": fields,
            }
        )
    return sections


def _fields(matrix: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        field
        for section in matrix
        for field in (section.get("fields") if isinstance(section.get("fields"), list) else [])
        if isinstance(field, dict)
    ]


def _unresolved_mappings(matrix: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for section in matrix:
        operation = str(section.get("operation") or "")
        for field in section.get("fields") if isinstance(section.get("fields"), list) else []:
            if not isinstance(field, dict):
                continue
            if str(field.get("review_status") or "") in {"verified", "local_only_confirmed"}:
                continue
            rows.append(
                {
                    "operation": operation,
                    "internal_field": str(field.get("internal_field") or ""),
                    "review_status": str(field.get("review_status") or ""),
                    "open_questions": list(field.get("open_questions") or []),
                }
            )
    return rows


def _summary(
    *,
    policy: dict[str, Any],
    field_map: dict[str, Any],
    matrix: list[dict[str, Any]],
) -> dict[str, Any]:
    fields = _fields(matrix)
    unresolved = [
        field
        for field in fields
        if str(field.get("review_status") or "") not in {"verified", "local_only_confirmed"}
    ]
    return {
        "provider": str(field_map.get("provider") or ""),
        "field_mapping_version": str(field_map.get("field_mapping_version") or ""),
        "field_map_path": _field_map_path(policy),
        "operation_count": len(matrix),
        "field_count": len(fields),
        "candidate_provider_field_count": sum(1 for field in fields if str(field.get("provider_field") or "").strip()),
        "verified_field_count": sum(1 for field in fields if str(field.get("review_status") or "") == "verified"),
        "unresolved_field_count": len(unresolved),
        "open_question_count": sum(len(field.get("open_questions") or []) for field in fields),
        "ready_for_live_payload_development": False,
        "ready_for_live_execute": False,
    }


def _phase2_contract() -> dict[str, Any]:
    return {
        "review_only": True,
        "live_payload_generation_enabled": False,
        "create_execute_hard_block_required": True,
        "next_required_reviews": [
            "provider_field_mapping",
            "template_slots",
            "project_naming_rules",
        ],
    }


def build_create_phase2_provider_mapping_prep(*, policy: dict[str, Any]) -> dict[str, Any]:
    field_map = load_provider_field_map(policy)
    field_contract = provider_field_map_contract(field_map, policy)
    field_digest = provider_field_map_digest(field_map)
    payload_schema = disabled_create_payload_schema(policy)
    matrix = _review_matrix(field_map=field_map, payload_schema=payload_schema)
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
        "workflow": "create_phase2_provider_mapping_prep",
        "phase": "phase2_preparation",
        "execution_enabled": False,
        "external_api_calls": 0,
        "status": "invalid" if invalid_config else "needs_review",
        "summary": _summary(policy=policy, field_map=field_map, matrix=matrix),
        "phase2_preparation_contract": _phase2_contract(),
        "payload_schema": payload_schema,
        "provider_field_map": field_map,
        "provider_field_map_contract": field_contract,
        "provider_field_map_digest": field_digest,
        "provider_readiness_contract": readiness,
        "review_matrix": matrix,
        "unresolved_mappings": _unresolved_mappings(matrix),
        "violations": violations,
        "actions": [],
    }


def run_create_phase2_provider_mapping_prep_request(
    request: dict[str, Any],
    *,
    runs_dir: str | Path,
) -> dict[str, Any]:
    cfg = _prep_config(request)
    policy = cfg.get("policy") if isinstance(cfg.get("policy"), dict) else {}
    payload = build_create_phase2_provider_mapping_prep(policy=policy)
    artifact_path = write_run_artifact(runs_dir, "create_phase2_provider_mapping_prep", payload)
    return {**payload, "artifact_path": str(artifact_path)}
