from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from roibang_v2.runs import write_run_artifact
from roibang_v2.workflows.create_provider_field_map import (
    load_provider_field_map,
    provider_field_map_contract,
    provider_field_map_digest,
)


def _review_config(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("create_provider_evidence_review")
    return dict(value) if isinstance(value, dict) else dict(request)


def _field_map_path(policy: dict[str, Any]) -> str:
    return str(policy.get("provider_field_map_path") or "").strip()


def _evidence_catalog_path(policy: dict[str, Any]) -> str:
    return str(policy.get("provider_evidence_catalog_path") or "").strip()


def _invalid_catalog(provider: str = "oceanengine") -> dict[str, Any]:
    return {
        "provider": provider,
        "evidence_catalog_version": "",
        "source": "phase2_placeholder_invalid_provider_evidence_catalog",
        "evidence": {},
    }


def _load_provider_evidence_catalog(policy: dict[str, Any], *, provider: str) -> dict[str, Any]:
    path = _evidence_catalog_path(policy)
    if not path:
        return _invalid_catalog(provider)
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _invalid_catalog(provider)
    if not _is_valid_catalog(payload):
        return _invalid_catalog(provider)
    return payload


def _is_valid_catalog(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    if not str(value.get("provider") or "").strip():
        return False
    if not str(value.get("evidence_catalog_version") or "").strip():
        return False
    evidence = value.get("evidence")
    if not isinstance(evidence, dict):
        return False
    for item in evidence.values():
        if not isinstance(item, dict):
            return False
        if not str(item.get("operation") or "").strip():
            return False
        if not isinstance(item.get("provider_fields"), list):
            return False
        if "reviewed" not in item:
            return False
    return True


def _catalog_evidence(catalog: dict[str, Any]) -> dict[str, dict[str, Any]]:
    evidence = catalog.get("evidence") if isinstance(catalog.get("evidence"), dict) else {}
    return {str(key): value for key, value in evidence.items() if isinstance(value, dict)}


def _is_local_only(entry: dict[str, Any]) -> bool:
    mapping_kind = str(entry.get("mapping_kind") or "").strip()
    return mapping_kind in {"local_lookup_key", "local_only"}


def _evidence_refs(entry: dict[str, Any]) -> list[str]:
    refs = entry.get("evidence_refs")
    if not isinstance(refs, list):
        return []
    return [str(item).strip() for item in refs if str(item or "").strip()]


def _status_and_issues(
    *,
    operation: str,
    entry: dict[str, Any],
    evidence_by_ref: dict[str, dict[str, Any]],
) -> tuple[str, list[str]]:
    provider_field = str(entry.get("provider_field") or "").strip()
    if _is_local_only(entry) and not provider_field:
        if bool(entry.get("local_only_confirmed", False)):
            return "local_only_confirmed", []
        return "local_only_needs_confirmation", ["local-only field requires explicit confirmation"]
    if not provider_field:
        return "needs_provider_field", ["provider field is empty"]
    refs = _evidence_refs(entry)
    if not refs:
        return "needs_evidence_ref", ["provider field requires at least one evidence ref"]
    missing_refs = [ref for ref in refs if ref not in evidence_by_ref]
    if missing_refs:
        return "missing_evidence", [f"evidence {ref} is missing from catalog" for ref in missing_refs]
    unreviewed = [ref for ref in refs if not bool(evidence_by_ref[ref].get("reviewed", False))]
    if unreviewed:
        return "needs_evidence_review", [f"evidence {ref} is not reviewed" for ref in unreviewed]
    operation_mismatches = [
        ref
        for ref in refs
        if str(evidence_by_ref[ref].get("operation") or "").strip() != operation
    ]
    if operation_mismatches:
        return "evidence_operation_mismatch", [
            f"evidence {ref} operation does not match {operation}" for ref in operation_mismatches
        ]
    field_missing = [
        ref
        for ref in refs
        if provider_field
        not in {str(item).strip() for item in evidence_by_ref[ref].get("provider_fields") or []}
    ]
    if field_missing:
        return "field_not_in_evidence", [
            f"provider field {provider_field} is not listed in evidence {ref}" for ref in field_missing
        ]
    if not bool(entry.get("verified", False)):
        return "needs_mapping_verification", ["field mapping is not marked verified"]
    return "verified", []


def _field_row(
    *,
    operation: str,
    entry: dict[str, Any],
    evidence_by_ref: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    status, issues = _status_and_issues(
        operation=operation,
        entry=entry,
        evidence_by_ref=evidence_by_ref,
    )
    return {
        "internal_field": str(entry.get("internal_field") or ""),
        "provider_field": str(entry.get("provider_field") or ""),
        "mapping_kind": str(entry.get("mapping_kind") or ""),
        "evidence_refs": _evidence_refs(entry),
        "evidence_status": status,
        "evidence_issues": issues,
    }


def _review_sections(
    *,
    field_map: dict[str, Any],
    evidence_by_ref: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    operations = field_map.get("operations") if isinstance(field_map.get("operations"), dict) else {}
    sections: list[dict[str, Any]] = []
    for operation, rows in operations.items():
        fields = [
            _field_row(operation=str(operation), entry=entry, evidence_by_ref=evidence_by_ref)
            for entry in rows
            if isinstance(entry, dict)
        ] if isinstance(rows, list) else []
        sections.append({"operation": str(operation), "fields": fields})
    return sections


def _fields(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        field
        for section in sections
        for field in (section.get("fields") if isinstance(section.get("fields"), list) else [])
        if isinstance(field, dict)
    ]


def _unresolved_items(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for section in sections:
        operation = str(section.get("operation") or "")
        for field in section.get("fields") if isinstance(section.get("fields"), list) else []:
            if not isinstance(field, dict):
                continue
            if str(field.get("evidence_status") or "") == "verified":
                continue
            rows.append(
                {
                    "operation": operation,
                    "internal_field": str(field.get("internal_field") or ""),
                    "provider_field": str(field.get("provider_field") or ""),
                    "evidence_status": str(field.get("evidence_status") or ""),
                    "evidence_issues": list(field.get("evidence_issues") or []),
                }
            )
    return rows


def _summary(
    *,
    policy: dict[str, Any],
    field_map: dict[str, Any],
    catalog: dict[str, Any],
    sections: list[dict[str, Any]],
) -> dict[str, Any]:
    fields = _fields(sections)
    evidence_by_ref = _catalog_evidence(catalog)
    return {
        "provider": str(field_map.get("provider") or ""),
        "field_mapping_version": str(field_map.get("field_mapping_version") or ""),
        "field_map_path": _field_map_path(policy),
        "evidence_catalog_path": _evidence_catalog_path(policy),
        "field_count": len(fields),
        "catalog_evidence_count": len(evidence_by_ref),
        "reviewed_evidence_count": sum(1 for item in evidence_by_ref.values() if bool(item.get("reviewed", False))),
        "ready_field_count": sum(1 for field in fields if str(field.get("evidence_status") or "") == "verified"),
        "unresolved_field_count": sum(1 for field in fields if str(field.get("evidence_status") or "") != "verified"),
        "ready_for_live_payload_development": False,
        "ready_for_live_execute": False,
    }


def _phase2_provider_evidence_contract() -> dict[str, Any]:
    return {
        "review_only": True,
        "external_api_allowed": False,
        "live_payload_generation_enabled": False,
        "create_execute_hard_block_required": True,
        "mapping_verified_must_remain_false": True,
    }


def build_create_provider_evidence_review(*, policy: dict[str, Any]) -> dict[str, Any]:
    field_map = load_provider_field_map(policy)
    field_contract = provider_field_map_contract(field_map, policy)
    field_digest = provider_field_map_digest(field_map)
    catalog = _load_provider_evidence_catalog(policy, provider=str(field_map.get("provider") or "oceanengine"))
    evidence_by_ref = _catalog_evidence(catalog)
    sections = _review_sections(field_map=field_map, evidence_by_ref=evidence_by_ref)
    invalid_field_map = str(field_map.get("source") or "") == "phase1_placeholder_invalid_provider_field_map_config"
    invalid_catalog = str(catalog.get("source") or "") == "phase2_placeholder_invalid_provider_evidence_catalog"
    violations: list[str] = []
    if invalid_field_map:
        violations.append("provider field map config is missing or malformed")
    if invalid_catalog:
        violations.append("provider evidence catalog config is missing or malformed")
    status = "invalid" if violations else "needs_review"
    return {
        "ok": not violations,
        "workflow": "create_provider_evidence_review",
        "phase": "phase2_preparation",
        "execution_enabled": False,
        "external_api_calls": 0,
        "status": status,
        "summary": _summary(policy=policy, field_map=field_map, catalog=catalog, sections=sections),
        "phase2_provider_evidence_contract": _phase2_provider_evidence_contract(),
        "provider_field_map": field_map,
        "provider_field_map_contract": field_contract,
        "provider_field_map_digest": field_digest,
        "provider_evidence_catalog": catalog,
        "evidence_review_sections": sections,
        "unresolved_evidence_items": _unresolved_items(sections),
        "violations": violations,
        "actions": [],
    }


def run_create_provider_evidence_review_request(
    request: dict[str, Any],
    *,
    runs_dir: str | Path,
) -> dict[str, Any]:
    cfg = _review_config(request)
    policy = cfg.get("policy") if isinstance(cfg.get("policy"), dict) else {}
    payload = build_create_provider_evidence_review(policy=policy)
    artifact_path = write_run_artifact(runs_dir, "create_provider_evidence_review", payload)
    return {**payload, "artifact_path": str(artifact_path)}
