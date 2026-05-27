from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from roibang_v2.runs import write_run_artifact
from roibang_v2.workflows.create_dry_run import _projects_with_account_unit_ordinals
from roibang_v2.workflows.create_dry_run import _unit_promotion_materials


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _task_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip())
    return cleaned.strip("-") or "operation"


def _feishu_status(result: dict[str, Any]) -> str:
    feishu = result.get("feishu") if isinstance(result.get("feishu"), dict) else {}
    if not feishu:
        return ""
    if not bool(feishu.get("attempted")):
        return "not_attempted"
    return "sent" if bool(feishu.get("ok")) else "failed"


def _project_units(project: dict[str, Any]) -> list[dict[str, Any]]:
    units = project.get("units")
    return [dict(row) for row in units if isinstance(row, dict)] if isinstance(units, list) else []


def _unit_materials(unit: dict[str, Any]) -> list[dict[str, Any]]:
    materials = unit.get("materials")
    return [dict(row) for row in materials if isinstance(row, dict)] if isinstance(materials, list) else []


def _copywriting_detail(request: dict[str, Any]) -> dict[str, Any]:
    template = request.get("template_parameters") if isinstance(request.get("template_parameters"), dict) else {}
    title_pool = list(template.get("title_pool") or []) if isinstance(template.get("title_pool"), list) else []
    cta_pool = list(template.get("cta_pool") or []) if isinstance(template.get("cta_pool"), list) else []
    selling_points = (
        list(template.get("product_selling_points") or [])
        if isinstance(template.get("product_selling_points"), list)
        else []
    )
    selection = template.get("unit_creative_selection") if isinstance(template.get("unit_creative_selection"), dict) else {}
    return {
        "title_pool_count": len(title_pool),
        "title_pool": title_pool,
        "cta_pool_count": len(cta_pool),
        "cta_pool": cta_pool,
        "selling_point_count": len(selling_points),
        "selling_points": selling_points,
        "unit_creative_selection": selection,
        "note": "前端日志同时记录创建计划中的文案/CTA（行动按钮）/卖点池、随机分配规则，以及按固定脚本规则推导出的单元级文案分配。",
    }


def create_operation_details_from_plan(plan_payload: dict[str, Any]) -> dict[str, Any]:
    request = plan_payload.get("create_request") if isinstance(plan_payload.get("create_request"), dict) else {}
    strategy_plan = (
        plan_payload.get("create_strategy_plan")
        if isinstance(plan_payload.get("create_strategy_plan"), dict)
        else {}
    )
    if request and not isinstance(strategy_plan.get("request"), dict):
        strategy_plan = {**strategy_plan, "request": request}
    strategy = strategy_plan.get("strategy") if isinstance(strategy_plan.get("strategy"), dict) else {}
    projects = [dict(row) for row in strategy.get("projects") or [] if isinstance(row, dict)]
    projects_with_ordinals = _projects_with_account_unit_ordinals(projects)
    accounts: dict[str, dict[str, Any]] = {}
    assignment_rows: list[dict[str, Any]] = []
    unit_copywriting: list[dict[str, Any]] = []
    unique_materials: dict[str, dict[str, Any]] = {}
    for project in projects_with_ordinals:
        advertiser_id = _text(project.get("advertiser_id"))
        account = accounts.setdefault(
            advertiser_id,
            {
                "advertiser_id": advertiser_id,
                "project_count": 0,
                "unit_count": 0,
                "material_assignment_count": 0,
                "unique_material_count": 0,
                "materials": {},
            },
        )
        account["project_count"] += 1
        for unit in _project_units(project):
            account["unit_count"] += 1
            materials = _unit_materials(unit)
            creative_payload = _unit_promotion_materials(
                plan=strategy_plan,
                project=project,
                unit=unit,
                materials=materials,
            )
            unit_copywriting.append(
                {
                    "advertiser_id": advertiser_id,
                    "project_key": _text(project.get("project_key")),
                    "project_name": _text(project.get("project_name")),
                    "unit_key": _text(unit.get("unit_key")),
                    "promotion_name": _text(unit.get("promotion_name")),
                    "title_material_list": creative_payload.get("title_material_list") or [],
                    "call_to_action_buttons": creative_payload.get("call_to_action_buttons") or [],
                    "product_info": creative_payload.get("product_info") or {},
                }
            )
            for material in materials:
                material_id = _text(material.get("material_id"))
                row = {
                    "advertiser_id": advertiser_id,
                    "project_key": _text(project.get("project_key")),
                    "project_name": _text(project.get("project_name")),
                    "unit_key": _text(unit.get("unit_key")),
                    "promotion_name": _text(unit.get("promotion_name")),
                    "material_id": material_id,
                    "source_video_id": _text(material.get("source_video_id")),
                    "name": _text(material.get("name")),
                    "stat_cost": material.get("stat_cost", 0),
                    "convert_cnt": material.get("convert_cnt", 0),
                    "score": material.get("score", 0),
                    "rank": material.get("rank", 0),
                    "effective_create_date": _text(material.get("effective_create_date")),
                    "first_seen_metric_date": _text(material.get("first_seen_metric_date")),
                }
                assignment_rows.append(row)
                account["material_assignment_count"] += 1
                if material_id:
                    account["materials"][material_id] = row
                    unique_materials.setdefault(material_id, row)
    account_rows = []
    for row in accounts.values():
        materials = list(row.pop("materials", {}).values())
        row["unique_material_count"] = len(materials)
        row["materials"] = materials
        account_rows.append(row)
    return {
        "product": _text(request.get("product")),
        "product_key": _text(request.get("product_key")),
        "mode_key": _text(plan_payload.get("mode_key")),
        "plan_id": _text((plan_payload.get("summary") or {}).get("plan_id") if isinstance(plan_payload.get("summary"), dict) else ""),
        "target_date": _text(request.get("target_date")),
        "source_advertiser_id": _text(request.get("source_advertiser_id")),
        "accounts": account_rows,
        "material_assignment_count": len(assignment_rows),
        "unique_material_count": len(unique_materials),
        "material_assignments": assignment_rows,
        "unique_materials": list(unique_materials.values()),
        "copywriting": _copywriting_detail(request),
        "unit_copywriting": unit_copywriting,
    }


def record_frontend_operation(
    *,
    runs_dir: str | Path,
    operation_type: str,
    status: str,
    actor: str,
    request: dict[str, Any],
    result: dict[str, Any],
    details: dict[str, Any],
) -> dict[str, Any]:
    task_id = _text(request.get("task_id")) or f"ui-{_slug(operation_type)}-{_task_timestamp()}"
    review = details.get("review") if isinstance(details.get("review"), dict) else {}
    review_summary = review.get("summary") if isinstance(review.get("summary"), dict) else {}
    review_blocking_reasons = review.get("blocking_reasons") if isinstance(review.get("blocking_reasons"), list) else []
    review_warning_count = int(review_summary.get("warning_count") or len(review.get("warnings") or []))
    payload = {
        "ok": status in {"completed", "succeeded", "success"},
        "task_id": task_id,
        "workflow": "frontend_operation_log",
        "phase": "frontend",
        "status": status,
        "operation_type": operation_type,
        "actor": actor,
        "execution_enabled": False,
        "external_api_calls": 0,
        "summary": {
            "operation_type": operation_type,
            "status": status,
            "product": _text(details.get("product")),
            "product_key": _text(details.get("product_key")),
            "account_count": len(details.get("accounts") or []),
            "material_assignment_count": int(details.get("material_assignment_count") or 0),
            "unique_material_count": int(details.get("unique_material_count") or 0),
            "review_status": "passed" if (review and bool(review.get("can_execute"))) else ("blocked" if review else ""),
            "review_blocking_reason_count": len(review_blocking_reasons),
            "review_warning_count": review_warning_count,
            "execute_artifact_path": _text(result.get("execute_artifact_path")),
            "report_artifact_path": _text(result.get("report_artifact_path")),
            "feishu_status": _feishu_status(result),
        },
        "request": request,
        "result": result,
        "details": details,
        "created_at": _now_iso(),
    }
    artifact = write_run_artifact(runs_dir, "frontend_operation_log", payload)
    event = {
        "created_at": payload["created_at"],
        "task_id": task_id,
        "operation_type": operation_type,
        "status": status,
        "actor": actor,
        "artifact_path": str(artifact),
        "summary": payload["summary"],
    }
    event_path = Path(runs_dir) / "frontend_operation_log" / "events.jsonl"
    event_path.parent.mkdir(parents=True, exist_ok=True)
    with event_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
    return {**payload, "artifact_path": str(artifact), "event_log_path": str(event_path)}
