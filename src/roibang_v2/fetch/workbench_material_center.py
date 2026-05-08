from __future__ import annotations

import json
import ssl
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

from roibang_v2.fetch.openapi_http import HttpResponse


class WorkbenchMaterialCenterError(RuntimeError):
    pass


WorkbenchMaterialCenterOpener = Callable[[str, dict[str, Any], dict[str, str], float], HttpResponse]
Sleeper = Callable[[float], None]


DEFAULT_VIDEO_FIELDS = [
    "lego_material_delivery_status",
    "audit_suggestion_level",
    "material_property",
    "ff_see_status",
    "delivery_promotion_cnt",
    "stat_cost",
    "show_cnt",
    "click_cnt",
    "ctr",
    "cpc_platform",
    "cpm_platform",
    "convert_cnt",
    "conversion_cost",
    "conversion_rate",
    "deep_convert_cnt",
    "deep_convert_cost",
    "deep_convert_rate",
    "game_non_standard_v2",
]


def _read_session_file(path: str | Path) -> dict[str, str]:
    if not str(path).strip():
        raise WorkbenchMaterialCenterError("material center sync requires session_file")
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise WorkbenchMaterialCenterError("material center session_file must contain a JSON object")
    cookie = str(payload.get("cookie") or "").strip()
    csrf_token = str(payload.get("csrf_token") or payload.get("csrftoken") or "").strip()
    if not cookie:
        raise WorkbenchMaterialCenterError("material center session_file requires cookie")
    if not csrf_token:
        raise WorkbenchMaterialCenterError("material center session_file requires csrf_token")
    return {"cookie": cookie, "csrf_token": csrf_token}


def _default_opener(
    url: str,
    body: dict[str, Any],
    headers: dict[str, str],
    timeout_seconds: float,
) -> HttpResponse:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    context = None
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


def _headers(session: dict[str, str], config: dict[str, Any], *, advertiser_id: str) -> dict[str, str]:
    headers = {
        "accept": "application/json, text/plain, */*",
        "content-type": "application/json",
        "origin": "https://ad.oceanengine.com",
        "referer": str(
            config.get("referer")
            or f"https://ad.oceanengine.com/material_center/management/video?aadvid={advertiser_id}"
        ),
        "user-agent": str(config.get("user_agent") or "RoiBang-v2 readonly material center sync"),
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


def _body(
    config: dict[str, Any],
    *,
    statistic_start_time: str,
    statistic_end_time: str,
    page: int,
    limit: int,
) -> dict[str, Any]:
    return {
        "fields": list(config.get("fields") or DEFAULT_VIDEO_FIELDS),
        "filter": list(config.get("filter") or []),
        "order": int(config.get("order") or 1),
        "order_field": str(config.get("order_field") or "create_time"),
        "statistic_start_time": statistic_start_time,
        "statistic_end_time": statistic_end_time,
        "page": page,
        "limit": limit,
        "need_summation": bool(config.get("need_summation", False)),
        "scene": str(config.get("scene") or "333430303336343739"),
    }


def _max_pages(config: dict[str, Any]) -> int:
    limits = config.get("limits") if isinstance(config.get("limits"), dict) else {}
    return int(config.get("max_pages") or limits.get("max_pages") or 0)


def _parse_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if " " in text and "T" not in text:
        text = text.replace(" ", "T", 1)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo("Asia/Shanghai"))
    return parsed


def _created_at_range(config: dict[str, Any]) -> tuple[datetime | None, datetime | None]:
    value = config.get("created_at_range") if isinstance(config.get("created_at_range"), dict) else {}
    return _parse_datetime(value.get("start")), _parse_datetime(value.get("end"))


def _row_created_at(row: dict[str, Any]) -> datetime | None:
    return _parse_datetime(row.get("created_at") or row.get("create_time") or row.get("create_date"))


def _row_in_created_at_range(row: dict[str, Any], start: datetime | None, end: datetime | None) -> bool:
    if start is None and end is None:
        return True
    created_at = _row_created_at(row)
    if created_at is None:
        return False
    if start is not None and created_at < start:
        return False
    if end is not None and created_at > end:
        return False
    return True


def _page_reached_before_created_at_range(rows: list[dict[str, Any]], start: datetime | None) -> bool:
    if start is None:
        return False
    dated_rows = [_row_created_at(row) for row in rows]
    return any(created_at is not None and created_at < start for created_at in dated_rows)


def _validate_response(response: HttpResponse) -> dict[str, Any]:
    if response.status_code >= 400:
        raise WorkbenchMaterialCenterError(f"material center video material list failed with HTTP {response.status_code}")
    payload = response.json_body
    code = payload.get("code")
    if code is None:
        base_resp = payload.get("BaseResp") if isinstance(payload.get("BaseResp"), dict) else {}
        code = base_resp.get("StatusCode")
    if int(code or 0) != 0:
        raise WorkbenchMaterialCenterError(f"material center video material list returned code {code}")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise WorkbenchMaterialCenterError("material center video material list missing data object")
    return data


def _materials(data: dict[str, Any]) -> list[dict[str, Any]]:
    rows = data.get("materials")
    if isinstance(rows, list):
        return [row for row in rows if isinstance(row, dict)]
    rows = data.get("list")
    if isinstance(rows, list):
        return [row for row in rows if isinstance(row, dict)]
    return []


def _page_info(data: dict[str, Any]) -> dict[str, Any]:
    value = data.get("page_info")
    if isinstance(value, dict):
        return value
    value = data.get("pagination")
    return value if isinstance(value, dict) else {}


def fetch_video_materials(
    config: dict[str, Any],
    *,
    advertiser_id: str,
    statistic_start_time: str,
    statistic_end_time: str,
    opener: WorkbenchMaterialCenterOpener | None = None,
    sleeper: Sleeper | None = None,
) -> dict[str, Any]:
    if not bool(config.get("enabled", False)):
        raise WorkbenchMaterialCenterError("material center video material list is disabled")

    session = _read_session_file(config.get("session_file") or "")
    base_url = str(
        config.get("url") or "https://ad.oceanengine.com/material_center/api/v1/management/video/material_list"
    )
    url = base_url + "?" + urllib.parse.urlencode({"aadvid": advertiser_id})
    limit = int(config.get("limit") or 100)
    max_pages = _max_pages(config)
    timeout_seconds = float(config.get("timeout_seconds") or 20)
    max_retries = int(config.get("max_retries") or 0)
    retry_sleep_seconds = float(config.get("retry_sleep_seconds") or 1)
    retry_statuses = {int(item) for item in config.get("retry_statuses", [429, 500, 502, 503, 504])}
    audit_dir = Path(config.get("response_audit_dir") or "data/runs/workbench_material_center")
    audit_path = audit_dir / "material_center_video_material_list.jsonl"
    real_opener = opener or _default_opener
    real_sleeper = sleeper or time.sleep

    page = 1
    pages_seen = 0
    has_more = True
    transport_calls = 0
    total_count = 0
    rows_received = 0
    rows_importable = 0
    stopped_by_created_at_range = False
    materials: list[dict[str, Any]] = []
    created_start, created_end = _created_at_range(config)
    stop_when_created_before = bool(config.get("stop_when_created_before_range", False))
    while has_more:
        if max_pages and pages_seen >= max_pages:
            break
        body = _body(
            config,
            statistic_start_time=statistic_start_time,
            statistic_end_time=statistic_end_time,
            page=page,
            limit=limit,
        )
        headers = _headers(session, config, advertiser_id=advertiser_id)
        attempts = max_retries + 1
        response: HttpResponse | None = None
        for attempt in range(1, attempts + 1):
            response = real_opener(url, body, headers, timeout_seconds)
            transport_calls += 1
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
            raise WorkbenchMaterialCenterError("material center video material list received no response")
        data = _validate_response(response)
        page_rows = _materials(data)
        page_info = _page_info(data)
        for row in page_rows:
            if not _row_in_created_at_range(row, created_start, created_end):
                continue
            materials.append({**row, "advertiser_id": advertiser_id, "source_advertiser_id": advertiser_id})
            rows_importable += 1
        rows_received += len(page_rows)
        pages_seen += 1
        total_count = int(page_info.get("total_count") or page_info.get("total") or total_count or rows_received)
        has_more = bool(page_info.get("has_more", page_info.get("hasMore", False)))
        if stop_when_created_before and _page_reached_before_created_at_range(page_rows, created_start):
            stopped_by_created_at_range = True
            has_more = False
        page = int(page_info.get("page") or page) + 1

    return {
        "enabled": True,
        "source": "material_center_video_material_list",
        "external_api_calls": transport_calls,
        "materials": materials,
        "summary": {
            "enabled": True,
            "source": "material_center_video_material_list",
            "advertiser_id": advertiser_id,
            "planned_request_count": transport_calls,
            "transport_calls": transport_calls,
            "rows_received": rows_received,
            "rows_importable": rows_importable,
            "total_count": total_count,
            "stopped_by_created_at_range": stopped_by_created_at_range,
            "statistic_start_time": statistic_start_time,
            "statistic_end_time": statistic_end_time,
        },
    }
