from __future__ import annotations

from pathlib import Path
from typing import Any

from roibang_v2.fetch.openapi_executor import Transport, execute_openapi_readonly_plan
from roibang_v2.fetch.openapi_readonly import build_readonly_request
from roibang_v2.materials.product_source import (
    import_product_source_file,
    import_product_source_materials,
    select_product_source_materials,
    target_existing_material_ids,
)
from roibang_v2.runs import write_run_artifact


def build_material_provision_plan(
    *,
    db_path: str | Path,
    product: str,
    source_advertiser_id: str,
    organization_id: str,
    target_advertiser_id: str,
    required_material_count: int,
    material_type: str,
    available_statuses: list[str],
) -> dict[str, Any]:
    if required_material_count < 1:
        raise ValueError("required_material_count must be greater than 0")
    selected = select_product_source_materials(
        db_path=db_path,
        product=product,
        source_advertiser_id=source_advertiser_id,
        material_type=material_type,
        review_statuses=available_statuses,
        limit=required_material_count,
    )
    existing = target_existing_material_ids(
        db_path=db_path,
        target_advertiser_id=target_advertiser_id,
        material_ids=[item["material_id"] for item in selected],
    )
    missing = [item for item in selected if item["material_id"] not in existing]
    status = "needs_provision" if missing else "sufficient"
    return {
        "workflow": "material_source",
        "phase": "phase1",
        "status": status,
        "product": product,
        "source_advertiser_id": source_advertiser_id,
        "organization_id": organization_id,
        "target_advertiser_id": target_advertiser_id,
        "material_type": material_type,
        "available_statuses": available_statuses,
        "required_material_count": required_material_count,
        "selected_count": len(selected),
        "target_existing_count": len(existing),
        "provision_needed": len(missing),
        "selected_materials": selected,
        "missing_materials": missing,
        "execution_enabled": False,
        "external_api_calls": 0,
        "actions": [],
    }


def _material_source_config(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("material_source")
    return dict(value) if isinstance(value, dict) else dict(request)


def _source_accounts(cfg: dict[str, Any]) -> list[dict[str, str]]:
    rows = cfg.get("source_accounts")
    if not isinstance(rows, list) or not rows:
        source_advertiser_id = str(cfg.get("source_advertiser_id") or "").strip()
        if not source_advertiser_id:
            raise ValueError("openapi_source_materials requires source_accounts or source_advertiser_id")
        rows = [
            {
                "source_advertiser_id": source_advertiser_id,
                "organization_id": str(cfg.get("organization_id") or ""),
            }
        ]
    normalized: list[dict[str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        source_advertiser_id = str(row.get("source_advertiser_id") or row.get("advertiser_id") or "").strip()
        if not source_advertiser_id:
            continue
        normalized.append(
            {
                "source_advertiser_id": source_advertiser_id,
                "organization_id": str(row.get("organization_id") or cfg.get("organization_id") or "").strip(),
            }
        )
    if not normalized:
        raise ValueError("openapi_source_materials requires at least one source_advertiser_id")
    return normalized


def _material_source_plan(cfg: dict[str, Any]) -> dict[str, Any]:
    page_size = int(cfg.get("page_size") or 100)
    requests: list[dict[str, Any]] = []
    product = str(cfg.get("product") or "").strip()
    for source_account in _source_accounts(cfg):
        advertiser_id = source_account["source_advertiser_id"]
        requests.append(
            {
                "source_account": source_account,
                **build_readonly_request(
                    "video_material_get",
                    {
                        "advertiser_id": advertiser_id,
                        "page": 1,
                        "page_size": page_size,
                    },
                ),
            }
        )
    return {
        "ok": True,
        "workflow": "material_source_openapi_plan",
        "phase": "phase1",
        "execution_enabled": False,
        "external_api_calls": 0,
        "product": product,
        "requests": requests,
    }


def build_material_source_preflight(request: dict[str, Any]) -> dict[str, Any]:
    cfg = _material_source_config(request)
    kind = str(cfg.get("kind") or "local_product_source")
    if kind != "openapi_source_materials":
        raise ValueError(f"unsupported material source preflight kind: {kind}")
    plan = _material_source_plan(cfg)
    return {
        "ok": True,
        "workflow": "material_source_preflight",
        "phase": "phase1",
        "execution_enabled": False,
        "external_api_calls": 0,
        "summary": {
            "kind": kind,
            "enabled": bool(cfg.get("enabled", False)),
            "source_account_count": len(_source_accounts(cfg)),
            "planned_request_count": len(plan["requests"]),
            "target_advertiser_id": str(cfg.get("target_advertiser_id") or ""),
        },
        "plan": plan,
    }


def _rows_for_source_account(execution: dict[str, Any], source_advertiser_id: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in execution.get("responses") or []:
        if not isinstance(item, dict):
            continue
        request = item.get("request") if isinstance(item.get("request"), dict) else {}
        source_account = request.get("source_account") if isinstance(request.get("source_account"), dict) else {}
        if str(source_account.get("source_advertiser_id") or "") != source_advertiser_id:
            continue
        rows.extend(row for row in item.get("rows") or [] if isinstance(row, dict))
    return rows


def _run_openapi_source_materials(
    cfg: dict[str, Any],
    *,
    db_path: str | Path,
    transport: Transport | None,
) -> dict[str, Any]:
    if not bool(cfg.get("enabled", False)):
        preflight = build_material_source_preflight({"material_source": cfg})
        return {
            "ok": True,
            "workflow": "material_source",
            "phase": "phase1",
            "execution_enabled": False,
            "external_api_calls": 0,
            "skipped": True,
            "reason": "openapi_source_materials disabled",
            "preflight": preflight,
        }
    if transport is None:
        raise RuntimeError("openapi_source_materials enabled requires an explicit readonly transport")

    plan = _material_source_plan(cfg)
    execution = execute_openapi_readonly_plan(plan, transport=transport)
    product = str(cfg.get("product") or "").strip()
    target_advertiser_id = str(cfg["target_advertiser_id"])
    required_material_count = int(cfg.get("required_material_count") or 1)
    material_type = str(cfg.get("material_type") or "video")
    available_statuses = [str(item) for item in cfg.get("available_statuses", ["APPROVED"]) if str(item)]
    imports: list[dict[str, Any]] = []
    plans: list[dict[str, Any]] = []
    for source_account in _source_accounts(cfg):
        source_advertiser_id = source_account["source_advertiser_id"]
        organization_id = source_account["organization_id"]
        imported = import_product_source_materials(
            db_path=db_path,
            product=product,
            source_advertiser_id=source_advertiser_id,
            organization_id=organization_id,
            materials=_rows_for_source_account(execution, source_advertiser_id),
            source="openapi_source_materials",
        )
        imports.append(imported)
        plans.append(
            build_material_provision_plan(
                db_path=db_path,
                product=product,
                source_advertiser_id=source_advertiser_id,
                organization_id=organization_id,
                target_advertiser_id=target_advertiser_id,
                required_material_count=required_material_count,
                material_type=material_type,
                available_statuses=available_statuses,
            )
        )

    return {
        "ok": True,
        "workflow": "material_source",
        "phase": "phase1",
        "execution_enabled": False,
        "external_api_calls": int(execution["summary"]["transport_calls"]),
        "skipped": False,
        "summary": {
            "source_account_count": len(_source_accounts(cfg)),
            "transport_calls": int(execution["summary"]["transport_calls"]),
            "rows_received": int(execution["summary"]["rows_received"]),
            "materials_imported": sum(int(item["materials_imported"]) for item in imports),
            "product_source_materials_imported": sum(int(item["product_source_materials_imported"]) for item in imports),
            "provision_needed": sum(int(item["provision_needed"]) for item in plans),
        },
        "execution": {
            "summary": execution["summary"],
        },
        "imports": imports,
        "plans": plans,
    }


def run_material_source_request(
    request: dict[str, Any],
    *,
    db_path: str | Path,
    runs_dir: str | Path,
    transport: Transport | None = None,
) -> dict[str, Any]:
    cfg = _material_source_config(request)
    kind = str(cfg.get("kind") or "local_product_source")
    if kind == "openapi_source_materials":
        payload = _run_openapi_source_materials(cfg, db_path=db_path, transport=transport)
        artifact = write_run_artifact(runs_dir, "material_source", payload)
        return {**payload, "artifact_path": str(artifact)}
    if kind != "local_product_source":
        raise ValueError(f"unsupported material source kind in phase1: {kind}")
    imported = import_product_source_file(cfg["source_file"], db_path=db_path)
    product = str(cfg.get("product") or imported["product"])
    source_advertiser_id = str(cfg.get("source_advertiser_id") or imported["source_advertiser_id"])
    organization_id = str(cfg.get("organization_id") or imported["organization_id"])
    plan = build_material_provision_plan(
        db_path=db_path,
        product=product,
        source_advertiser_id=source_advertiser_id,
        organization_id=organization_id,
        target_advertiser_id=str(cfg["target_advertiser_id"]),
        required_material_count=int(cfg.get("required_material_count") or 1),
        material_type=str(cfg.get("material_type") or "video"),
        available_statuses=[str(item) for item in cfg.get("available_statuses", ["APPROVED"]) if str(item)],
    )
    payload = {
        "ok": True,
        "workflow": "material_source",
        "phase": "phase1",
        "execution_enabled": False,
        "external_api_calls": 0,
        "import": imported,
        "plan": plan,
    }
    artifact = write_run_artifact(runs_dir, "material_source", payload)
    return {**payload, "artifact_path": str(artifact)}
