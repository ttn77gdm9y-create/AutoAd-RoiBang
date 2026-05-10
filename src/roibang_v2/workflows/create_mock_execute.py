from __future__ import annotations

from pathlib import Path
from typing import Any

from roibang_v2.runs import write_run_artifact
from roibang_v2.workflows.create_execute import build_create_execute
from roibang_v2.workflows.create_provider_id_ledger import record_create_provider_id


def _mock_execute_config(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("create_mock_execute")
    return dict(value) if isinstance(value, dict) else dict(request)


def _safe_key(value: str) -> str:
    chars: list[str] = []
    for char in str(value).strip().lower():
        chars.append(char if char.isalnum() else "_")
    return "_".join(part for part in "".join(chars).split("_") if part)


def _summary(approval: dict[str, Any]) -> dict[str, Any]:
    value = approval.get("summary") if isinstance(approval.get("summary"), dict) else {}
    return {
        "plan_id": str(value.get("plan_id") or ""),
        "request_id": str(value.get("request_id") or ""),
        "project_count": int(value.get("project_count") or 0),
        "unit_count": int(value.get("unit_count") or 0),
        "material_count": int(value.get("material_count") or 0),
    }


def _provider_id_requirements(approval: dict[str, Any]) -> dict[str, Any]:
    value = approval.get("provider_id_ledger_requirements")
    return dict(value) if isinstance(value, dict) else {}


def _rows(value: Any) -> list[dict[str, Any]]:
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def _project_records(requirements: dict[str, Any]) -> list[dict[str, Any]]:
    return _rows(requirements.get("produced_by_create_project"))


def _unit_records(requirements: dict[str, Any]) -> list[dict[str, Any]]:
    return _rows(requirements.get("produced_by_create_unit"))


def _mock_provider_id(entity_type: str, local_key: str) -> str:
    prefix = "mock_project" if entity_type == "project" else "mock_promotion"
    return f"{prefix}_{_safe_key(local_key)}"


def _record_projects(
    *,
    db_path: str | Path,
    approval_summary: dict[str, Any],
    requirements: dict[str, Any],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for row in _project_records(requirements):
        local_key = str(row.get("local_key") or "")
        if not local_key:
            continue
        records.append(
            record_create_provider_id(
                db_path=db_path,
                entity_type="project",
                local_key=local_key,
                provider_id=_mock_provider_id("project", local_key),
                plan_id=str(approval_summary.get("plan_id") or ""),
                request_id=str(approval_summary.get("request_id") or ""),
                source_workflow="create_mock_execute",
                response_payload={
                    "mock": True,
                    "entity_type": "project",
                    "local_key": local_key,
                },
            )
        )
    return records


def _record_units(
    *,
    db_path: str | Path,
    approval_summary: dict[str, Any],
    requirements: dict[str, Any],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for row in _unit_records(requirements):
        local_key = str(row.get("local_key") or "")
        if not local_key:
            continue
        records.append(
            record_create_provider_id(
                db_path=db_path,
                entity_type="promotion",
                local_key=local_key,
                provider_id=_mock_provider_id("promotion", local_key),
                plan_id=str(approval_summary.get("plan_id") or ""),
                request_id=str(approval_summary.get("request_id") or ""),
                parent_local_key=str(row.get("parent_local_key") or ""),
                source_workflow="create_mock_execute",
                response_payload={
                    "mock": True,
                    "entity_type": "promotion",
                    "local_key": local_key,
                    "parent_local_key": str(row.get("parent_local_key") or ""),
                },
            )
        )
    return records


def _ordered_steps(
    *,
    summary: dict[str, Any],
    project_record_count: int,
    unit_record_count: int,
) -> list[dict[str, Any]]:
    return [
        {
            "operation": "create_project",
            "planned_count": int(summary.get("project_count") or 0),
            "recorded_provider_id_count": project_record_count,
            "status": "simulated",
        },
        {
            "operation": "create_unit",
            "planned_count": int(summary.get("unit_count") or 0),
            "recorded_provider_id_count": unit_record_count,
            "status": "simulated",
        },
        {
            "operation": "bind_material",
            "planned_count": int(summary.get("material_count") or 0),
            "recorded_provider_id_count": 0,
            "status": "simulated",
        },
    ]


def build_create_mock_execute(
    *,
    create_approval_artifact: dict[str, Any],
    policy: dict[str, Any],
    db_path: str | Path,
) -> dict[str, Any]:
    approval_summary = _summary(create_approval_artifact)
    requirements = _provider_id_requirements(create_approval_artifact)
    project_records = _record_projects(
        db_path=db_path,
        approval_summary=approval_summary,
        requirements=requirements,
    )
    unit_records = _record_units(
        db_path=db_path,
        approval_summary=approval_summary,
        requirements=requirements,
    )
    final_execute = build_create_execute(
        create_approval_artifact=create_approval_artifact,
        policy=policy,
        db_path=db_path,
    )
    unresolved_after_mock = int(final_execute.get("resolved_payload_contract", {}).get("unresolved_lookup_count") or 0)
    provider_id_records = project_records + unit_records
    return {
        "ok": unresolved_after_mock == 0 and all(str(row.get("status") or "") == "recorded" for row in provider_id_records),
        "workflow": "create_mock_execute",
        "phase": "phase2_preparation",
        "execution_enabled": False,
        "external_api_calls": 0,
        "status": "simulated" if unresolved_after_mock == 0 else "blocked",
        "mock_execution_mode": "local_provider_id_simulation",
        "summary": {
            **approval_summary,
            "recorded_provider_id_count": len(provider_id_records),
            "unresolved_lookup_count_after_mock": unresolved_after_mock,
        },
        "ordered_steps": _ordered_steps(
            summary=approval_summary,
            project_record_count=len(project_records),
            unit_record_count=len(unit_records),
        ),
        "provider_id_records": provider_id_records,
        "final_create_execute": final_execute,
        "live_api_calls": [],
        "violations": [] if unresolved_after_mock == 0 else ["mock execute left unresolved lookup placeholders"],
        "actions": [],
    }


def run_create_mock_execute_request(
    request: dict[str, Any],
    *,
    runs_dir: str | Path,
    db_path: str | Path,
) -> dict[str, Any]:
    cfg = _mock_execute_config(request)
    approval = cfg.get("create_approval_artifact")
    if not isinstance(approval, dict):
        raise ValueError("create mock execute requires create_approval_artifact")
    policy = cfg.get("policy") if isinstance(cfg.get("policy"), dict) else {}
    payload = build_create_mock_execute(
        create_approval_artifact=approval,
        policy=policy,
        db_path=db_path,
    )
    artifact_path = write_run_artifact(runs_dir, "create_mock_execute", payload)
    return {**payload, "artifact_path": str(artifact_path)}
