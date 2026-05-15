from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from roibang_v2.fetch.openapi_executor import Transport
from roibang_v2.fetch.openapi_executor import execute_openapi_readonly_plan
from roibang_v2.fetch.openapi_http import build_http_transport
from roibang_v2.fetch.openapi_readonly import build_openapi_readonly_plan
from roibang_v2.fetch.openapi_readonly import build_readonly_request
from roibang_v2.fetch.workbench_account_discovery import Sleeper as WorkbenchSleeper
from roibang_v2.fetch.workbench_account_discovery import WorkbenchOpener
from roibang_v2.fetch.workbench_account_discovery import discover_spending_accounts
from roibang_v2.runs import write_run_artifact
from roibang_v2.workflows.scheduler_status import FeishuSender
from roibang_v2.workflows.scheduler_status import send_feishu_app_chat_text
from roibang_v2.workflows.project_hourly_realtime_sync import _enabled
from roibang_v2.workflows.project_hourly_realtime_sync import _json_rows


REPORT_PRESETS = ["account_daily", "project_daily", "promotion_daily"]
WINDOWS = {"today": "target_date", "yesterday": "yesterday_date"}
STATUS_LABELS = {
    "PROJECT_STATUS_ENABLE": "启用",
    "PROJECT_STATUS_DISABLE": "已关闭",
    "PROJECT_STATUS_DELETE": "已删除",
    "PROMOTION_STATUS_ENABLE": "启用",
    "PROMOTION_STATUS_DISABLE": "已关闭",
    "PROMOTION_STATUS_DELETE": "已删除",
}


def _config(request: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(request, dict):
        return {}
    value = request.get("delivery_patrol")
    return dict(value) if isinstance(value, dict) else dict(request)


def _account_remark(row: dict[str, Any]) -> str:
    return str(row.get("account_remark") or row.get("advertiser_remark") or "").strip()


def _account_scope(cfg: dict[str, Any], *, source: str) -> dict[str, Any]:
    scope = cfg.get("account_scope") if isinstance(cfg.get("account_scope"), dict) else {}
    return {
        "source": str(scope.get("source") or source),
        "account_remark_equals": str(
            scope.get("account_remark_equals") or cfg.get("account_remark_equals") or ""
        ).strip(),
        "min_spend": float(scope.get("min_spend", cfg.get("min_spend", 0)) or 0),
    }


def _matches_account_scope(account: dict[str, Any], cfg: dict[str, Any]) -> bool:
    product_keyword = str(cfg.get("product_keyword") or "").strip()
    product = str(account.get("product") or "").strip()
    account_name = str(account.get("account_name") or "").strip()
    if product_keyword and product_keyword not in product and product_keyword not in account_name:
        return False
    remark_equals = str(_account_scope(cfg, source="")["account_remark_equals"] or "").strip()
    if remark_equals and _account_remark(account) != remark_equals:
        return False
    return True


def _normalize_account(row: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:
    product_keyword = str(cfg.get("product_keyword") or "").strip()
    return {
        "advertiser_id": str(row.get("advertiser_id") or row.get("account_id") or "").strip(),
        "account_name": str(row.get("account_name") or row.get("advertiser_name") or "").strip(),
        "account_remark": _account_remark(row),
        "product": str(row.get("product") or product_keyword).strip(),
        "platform": str(row.get("platform") or "WECHAT_GAME").strip(),
    }


def _load_allowed_accounts(cfg: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    path_text = str(cfg.get("allowed_target_accounts_path") or "").strip()
    if not path_text:
        raise ValueError("delivery patrol requires allowed_target_accounts_path")
    path = Path(path_text)
    if not path.exists():
        raise ValueError(f"allowed_target_accounts_path not found: {path}")
    accounts: list[dict[str, Any]] = []
    for row in _json_rows(json.loads(path.read_text(encoding="utf-8"))):
        account = _normalize_account(row, cfg)
        if not account["advertiser_id"] or not _enabled(row.get("enable", row.get("enabled", True))):
            continue
        if not _matches_account_scope(account, cfg):
            continue
        accounts.append(account)
    return accounts, {"enabled": False, "source": "allowed_target_accounts"}


def _discover_workbench_accounts(
    cfg: dict[str, Any],
    target_dates: dict[str, str],
    *,
    workbench_opener: WorkbenchOpener | None = None,
    workbench_sleeper: WorkbenchSleeper | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    discovery = cfg.get("active_account_discovery") if isinstance(cfg.get("active_account_discovery"), dict) else {}
    scope = _account_scope(cfg, source="workbench_account_list")
    workbench = dict(discovery.get("workbench") if isinstance(discovery.get("workbench"), dict) else {})
    workbench["enabled"] = True
    result = discover_spending_accounts(
        workbench,
        target_date=target_dates["today"],
        min_spend=float(discovery.get("min_spend", scope["min_spend"]) or 0),
        opener=workbench_opener,
        sleeper=workbench_sleeper,
    )
    accounts = []
    for row in result.get("accounts") or []:
        if not isinstance(row, dict):
            continue
        account = _normalize_account(row, cfg)
        if account["advertiser_id"] and _matches_account_scope(account, cfg):
            accounts.append(account)
    filtered_total_spend = 0.0
    for row in result.get("accounts") or []:
        if isinstance(row, dict) and _matches_account_scope(_normalize_account(row, cfg), cfg):
            filtered_total_spend += float(row.get("stat_cost") or 0)
    filtered_total_spend = round(filtered_total_spend, 2)
    return accounts, {
        **(result.get("summary") if isinstance(result.get("summary"), dict) else {}),
        "enabled": True,
        "source": "workbench_account_list",
        "active_account_count": len(accounts),
        "external_api_calls": int(result.get("external_api_calls") or 0),
        "total_spend": filtered_total_spend,
    }


def _load_patrol_accounts(
    cfg: dict[str, Any],
    target_dates: dict[str, str],
    *,
    accounts_override: list[dict[str, Any]] | None = None,
    discovery_summary: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if accounts_override is not None:
        accounts = [_normalize_account(account, cfg) for account in accounts_override]
        return [account for account in accounts if _matches_account_scope(account, cfg)], discovery_summary or {}
    _ = target_dates
    return _load_allowed_accounts(cfg)


def _target_dates(cfg: dict[str, Any]) -> dict[str, str]:
    target = str(cfg.get("target_date") or "").strip()
    if not target:
        target = date.today().isoformat()
    yesterday = str(cfg.get("yesterday_date") or "").strip()
    if not yesterday:
        yesterday = (date.fromisoformat(target) - timedelta(days=1)).isoformat()
    return {"today": target, "yesterday": yesterday}


def build_delivery_patrol_plan(
    db_path: str | Path,
    request: dict[str, Any] | None,
    *,
    accounts_override: list[dict[str, Any]] | None = None,
    discovery_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    _ = db_path
    cfg = _config(request)
    target_dates = _target_dates(cfg)
    accounts, account_discovery = _load_patrol_accounts(
        cfg,
        target_dates,
        accounts_override=accounts_override,
        discovery_summary=discovery_summary,
    )
    account_scope = _account_scope(cfg, source=str(account_discovery.get("source") or "allowed_target_accounts"))
    page_size = int(cfg.get("page_size") or 100)
    plan = build_openapi_readonly_plan(
        accounts=accounts,
        dates=[target_dates["today"], target_dates["yesterday"]],
        endpoints=["report_custom"],
        report_presets=REPORT_PRESETS,
        platforms=["WECHAT_GAME"],
        page_size=page_size,
    )
    for account in accounts:
        account_ref = {
            "advertiser_id": str(account["advertiser_id"]),
                "account_name": str(account.get("account_name") or ""),
                "account_remark": str(account.get("account_remark") or ""),
                "product": str(account.get("product") or ""),
                "platform": str(account.get("platform") or ""),
            }
        for endpoint_key in ["project_list", "promotion_list"]:
            endpoint_page_size = min(page_size, 20) if endpoint_key == "promotion_list" else page_size
            plan["requests"].append(
                {
                    "date": target_dates["today"],
                    "account": account_ref,
                    **build_readonly_request(
                        endpoint_key,
                        {
                            "advertiser_id": account_ref["advertiser_id"],
                            "page": 1,
                            "page_size": endpoint_page_size,
                        },
                    ),
                }
            )
    plan["summary"]["planned_request_count"] = len(plan["requests"])
    return {
        "ok": True,
        "workflow": "delivery_patrol_plan",
        "phase": "control_analysis",
        "execution_enabled": False,
        "external_api_calls": 0,
        "summary": {
            "target_date": target_dates["today"],
            "yesterday_date": target_dates["yesterday"],
            "allowed_account_count": len(accounts),
            "date_count": 2,
            "planned_request_count": int(plan["summary"]["planned_request_count"]),
            "account_scope": account_scope,
            "account_discovery": account_discovery,
        },
        "accounts": accounts,
        "target_dates": target_dates,
        "account_discovery": account_discovery,
        "account_scope": account_scope,
        "plan": plan,
    }


def _number(value: Any) -> float:
    try:
        return float(str(value or "0").replace(",", "").replace("%", ""))
    except ValueError:
        return 0.0


def _rate(numerator: float, denominator: float) -> float | None:
    if denominator <= 0:
        return None
    return round(numerator / denominator, 4)


def _empty_metrics() -> dict[str, Any]:
    return {
        "stat_cost": 0.0,
        "ctr": None,
        "active_register": 0.0,
        "register_cost": None,
        "billing_convert_cnt": 0.0,
        "billing_conversion_cost": None,
        "billing_1day_pay_roi": None,
        "raw": {"show_cnt": 0.0, "click_cnt": 0.0},
    }


def _add_metrics(target: dict[str, Any], metrics: dict[str, Any]) -> None:
    stat_cost = _number(metrics.get("stat_cost"))
    show_cnt = _number(metrics.get("show_cnt"))
    click_cnt = _number(metrics.get("click_cnt"))
    active_register = _number(metrics.get("active_register"))
    billing_convert_cnt = _number(metrics.get("attribution_convert_cnt") or metrics.get("convert_cnt"))
    roi = _number(
        metrics.get("attribution_billing_game_in_app_roi_1day")
        or metrics.get("billing_1day_pay_roi")
        or metrics.get("pay_amount_roi")
    )
    previous_cost = float(target["stat_cost"] or 0)
    target["stat_cost"] = round(previous_cost + stat_cost, 4)
    target["active_register"] = round(float(target["active_register"] or 0) + active_register, 4)
    target["billing_convert_cnt"] = round(float(target["billing_convert_cnt"] or 0) + billing_convert_cnt, 4)
    target["raw"]["show_cnt"] = round(float(target["raw"]["show_cnt"] or 0) + show_cnt, 4)
    target["raw"]["click_cnt"] = round(float(target["raw"]["click_cnt"] or 0) + click_cnt, 4)
    if roi and stat_cost:
        weighted = float(target.get("_roi_weighted") or 0) + roi * stat_cost
        target["_roi_weighted"] = weighted


def _finalize_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    stat_cost = float(metrics["stat_cost"] or 0)
    show_cnt = float(metrics["raw"]["show_cnt"] or 0)
    click_cnt = float(metrics["raw"]["click_cnt"] or 0)
    active_register = float(metrics["active_register"] or 0)
    billing_convert_cnt = float(metrics["billing_convert_cnt"] or 0)
    result = dict(metrics)
    result["raw"] = dict(metrics["raw"])
    result["ctr"] = _rate(click_cnt, show_cnt)
    result["register_cost"] = _rate(stat_cost, active_register)
    result["billing_conversion_cost"] = _rate(stat_cost, billing_convert_cnt)
    roi_weighted = float(metrics.get("_roi_weighted") or 0)
    result["billing_1day_pay_roi"] = round(roi_weighted / stat_cost, 4) if stat_cost and roi_weighted else None
    result.pop("_roi_weighted", None)
    return result


def _metric_text(metrics: dict[str, Any]) -> str:
    roi = metrics.get("billing_1day_pay_roi")
    roi_text = "无" if roi is None else str(roi)
    billing_cost = metrics.get("billing_conversion_cost")
    billing_cost_text = "无" if billing_cost is None else str(billing_cost)
    register_cost = metrics.get("register_cost")
    register_cost_text = "无" if register_cost is None else str(register_cost)
    return (
        f"消耗 {metrics.get('stat_cost', 0)}，"
        f"注册成本 {register_cost_text}，"
        f"计费转化 {metrics.get('billing_convert_cnt', 0)}，"
        f"计费转化成本 {billing_cost_text}，"
        f"计费当日ROI {roi_text}"
    )


def _status_text(value: Any) -> str:
    status = str(value or "").strip()
    return STATUS_LABELS.get(status, status or "未知")


def _aggregate_window_metrics(items: list[dict[str, Any]], window: str) -> dict[str, Any]:
    total = _empty_metrics()
    for item in items:
        metrics = item.get("metrics") if isinstance(item.get("metrics"), dict) else {}
        window_metrics = metrics.get(window) if isinstance(metrics.get(window), dict) else {}
        stat_cost = _number(window_metrics.get("stat_cost"))
        total["stat_cost"] = round(float(total["stat_cost"] or 0) + stat_cost, 4)
        total["active_register"] = round(
            float(total["active_register"] or 0) + _number(window_metrics.get("active_register")),
            4,
        )
        total["billing_convert_cnt"] = round(
            float(total["billing_convert_cnt"] or 0) + _number(window_metrics.get("billing_convert_cnt")),
            4,
        )
        raw = window_metrics.get("raw") if isinstance(window_metrics.get("raw"), dict) else {}
        total["raw"]["show_cnt"] = round(float(total["raw"]["show_cnt"] or 0) + _number(raw.get("show_cnt")), 4)
        total["raw"]["click_cnt"] = round(float(total["raw"]["click_cnt"] or 0) + _number(raw.get("click_cnt")), 4)
        roi = window_metrics.get("billing_1day_pay_roi")
        if roi is not None and stat_cost:
            total["_roi_weighted"] = float(total.get("_roi_weighted") or 0) + _number(roi) * stat_cost
    return _finalize_metrics(total)


def _overall_metrics(accounts: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        "today": _aggregate_window_metrics(accounts, "today"),
        "yesterday": _aggregate_window_metrics(accounts, "yesterday"),
    }


def _top_entities(items: list[dict[str, Any]], *, limit: int = 5) -> list[dict[str, Any]]:
    spent = [item for item in items if float((item.get("metrics") or {}).get("today", {}).get("stat_cost") or 0) > 0]
    return sorted(
        spent,
        key=lambda item: float((item.get("metrics") or {}).get("today", {}).get("stat_cost") or 0),
        reverse=True,
    )[:limit]


def _attention_projects(projects: list[dict[str, Any]], *, limit: int = 5) -> list[dict[str, Any]]:
    attention: list[dict[str, Any]] = []
    for project in projects:
        today = project.get("metrics", {}).get("today", {})
        stat_cost = _number(today.get("stat_cost"))
        billing_convert_cnt = _number(today.get("billing_convert_cnt"))
        roi_raw = today.get("billing_1day_pay_roi")
        roi = None if roi_raw is None else _number(roi_raw)
        reason = ""
        if stat_cost >= 500 and billing_convert_cnt <= 0:
            reason = "今天消耗>=500 且计费时间转化数为0"
        elif stat_cost >= 800 and roi is not None and roi < 0.05:
            reason = "今天消耗>=800 且计费当日ROI<0.05"
        if reason:
            attention.append({**project, "attention_reason": reason})
    return sorted(
        attention,
        key=lambda item: float((item.get("metrics") or {}).get("today", {}).get("stat_cost") or 0),
        reverse=True,
    )[:limit]


def _format_delivery_patrol_message(payload: dict[str, Any]) -> str:
    windows = payload.get("windows") if isinstance(payload.get("windows"), dict) else {}
    target_date = str(windows.get("today") or payload.get("summary", {}).get("target_date") or "")
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    overall = summary.get("overall_metrics") if isinstance(summary.get("overall_metrics"), dict) else {}
    today_overall = overall.get("today") if isinstance(overall.get("today"), dict) else _empty_metrics()
    yesterday_overall = overall.get("yesterday") if isinstance(overall.get("yesterday"), dict) else _empty_metrics()
    lines = [
        f"RoiBang-V2 投放账户巡检 {target_date}",
        "",
        (
            f"账户 {summary.get('account_count', 0)} 个，"
            f"项目 {summary.get('project_count', 0)} 个，"
            f"单元 {summary.get('promotion_count', 0)} 个，"
            f"接口调用 {summary.get('transport_calls', 0)} 次"
        ),
        (
            "整体表现："
            f"今日{_metric_text(today_overall)}；"
            f"昨日{_metric_text(yesterday_overall)}"
        ),
        "",
        "账户数据",
    ]
    accounts = payload.get("accounts") if isinstance(payload.get("accounts"), list) else []
    for account in _top_entities([item for item in accounts if isinstance(item, dict)], limit=8):
        today = account.get("metrics", {}).get("today", {})
        lines.append(f"- 账户：{account.get('account_name') or account.get('advertiser_id')}，{_metric_text(today)}")
    if not any(line.startswith("- 账户：") for line in lines):
        lines.append("- 无今日消耗账户")

    lines.extend(["", "重点项目"])
    projects = payload.get("projects") if isinstance(payload.get("projects"), list) else []
    for project in _top_entities([item for item in projects if isinstance(item, dict)], limit=8):
        today = project.get("metrics", {}).get("today", {})
        lines.append(
            f"- {project.get('project_name') or project.get('project_id')}，"
            f"项目ID {project.get('project_id') or '未知'}，"
            f"状态 {_status_text(project.get('status'))}，{_metric_text(today)}"
        )
    if not any(line.startswith("- ") for line in lines[lines.index("重点项目") + 1 :]):
        lines.append("- 无今日消耗项目")

    lines.extend(["", "要注意的重点项目"])
    for project in _attention_projects([item for item in projects if isinstance(item, dict)], limit=5):
        today = project.get("metrics", {}).get("today", {})
        lines.append(
            f"- {project.get('project_name') or project.get('project_id')}，"
            f"项目ID {project.get('project_id') or '未知'}，"
            f"状态 {_status_text(project.get('status'))}，"
            f"原因 {project.get('attention_reason')}，{_metric_text(today)}"
        )
    if not any(line.startswith("- ") for line in lines[lines.index("要注意的重点项目") + 1 :]):
        lines.append("- 暂无")

    lines.extend(["", "重点单元"])
    promotions = payload.get("promotions") if isinstance(payload.get("promotions"), list) else []
    for promotion in _top_entities([item for item in promotions if isinstance(item, dict)], limit=8):
        today = promotion.get("metrics", {}).get("today", {})
        lines.append(
            f"- {promotion.get('promotion_name') or promotion.get('promotion_id')}，"
            f"状态 {_status_text(promotion.get('status'))}，{_metric_text(today)}"
        )
    if not any(line.startswith("- ") for line in lines[lines.index("重点单元") + 1 :]):
        lines.append("- 无今日消耗单元")
    artifact_path = str(payload.get("artifact_path") or "")
    if artifact_path:
        lines.extend(["", f"完整 JSON：{artifact_path}"])
    return "\n".join(lines).rstrip() + "\n"


def _deliver_feishu(cfg: dict[str, Any], message: str, *, feishu_sender: FeishuSender) -> dict[str, Any]:
    delivery = cfg.get("delivery") if isinstance(cfg.get("delivery"), dict) else {}
    feishu = delivery.get("feishu") if isinstance(delivery.get("feishu"), dict) else {}
    if not bool(feishu.get("enabled", False)):
        return {"enabled": False, "attempted": False, "ok": True, "reason": "disabled"}
    try:
        result = feishu_sender(feishu, message)
    except Exception as exc:
        return {"enabled": True, "attempted": True, "ok": False, "reason": str(exc)}
    return {"enabled": True, "attempted": True, **result}


def _window_for_date(target_dates: dict[str, str], value: Any) -> str:
    current = str(value or "").strip()[:10]
    for window, target_date in target_dates.items():
        if current == target_date:
            return window
    return ""


def _entity_metrics() -> dict[str, dict[str, Any]]:
    return {"today": _empty_metrics(), "yesterday": _empty_metrics()}


def _ensure_account(bucket: dict[str, Any], account: dict[str, Any]) -> dict[str, Any]:
    advertiser_id = str(account.get("advertiser_id") or "")
    if advertiser_id not in bucket:
        bucket[advertiser_id] = {
            "advertiser_id": advertiser_id,
            "account_name": str(account.get("account_name") or ""),
            "account_remark": str(account.get("account_remark") or account.get("advertiser_remark") or ""),
            "product": str(account.get("product") or ""),
            "metrics": _entity_metrics(),
            "summary": {
                "today_spent_project_count": 0,
                "today_spent_promotion_count": 0,
            },
        }
    return bucket[advertiser_id]


def _dimensions(row: dict[str, Any]) -> dict[str, Any]:
    value = row.get("dimensions")
    return value if isinstance(value, dict) else {}


def _metrics(row: dict[str, Any]) -> dict[str, Any]:
    value = row.get("metrics")
    return value if isinstance(value, dict) else {}


def _first_text(row: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value not in (None, "", 0, "0"):
            return str(value)
    return ""


def _build_result(plan_payload: dict[str, Any], execution: dict[str, Any]) -> dict[str, Any]:
    accounts: dict[str, dict[str, Any]] = {}
    projects: dict[tuple[str, str], dict[str, Any]] = {}
    promotions: dict[tuple[str, str], dict[str, Any]] = {}
    target_dates = plan_payload["target_dates"]
    for account in plan_payload["accounts"]:
        _ensure_account(accounts, account)

    for item in execution.get("responses") or []:
        if not isinstance(item, dict):
            continue
        request = item.get("request") if isinstance(item.get("request"), dict) else {}
        account_ref = request.get("account") if isinstance(request.get("account"), dict) else {}
        advertiser_id = str(account_ref.get("advertiser_id") or "")
        endpoint_key = str(request.get("endpoint_key") or "")
        if not advertiser_id:
            continue
        if endpoint_key == "project_list":
            for row in item.get("rows") or []:
                if not isinstance(row, dict):
                    continue
                project_id = _first_text(row, "project_id", "cdp_project_id")
                if not project_id:
                    continue
                project = projects.setdefault(
                    (advertiser_id, project_id),
                    {
                        "advertiser_id": advertiser_id,
                        "project_id": project_id,
                        "project_name": _first_text(row, "project_name", "cdp_project_name", "name"),
                        "status": "",
                        "metrics": _entity_metrics(),
                    },
                )
                project["project_name"] = project["project_name"] or _first_text(row, "project_name", "cdp_project_name", "name")
                project["status"] = _first_text(row, "project_status", "project_status_name", "status")
            continue
        if endpoint_key == "promotion_list":
            for row in item.get("rows") or []:
                if not isinstance(row, dict):
                    continue
                promotion_id = _first_text(row, "promotion_id", "cdp_promotion_id")
                if not promotion_id:
                    continue
                promotion = promotions.setdefault(
                    (advertiser_id, promotion_id),
                    {
                        "advertiser_id": advertiser_id,
                        "project_id": _first_text(row, "project_id", "cdp_project_id"),
                        "project_name": _first_text(row, "project_name", "cdp_project_name"),
                        "promotion_id": promotion_id,
                        "promotion_name": _first_text(row, "promotion_name", "cdp_promotion_name", "name"),
                        "status": "",
                        "metrics": _entity_metrics(),
                    },
                )
                promotion["project_id"] = promotion["project_id"] or _first_text(row, "project_id", "cdp_project_id")
                promotion["project_name"] = promotion["project_name"] or _first_text(row, "project_name", "cdp_project_name")
                promotion["promotion_name"] = promotion["promotion_name"] or _first_text(
                    row, "promotion_name", "cdp_promotion_name", "name"
                )
                promotion["status"] = _first_text(row, "promotion_status", "promotion_status_name", "status")
            continue
        if endpoint_key != "report_custom":
            continue
        preset = str(request.get("report_preset") or "")
        window = _window_for_date(target_dates, request.get("date"))
        if not window:
            continue
        account = _ensure_account(accounts, account_ref)
        for row in item.get("rows") or []:
            if not isinstance(row, dict):
                continue
            dimensions = _dimensions(row)
            metrics = _metrics(row)
            if preset == "account_daily":
                _add_metrics(account["metrics"][window], metrics)
            elif preset == "project_daily":
                project_id = str(dimensions.get("cdp_project_id") or dimensions.get("project_id") or "")
                if not project_id:
                    continue
                key = (advertiser_id, project_id)
                project = projects.setdefault(
                    key,
                    {
                        "advertiser_id": advertiser_id,
                        "project_id": project_id,
                        "project_name": str(dimensions.get("cdp_project_name") or dimensions.get("project_name") or ""),
                        "status": "",
                        "metrics": _entity_metrics(),
                    },
                )
                _add_metrics(project["metrics"][window], metrics)
            elif preset == "promotion_daily":
                promotion_id = str(dimensions.get("cdp_promotion_id") or dimensions.get("promotion_id") or "")
                if not promotion_id:
                    continue
                key = (advertiser_id, promotion_id)
                promotion = promotions.setdefault(
                    key,
                    {
                        "advertiser_id": advertiser_id,
                        "project_id": str(dimensions.get("cdp_project_id") or dimensions.get("project_id") or ""),
                        "project_name": str(dimensions.get("cdp_project_name") or dimensions.get("project_name") or ""),
                        "promotion_id": promotion_id,
                        "promotion_name": str(
                            dimensions.get("cdp_promotion_name") or dimensions.get("promotion_name") or ""
                        ),
                        "status": "",
                        "metrics": _entity_metrics(),
                    },
                )
                _add_metrics(promotion["metrics"][window], metrics)

    for collection in (accounts.values(), projects.values(), promotions.values()):
        for item in collection:
            item["metrics"] = {
                "today": _finalize_metrics(item["metrics"]["today"]),
                "yesterday": _finalize_metrics(item["metrics"]["yesterday"]),
            }

    today_spent_projects: dict[str, set[str]] = {}
    for (advertiser_id, project_id), project in projects.items():
        if float(project["metrics"]["today"]["stat_cost"] or 0) > 0:
            today_spent_projects.setdefault(advertiser_id, set()).add(project_id)
    today_spent_promotions: dict[str, set[str]] = {}
    for (advertiser_id, promotion_id), promotion in promotions.items():
        if float(promotion["metrics"]["today"]["stat_cost"] or 0) > 0:
            today_spent_promotions.setdefault(advertiser_id, set()).add(promotion_id)
    for advertiser_id, account in accounts.items():
        account["summary"]["today_spent_project_count"] = len(today_spent_projects.get(advertiser_id, set()))
        account["summary"]["today_spent_promotion_count"] = len(today_spent_promotions.get(advertiser_id, set()))

    account_list = sorted(accounts.values(), key=lambda item: item["advertiser_id"])
    project_list = sorted(projects.values(), key=lambda item: (item["advertiser_id"], item["project_id"]))
    promotion_list = sorted(promotions.values(), key=lambda item: (item["advertiser_id"], item["promotion_id"]))
    return {
        "accounts": account_list,
        "projects": project_list,
        "promotions": promotion_list,
    }


def _require_readonly_enabled(openapi_http: dict[str, Any], execution: dict[str, Any], transport: Transport | None) -> None:
    if transport is not None:
        return
    if str(execution.get("status") or "") != "execute":
        raise RuntimeError("delivery patrol requires execution.status=execute")
    if not bool(execution.get("external_api_enabled", False)):
        raise RuntimeError("delivery patrol requires execution.external_api_enabled=true")
    if not bool(openapi_http.get("enabled", False)):
        raise RuntimeError("delivery patrol requires openapi_http.enabled=true")


def run_delivery_patrol_request(
    request: dict[str, Any] | None,
    *,
    db_path: str | Path,
    runs_dir: str | Path,
    transport: Transport | None = None,
    http_opener=None,
    http_sleeper=None,
    workbench_opener: WorkbenchOpener | None = None,
    workbench_sleeper: WorkbenchSleeper | None = None,
    feishu_sender: FeishuSender | None = None,
) -> dict[str, Any]:
    cfg = _config(request)
    openapi_http = cfg.get("openapi_http") if isinstance(cfg.get("openapi_http"), dict) else {}
    execution_cfg = cfg.get("execution") if isinstance(cfg.get("execution"), dict) else {}
    _require_readonly_enabled(openapi_http, execution_cfg, transport)
    target_dates = _target_dates(cfg)
    discovery_cfg = cfg.get("active_account_discovery") if isinstance(cfg.get("active_account_discovery"), dict) else {}
    account_scope = _account_scope(cfg, source="")
    discovered_accounts = None
    discovery_summary = None
    if bool(discovery_cfg.get("enabled", False)) or account_scope["source"] == "workbench_account_list":
        discovered_accounts, discovery_summary = _discover_workbench_accounts(
            cfg,
            target_dates,
            workbench_opener=workbench_opener,
            workbench_sleeper=workbench_sleeper,
        )
    plan_payload = build_delivery_patrol_plan(
        db_path,
        cfg,
        accounts_override=discovered_accounts,
        discovery_summary=discovery_summary,
    )
    real_transport = transport or build_http_transport(
        openapi_http,
        response_dir=openapi_http.get("response_audit_dir") or Path(runs_dir) / "openapi_http" / "delivery-patrol",
        opener=http_opener,
        sleeper=http_sleeper,
    )
    execution = execute_openapi_readonly_plan(
        plan_payload["plan"],
        transport=real_transport,
        retry_api_codes=list(openapi_http.get("retry_api_codes") or []),
        max_api_retries=int(openapi_http.get("max_api_retries") or 0),
        retry_sleep_seconds=float(openapi_http.get("retry_sleep_seconds") or 1),
        sleeper=http_sleeper,
    )
    entities = _build_result(plan_payload, execution)
    transport_calls = int(execution["summary"]["transport_calls"])
    discovery_calls = int((plan_payload.get("account_discovery") or {}).get("external_api_calls") or 0)
    overall_metrics = _overall_metrics(entities["accounts"])
    payload = {
        "ok": True,
        "workflow": "delivery_patrol",
        "phase": "control_analysis",
        "execution_enabled": False,
        "external_api_calls": transport_calls + discovery_calls,
        "summary": {
            **plan_payload["summary"],
            "transport_calls": transport_calls,
            "discovery_calls": discovery_calls,
            "rows_received": int(execution["summary"]["rows_received"]),
            "account_count": len(entities["accounts"]),
            "project_count": len(entities["projects"]),
            "promotion_count": len(entities["promotions"]),
            "overall_metrics": overall_metrics,
        },
        "windows": {
            "today": plan_payload["target_dates"]["today"],
            "yesterday": plan_payload["target_dates"]["yesterday"],
        },
        **entities,
        "plan_summary": plan_payload["summary"],
        "execution_summary": execution["summary"],
        "guardrails": [
            "Readonly only: this workflow reads account/project/promotion report data.",
            "No create/update/delete/pause/budget/schedule API is called.",
        ],
    }
    payload["artifact_path"] = str(write_run_artifact(runs_dir, "delivery_patrol", payload))
    payload["message"] = _format_delivery_patrol_message(payload)
    patrol_dir = Path(runs_dir) / "delivery_patrol"
    patrol_dir.mkdir(parents=True, exist_ok=True)
    (patrol_dir / "latest.md").write_text(payload["message"], encoding="utf-8")
    payload["delivery"] = {
        "feishu": _deliver_feishu(
            cfg,
            payload["message"],
            feishu_sender=feishu_sender or send_feishu_app_chat_text,
        )
    }
    payload["artifact_path"] = str(write_run_artifact(runs_dir, "delivery_patrol", payload))
    (patrol_dir / "latest.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload
