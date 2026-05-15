from __future__ import annotations

import json
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

from roibang_v2.fetch.openapi_http import HttpResponse


class WorkbenchAccountDiscoveryError(RuntimeError):
    pass


WorkbenchOpener = Callable[[str, dict[str, Any], dict[str, str], float], HttpResponse]
Sleeper = Callable[[float], None]


DEFAULT_CASCADE_METRICS = [
    "advertiser_name",
    "advertiser_id",
    "advertiser_followed",
    "advertiser_remark",
    "advertiser_budget",
    "advertiser_status",
    "advertiser_status_name",
    "advertiser_share_balance",
]

DEFAULT_FIELDS = [
    "stat_total_balance",
    "stat_cost",
    "attribution_billing_game_in_app_roi_1day",
    "active_register_cost",
    "attribution_convert_cost",
    "ctr",
    "cpm_platform",
    "attribution_day_active_pay_count",
    "attribution_day_active_pay_cost",
    "attribution_billing_game_pay_7d_count",
    "attribution_billing_game_pay_7d_cost",
    "attribution_billing_game_in_app_roi_7days",
    "pay_amount_roi",
    "attribution_billing_game_in_app_ltv_1day",
    "attribution_billing_game_in_app_ltv_7days",
    "active_register",
    "attribution_convert_cnt",
    "ad_report_cnt",
    "ad_dislike_cnt",
    "dy_like",
    "dy_comment",
    "dy_share",
    "stat_ecp_general_balance_valid",
    "stat_ecp_general_grant_balance_valid",
    "stat_ecp_general_non_grant_balance_valid",
]


def _number(value: Any) -> float:
    try:
        return float(str(value or "0").replace(",", "").replace("%", ""))
    except ValueError:
        return 0.0


def _epoch_range_for_date(target_date: str) -> tuple[str, str]:
    tz = ZoneInfo("Asia/Shanghai")
    start = datetime.fromisoformat(target_date).replace(tzinfo=tz)
    end = start + timedelta(days=1)
    return str(int(start.timestamp())), str(int(end.timestamp()))


def _read_session_file(path: str | Path) -> dict[str, str]:
    if not str(path).strip():
        raise WorkbenchAccountDiscoveryError("workbench account discovery requires session_file")
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise WorkbenchAccountDiscoveryError("workbench session_file must contain a JSON object")
    cookie = str(payload.get("cookie") or "").strip()
    csrf_token = str(payload.get("csrf_token") or payload.get("csrftoken") or "").strip()
    ebpid = str(payload.get("ebpid") or "").strip()
    if not cookie:
        raise WorkbenchAccountDiscoveryError("workbench session_file requires cookie")
    if not csrf_token:
        raise WorkbenchAccountDiscoveryError("workbench session_file requires csrf_token")
    if not ebpid:
        raise WorkbenchAccountDiscoveryError("workbench session_file requires ebpid")
    return {"cookie": cookie, "csrf_token": csrf_token, "ebpid": ebpid}


def _default_opener(
    url: str,
    body: dict[str, Any],
    headers: dict[str, str],
    timeout_seconds: float,
) -> HttpResponse:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    context = None
    # Same emergency escape hatch as the OpenAPI transport, but formal automation
    # should rely on the Python CA bundle instead of setting this.
    import os

    if str(os.environ.get("OCEANENGINE_SSL_VERIFY", "true")).strip().lower() in {"0", "false", "no"}:
        context = ssl._create_unverified_context()
    with urllib.request.urlopen(request, timeout=timeout_seconds, context=context) as response:
        raw = response.read().decode("utf-8")
        payload = json.loads(raw) if raw else {}
        return HttpResponse(int(response.status), payload if isinstance(payload, dict) else {"data": payload})


def _append_audit(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def _audit_record(
    *,
    url: str,
    body: dict[str, Any],
    status_code: int,
    response_json: dict[str, Any],
    attempt: int,
) -> dict[str, Any]:
    return {
        "attempt": attempt,
        "status_code": status_code,
        "request": {
            "method": "POST",
            "url": url,
            "headers": {"Cookie": "<redacted>", "x-csrftoken": "<redacted>"},
            "body": body,
        },
        "response_json": response_json,
    }


def _base_body(config: dict[str, Any], *, target_date: str, offset: int, limit: int) -> dict[str, Any]:
    start_time, end_time = _epoch_range_for_date(target_date)
    keyword = str(config.get("keyword") or "").strip()
    search = {"keyword": keyword, "searchType": int(config.get("search_type", 0)), "queryType": "phrase"}
    if config.get("query_type"):
        search["queryType"] = str(config["query_type"])
    body = {
        "startTime": start_time,
        "endTime": end_time,
        "cascadeMetrics": list(config.get("cascade_metrics") or DEFAULT_CASCADE_METRICS),
        "fields": list(config.get("fields") or DEFAULT_FIELDS),
        "orderField": str(config.get("order_field") or "stat_cost"),
        "orderType": int(config.get("order_type", 1)),
        "offset": offset,
        "limit": limit,
        "accountType": int(config.get("account_type", 0)),
        "filter": {
            "pricingCategory": list(config.get("pricing_category") or [2]),
            "advertiser": {},
            "campaign": {},
            "search": search,
            "isActive": bool(config.get("is_active", True)),
        },
        "platformVersion": str(config.get("platform_version") or "2"),
    }
    if config.get("refer"):
        body["refer"] = str(config["refer"])
    return body


def _headers(session: dict[str, str], config: dict[str, Any]) -> dict[str, str]:
    headers = {
        "accept": "application/json, text/plain, */*",
        "content-type": "application/json",
        "origin": "https://business.oceanengine.com",
        "referer": str(config.get("referer") or "https://business.oceanengine.com/"),
        "user-agent": str(config.get("user_agent") or "RoiBang-v2 readonly workbench discovery"),
        "Cookie": session["cookie"],
        "x-csrftoken": session["csrf_token"],
    }
    extra_headers = config.get("headers") if isinstance(config.get("headers"), dict) else {}
    for key, value in extra_headers.items():
        lower = str(key).strip().lower()
        if lower in {"cookie", "x-csrftoken", "x-csrf-token"}:
            continue
        headers[str(key)] = str(value)
    return headers


def _account_from_row(row: dict[str, Any]) -> dict[str, Any]:
    metrics = row.get("metrics") if isinstance(row.get("metrics"), dict) else {}
    return {
        "advertiser_id": str(row.get("advertiser_id") or ""),
        "account_name": str(row.get("advertiser_name") or ""),
        "advertiser_remark": str(row.get("advertiser_remark") or ""),
        "stat_cost": _number(metrics.get("stat_cost")),
        "ctr": _number(metrics.get("ctr")),
        "metrics": dict(metrics),
    }


def _validate_response(response: HttpResponse) -> dict[str, Any]:
    if response.status_code >= 400:
        raise WorkbenchAccountDiscoveryError(f"workbench account list failed with HTTP {response.status_code}")
    payload = response.json_body
    if int(payload.get("code") or 0) != 0:
        raise WorkbenchAccountDiscoveryError(f"workbench account list returned code {payload.get('code')}")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise WorkbenchAccountDiscoveryError("workbench account list missing data object")
    return data


def discover_spending_accounts(
    config: dict[str, Any],
    *,
    target_date: str,
    min_spend: float,
    opener: WorkbenchOpener | None = None,
    sleeper: Sleeper | None = None,
) -> dict[str, Any]:
    if not bool(config.get("enabled", False)):
        raise WorkbenchAccountDiscoveryError("workbench account discovery is disabled")

    session = _read_session_file(config.get("session_file") or "")
    ebpid = str(config.get("ebpid") or session["ebpid"])
    base_url = str(config.get("url") or "https://business.oceanengine.com/api/ebp/promotion/ad/get_account_list")
    url = base_url + "?" + urllib.parse.urlencode({"ebpid": ebpid})
    limit = int(config.get("limit") or 100)
    max_pages = int(config.get("max_pages") or 0)
    timeout_seconds = float(config.get("timeout_seconds") or 20)
    max_retries = int(config.get("max_retries") or 0)
    retry_sleep_seconds = float(config.get("retry_sleep_seconds") or 1)
    retry_statuses = {int(item) for item in config.get("retry_statuses", [429, 500, 502, 503, 504])}
    stop_at_zero = bool(config.get("stop_when_sorted_cost_reaches_zero", True))
    audit_dir = Path(config.get("response_audit_dir") or "data/runs/workbench_account_discovery")
    audit_path = audit_dir / "workbench_account_list.jsonl"
    real_opener = opener or _default_opener
    real_sleeper = sleeper or time.sleep
    allowed_account_ids = (
        {str(item) for item in config.get("allowed_account_ids", [])}
        if isinstance(config.get("allowed_account_ids"), list)
        else set()
    )

    accounts: list[dict[str, Any]] = []
    rows_received = 0
    transport_calls = 0
    total_count = 0
    offset = 1
    has_more = True
    pages_seen = 0
    while has_more:
        if max_pages and pages_seen >= max_pages:
            break
        body = _base_body(config, target_date=target_date, offset=offset, limit=limit)
        headers = _headers(session, config)
        attempts = max_retries + 1
        response: HttpResponse | None = None
        for attempt in range(1, attempts + 1):
            transport_calls += 1
            try:
                response = real_opener(url, body, headers, timeout_seconds)
            except (OSError, TimeoutError, urllib.error.URLError) as exc:
                _append_audit(
                    audit_path,
                    _audit_record(
                        url=url,
                        body=body,
                        status_code=0,
                        response_json={"error": type(exc).__name__, "message": str(exc)},
                        attempt=attempt,
                    ),
                )
                if attempt == attempts:
                    raise WorkbenchAccountDiscoveryError(
                        f"workbench account list transport failed after {attempts} attempt(s): {exc}"
                    ) from exc
                real_sleeper(retry_sleep_seconds)
                continue
            _append_audit(
                audit_path,
                _audit_record(
                    url=url,
                    body=body,
                    status_code=response.status_code,
                    response_json=response.json_body,
                    attempt=attempt,
                ),
            )
            if response.status_code not in retry_statuses or attempt == attempts:
                break
            real_sleeper(retry_sleep_seconds)
        if response is None:
            raise WorkbenchAccountDiscoveryError("workbench account discovery received no response")
        data = _validate_response(response)
        pages_seen += 1
        rows = data.get("list") if isinstance(data.get("list"), list) else []
        pagination = data.get("pagination") if isinstance(data.get("pagination"), dict) else {}
        total_count = int(pagination.get("total") or total_count or len(rows))
        rows_received += len(rows)
        reached_threshold = False
        for row in rows:
            if not isinstance(row, dict):
                continue
            account = _account_from_row(row)
            if not account["advertiser_id"]:
                continue
            if allowed_account_ids and account["advertiser_id"] not in allowed_account_ids:
                continue
            if account["stat_cost"] > min_spend:
                accounts.append(account)
            elif stop_at_zero:
                reached_threshold = True
        has_more = bool(pagination.get("hasMore", False)) and not reached_threshold
        offset = int(pagination.get("page") or offset) + 1

    return {
        "enabled": True,
        "source": "workbench_account_list",
        "external_api_calls": transport_calls,
        "active_account_ids": [account["advertiser_id"] for account in accounts],
        "accounts": accounts,
        "summary": {
            "enabled": True,
            "source": "workbench_account_list",
            "target_date": target_date,
            "candidate_account_count": len(allowed_account_ids) if allowed_account_ids else total_count or rows_received,
            "active_account_count": len(accounts),
            "min_spend": float(min_spend),
            "planned_request_count": transport_calls,
            "transport_calls": transport_calls,
            "rows_received": rows_received,
            "total_spend": round(sum(float(account["stat_cost"]) for account in accounts), 2),
        },
    }
