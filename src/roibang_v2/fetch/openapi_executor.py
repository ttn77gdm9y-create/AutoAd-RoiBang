from __future__ import annotations

import math
import hashlib
import json
import time
from copy import deepcopy
from typing import Any, Callable

from roibang_v2.fetch.openapi_readonly import validate_readonly_endpoint


Transport = Callable[[dict[str, Any]], dict[str, Any]]
Sleeper = Callable[[float], None]


def _to_number(value: Any) -> int | float | Any:
    if isinstance(value, int | float):
        return value
    raw = str(value).strip()
    if not raw:
        return value
    try:
        number = float(raw)
    except ValueError:
        return value
    return int(number) if number.is_integer() else number


def _page_info(response: dict[str, Any]) -> dict[str, int]:
    data = response.get("data") if isinstance(response.get("data"), dict) else {}
    info = data.get("page_info") if isinstance(data.get("page_info"), dict) else {}
    if not info:
        info = data.get("page") if isinstance(data.get("page"), dict) else {}
    page = int(info.get("page") or 1)
    page_size = int(info.get("page_size") or 0)
    total_page = int(info.get("total_page") or 0)
    total_count = int(info.get("total_count") or info.get("total_number") or 0)
    if not total_page:
        total_page = math.ceil(total_count / page_size) if page_size and total_count else 1
    return {
        "page": page,
        "total_page": total_page,
    }


def _rows(response: dict[str, Any]) -> list[dict[str, Any]]:
    data = response.get("data") if isinstance(response.get("data"), dict) else {}
    rows = data.get("rows")
    if not isinstance(rows, list):
        rows = data.get("logs")
    if not isinstance(rows, list):
        rows = data.get("list")
    if not isinstance(rows, list):
        rows = data.get("materials")
    if not isinstance(rows, list):
        rows = data.get("data")
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _raise_for_api_error(response: dict[str, Any]) -> None:
    code = response.get("code")
    if code in (None, "", 0, "0"):
        return
    message = str(response.get("message") or response.get("msg") or "")
    raise RuntimeError(f"OpenAPI response code={code}: {message}")


def _api_code(response: dict[str, Any]) -> str:
    code = response.get("code")
    return "" if code in (None, "", 0, "0") else str(code)


def _should_retry_api_code(response: dict[str, Any], retry_api_codes: set[str]) -> bool:
    code = _api_code(response)
    return bool(code and code in retry_api_codes)


def _send_with_api_retries(
    request: dict[str, Any],
    *,
    transport: Transport,
    retry_api_codes: set[str],
    max_api_retries: int,
    retry_sleep_seconds: float,
    sleeper: Sleeper,
) -> tuple[dict[str, Any], int]:
    attempts = max(0, max_api_retries) + 1
    for attempt in range(1, attempts + 1):
        response = transport(request)
        if not _should_retry_api_code(response, retry_api_codes) or attempt == attempts:
            return response, attempt
        sleeper(retry_sleep_seconds)
    raise RuntimeError("OpenAPI retry loop did not return a response")


def _next_page_request(request: dict[str, Any], page: int) -> dict[str, Any]:
    next_request = deepcopy(request)
    query_params = next_request.setdefault("query_params", {})
    query_params["page"] = str(page)
    return next_request


def execute_openapi_readonly_plan(
    plan: dict[str, Any],
    *,
    transport: Transport | None = None,
    max_pages: int = 20,
    retry_api_codes: list[int | str] | None = None,
    max_api_retries: int = 0,
    retry_sleep_seconds: float = 1,
    sleeper: Sleeper | None = None,
) -> dict[str, Any]:
    if transport is None:
        raise RuntimeError("readonly executor requires an explicit transport; real HTTP is not enabled")

    collected: list[dict[str, Any]] = []
    transport_calls = 0
    rows_received = 0
    retry_code_set = {str(item) for item in (retry_api_codes or [])}
    real_sleeper = sleeper or time.sleep
    for planned in plan.get("requests") or []:
        if not isinstance(planned, dict):
            continue
        validate_readonly_endpoint(str(planned.get("endpoint_key") or ""))
        page_request = deepcopy(planned)
        pages_seen = 0
        while True:
            response, call_count = _send_with_api_retries(
                page_request,
                transport=transport,
                retry_api_codes=retry_code_set,
                max_api_retries=max_api_retries,
                retry_sleep_seconds=retry_sleep_seconds,
                sleeper=real_sleeper,
            )
            transport_calls += call_count
            _raise_for_api_error(response)
            pages_seen += 1
            response_rows = _rows(response)
            rows_received += len(response_rows)
            collected.append(
                {
                    "request": page_request,
                    "response": response,
                    "rows": response_rows,
                }
            )
            page_info = _page_info(response)
            if (
                str(page_request.get("endpoint_key"))
                not in {
                    "report_custom",
                    "operation_log_search",
                    "video_material_get",
                    "account_video_material_get",
                    "ebp_video_material_get",
                    "material_attributes_list",
                }
                or page_info["page"] >= page_info["total_page"]
                or pages_seen >= max_pages
            ):
                break
            page_request = _next_page_request(page_request, page_info["page"] + 1)

    return {
        "ok": True,
        "workflow": "openapi_readonly_execution",
        "phase": "phase1",
        "execution_enabled": False,
        "external_api_calls": 0,
        "summary": {
            "planned_request_count": len(plan.get("requests") or []),
            "transport_calls": transport_calls,
            "rows_received": rows_received,
        },
        "responses": collected,
    }


def _snapshot_account(date_key: str, account: dict[str, Any]) -> dict[str, Any]:
    return {
        "advertiser_id": str(account.get("advertiser_id") or ""),
        "projects": [],
        "promotions": [],
        "promotion_metrics": [],
        "operation_logs": [],
        "_date": date_key,
        "_seen_promotions": set(),
        "_seen_projects": set(),
    }


def _add_promotion_daily_row(account_snapshot: dict[str, Any], row: dict[str, Any]) -> None:
    dimensions = row.get("dimensions") if isinstance(row.get("dimensions"), dict) else {}
    metrics = row.get("metrics") if isinstance(row.get("metrics"), dict) else {}
    advertiser_id = account_snapshot["advertiser_id"]
    project_id = str(dimensions.get("project_id") or dimensions.get("cdp_project_id") or "")
    project_name = str(dimensions.get("project_name") or dimensions.get("cdp_project_name") or "")
    promotion_id = str(dimensions.get("promotion_id") or dimensions.get("cdp_promotion_id") or "")
    promotion_name = str(dimensions.get("promotion_name") or dimensions.get("cdp_promotion_name") or "")
    if not promotion_id:
        return

    if project_id and project_id not in account_snapshot["_seen_projects"]:
        account_snapshot["_seen_projects"].add(project_id)
        account_snapshot["projects"].append(
            {
                "advertiser_id": advertiser_id,
                "project_id": project_id,
                "project_name": project_name,
                "project_status": "",
            }
        )
    if promotion_id not in account_snapshot["_seen_promotions"]:
        account_snapshot["_seen_promotions"].add(promotion_id)
        account_snapshot["promotions"].append(
            {
                "advertiser_id": advertiser_id,
                "project_id": project_id,
                "project_name": project_name,
                "promotion_id": promotion_id,
                "promotion_name": promotion_name,
                "promotion_status_name": "",
            }
        )
    normalized_metrics = {"promotion_id": promotion_id}
    for key, value in metrics.items():
        normalized_metrics[str(key)] = _to_number(value)
    account_snapshot["promotion_metrics"].append(normalized_metrics)


def _entity_type(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return ""
    if "账户" in raw or "account" in raw or "advertiser" in raw:
        return "account"
    if "项目" in raw or "project" in raw or "campaign" in raw:
        return "project"
    if "单元" in raw or "广告计划" in raw or "promotion" in raw or raw == "ad":
        return "promotion"
    if "创意" in raw or "creative" in raw:
        return "creative"
    return raw


def _detail(value: Any) -> str:
    if isinstance(value, list):
        return "\n".join(str(item) for item in value if str(item).strip())
    return str(value or "")


def _add_operation_log_rows(account_snapshot: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    for row in rows:
        operation_id = str(_first_nonzero(row, "request_id", "operation_id", "log_id", "second_log_id", "id"))
        entity_id = str(row.get("object_id") or row.get("entity_id") or row.get("target_id") or "")
        occurred_at = str(row.get("create_time") or row.get("occurred_at") or row.get("operation_time") or "")
        entity_type = _entity_type(row.get("object_type") or row.get("entity_type") or row.get("target_type"))
        action = str(row.get("content_title") or row.get("action") or row.get("operation") or row.get("operation_type") or "")
        detail = _detail(row.get("content_log") or row.get("detail") or row.get("description") or row.get("message"))
        if not operation_id:
            stable = json.dumps(
                {
                    "advertiser_id": account_snapshot["advertiser_id"],
                    "occurred_at": occurred_at,
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "action": action,
                    "detail": detail,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            operation_id = "op_" + hashlib.sha256(stable.encode("utf-8")).hexdigest()[:24]
        if not occurred_at or not entity_type or not entity_id:
            continue
        account_snapshot["operation_logs"].append(
            {
                "operation_id": operation_id,
                "occurred_at": occurred_at,
                "operator": str(row.get("operator") or row.get("operator_name") or row.get("user_name") or ""),
                "entity_type": entity_type,
                "entity_id": entity_id,
                "action": action,
                "detail": detail,
                "payload": {
                    "object_name": str(row.get("object_name") or ""),
                    "object_type": str(row.get("object_type") or ""),
                },
            }
        )


def _first_nonzero(row: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value not in (None, "", 0, "0"):
            return str(value)
    return ""


def build_snapshots_from_execution(execution: dict[str, Any]) -> list[dict[str, Any]]:
    snapshots: dict[str, dict[str, Any]] = {}
    account_snapshots: dict[tuple[str, str], dict[str, Any]] = {}
    for item in execution.get("responses") or []:
        if not isinstance(item, dict):
            continue
        request = item.get("request") if isinstance(item.get("request"), dict) else {}
        if request.get("endpoint_key") not in {"report_custom", "operation_log_search"}:
            continue
        if request.get("endpoint_key") == "report_custom" and request.get("report_preset") != "promotion_daily":
            continue
        date_key = str(request.get("date") or "")
        account = request.get("account") if isinstance(request.get("account"), dict) else {}
        advertiser_id = str(account.get("advertiser_id") or "")
        if not date_key or not advertiser_id:
            continue
        snapshot = snapshots.setdefault(
            date_key,
            {"period": {"start": date_key, "end": date_key}, "accounts": []},
        )
        account_key = (date_key, advertiser_id)
        if account_key not in account_snapshots:
            account_snapshot = _snapshot_account(date_key, account)
            account_snapshots[account_key] = account_snapshot
            snapshot["accounts"].append(account_snapshot)
        for row in item.get("rows") or []:
            if request.get("endpoint_key") == "report_custom" and isinstance(row, dict):
                _add_promotion_daily_row(account_snapshots[account_key], row)
        if request.get("endpoint_key") == "operation_log_search":
            _add_operation_log_rows(
                account_snapshots[account_key],
                [row for row in item.get("rows") or [] if isinstance(row, dict)],
            )

    normalized: list[dict[str, Any]] = []
    for date_key in sorted(snapshots):
        snapshot = snapshots[date_key]
        for account in snapshot["accounts"]:
            account.pop("_date", None)
            account.pop("_seen_promotions", None)
            account.pop("_seen_projects", None)
        normalized.append(snapshot)
    return normalized
