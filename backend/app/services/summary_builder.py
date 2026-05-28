from __future__ import annotations

from typing import Any

from backend.app.services.account_names import account_name_for
from backend.app.services.ui_labels import project_action_label
from backend.app.services.ui_labels import status_label


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def build_json_summary(
    title: str,
    payload: dict[str, Any],
    *,
    artifact_path: str = "",
    account_names: dict[str, str] | None = None,
) -> dict[str, Any]:
    account_names = account_names or {}
    summary = _dict(payload.get("summary"))
    status = str(payload.get("status") or summary.get("status") or "unknown")
    items = []
    create_request = _dict(payload.get("create_request")) or _dict(_dict(payload.get("create_strategy_plan")).get("request"))
    if create_request:
        product = str(create_request.get("product") or "")
        product_key = str(create_request.get("product_key") or "")
        if product:
            items.append({"label": "产品", "value": product})
        if product_key:
            items.append({"label": "产品 Key", "value": product_key})
    if summary.get("plan_id"):
        items.append({"label": "计划 ID", "value": summary["plan_id"]})

    mapping = [
        ("目标数", "target_site_count"),
        ("成功数", "success_count"),
        ("失败数", "failure_count"),
        ("账户数", "account_count"),
        ("项目数", "project_count"),
        ("项目数", "planned_project_count"),
        ("单元数", "planned_unit_count"),
        ("素材数", "planned_material_count"),
        ("违规数", "violation_count"),
        ("任务数", "task_count"),
    ]
    for label, key in mapping:
        if key in summary:
            items.append({"label": label, "value": summary[key]})

    create_rows = _create_plan_rows(payload, account_names)
    actions = _list(payload.get("actions"))
    rows = []
    columns: list[str] = []
    project_execute_rows = _project_execute_rows(payload, account_names)
    project_config_rows = _project_config_rows(payload, account_names)
    if project_execute_rows:
        columns = ["账户 ID", "账户名", "动作", "项目 ID", "项目名", "项目数", "状态"]
        rows = project_execute_rows
    elif project_config_rows:
        columns = ["账户 ID", "账户名", "项目 ID", "项目名", "消耗", "筛选原因"]
        rows = project_config_rows
    elif create_rows:
        columns = ["账户 ID", "账户名", "项目", "单元", "素材数"]
        rows = create_rows
    else:
        for action in actions[:200]:
            row = _dict(action)
            if row:
                advertiser_id = str(row.get("advertiser_id") or "")
                rows.append(
                    {
                        "账户 ID": advertiser_id,
                        "账户名": account_name_for(account_names, advertiser_id),
                        "落地页 ID": str(row.get("site_id") or row.get("orange_site_id") or ""),
                        "状态": status_label(row.get("status") or row.get("target_status")),
                    }
                )
        columns = ["账户 ID", "账户名", "落地页 ID", "状态"] if rows else []

    warnings = [str(item) for item in _list(payload.get("warnings") or summary.get("warnings"))]
    blocking = [str(item) for item in _list(payload.get("blocking_reasons") or summary.get("blocking_reasons"))]
    return {
        "summary": {
            "title": title,
            "status": status,
            "risk_level": "high" if blocking else "low",
            "execution_enabled": False,
            "items": items,
            "warnings": warnings,
            "blocking_reasons": blocking,
        },
        "table": {"columns": columns, "rows": rows},
        "artifact_path": artifact_path or str(payload.get("artifact_path") or ""),
        "raw": payload,
    }


def _create_plan_rows(payload: dict[str, Any], account_names: dict[str, str]) -> list[dict[str, Any]]:
    strategy_plan = _dict(payload.get("create_strategy_plan"))
    strategy = _dict(strategy_plan.get("strategy"))
    rows: list[dict[str, Any]] = []
    for project_value in _list(strategy.get("projects")):
        project = _dict(project_value)
        if not project:
            continue
        for unit_value in _list(project.get("units")):
            unit = _dict(unit_value)
            if not unit:
                continue
            rows.append(
                {
                    "账户 ID": str(project.get("advertiser_id") or ""),
                    "账户名": account_name_for(account_names, project.get("advertiser_id")),
                    "项目": str(project.get("project_name") or project.get("project_key") or ""),
                    "单元": str(unit.get("promotion_name") or unit.get("unit_key") or ""),
                    "素材数": len(_list(unit.get("materials"))),
                }
            )
    return rows[:200]


def _project_execute_rows(payload: dict[str, Any], account_names: dict[str, str]) -> list[dict[str, Any]]:
    if str(payload.get("workflow") or "") != "project_update_execute":
        return []
    rows: list[dict[str, Any]] = []
    for item in _list(payload.get("results"))[:200]:
        row = _dict(item)
        if not row:
            continue
        advertiser_id = str(row.get("advertiser_id") or "")
        action = str(row.get("action_type") or row.get("operation") or "")
        rows.append(
            {
                "账户 ID": advertiser_id,
                "账户名": account_name_for(account_names, advertiser_id),
                "动作": project_action_label(action),
                "项目 ID": str(row.get("project_id") or ""),
                "项目名": str(row.get("project_name") or row.get("name") or ""),
                "项目数": row.get("project_count") or "",
                "状态": status_label(row.get("status")),
            }
        )
    return rows


def _project_config_rows(payload: dict[str, Any], account_names: dict[str, str]) -> list[dict[str, Any]]:
    if str(payload.get("workflow") or "") != "project_realtime_filter_config":
        return []
    rows: list[dict[str, Any]] = []
    for item in _list(payload.get("matched_projects"))[:200]:
        row = _dict(item)
        if not row:
            continue
        advertiser_id = str(row.get("advertiser_id") or "")
        metrics = _dict(row.get("metrics"))
        rows.append(
            {
                "账户 ID": advertiser_id,
                "账户名": account_name_for(account_names, advertiser_id),
                "项目 ID": str(row.get("project_id") or ""),
                "项目名": str(row.get("project_name") or row.get("name") or ""),
                "消耗": metrics.get("stat_cost") if metrics else "",
                "筛选原因": "；".join(str(reason) for reason in _list(row.get("match_reasons")) if str(reason or "").strip()),
            }
        )
    return rows
