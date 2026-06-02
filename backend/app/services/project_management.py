from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Any

from roibang_v2.ui.background_tasks import build_runner_command
from roibang_v2.ui.background_tasks import build_task_record
from roibang_v2.ui.background_tasks import start_runner
from roibang_v2.ui.background_tasks import write_task_record
from roibang_v2.ui.script_runner import build_project_update_execute_command
from roibang_v2.ui.script_runner import build_project_filter_command
from roibang_v2.workflows.frontend_operation_log import record_frontend_operation

from backend.app.safety.confirmation import EXECUTE_CONFIRMATION_PHRASE
from backend.app.services.account_names import account_name_for
from backend.app.services.account_names import load_account_name_map

ACTION_LABELS = {
    "delete_project": "删除项目",
    "status_update": "开启/关闭项目",
    "budget_update": "调整预算",
    "bid_update": "调整出价",
    "roi_coeff_update": "调整 ROI 系数",
}

METRIC_LABELS = {
    "stat_cost": "消耗",
    "active_register": "注册数",
    "register_cost": "注册成本",
    "billing_convert_cnt": "计费时间转化数",
    "billing_conversion_cost": "计费时间转化成本",
    "billing_1day_pay_roi": "计费当日付费 ROI",
}

OP_LABELS = {
    "lt": "小于",
    "lte": "小于等于",
    "gt": "大于",
    "gte": "大于等于",
    "eq": "等于",
}

WINDOW_LABELS = {
    "today": "今天",
    "yesterday": "昨天",
    "last_3_days": "近 3 天",
}


def build_project_management_config_preview(request: dict[str, Any], *, project_root: str | Path) -> dict[str, Any]:
    action_type = _text(request.get("action_type"))
    project_update_id = _text(request.get("project_update_id")) or _default_project_update_id()
    advertiser_ids = _split_account_ids(request.get("advertiser_ids"))
    output_path = _text(request.get("output_path")) or _default_project_update_path(project_update_id)
    name_contains = _text(request.get("name_contains"))
    spend_window = _text(request.get("spend_window"))
    opt_status = _text(request.get("opt_status"))
    budget = _text(request.get("budget"))
    cpa_bid = _text(request.get("cpa_bid"))
    roi_goal = _text(request.get("roi_goal"))
    metric_filters = _metric_filters_from_request(request)
    validation_reasons = _config_validation_reasons(
        project_update_id=project_update_id,
        action_type=action_type,
        advertiser_ids=advertiser_ids,
        spend_window=spend_window,
        metric_filters=metric_filters,
        output_path=output_path,
        opt_status=opt_status,
        budget=budget,
        cpa_bid=cpa_bid,
        roi_goal=roi_goal,
    )
    if validation_reasons:
        return _blocked_preview(project_update_id, action_type, output_path, validation_reasons, request)

    account_names = load_account_name_map(Path(project_root) / "configs")
    metric_filter_label = _metric_filters_label(metric_filters)
    spend_window_label = _spend_window_label(spend_window, metric_filters)

    command = build_project_filter_command(
        project_update_id=project_update_id,
        advertiser_ids="\n".join(advertiser_ids),
        action_type=action_type,
        name_contains=name_contains,
        spend_window=spend_window,
        metric_field="",
        metric_op="",
        metric_value="",
        metric_filters=metric_filters,
        output_path=output_path,
        opt_status=opt_status,
        budget=budget,
        cpa_bid=cpa_bid,
        roi_goal=roi_goal,
    )
    rows = [
        {
            "账户 ID": advertiser_id,
            "账户名": account_name_for(account_names, advertiser_id),
            "动作": _action_label(action_type),
            "项目名包含": name_contains,
            "数据窗口": spend_window_label,
            "筛选条件": metric_filter_label,
            "目标值": _target_value(action_type, opt_status=opt_status, budget=budget, cpa_bid=cpa_bid, roi_goal=roi_goal),
            "输出 JSON": output_path,
        }
        for advertiser_id in advertiser_ids
    ]
    return {
        "summary": {
            "title": "项目管理配置预览",
            "status": "planned",
            "risk_level": _risk_level(action_type, opt_status),
            "execution_enabled": False,
            "items": [
                {"label": "配置 ID", "value": project_update_id},
                {"label": "动作", "value": _action_label(action_type)},
                {"label": "账户数", "value": len(advertiser_ids)},
                {"label": "数据窗口", "value": spend_window_label},
                {"label": "筛选条件", "value": metric_filter_label},
                {"label": "目标值", "value": _target_value(action_type, opt_status=opt_status, budget=budget, cpa_bid=cpa_bid, roi_goal=roi_goal)},
                {"label": "输出 JSON", "value": output_path},
            ],
            "warnings": ["这里只生成项目管理 JSON 预览，不执行删除、暂停、预算或出价修改。"],
            "blocking_reasons": [],
        },
        "table": {
            "columns": ["账户 ID", "账户名", "动作", "项目名包含", "数据窗口", "筛选条件", "目标值", "输出 JSON"],
            "rows": rows,
        },
        "artifact_path": "",
        "raw": {
            "project_root": str(project_root),
            "request": request,
            "command": command,
            "metric_filters": metric_filters,
        },
    }


def start_project_management_config_task(request: dict[str, Any], *, project_root: str | Path) -> dict[str, Any]:
    preview = build_project_management_config_preview(request, project_root=project_root)
    if preview["summary"]["status"] == "blocked":
        return preview

    root = Path(project_root)
    runs_dir = root / "data" / "runs"
    task = build_task_record(
        runs_dir=runs_dir,
        operation_type="project_management_config_generate",
        command=list(preview["raw"]["command"]),
        cwd=str(root),
        request=request,
    )
    task_path = write_task_record(runs_dir, task)
    pid = start_runner(build_runner_command(task_path), cwd=root)
    task["pid"] = pid
    write_task_record(runs_dir, task)
    operation_log = _record_config_operation(runs_dir, task, request, preview)

    return {
        "summary": {
            "title": "项目管理配置生成任务",
            "status": "queued",
            "risk_level": preview["summary"]["risk_level"],
            "execution_enabled": False,
            "items": [
                *preview["summary"]["items"],
                {"label": "任务 ID", "value": task["task_id"]},
                {"label": "任务状态", "value": task["status"]},
            ],
            "warnings": ["配置生成任务已进入任务中心；这里仍未执行项目删除、暂停、预算或出价修改。"],
            "blocking_reasons": [],
        },
        "table": preview["table"],
        "artifact_path": str(task_path),
        "task": task,
        "raw": {"preview": preview, "task": task, "operation_log": operation_log},
    }


def build_project_management_execute_preview(request: dict[str, Any], *, project_root: str | Path) -> dict[str, Any]:
    project_update_path = _text(request.get("project_update_path")) or _text(request.get("path"))
    if not project_update_path:
        return _blocked_execute_preview("未填写项目管理 JSON 路径", request, project_update_path)

    path = _resolve_project_update_path(project_root, project_update_path)
    if not path.exists():
        return _blocked_execute_preview(f"项目管理 JSON 不存在：{project_update_path}", request, project_update_path)

    try:
        project_update = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return _blocked_execute_preview(f"项目管理 JSON 解析失败：{exc}", request, project_update_path)

    actions = _action_rows(project_update.get("actions"))
    if not actions:
        return _blocked_execute_preview("项目管理 JSON 中没有 actions，不能执行", request, project_update_path)
    validation_reasons = _execute_validation_reasons(project_update, actions, request)
    if validation_reasons:
        blocked = _blocked_execute_preview(validation_reasons[0], request, project_update_path)
        blocked["summary"]["blocking_reasons"] = validation_reasons
        return blocked

    account_names = load_account_name_map(Path(project_root) / "configs")
    project_update_account_names = _project_update_account_names(project_update)
    rows = [_execute_action_row(action, account_names, project_update_account_names) for action in actions]
    execute_command = build_project_update_execute_command(project_update_path=project_update_path, execute=True)

    return {
        "summary": {
            "title": "项目管理执行预览",
            "status": "ready",
            "risk_level": _max_action_risk(actions),
            "execution_enabled": True,
            "items": _execute_summary_items(request, project_update, actions, project_update_path),
            "warnings": [f"这是高风险真实执行入口；点击执行前必须核对中文摘要和项目明细，并输入“{EXECUTE_CONFIRMATION_PHRASE}”。"],
            "blocking_reasons": [],
        },
        "table": {
            "columns": ["账户 ID", "账户名", "项目 ID", "项目名", "动作", "目标值"],
            "rows": rows,
        },
        "artifact_path": project_update_path,
        "raw": {
            "request": request,
            "project_update": project_update,
            "execute_command": execute_command,
        },
    }


def start_project_management_execute_task(request: dict[str, Any], *, project_root: str | Path) -> dict[str, Any]:
    preview = build_project_management_execute_preview(request, project_root=project_root)
    if preview["summary"]["status"] == "blocked":
        return preview

    root = Path(project_root)
    runs_dir = root / "data" / "runs"
    task = build_task_record(
        runs_dir=runs_dir,
        operation_type="project_update_execute",
        command=list(preview["raw"]["execute_command"]),
        cwd=str(root),
        request=request,
    )
    task_path = write_task_record(runs_dir, task)
    pid = start_runner(build_runner_command(task_path), cwd=root)
    task["pid"] = pid
    write_task_record(runs_dir, task)
    operation_log = _record_execute_operation(runs_dir, task, request, preview)

    return {
        "summary": {
            "title": "项目管理执行任务",
            "status": "queued",
            "risk_level": preview["summary"]["risk_level"],
            "execution_enabled": True,
            "items": [
                *preview["summary"]["items"],
                {"label": "任务 ID", "value": task["task_id"]},
                {"label": "任务状态", "value": task["status"]},
            ],
            "warnings": ["真实执行任务已提交；可在当前页面或任务中心查看中文进度和结果。"],
            "blocking_reasons": [],
        },
        "table": preview["table"],
        "artifact_path": str(task_path),
        "task": task,
        "raw": {"preview": preview, "task": task, "operation_log": operation_log},
    }


def _blocked_preview(
    project_update_id: str,
    action_type: str,
    output_path: str,
    reason: str | list[str],
    request: dict[str, Any],
) -> dict[str, Any]:
    reasons = reason if isinstance(reason, list) else [reason]
    return {
        "summary": {
            "title": "项目管理配置预览",
            "status": "blocked",
            "risk_level": "high",
            "execution_enabled": False,
            "items": [
                {"label": "配置 ID", "value": project_update_id},
                {"label": "动作", "value": _action_label(action_type)},
                {"label": "输出 JSON", "value": output_path},
            ],
            "warnings": [],
            "blocking_reasons": reasons,
        },
        "table": {"columns": ["账户 ID", "账户名", "动作", "项目名包含", "数据窗口", "筛选条件", "目标值", "输出 JSON"], "rows": []},
        "artifact_path": "",
        "raw": {"request": request},
    }


def _blocked_execute_preview(reason: str, request: dict[str, Any], project_update_path: str) -> dict[str, Any]:
    return {
        "summary": {
            "title": "项目管理执行预览",
            "status": "blocked",
            "risk_level": "high",
            "execution_enabled": False,
            "items": [{"label": "项目管理 JSON", "value": project_update_path}],
            "warnings": [],
            "blocking_reasons": [reason],
        },
        "table": {"columns": ["账户 ID", "账户名", "项目 ID", "项目名", "动作", "目标值"], "rows": []},
        "artifact_path": project_update_path,
        "raw": {"request": request},
    }


def _resolve_project_update_path(project_root: str | Path, path: str) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return Path(project_root) / candidate


def _record_config_operation(
    runs_dir: Path,
    task: dict[str, Any],
    request: dict[str, Any],
    preview: dict[str, Any],
) -> dict[str, Any]:
    return record_frontend_operation(
        runs_dir=runs_dir,
        operation_type="project_management_config_generate",
        status=_text(task.get("status")) or "queued",
        actor=_text(request.get("owner")) or _text(request.get("operator")) or "local-ui",
        request={**request, "task_id": task["task_id"]},
        result={
            "task_id": task["task_id"],
            "task_artifact_path": task.get("artifact_path"),
            "status": task.get("status"),
            "execute_artifact_path": _summary_item_value(preview, "输出 JSON") or _text(request.get("output_path")),
        },
        details={
            "product": _text(request.get("product") or request.get("product_name")),
            "product_key": _text(request.get("product_key")),
            "accounts": [{"advertiser_id": advertiser_id} for advertiser_id in _split_account_ids(request.get("advertiser_ids"))],
            "review": {
                "can_execute": False,
                "summary": {"warning_count": len(preview.get("summary", {}).get("warnings") or [])},
                "warnings": list(preview.get("summary", {}).get("warnings") or []),
                "blocking_reasons": list(preview.get("summary", {}).get("blocking_reasons") or []),
            },
        },
    )


def _record_execute_operation(
    runs_dir: Path,
    task: dict[str, Any],
    request: dict[str, Any],
    preview: dict[str, Any],
) -> dict[str, Any]:
    raw = preview.get("raw") if isinstance(preview.get("raw"), dict) else {}
    project_update = raw.get("project_update") if isinstance(raw.get("project_update"), dict) else {}
    actions = _action_rows(project_update.get("actions"))
    account_ids = sorted({_text(action.get("advertiser_id")) for action in actions if _text(action.get("advertiser_id"))})
    return record_frontend_operation(
        runs_dir=runs_dir,
        operation_type="project_update_execute",
        status=_text(task.get("status")) or "queued",
        actor=_text(project_update.get("operator")) or _text(request.get("owner")) or "local-ui",
        request={**request, "task_id": task["task_id"]},
        result={
            "task_id": task["task_id"],
            "task_artifact_path": task.get("artifact_path"),
            "status": task.get("status"),
            "execute_artifact_path": preview.get("artifact_path"),
        },
        details={
            "product": _text(project_update.get("product") or request.get("product") or request.get("product_name")),
            "product_key": _text(project_update.get("product_key") or request.get("product_key")),
            "accounts": [{"advertiser_id": advertiser_id} for advertiser_id in account_ids],
            "project_actions": actions,
            "review": {
                "can_execute": bool(preview.get("summary", {}).get("execution_enabled")),
                "summary": {"warning_count": len(preview.get("summary", {}).get("warnings") or [])},
                "warnings": list(preview.get("summary", {}).get("warnings") or []),
                "blocking_reasons": list(preview.get("summary", {}).get("blocking_reasons") or []),
            },
        },
    )


def _action_rows(value: Any) -> list[dict[str, Any]]:
    return [dict(item) for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _execute_validation_reasons(
    project_update: dict[str, Any],
    actions: list[dict[str, Any]],
    request: dict[str, Any],
) -> list[str]:
    reasons: list[str] = []
    for index, action in enumerate(actions, start=1):
        action_type = _text(action.get("action_type"))
        if action_type not in ACTION_LABELS:
            reasons.append(f"第 {index} 条项目管理动作不支持：{action_type or '未选择'}")
            continue
        label = _action_label(action_type)
        if not _text(action.get("advertiser_id")):
            reasons.append(f"第 {index} 条{label}缺少账户 ID")
        if not _text(action.get("project_id")):
            reasons.append(f"第 {index} 条{label}缺少项目 ID")
    if _requires_suggestion_metadata(project_update, request):
        reasons.extend(_suggestion_project_update_validation_reasons(project_update, actions))
    return reasons


def _execute_action_row(
    action: dict[str, Any],
    account_names: dict[str, str] | None = None,
    project_update_account_names: dict[str, str] | None = None,
) -> dict[str, Any]:
    action_type = _text(action.get("action_type"))
    advertiser_id = _text(action.get("advertiser_id"))
    return {
        "账户 ID": advertiser_id,
        "账户名": _text(action.get("advertiser_name") or action.get("account_name"))
        or (project_update_account_names or {}).get(advertiser_id, "")
        or account_name_for(account_names or {}, advertiser_id),
        "项目 ID": _text(action.get("project_id")),
        "项目名": _text(action.get("project_name") or action.get("name")),
        "动作": _execute_action_label(action),
        "目标值": _target_value(
            action_type,
            opt_status=_text(action.get("opt_status")),
            budget=_text(action.get("budget") or action.get("adjustment_ratio")),
            cpa_bid=_text(action.get("cpa_bid") or action.get("adjustment_ratio")),
            roi_goal=_text(action.get("roi_goal")),
        ),
    }


def _max_action_risk(actions: list[dict[str, Any]]) -> str:
    risks = [_risk_level(_text(action.get("action_type")), _text(action.get("opt_status"))) for action in actions]
    if "high" in risks:
        return "high"
    if "medium" in risks:
        return "medium"
    return "low"


def _execute_summary_items(
    request: dict[str, Any],
    project_update: dict[str, Any],
    actions: list[dict[str, Any]],
    project_update_path: str,
) -> list[dict[str, Any]]:
    action_labels = sorted({_execute_action_label(action) for action in actions if _execute_action_label(action)})
    account_ids = {_text(action.get("advertiser_id")) for action in actions if _text(action.get("advertiser_id"))}
    project_ids = {_text(action.get("project_id")) for action in actions if _text(action.get("project_id"))}
    items = [
        {"label": "配置来源", "value": _config_source_label(request.get("config_source"))},
    ]
    if _text(project_update.get("中文摘要")):
        items.append({"label": "中文摘要", "value": _text(project_update.get("中文摘要"))})
    product_label = _product_label(project_update)
    if product_label:
        items.append({"label": "产品", "value": product_label})
    items.extend(
        [
            {"label": "配置 ID", "value": _text(project_update.get("project_update_id"))},
        ]
    )
    source_artifact = _source_artifact(project_update)
    if source_artifact:
        items.append({"label": "来源建议", "value": source_artifact})
    if _text(project_update.get("risk_summary")):
        items.append({"label": "风险摘要", "value": _text(project_update.get("risk_summary"))})
    items.extend(
        [
            {"label": "动作类型", "value": "、".join(action_labels)},
            {"label": "动作数", "value": len(actions)},
            {"label": "账户数", "value": len(account_ids)},
            {"label": "项目数", "value": len(project_ids)},
        ]
    )
    for label, count in _execute_action_counts(actions).items():
        if count:
            items.append({"label": label, "value": count})
    items.append({"label": "项目管理 JSON", "value": project_update_path})
    return items


def _requires_suggestion_metadata(project_update: dict[str, Any], request: dict[str, Any]) -> bool:
    source = project_update.get("source") if isinstance(project_update.get("source"), dict) else {}
    return (
        _text(request.get("config_source")) == "suggestions_generated"
        or _text(project_update.get("source_artifact")) != ""
        or _text(source.get("workflow")) == "delivery_patrol_suggestions"
    )


def _suggestion_project_update_validation_reasons(project_update: dict[str, Any], actions: list[dict[str, Any]]) -> list[str]:
    reasons: list[str] = []
    if not _text(project_update.get("中文摘要")):
        reasons.append("建议生成的项目管理 JSON 缺少中文摘要")
    if not _source_artifact(project_update):
        reasons.append("建议生成的项目管理 JSON 缺少来源建议 artifact")
    if not _text(project_update.get("risk_summary")):
        reasons.append("建议生成的项目管理 JSON 缺少中文风险摘要")
    if project_update.get("execution_allowed") is not False:
        reasons.append("建议生成的项目管理 JSON 必须保持 execution_allowed=false，由项目管理确认入口控制真实执行")
    if project_update.get("dry_run_required") is not True:
        reasons.append("建议生成的项目管理 JSON 必须保持 dry_run_required=true")
    execution = project_update.get("execution") if isinstance(project_update.get("execution"), dict) else {}
    if execution.get("enabled") is True:
        reasons.append("建议生成的项目管理 JSON 必须保持 execution.enabled=false，由项目管理确认入口控制真实执行")
    account_names = _project_update_account_names(project_update)
    for advertiser_id in sorted({_text(action.get("advertiser_id")) for action in actions if _text(action.get("advertiser_id"))}):
        action_name = next(
            (
                _text(action.get("account_name") or action.get("advertiser_name"))
                for action in actions
                if _text(action.get("advertiser_id")) == advertiser_id
                and _text(action.get("account_name") or action.get("advertiser_name"))
            ),
            "",
        )
        if not action_name and not account_names.get(advertiser_id):
            reasons.append(f"建议生成的项目管理 JSON 缺少账户名：{advertiser_id}")
    return reasons


def _project_update_account_names(project_update: dict[str, Any]) -> dict[str, str]:
    rows = project_update.get("accounts") if isinstance(project_update.get("accounts"), list) else []
    names: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        account_id = _text(row.get("account_id") or row.get("advertiser_id"))
        account_name = _text(row.get("account_name") or row.get("advertiser_name"))
        if account_id and account_name and account_name != "未配置账户名":
            names[account_id] = account_name
    return names


def _source_artifact(project_update: dict[str, Any]) -> str:
    source = project_update.get("source") if isinstance(project_update.get("source"), dict) else {}
    return _text(project_update.get("source_artifact") or source.get("artifact_path"))


def _product_label(project_update: dict[str, Any]) -> str:
    product_name = _text(project_update.get("product_name") or project_update.get("product"))
    product_key = _text(project_update.get("product_key"))
    if product_name and product_key:
        return f"{product_name}（{product_key}）"
    return product_name or product_key


def _execute_action_label(action: dict[str, Any]) -> str:
    explicit = _text(action.get("中文动作"))
    if explicit:
        return explicit
    action_type = _text(action.get("action_type"))
    if action_type == "status_update" and _text(action.get("opt_status")) == "DISABLE":
        return "暂停项目"
    if action_type == "status_update" and _text(action.get("opt_status")) == "ENABLE":
        return "开启项目"
    return _action_label(action_type)


def _execute_action_counts(actions: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"删除项目": 0, "暂停项目": 0, "调预算": 0, "调出价": 0, "调整时段": 0}
    for action in actions:
        label = _execute_action_label(action)
        if label == "调整预算":
            label = "调预算"
        if label == "调整出价":
            label = "调出价"
        if label in counts:
            counts[label] += 1
    return counts


def _split_account_ids(value: Any) -> list[str]:
    if isinstance(value, list):
        raw_items = value
    else:
        raw_items = str(value or "").replace("\n", ",").split(",")
    return [str(item).strip() for item in raw_items if str(item).strip()]


def _metric_filters_from_request(request: dict[str, Any]) -> list[dict[str, str]]:
    rows = request.get("metric_filters")
    output: list[dict[str, str]] = []
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict):
                continue
            field = _text(row.get("field"))
            op = _text(row.get("op"))
            value = _text(row.get("value"))
            if field or op or value:
                output.append({"field": field, "op": op, "value": value})
    if output:
        return output

    field = _text(request.get("metric_field"))
    op = _text(request.get("metric_op"))
    value = _text(request.get("metric_value"))
    if field or op or value:
        return [{"field": field, "op": op, "value": value}]
    return []


def _config_validation_reasons(
    *,
    project_update_id: str,
    action_type: str,
    advertiser_ids: list[str],
    spend_window: str,
    metric_filters: list[dict[str, str]],
    output_path: str,
    opt_status: str,
    budget: str,
    cpa_bid: str,
    roi_goal: str,
) -> list[str]:
    reasons: list[str] = []
    if not action_type:
        reasons.append("必须明确选择项目管理动作")
    elif action_type not in ACTION_LABELS:
        reasons.append(f"不支持的项目管理动作：{action_type}")
    if not advertiser_ids:
        reasons.append("必须明确填写本次账户 ID")
    if spend_window and spend_window not in WINDOW_LABELS:
        reasons.append(f"不支持的数据窗口：{spend_window}")
    if metric_filters:
        if not spend_window:
            reasons.append("使用数据筛选时必须明确选择数据窗口")
        reasons.extend(_metric_filter_validation_reasons(metric_filters))
    if action_type == "status_update" and not opt_status:
        reasons.append("开启/关闭项目必须明确选择目标状态")
    if action_type == "budget_update" and not budget:
        reasons.append("调整预算必须明确填写目标预算")
    if action_type == "bid_update" and not cpa_bid:
        reasons.append("调整出价必须明确填写目标出价")
    if action_type == "roi_coeff_update" and not roi_goal:
        reasons.append("调整 ROI 系数必须明确填写目标 ROI 系数")
    return reasons


def _metric_filter_validation_reasons(metric_filters: list[dict[str, str]]) -> list[str]:
    reasons: list[str] = []
    for index, item in enumerate(metric_filters, start=1):
        field = _text(item.get("field"))
        op = _text(item.get("op"))
        value = _text(item.get("value"))
        if not field:
            reasons.append(f"第 {index} 个筛选条件必须选择指标")
        elif field not in METRIC_LABELS:
            reasons.append(f"第 {index} 个筛选条件不支持指标：{field}")
        if not op:
            reasons.append(f"第 {index} 个筛选条件必须选择比较符")
        elif op not in OP_LABELS:
            reasons.append(f"第 {index} 个筛选条件不支持比较符：{op}")
        if not value:
            reasons.append(f"第 {index} 个筛选条件必须填写筛选值")
        else:
            try:
                float(value)
            except ValueError:
                reasons.append(f"第 {index} 个筛选条件筛选值必须是数字")
    return reasons


def _text(value: Any) -> str:
    return str(value or "").strip()


def _default_project_update_id() -> str:
    return f"project-update-{datetime.now().strftime('%Y%m%d-%H%M%S')}"


def _default_project_update_path(project_update_id: str) -> str:
    return f"configs/project-updates/{project_update_id}.local.json"


def _summary_item_value(preview: dict[str, Any], label: str) -> str:
    summary = preview.get("summary") if isinstance(preview.get("summary"), dict) else {}
    for item in summary.get("items") or []:
        if isinstance(item, dict) and _text(item.get("label")) == label:
            return _text(item.get("value"))
    return ""


def _action_label(action_type: str) -> str:
    return ACTION_LABELS.get(action_type, action_type or "未选择")


def _metric_filter_label(metric_field: str, metric_op: str, metric_value: str) -> str:
    metric = METRIC_LABELS.get(metric_field, metric_field)
    op = OP_LABELS.get(metric_op, metric_op)
    return f"{metric} {op} {metric_value}"


def _metric_filters_label(metric_filters: list[dict[str, str]]) -> str:
    if not metric_filters:
        return "账户范围内全部可操作项目"
    return " 且 ".join(_metric_filter_label(_text(item.get("field")), _text(item.get("op")), _text(item.get("value"))) for item in metric_filters)


def _spend_window_label(spend_window: str, metric_filters: list[dict[str, str]]) -> str:
    if not metric_filters:
        return "未使用"
    return WINDOW_LABELS.get(spend_window, spend_window)


def _target_value(action_type: str, *, opt_status: str, budget: str, cpa_bid: str, roi_goal: str) -> str:
    if action_type == "status_update":
        return {"ENABLE": "开启", "DISABLE": "关闭"}.get(opt_status, opt_status)
    if action_type == "budget_update":
        return f"预算 {budget}" if budget else ""
    if action_type == "bid_update":
        return f"出价 {cpa_bid}" if cpa_bid else ""
    if action_type == "roi_coeff_update":
        return f"ROI 系数 {roi_goal}" if roi_goal else ""
    return ""


def _risk_level(action_type: str, opt_status: str) -> str:
    if action_type == "delete_project":
        return "high"
    if action_type == "status_update" and opt_status == "DISABLE":
        return "high"
    if action_type in {"status_update", "budget_update", "bid_update", "roi_coeff_update"}:
        return "medium"
    return "high"


def _config_source_label(value: Any) -> str:
    source = _text(value)
    if source == "current_generated":
        return "本页刚生成的新配置"
    if source == "suggestions_generated":
        return "投放建议工作台生成的项目管理配置"
    if source == "manual":
        return "手动指定的历史配置"
    return "项目管理配置"
