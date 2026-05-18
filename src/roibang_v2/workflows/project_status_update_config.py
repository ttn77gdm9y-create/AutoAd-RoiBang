from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable

from roibang_v2.runs import write_run_artifact
from roibang_v2.workflows.project_update_execute import PROJECT_LIST_ENDPOINT


Transport = Callable[[dict[str, Any]], dict[str, Any]]
MANAGEMENT_ACTION_TYPES = {"status_update", "budget_update", "bid_update", "roi_coeff_update", "delete_project"}
PROJECT_REPORT_ENDPOINT = "/open_api/v3.0/report/custom/get/"
SPEND_WINDOW_LABELS = {
    "today": "今天",
    "yesterday": "昨天",
    "last_3_days": "最近3天",
}
REPORT_METRICS = [
    "stat_cost",
    "show_cnt",
    "click_cnt",
    "active_register",
    "attribution_convert_cnt",
    "attribution_billing_game_in_app_roi_1day",
]
METRIC_FILTER_FIELDS = {
    "stat_cost",
    "active_register",
    "register_cost",
    "billing_convert_cnt",
    "billing_conversion_cost",
    "billing_1day_pay_roi",
}
METRIC_FILTER_OPS = {"lt", "lte", "gt", "gte", "eq"}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _rows(value: Any) -> list[dict[str, Any]]:
    return [dict(item) for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _wire_id(value: Any) -> int | str:
    text = _text(value)
    return int(text) if text.isdigit() else text


def _required_text(cfg: dict[str, Any], key: str) -> str:
    value = _text(cfg.get(key))
    if not value:
        raise ValueError(f"project status update config requires {key}")
    return value


def _api_code(response: dict[str, Any]) -> str:
    code = response.get("code")
    return "" if code in (None, "", 0, "0") else str(code)


def _raise_for_api_error(response: dict[str, Any]) -> None:
    code = _api_code(response)
    if not code:
        return
    message = _text(response.get("message") or response.get("msg"))
    raise RuntimeError(f"OpenAPI response code={code}: {message}")


def _response_rows(response: dict[str, Any]) -> list[dict[str, Any]]:
    data = response.get("data") if isinstance(response.get("data"), dict) else {}
    for key in ["list", "rows", "data"]:
        value = data.get(key)
        if isinstance(value, list):
            return [dict(row) for row in value if isinstance(row, dict)]
    return []


def _total_number(response: dict[str, Any]) -> int:
    data = response.get("data") if isinstance(response.get("data"), dict) else {}
    page_info = data.get("page_info") if isinstance(data.get("page_info"), dict) else {}
    for key in ["total_number", "total_count", "total"]:
        try:
            value = int(page_info.get(key))
        except (TypeError, ValueError):
            continue
        return value
    return 0


def _response_report_rows(response: dict[str, Any]) -> list[dict[str, Any]]:
    data = response.get("data") if isinstance(response.get("data"), dict) else {}
    value = data.get("rows")
    if not isinstance(value, list):
        value = data.get("list")
    return [dict(row) for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def _advertiser_ids(cfg: dict[str, Any]) -> list[str]:
    values = cfg.get("advertiser_ids")
    if not isinstance(values, list):
        values = cfg.get("accounts")
    if not isinstance(values, list):
        values = []
    result: list[str] = []
    for item in values:
        if isinstance(item, dict):
            value = _text(item.get("advertiser_id") or item.get("account_id"))
        else:
            value = _text(item)
        if value:
            result.append(value)
    return result


def _action_type(cfg: dict[str, Any]) -> str:
    action_type = _text(cfg.get("action_type") or "status_update")
    if action_type not in MANAGEMENT_ACTION_TYPES:
        raise ValueError(f"project management config action_type must be one of {sorted(MANAGEMENT_ACTION_TYPES)}")
    return action_type


def _default_filtering(action_type: str, opt_status: str) -> dict[str, Any]:
    if action_type == "status_update" and opt_status == "DISABLE":
        return {"status_first": "PROJECT_STATUS_ENABLE"}
    if action_type == "status_update" and opt_status == "ENABLE":
        return {"status_first": "PROJECT_STATUS_DISABLE", "status_second": "PROJECT_STATUS_STOP"}
    if action_type == "delete_project":
        return {}
    return {"status_first": "PROJECT_STATUS_ENABLE"}


def _name_contains(cfg: dict[str, Any]) -> list[str]:
    value = cfg.get("name_contains")
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, list):
        values = value
    else:
        values = []
    result: list[str] = []
    for item in values:
        for part in _text(item).split(","):
            text = part.strip()
            if text:
                result.append(text)
    return result


def _filtering_with_name(cfg: dict[str, Any], action_type: str, opt_status: str, keywords: list[str]) -> dict[str, Any]:
    filtering = dict(cfg.get("filtering")) if isinstance(cfg.get("filtering"), dict) else _default_filtering(action_type, opt_status)
    if keywords and not _text(filtering.get("name")):
        filtering["name"] = keywords[0]
    return filtering


def _parse_date(value: Any) -> date:
    text = _text(value)
    if not text:
        return date.today()
    return date.fromisoformat(text)


def _week_start(value: date) -> date:
    return value - timedelta(days=value.weekday())


def _spend_window_dates(window: str, *, end_date: date) -> tuple[date, date]:
    if window == "today":
        return end_date, end_date
    if window == "yesterday":
        target = end_date - timedelta(days=1)
        return target, target
    if window == "last_3_days":
        return end_date - timedelta(days=2), end_date
    raise ValueError("project realtime filter only supports today, yesterday, last_3_days")


def _normalize_metric_filter(item: dict[str, Any]) -> dict[str, Any]:
    field = _text(item.get("field"))
    op = _text(item.get("op"))
    if field not in METRIC_FILTER_FIELDS:
        raise ValueError(f"project realtime filter field must be one of {sorted(METRIC_FILTER_FIELDS)}")
    if op not in METRIC_FILTER_OPS:
        raise ValueError(f"project realtime filter op must be one of {sorted(METRIC_FILTER_OPS)}")
    return {"field": field, "op": op, "value": _number(item.get("value"), f"metric_filters.{field}.value")}


def _metric_filters(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [_normalize_metric_filter(item) for item in value if isinstance(item, dict)]


def _realtime_filter(cfg: dict[str, Any]) -> dict[str, Any]:
    value = cfg.get("realtime_filter")
    if not isinstance(value, dict):
        value = cfg.get("spend_filter")
        if not isinstance(value, dict):
            return {}
    window = _text(value.get("window") or "today")
    end_date = _parse_date(value.get("end_date"))
    start, end = _spend_window_dates(window, end_date=end_date)
    filters = _metric_filters(value.get("metric_filters"))
    if not filters and ("max_stat_cost_exclusive" in value or "max_stat_cost" in value):
        threshold = value.get("max_stat_cost_exclusive", value.get("max_stat_cost"))
        max_stat_cost_exclusive = _number(threshold, "spend_filter.max_stat_cost_exclusive")
        if max_stat_cost_exclusive < 0:
            raise ValueError("project management spend_filter max_stat_cost_exclusive must be >= 0")
        filters = [{"field": "stat_cost", "op": "lt", "value": max_stat_cost_exclusive}]
    if not filters:
        raise ValueError("project realtime filter requires metric_filters")
    return {
        "window": window,
        "window_label": SPEND_WINDOW_LABELS[window],
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "metric_filters": filters,
    }


def _name_matched(project: dict[str, Any], keywords: list[str]) -> bool:
    if not keywords:
        return True
    name = _text(project.get("name"))
    return all(keyword in name for keyword in keywords)


def _lookup_request(advertiser_id: str, filtering: dict[str, Any], *, page: int, page_size: int) -> dict[str, Any]:
    return {
        "operation": "lookup_project_list",
        "method": "GET",
        "endpoint": PROJECT_LIST_ENDPOINT,
        "payload": {
            "advertiser_id": _wire_id(advertiser_id),
            "filtering": filtering,
            "page": page,
            "page_size": page_size,
        },
    }


def _report_request(advertiser_id: str, spend_filter: dict[str, Any], *, page: int, page_size: int) -> dict[str, Any]:
    return {
        "operation": "lookup_project_report",
        "method": "GET",
        "endpoint": PROJECT_REPORT_ENDPOINT,
        "payload": {
            "advertiser_id": _wire_id(advertiser_id),
            "data_topic": "BASIC_DATA",
            "dimensions": ["cdp_project_id", "cdp_project_name"],
            "metrics": REPORT_METRICS,
            "filters": [],
            "start_time": spend_filter["start_date"],
            "end_time": spend_filter["end_date"],
            "order_by": [{"field": "stat_cost", "type": "DESC"}],
            "page": page,
            "page_size": page_size,
        },
    }


def _fetch_projects(
    advertiser_id: str,
    *,
    filtering: dict[str, Any],
    page_size: int,
    transport: Transport,
) -> tuple[list[dict[str, Any]], int]:
    page = 1
    calls = 0
    projects: list[dict[str, Any]] = []
    while True:
        response = transport(_lookup_request(advertiser_id, filtering, page=page, page_size=page_size))
        calls += 1
        _raise_for_api_error(response)
        rows = _response_rows(response)
        projects.extend(rows)
        total_number = _total_number(response)
        if not rows or len(rows) < page_size:
            break
        if total_number and len(projects) >= total_number:
            break
        page += 1
    return projects, calls


def _rate(numerator: float, denominator: float) -> float | None:
    if denominator <= 0:
        return None
    return round(numerator / denominator, 4)


def _empty_metrics() -> dict[str, Any]:
    return {
        "stat_cost": 0.0,
        "show_cnt": 0.0,
        "click_cnt": 0.0,
        "ctr": None,
        "active_register": 0.0,
        "register_cost": None,
        "billing_convert_cnt": 0.0,
        "billing_conversion_cost": None,
        "billing_1day_pay_roi": None,
    }


def _finalize_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    stat_cost = float(metrics.get("stat_cost") or 0)
    show_cnt = float(metrics.get("show_cnt") or 0)
    click_cnt = float(metrics.get("click_cnt") or 0)
    active_register = float(metrics.get("active_register") or 0)
    billing_convert_cnt = float(metrics.get("billing_convert_cnt") or 0)
    roi_weighted_sum = float(metrics.pop("_billing_1day_pay_roi_weighted_sum", 0) or 0)
    metrics["ctr"] = _rate(click_cnt, show_cnt)
    metrics["register_cost"] = _rate(stat_cost, active_register)
    metrics["billing_conversion_cost"] = _rate(stat_cost, billing_convert_cnt)
    metrics["billing_1day_pay_roi"] = round(roi_weighted_sum / stat_cost, 4) if stat_cost > 0 and roi_weighted_sum else None
    return metrics


def _fetch_project_metrics(
    advertiser_id: str,
    *,
    spend_filter: dict[str, Any],
    page_size: int,
    transport: Transport,
) -> tuple[dict[str, dict[str, Any]], int]:
    page = 1
    calls = 0
    metrics_by_project_id: dict[str, dict[str, Any]] = {}
    while True:
        response = transport(_report_request(advertiser_id, spend_filter, page=page, page_size=page_size))
        calls += 1
        _raise_for_api_error(response)
        rows = _response_report_rows(response)
        for row in rows:
            dimensions = row.get("dimensions") if isinstance(row.get("dimensions"), dict) else {}
            metrics = row.get("metrics") if isinstance(row.get("metrics"), dict) else {}
            project_id = _text(dimensions.get("project_id") or dimensions.get("cdp_project_id"))
            if not project_id:
                continue
            target = metrics_by_project_id.setdefault(project_id, _empty_metrics())
            stat_cost = _number(metrics.get("stat_cost") or 0, "stat_cost")
            target["stat_cost"] = round(float(target["stat_cost"] or 0) + stat_cost, 4)
            target["show_cnt"] = round(float(target["show_cnt"] or 0) + _number(metrics.get("show_cnt") or 0, "show_cnt"), 4)
            target["click_cnt"] = round(float(target["click_cnt"] or 0) + _number(metrics.get("click_cnt") or 0, "click_cnt"), 4)
            target["active_register"] = round(
                float(target["active_register"] or 0) + _number(metrics.get("active_register") or 0, "active_register"),
                4,
            )
            target["billing_convert_cnt"] = round(
                float(target["billing_convert_cnt"] or 0)
                + _number(metrics.get("attribution_convert_cnt") or metrics.get("billing_convert_cnt") or 0, "billing_convert_cnt"),
                4,
            )
            roi = metrics.get("attribution_billing_game_in_app_roi_1day") or metrics.get("billing_1day_pay_roi")
            target["_billing_1day_pay_roi_weighted_sum"] = round(
                float(target.get("_billing_1day_pay_roi_weighted_sum") or 0) + stat_cost * _number(roi or 0, "billing_1day_pay_roi"),
                4,
            )
        total_number = _total_number(response)
        if not rows or len(rows) < page_size:
            break
        if total_number and sum(1 for _ in metrics_by_project_id) >= total_number:
            break
        page += 1
    return {project_id: _finalize_metrics(metrics) for project_id, metrics in metrics_by_project_id.items()}, calls


def _number(value: Any, key: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"project management config requires numeric {key}")
    try:
        return float(str(value).replace(",", "").replace("%", ""))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"project management config requires numeric {key}") from exc


def _compare_metric(actual: Any, op: str, expected: float) -> bool:
    if actual is None:
        return False
    actual_number = float(actual)
    if op == "lt":
        return actual_number < expected
    if op == "lte":
        return actual_number <= expected
    if op == "gt":
        return actual_number > expected
    if op == "gte":
        return actual_number >= expected
    if op == "eq":
        return actual_number == expected
    raise ValueError(f"unsupported metric filter op: {op}")


def _metric_match_reasons(metrics: dict[str, Any], filters: list[dict[str, Any]]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    for metric_filter in filters:
        field = str(metric_filter["field"])
        op = str(metric_filter["op"])
        expected = float(metric_filter["value"])
        if not _compare_metric(metrics.get(field), op, expected):
            return False, reasons
        reasons.append(f"{field} {op} {expected}")
    return True, reasons


def _action_extra_fields(cfg: dict[str, Any], action_type: str) -> dict[str, Any]:
    if action_type == "status_update":
        opt_status = _required_text(cfg, "opt_status")
        if opt_status not in {"ENABLE", "DISABLE"}:
            raise ValueError("project status update config opt_status must be ENABLE or DISABLE")
        return {"opt_status": opt_status}
    if action_type == "budget_update":
        budget_mode = _text(cfg.get("budget_mode") or "BUDGET_MODE_DAY")
        if budget_mode not in {"BUDGET_MODE_DAY", "BUDGET_MODE_INFINITE"}:
            raise ValueError("project budget update config budget_mode must be BUDGET_MODE_DAY or BUDGET_MODE_INFINITE")
        fields: dict[str, Any] = {"budget_mode": budget_mode}
        if budget_mode == "BUDGET_MODE_DAY":
            budget = _number(cfg.get("budget"), "budget")
            if budget <= 0:
                raise ValueError("project budget update config budget must be greater than 0")
            fields["budget"] = int(budget) if budget.is_integer() else budget
        return fields
    if action_type == "bid_update":
        cpa_bid = _number(cfg.get("cpa_bid"), "cpa_bid")
        if cpa_bid <= 0:
            raise ValueError("project bid update config cpa_bid must be greater than 0")
        return {"cpa_bid": int(cpa_bid) if cpa_bid.is_integer() else cpa_bid}
    if action_type == "roi_coeff_update":
        roi_goal = _number(cfg.get("roi_goal"), "roi_goal")
        if roi_goal < 0.01 or roi_goal > 5:
            raise ValueError("project roi coeff update config roi_goal must be between 0.01 and 5")
        return {"roi_goal": roi_goal}
    if action_type == "delete_project":
        return {}
    raise ValueError(f"unsupported project management action_type: {action_type}")


def _workflow_name(cfg: dict[str, Any], action_type: str) -> str:
    explicit = _text(cfg.get("workflow"))
    if explicit:
        return explicit
    if isinstance(cfg.get("realtime_filter"), dict) or isinstance(cfg.get("spend_filter"), dict):
        return "project_realtime_filter_config"
    if action_type == "status_update":
        return "project_status_update_config"
    return "project_management_update_config"


def _build_action(
    *,
    action_type: str,
    advertiser_id: str,
    project: dict[str, Any],
    fields: dict[str, Any],
    reason: str,
) -> dict[str, Any]:
    action = {
        "action_type": action_type,
        "advertiser_id": advertiser_id,
        "entity_type": "project",
        "project_id": _text(project.get("project_id")),
        "project_name": _text(project.get("name")),
    }
    if "stat_cost" in project:
        action["stat_cost"] = float(project.get("stat_cost") or 0)
    if isinstance(project.get("metrics"), dict):
        action["metrics"] = dict(project["metrics"])
    action.update(fields)
    if reason:
        action["reason"] = reason
    return action


def build_project_status_update_config(
    request: dict[str, Any] | None,
    *,
    transport: Transport,
) -> dict[str, Any]:
    cfg = dict(request or {})
    project_update_id = _required_text(cfg, "project_update_id")
    action_type = _action_type(cfg)
    fields = _action_extra_fields(cfg, action_type)
    opt_status = _text(fields.get("opt_status"))
    advertiser_ids = _advertiser_ids(cfg)
    if not advertiser_ids:
        raise ValueError("project status update config requires advertiser_ids")
    name_keywords = _name_contains(cfg)
    filtering = _filtering_with_name(cfg, action_type, opt_status, name_keywords)
    page_size = int(cfg.get("page_size") or 100)
    spend_page_size = int(cfg.get("spend_page_size") or page_size)
    realtime_filter = _realtime_filter(cfg)
    reason = _text(cfg.get("reason"))
    workflow_name = _workflow_name(cfg, action_type)

    actions: list[dict[str, Any]] = []
    matched_projects: list[dict[str, Any]] = []
    skipped_projects: list[dict[str, Any]] = []
    project_seen_count = 0
    skipped_duration_project_count = 0
    skipped_realtime_filter_count = 0
    external_api_calls = 0
    for advertiser_id in advertiser_ids:
        projects, calls = _fetch_projects(
            advertiser_id,
            filtering=filtering,
            page_size=page_size,
            transport=transport,
        )
        external_api_calls += calls
        project_seen_count += len(projects)
        metrics_by_project_id: dict[str, dict[str, Any]] = {}
        if realtime_filter:
            metrics_by_project_id, calls = _fetch_project_metrics(
                advertiser_id,
                spend_filter=realtime_filter,
                page_size=spend_page_size,
                transport=transport,
            )
            external_api_calls += calls
        for project in projects:
            if not _name_matched(project, name_keywords):
                continue
            project_id = _text(project.get("project_id"))
            if not project_id:
                continue
            if _text(project.get("delivery_type")) == "DURATION":
                skipped_duration_project_count += 1
                skipped_projects.append(
                    {
                        "advertiser_id": advertiser_id,
                        "project_id": project_id,
                        "project_name": _text(project.get("name")),
                        "skip_reason": "duration_project",
                    }
                )
                continue
            match_reasons: list[str] = []
            if realtime_filter:
                metrics = metrics_by_project_id.get(project_id, _empty_metrics())
                matched, match_reasons = _metric_match_reasons(metrics, list(realtime_filter["metric_filters"]))
                if not matched:
                    skipped_realtime_filter_count += 1
                    skipped_projects.append(
                        {
                            "advertiser_id": advertiser_id,
                            "project_id": project_id,
                            "project_name": _text(project.get("name")),
                            "project_status": _text(project.get("status_first") or project.get("status")),
                            "skip_reason": "metric_filter_not_matched",
                            "metrics": metrics,
                        }
                    )
                    continue
                project = {**project, "stat_cost": metrics["stat_cost"], "metrics": metrics}
            matched_projects.append(
                {
                    "advertiser_id": advertiser_id,
                    "project_id": project_id,
                    "project_name": _text(project.get("name")),
                    "project_status": _text(project.get("status_first") or project.get("status")),
                    "metrics": project.get("metrics", {}),
                    "match_reasons": match_reasons,
                }
            )
            actions.append(
                _build_action(
                    action_type=action_type,
                    advertiser_id=advertiser_id,
                    project=project,
                    fields=fields,
                    reason=reason,
                )
            )

    project_update = {
        "project_update_id": project_update_id,
        "operator": _text(cfg.get("operator")),
        "source": {
            "workflow": workflow_name,
            "request": "realtime_metric_filter" if realtime_filter else "account_project_status_control",
        },
        "allowed_target_accounts_path": _text(cfg.get("allowed_target_accounts_path")),
        "execution": {"enabled": False, "status": "planned_only"},
        "actions": actions,
        "restore_actions": [],
    }
    return {
        "ok": True,
        "workflow": workflow_name,
        "phase": "control_config",
        "status": "completed",
        "execution_enabled": False,
        "external_api_calls": external_api_calls,
        "summary": {
            "project_update_id": project_update_id,
            "target_account_count": len(advertiser_ids),
            "project_seen_count": project_seen_count,
            "project_matched_count": len(matched_projects),
            "action_count": len(actions),
            "skipped_duration_project_count": skipped_duration_project_count,
            "skipped_realtime_filter_count": skipped_realtime_filter_count,
            "action_type": action_type,
            "opt_status": opt_status,
            "name_contains": name_keywords,
            **({"realtime_filter": {key: value for key, value in realtime_filter.items() if key != "window_label"}} if realtime_filter else {}),
            **(
                {
                    "spend_filter": {
                        "window": realtime_filter["window"],
                        "start_date": realtime_filter["start_date"],
                        "end_date": realtime_filter["end_date"],
                        "max_stat_cost_exclusive": realtime_filter["metric_filters"][0]["value"],
                    }
                }
                if isinstance(cfg.get("spend_filter"), dict)
                and realtime_filter
                and realtime_filter["metric_filters"][:1]
                and realtime_filter["metric_filters"][0]["field"] == "stat_cost"
                and realtime_filter["metric_filters"][0]["op"] == "lt"
                else {}
            ),
        },
        "matched_projects": matched_projects,
        "skipped_projects": skipped_projects,
        "project_update": project_update,
    }


def run_project_status_update_config_request(
    request: dict[str, Any] | None,
    *,
    runs_dir: str | Path,
    transport: Transport,
) -> dict[str, Any]:
    cfg = dict(request or {})
    result = build_project_status_update_config(cfg, transport=transport)
    output_path = Path(_text(cfg.get("output_path")) or "data/runs/project_status_update_config/project_update.local.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result["project_update"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result["project_update_path"] = str(output_path)
    result["artifact_path"] = str(write_run_artifact(runs_dir, _text(result.get("workflow")) or "project_status_update_config", result))
    return result
