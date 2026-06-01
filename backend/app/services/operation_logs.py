from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.app.services.account_names import account_name_for
from backend.app.services.account_names import load_account_name_map
from backend.app.services.ui_labels import create_mode_label
from backend.app.services.ui_labels import operation_label
from backend.app.services.ui_labels import project_action_label
from backend.app.services.ui_labels import status_label
from roibang_v2.ui.operation_logs import filter_operation_logs
from roibang_v2.ui.operation_logs import load_operation_log_detail
from roibang_v2.ui.operation_logs import load_operation_logs


def build_operation_logs_result(
    runs_dir: str | Path,
    *,
    configs_dir: str | Path | None = None,
    product: str = "",
    operation_type: str = "",
    status: str = "",
    limit: int = 200,
) -> dict[str, Any]:
    rows = filter_operation_logs(
        load_operation_logs(runs_dir, limit=limit),
        product=product,
        operation_type=operation_type,
        status=status,
    )
    table_rows = [_table_row(row) for row in rows]
    completed_count = sum(1 for row in rows if str(row.get("status") or "") in {"completed", "success", "succeeded"})
    failed_count = sum(1 for row in rows if str(row.get("status") or "") == "failed")
    return {
        "summary": {
            "title": "操作日志",
            "status": "loaded",
            "risk_level": "medium" if failed_count else "low",
            "execution_enabled": False,
            "items": [
                {"label": "日志数", "value": len(table_rows)},
                {"label": "完成", "value": completed_count},
                {"label": "失败", "value": failed_count},
            ],
            "warnings": [] if table_rows else ["没有符合筛选条件的操作日志。"],
            "blocking_reasons": [],
        },
        "table": {
            "columns": [
                "关联任务",
                "操作",
                "业务内容",
                "状态",
                "任务状态",
                "触发人",
                "产品",
                "产品 Key",
                "创建时间",
                "账户数",
                "结果摘要",
            ],
            "rows": table_rows,
        },
        "artifact_path": str(Path(runs_dir) / "frontend_operation_log"),
        "raw": {"rows": rows},
    }


def build_operation_log_detail_result(
    runs_dir: str | Path,
    task_id: str,
    *,
    configs_dir: str | Path | None = None,
) -> dict[str, Any]:
    detail = load_operation_log_detail(runs_dir, task_id)
    account_names = load_account_name_map(configs_dir) if configs_dir else {}
    row = detail.get("row") if isinstance(detail.get("row"), dict) else {}
    if not row:
        return {
            "summary": {
                "title": "操作日志详情",
                "status": "not_found",
                "risk_level": "medium",
                "execution_enabled": False,
                "items": [{"label": "任务 ID", "value": task_id}],
                "warnings": [],
                "blocking_reasons": [f"未找到操作日志：{task_id}"],
            },
            "table": {"columns": ["字段", "内容"], "rows": []},
            "sections": [],
            "artifact_path": "",
            "raw": detail,
        }

    failure = detail.get("failure") if isinstance(detail.get("failure"), dict) else {}
    feishu = detail.get("feishu") if isinstance(detail.get("feishu"), dict) else {}
    create_review = detail.get("create_review") if isinstance(detail.get("create_review"), dict) else {}
    artifact = detail.get("artifact") if isinstance(detail.get("artifact"), dict) else {}
    artifact_details = artifact.get("details") if isinstance(artifact.get("details"), dict) else {}
    project_actions = artifact_details.get("project_actions") if isinstance(artifact_details.get("project_actions"), list) else []
    account_remark = artifact_details.get("account_remark") if isinstance(artifact_details.get("account_remark"), dict) else {}
    account_rows = artifact_details.get("accounts") if isinstance(artifact_details.get("accounts"), list) else []
    site_status = artifact_details.get("site_status") if isinstance(artifact_details.get("site_status"), dict) else {}
    site_rows = artifact_details.get("sites") if isinstance(artifact_details.get("sites"), list) else []
    site_template_foundation = (
        artifact_details.get("site_template_foundation")
        if isinstance(artifact_details.get("site_template_foundation"), dict)
        else {}
    )
    blocking_reasons = _detail_blocking_reasons(failure, create_review)
    context_items = _business_context_items(row, artifact_details)
    business_context = _business_context(row, artifact_details)
    table_rows = [
        {"字段": "关联任务", "内容": str(row.get("task_id") or task_id)},
        {"字段": "操作", "内容": operation_label(row.get("operation_type"))},
        {"字段": "业务内容", "内容": business_context},
        {"字段": "状态", "内容": status_label(row.get("status"))},
        {"字段": "触发人", "内容": str(row.get("actor") or "")},
        {"字段": "产品", "内容": str(row.get("product") or "")},
        {"字段": "产品 Key", "内容": str(row.get("product_key") or "")},
        {"字段": "账户数", "内容": str(int(row.get("account_count") or 0))},
        {"字段": "结果摘要", "内容": _operation_result_summary(row, business_context)},
        {"字段": "失败阶段", "内容": str(failure.get("operation") or "")},
        {"字段": "失败代码", "内容": str(failure.get("code") or "")},
        {"字段": "失败原因", "内容": str(failure.get("message") or "")},
        {"字段": "飞书状态", "内容": str(feishu.get("status") or "")},
        {"字段": "飞书原因", "内容": str(feishu.get("reason") or "")},
    ]
    return {
        "summary": {
            "title": "操作日志详情",
            "status": str(row.get("status") or ""),
            "risk_level": "high" if blocking_reasons or str(row.get("status")) == "failed" else "low",
            "execution_enabled": False,
            "items": [
                {"label": "任务 ID", "value": str(row.get("task_id") or task_id)},
                {"label": "操作", "value": operation_label(row.get("operation_type"))},
                *context_items,
                {"label": "状态", "value": status_label(row.get("status"))},
                {"label": "产品", "value": str(row.get("product") or "")},
                {"label": "产品 Key", "value": str(row.get("product_key") or "")},
                {"label": "账户数", "value": int(row.get("account_count") or 0)},
                {"label": "素材分配数", "value": int(row.get("material_assignment_count") or 0)},
                {"label": "唯一素材数", "value": int(row.get("unique_material_count") or 0)},
                {"label": "复盘状态", "value": str(row.get("review_status") or "")},
                {"label": "飞书状态", "value": str(feishu.get("status") or row.get("feishu_status") or "")},
            ],
            "warnings": _detail_warnings(create_review),
            "blocking_reasons": blocking_reasons,
        },
        "table": {"columns": ["字段", "内容"], "rows": [row for row in table_rows if row["内容"]]},
        "sections": _detail_sections(
            create_review,
            project_actions=project_actions,
            account_remark=account_remark,
            account_rows=account_rows,
            site_status=site_status,
            site_rows=site_rows,
            site_template_foundation=site_template_foundation,
            account_names=account_names,
        ),
        "artifact_path": str(row.get("artifact_path") or ""),
        "raw": detail,
    }


def _table_row(row: dict[str, Any]) -> dict[str, Any]:
    business_context = _business_context(row, {})
    task_id = str(row.get("task_id") or "")
    return {
        "关联任务": task_id,
        "任务 ID": task_id,
        "操作": operation_label(row.get("operation_type")),
        "业务内容": business_context,
        "状态": status_label(row.get("status")),
        "任务状态": status_label(row.get("task_status") or row.get("status")),
        "触发人": str(row.get("actor") or ""),
        "产品": str(row.get("product") or ""),
        "产品 Key": str(row.get("product_key") or ""),
        "创建时间": str(row.get("created_at") or ""),
        "账户数": row.get("account_count") or 0,
        "结果摘要": _operation_result_summary(row, business_context),
    }


def _operation_result_summary(row: dict[str, Any], business_context: str = "") -> str:
    parts = [f"{operation_label(row.get('operation_type'))}：{status_label(row.get('status'))}"]
    context = (business_context or _business_context(row, {})).strip()
    if context:
        parts.append(_summary_context_phrase(context))
    account_count = _to_int(row.get("account_count"))
    if account_count:
        parts.append(f"账户 {account_count}")
    review_blocking_count = _to_int(row.get("review_blocking_reason_count"))
    if review_blocking_count:
        parts.append(f"阻断 {review_blocking_count}")
    return "，".join(part for part in parts if part)


def _summary_context_phrase(context: str) -> str:
    first = context.split("；", 1)[0].strip()
    return first.replace("：", " ") if first else ""


def _detail_blocking_reasons(failure: dict[str, Any], create_review: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    message = str(failure.get("message") or "").strip()
    if message:
        reasons.append(f"真实执行失败：{_localized_blocking_reason(message, {})}")
    review = create_review.get("review") if isinstance(create_review.get("review"), dict) else {}
    for reason in review.get("blocking_reasons") or []:
        text = str(reason or "").strip()
        if text and text not in reasons:
            reasons.append(_localized_blocking_reason(text, {}))
    return reasons


def _detail_warnings(create_review: dict[str, Any]) -> list[str]:
    review = create_review.get("review") if isinstance(create_review.get("review"), dict) else {}
    return [str(item) for item in review.get("warnings") or [] if str(item or "").strip()]


def _detail_sections(
    create_review: dict[str, Any],
    *,
    project_actions: list[Any] | None = None,
    account_remark: dict[str, Any] | None = None,
    account_rows: list[Any] | None = None,
    site_status: dict[str, Any] | None = None,
    site_rows: list[Any] | None = None,
    site_template_foundation: dict[str, Any] | None = None,
    account_names: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    account_names = account_names or {}
    creative_usage = create_review.get("creative_usage") if isinstance(create_review.get("creative_usage"), dict) else {}
    sections = [
        {
            "title": "账户分布",
            "table": {
                "columns": ["账户 ID", "账户名", "项目数", "单元数", "素材分配数", "唯一素材数"],
                "rows": [_account_row(row, account_names) for row in create_review.get("accounts") or [] if isinstance(row, dict)],
            },
        },
        {
            "title": "素材分配",
            "table": {
                "columns": ["素材 ID", "视频 ID", "素材名", "消耗", "转化", "使用次数", "分配账户", "覆盖账户数", "覆盖单元数"],
                "rows": [_material_row(row, account_names) for row in create_review.get("materials") or [] if isinstance(row, dict)],
            },
        },
        {
            "title": "文案",
            "table": {
                "columns": ["文案", "使用次数"],
                "rows": [
                    {"文案": str(row.get("title") or ""), "使用次数": int(row.get("usage_count") or 0)}
                    for row in creative_usage.get("titles") or []
                    if isinstance(row, dict)
                ],
            },
        },
        {
            "title": "CTA",
            "table": {
                "columns": ["CTA", "使用次数"],
                "rows": [
                    {"CTA": str(row.get("cta") or ""), "使用次数": int(row.get("usage_count") or 0)}
                    for row in creative_usage.get("ctas") or []
                    if isinstance(row, dict)
                ],
            },
        },
        {
            "title": "卖点",
            "table": {
                "columns": ["卖点", "使用次数"],
                "rows": [
                    {"卖点": str(row.get("selling_point") or ""), "使用次数": int(row.get("usage_count") or 0)}
                    for row in creative_usage.get("selling_points") or []
                    if isinstance(row, dict)
                ],
            },
        },
        {
            "title": "单元分配",
            "table": {
                "columns": ["账户 ID", "账户名", "项目", "单元", "素材", "文案", "CTA", "卖点"],
                "rows": [_unit_row(row, account_names) for row in create_review.get("unit_assignments") or [] if isinstance(row, dict)],
            },
        },
    ]
    action_rows = [_project_action_row(row, account_names) for row in project_actions or [] if isinstance(row, dict)]
    if action_rows:
        sections.insert(
            1,
            {
                "title": "项目动作",
                "table": {
                    "columns": ["账户 ID", "账户名", "项目 ID", "项目名", "动作", "目标值"],
                    "rows": action_rows,
                },
            },
        )
    account_remark_table_rows = _account_remark_rows(account_remark or {}, account_rows or [], account_names)
    if account_remark_table_rows:
        sections.insert(
            1,
            {
                "title": "账户备注",
                "table": {
                    "columns": ["账户 ID", "账户名", "目标备注", "配置 ID"],
                    "rows": account_remark_table_rows,
                },
            },
        )
    site_status_table_rows = _site_status_rows(site_status or {}, site_rows or [], account_names)
    if site_status_table_rows:
        sections.insert(
            1,
            {
                "title": "落地页状态",
                "table": {
                    "columns": ["账户 ID", "账户名", "落地页 ID", "目标状态"],
                    "rows": site_status_table_rows,
                },
            },
        )
    site_template_table_rows = _site_template_rows(site_template_foundation or {}, site_rows or [], account_names)
    if site_template_table_rows:
        sections.insert(
            1,
            {
                "title": "模板建站",
                "table": {
                    "columns": ["账户 ID", "账户名", "现有落地页 ID", "动作", "小游戏路径", "发布"],
                    "rows": site_template_table_rows,
                },
            },
        )
    return sections


def _account_row(row: dict[str, Any], account_names: dict[str, str]) -> dict[str, Any]:
    advertiser_id = str(row.get("advertiser_id") or "")
    return {
        "账户 ID": advertiser_id,
        "账户名": account_name_for(account_names, advertiser_id),
        "项目数": int(row.get("project_count") or 0),
        "单元数": int(row.get("unit_count") or 0),
        "素材分配数": int(row.get("material_assignment_count") or 0),
        "唯一素材数": int(row.get("unique_material_count") or 0),
    }


def _material_row(row: dict[str, Any], account_names: dict[str, str]) -> dict[str, Any]:
    return {
        "素材 ID": str(row.get("material_id") or ""),
        "视频 ID": str(row.get("video_id") or row.get("source_video_id") or ""),
        "素材名": str(row.get("name") or ""),
        "消耗": row.get("product_stat_cost") or row.get("stat_cost") or 0,
        "转化": row.get("product_convert_cnt") or row.get("convert_cnt") or 0,
        "使用次数": int(row.get("usage_count") or 0),
        "分配账户": _format_accounts(row.get("covered_accounts"), account_names),
        "覆盖账户数": int(row.get("covered_account_count") or 0),
        "覆盖单元数": int(row.get("covered_unit_count") or 0),
    }


def _unit_row(row: dict[str, Any], account_names: dict[str, str]) -> dict[str, Any]:
    advertiser_id = str(row.get("advertiser_id") or "")
    return {
        "账户 ID": advertiser_id,
        "账户名": account_name_for(account_names, advertiser_id),
        "项目": str(row.get("project_name") or row.get("project_key") or ""),
        "单元": str(row.get("promotion_name") or row.get("unit_key") or ""),
        "素材": _join_materials(row.get("materials")),
        "文案": "；".join(str(item) for item in row.get("titles") or [] if str(item or "").strip()),
        "CTA": "；".join(str(item) for item in row.get("ctas") or [] if str(item or "").strip()),
        "卖点": "；".join(str(item) for item in row.get("selling_points") or [] if str(item or "").strip()),
    }


def _project_action_row(row: dict[str, Any], account_names: dict[str, str]) -> dict[str, Any]:
    action_type = str(row.get("action_type") or "").strip()
    advertiser_id = str(row.get("advertiser_id") or "")
    return {
        "账户 ID": advertiser_id,
        "账户名": account_name_for(account_names, advertiser_id),
        "项目 ID": str(row.get("project_id") or ""),
        "项目名": str(row.get("project_name") or row.get("name") or ""),
        "动作": project_action_label(action_type),
        "目标值": _project_action_target(row, action_type),
    }


def _account_remark_rows(
    account_remark: dict[str, Any],
    accounts: list[Any],
    account_names: dict[str, str],
) -> list[dict[str, Any]]:
    remark = str(account_remark.get("remark") or "").strip()
    update_id = str(account_remark.get("update_id") or "").strip()
    if not remark:
        return []
    rows: list[dict[str, Any]] = []
    for account in accounts:
        if not isinstance(account, dict):
            continue
        advertiser_id = str(account.get("advertiser_id") or "").strip()
        if advertiser_id:
            rows.append(
                {
                    "账户 ID": advertiser_id,
                    "账户名": account_name_for(account_names, advertiser_id),
                    "目标备注": remark,
                    "配置 ID": update_id,
                }
            )
    return rows


def _site_status_rows(
    site_status: dict[str, Any],
    sites: list[Any],
    account_names: dict[str, str],
) -> list[dict[str, Any]]:
    status_label = str(site_status.get("status_label") or site_status.get("status") or "").strip()
    if not status_label:
        return []
    rows: list[dict[str, Any]] = []
    for site in sites:
        if not isinstance(site, dict):
            continue
        advertiser_id = str(site.get("advertiser_id") or "").strip()
        site_id = str(site.get("site_id") or "").strip()
        if advertiser_id and site_id:
            rows.append(
                {
                    "账户 ID": advertiser_id,
                    "账户名": account_name_for(account_names, advertiser_id),
                    "落地页 ID": site_id,
                    "目标状态": status_label,
                }
            )
    return rows


def _site_template_rows(
    site_template: dict[str, Any],
    sites: list[Any],
    account_names: dict[str, str],
) -> list[dict[str, Any]]:
    game_path = str(site_template.get("game_path") or "").strip()
    if not game_path:
        return []
    edit_existing = bool(site_template.get("edit_existing"))
    publish = bool(site_template.get("publish"))
    rows: list[dict[str, Any]] = []
    for site in sites:
        if not isinstance(site, dict):
            continue
        advertiser_id = str(site.get("advertiser_id") or "").strip()
        if not advertiser_id:
            continue
        rows.append(
            {
                "账户 ID": advertiser_id,
                "账户名": account_name_for(account_names, advertiser_id),
                "现有落地页 ID": str(site.get("site_id") or "").strip(),
                "动作": "修复现有落地页" if edit_existing else "新建落地页",
                "小游戏路径": game_path,
                "发布": "是" if publish else "否",
            }
        )
    return rows


CREATE_OPERATION_TYPES = {"create_mode", "create_plan_generate", "create_live_execute", "create_live_execute_once"}
PROJECT_OPERATION_TYPES = {
    "project_management_config_generate",
    "project_management_execute",
    "project_realtime_filter_config",
    "project_update_execute",
}
ACCOUNT_REMARK_OPERATION_TYPES = {"account_remark_config_generate", "account_remark_update"}
SITE_STATUS_OPERATION_TYPES = {"site_status_update"}
SITE_TEMPLATE_OPERATION_TYPES = {"site_template_foundation"}


def _business_context(row: dict[str, Any], details: dict[str, Any]) -> str:
    items = _business_context_items(row, details)
    if items:
        return "；".join(f"{item['label']}：{item['value']}" for item in items if str(item.get("value") or "").strip())
    operation_type = str(row.get("operation_type") or details.get("operation_type") or "").strip()
    if operation_type in PROJECT_OPERATION_TYPES:
        return "未指定动作"
    if operation_type in CREATE_OPERATION_TYPES:
        return "未指定固定模式"
    return ""


def _business_context_items(row: dict[str, Any], details: dict[str, Any]) -> list[dict[str, Any]]:
    operation_type = str(row.get("operation_type") or details.get("operation_type") or "").strip()
    if operation_type in CREATE_OPERATION_TYPES:
        return _create_context_items(row, details)
    if operation_type in PROJECT_OPERATION_TYPES:
        action_text = _project_actions_text(row, details)
        if action_text:
            return [{"label": "项目管理动作", "value": action_text}]
    if operation_type in ACCOUNT_REMARK_OPERATION_TYPES:
        remark = str(details.get("remark") or row.get("account_remark") or "").strip()
        account_count = _to_int(row.get("account_count"))
        items = []
        if remark:
            items.append({"label": "目标备注", "value": remark})
        if account_count:
            items.append({"label": "账户数", "value": account_count})
        return items
    if operation_type in SITE_STATUS_OPERATION_TYPES:
        status = str(details.get("status_label") or row.get("site_status_label") or row.get("site_status") or "").strip()
        site_count = _to_int(row.get("site_count"))
        items = []
        if status:
            items.append({"label": "目标状态", "value": status})
        if site_count:
            items.append({"label": "落地页数", "value": site_count})
        return items
    if operation_type in SITE_TEMPLATE_OPERATION_TYPES:
        game_path = str(details.get("game_path") or row.get("site_template_game_path") or "").strip()
        edit_existing = row.get("site_template_edit_existing")
        publish = row.get("site_template_publish")
        target_count = _to_int(row.get("site_template_target_count") or row.get("account_count"))
        items = []
        if isinstance(edit_existing, bool):
            items.append({"label": "建站动作", "value": "修复现有落地页" if edit_existing else "新建落地页"})
        if target_count:
            items.append({"label": "目标账户数", "value": target_count})
        if game_path:
            items.append({"label": "小游戏路径", "value": game_path})
        if isinstance(publish, bool):
            items.append({"label": "发布", "value": "是" if publish else "否"})
        return items
    return []


def _create_context_items(row: dict[str, Any], details: dict[str, Any]) -> list[dict[str, Any]]:
    mode_key = str(details.get("mode_key") or row.get("mode_key") or "").strip()
    display_name = str(details.get("display_name") or row.get("display_name") or "").strip()
    if not display_name and mode_key:
        display_name = create_mode_label(mode_key)
    template_name = str(details.get("project_template_name") or row.get("project_template_name") or "").strip()
    template_key = str(details.get("template_key") or row.get("template_key") or "").strip()
    template_path = str(details.get("template_catalog_path") or row.get("template_catalog_path") or "").strip()
    items = []
    if display_name:
        items.append({"label": "固定模式", "value": display_name})
    if template_name or template_key:
        items.append({"label": "基础模板", "value": template_name or template_key})
    if template_path:
        items.append({"label": "模板文件", "value": template_path})
    return items


def _project_actions_text(row: dict[str, Any], details: dict[str, Any]) -> str:
    actions: list[str] = []
    project_actions = details.get("project_actions") if isinstance(details.get("project_actions"), list) else []
    for action in project_actions:
        if not isinstance(action, dict):
            continue
        action_type = str(action.get("action_type") or "").strip()
        if action_type:
            actions.append(project_action_label(action_type))
    row_actions = row.get("project_action_types") if isinstance(row.get("project_action_types"), list) else []
    for action_type in row_actions:
        if str(action_type or "").strip():
            actions.append(project_action_label(action_type))
    direct_action = str(details.get("action_type") or row.get("action_type") or "").strip()
    if direct_action:
        actions.append(project_action_label(direct_action))
    output = []
    for action in actions:
        if action and action not in output:
            output.append(action)
    return "；".join(output)


def _format_accounts(value: Any, account_names: dict[str, str]) -> str:
    accounts = value if isinstance(value, list) else []
    output = []
    seen = set()
    for raw_account_id in accounts:
        account_id = str(raw_account_id or "").strip()
        if not account_id or account_id in seen:
            continue
        seen.add(account_id)
        output.append(f"{account_name_for(account_names, account_id)}（{account_id}）")
    return "；".join(output)


def _localized_blocking_reason(text: str, result: dict[str, Any]) -> str:
    if "existing active project/unit provider IDs" not in text:
        return text
    ledger = result.get("existing_plan_ledger") if isinstance(result.get("existing_plan_ledger"), dict) else {}
    counts_text = _existing_plan_counts_text(ledger)
    counts_part = f"（{counts_text}）" if counts_text else ""
    return (
        f"这个创建计划已有创建记录{counts_part}，系统未发起外部创建，已阻止重复执行。"
        "要新建一批，请重新生成计划。"
    )


def _existing_plan_counts_text(ledger: dict[str, Any]) -> str:
    by_entity_type = ledger.get("by_entity_type") if isinstance(ledger.get("by_entity_type"), dict) else {}
    pieces = []
    project_count = _to_int(by_entity_type.get("project"))
    promotion_count = _to_int(by_entity_type.get("promotion"))
    if project_count:
        pieces.append(f"项目 {project_count} 个")
    if promotion_count:
        pieces.append(f"单元 {promotion_count} 个")
    if pieces:
        return "、".join(pieces)
    total = _to_int(ledger.get("count"))
    return f"记录 {total} 条" if total else ""


def _to_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _project_action_target(row: dict[str, Any], action_type: str) -> str:
    if action_type == "status_update":
        return {"ENABLE": "开启", "DISABLE": "关闭"}.get(str(row.get("opt_status") or ""), str(row.get("opt_status") or ""))
    if action_type == "budget_update":
        value = row.get("budget") if row.get("budget") is not None else row.get("adjustment_ratio")
        return f"预算 {value}" if str(value or "").strip() else ""
    if action_type == "bid_update":
        value = row.get("cpa_bid") if row.get("cpa_bid") is not None else row.get("adjustment_ratio")
        return f"出价 {value}" if str(value or "").strip() else ""
    if action_type == "roi_coeff_update":
        value = row.get("roi_goal")
        return f"ROI 系数 {value}" if str(value or "").strip() else ""
    return ""


def _join_materials(value: Any) -> str:
    if not isinstance(value, list):
        return ""
    material_ids = []
    for item in value:
        if isinstance(item, dict):
            material_ids.append(str(item.get("material_id") or item.get("video_id") or ""))
        else:
            material_ids.append(str(item or ""))
    return "；".join(item for item in material_ids if item.strip())
