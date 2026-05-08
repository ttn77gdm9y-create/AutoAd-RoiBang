from __future__ import annotations

from pathlib import Path
from typing import Any

from roibang_v2.runs import write_run_artifact
from roibang_v2.workflows.create_provider_adapter import disabled_provider_adapter, provider_adapter_contract
from roibang_v2.workflows.create_provider_field_map import (
    load_provider_field_map,
    provider_field_map_contract,
    provider_field_map_digest,
)
from roibang_v2.workflows.create_provider_readiness import provider_readiness_contract


def _check_config(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("create_provider_field_map_check")
    return dict(value) if isinstance(value, dict) else dict(request)


def _field_map_path(policy: dict[str, Any]) -> str:
    return str(policy.get("provider_field_map_path") or "").strip()


def _field_issues(field_map: dict[str, Any], *, issue: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    operations = field_map.get("operations") if isinstance(field_map.get("operations"), dict) else {}
    for operation, entries in operations.items():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            if issue == "missing_provider_field" and str(entry.get("provider_field") or "").strip():
                continue
            if issue == "unverified" and bool(entry.get("verified", False)):
                continue
            rows.append(
                {
                    "operation": str(operation),
                    "internal_field": str(entry.get("internal_field") or ""),
                }
            )
    return rows


def _summary(
    *,
    policy: dict[str, Any],
    field_map_contract: dict[str, Any],
    readiness_contract: dict[str, Any],
) -> dict[str, Any]:
    return {
        "provider": str(field_map_contract.get("provider") or ""),
        "field_map_path": _field_map_path(policy),
        "operation_count": int(field_map_contract.get("operation_count") or 0),
        "field_count": int(field_map_contract.get("field_count") or 0),
        "verified_field_count": int(field_map_contract.get("verified_field_count") or 0),
        "missing_provider_field_count": int(field_map_contract.get("missing_provider_field_count") or 0),
        "missing_required_field_count": int(field_map_contract.get("missing_required_field_count") or 0),
        "duplicate_internal_field_count": int(field_map_contract.get("duplicate_internal_field_count") or 0),
        "duplicate_provider_field_count": int(field_map_contract.get("duplicate_provider_field_count") or 0),
        "unknown_internal_field_count": int(field_map_contract.get("unknown_internal_field_count") or 0),
        "provider_mismatch_count": int(field_map_contract.get("provider_mismatch_count") or 0),
        "field_mapping_version_mismatch_count": int(
            field_map_contract.get("field_mapping_version_mismatch_count") or 0
        ),
        "ready_for_live_execute": bool(readiness_contract.get("ready_for_live_execute", False)),
    }


def build_create_provider_field_map_check(*, policy: dict[str, Any]) -> dict[str, Any]:
    field_map = load_provider_field_map(policy)
    field_contract = provider_field_map_contract(field_map, policy)
    field_digest = provider_field_map_digest(field_map)
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
        "workflow": "create_provider_field_map_check",
        "phase": "phase1",
        "execution_enabled": False,
        "external_api_calls": 0,
        "status": "invalid" if invalid_config else str(field_contract.get("status") or "unverified"),
        "summary": _summary(policy=policy, field_map_contract=field_contract, readiness_contract=readiness),
        "provider_field_map": field_map,
        "provider_field_map_contract": field_contract,
        "provider_field_map_digest": field_digest,
        "provider_readiness_contract": readiness,
        "missing_provider_fields": _field_issues(field_map, issue="missing_provider_field"),
        "missing_required_fields": list(field_contract.get("missing_required_fields") or []),
        "duplicate_internal_fields": list(field_contract.get("duplicate_internal_fields") or []),
        "duplicate_provider_fields": list(field_contract.get("duplicate_provider_fields") or []),
        "unknown_internal_fields": list(field_contract.get("unknown_internal_fields") or []),
        "unverified_fields": _field_issues(field_map, issue="unverified"),
        "violations": violations,
        "actions": [],
    }


def run_create_provider_field_map_check_request(
    request: dict[str, Any],
    *,
    runs_dir: str | Path,
) -> dict[str, Any]:
    cfg = _check_config(request)
    policy = cfg.get("policy") if isinstance(cfg.get("policy"), dict) else {}
    payload = build_create_provider_field_map_check(policy=policy)
    artifact_path = write_run_artifact(runs_dir, "create_provider_field_map_check", payload)
    return {**payload, "artifact_path": str(artifact_path)}
