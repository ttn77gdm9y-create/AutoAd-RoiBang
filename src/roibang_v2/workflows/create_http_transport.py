from __future__ import annotations

import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable

from roibang_v2.fetch.openapi_http import HttpResponse
from roibang_v2.integrations.oceanengine.tokens import OAuthOpener, get_access_token

CreateOpener = Callable[[str, dict[str, Any], dict[str, str], float, str], HttpResponse]
Sleeper = Callable[[float], None]

CREATE_ENDPOINT_ALLOWLIST = {
    "create_project": "/open_api/v3.0/project/create/",
    "create_unit": "/open_api/v3.0/promotion/create/",
    "bind_material": "/open_api/2/file/material/bind/",
    "lookup_target_material": "/open_api/2/file/video/get/",
    "lookup_existing_project": "/open_api/v3.0/project/list/",
    "lookup_existing_unit": "/open_api/v3.0/promotion/list/",
    "lookup_project_list": "/open_api/v3.0/project/list/",
    "activate_unit": "/open_api/v3.0/promotion/status/update/",
    "lookup_project_schedule": "/open_api/v3.0/project/list/",
    "update_project_week_schedule": "/open_api/v3.0/project/week_schedule/update/",
    "update_project_status": "/open_api/v3.0/project/status/update/",
    "update_project_budget": "/open_api/v3.0/project/budget/update/",
    "update_project_cpa_bid": "/open_api/v3.0/project/cpa_bid/update/",
    "update_project_roi_goal": "/open_api/v3.0/project/roigoal/update/",
    "lookup_disabled_projects": "/open_api/v3.0/project/list/",
    "lookup_project_report": "/open_api/v3.0/report/custom/get/",
    "delete_project": "/open_api/v3.0/project/delete/",
    "handsel_site": "/open_api/2/tools/site/handsel/",
    "read_site": "/open_api/2/tools/site/read/",
    "update_site": "/open_api/2/tools/site/update/",
    "publish_site": "/open_api/2/tools/site/update_status/",
    "update_site_status": "/open_api/2/tools/site/update_status/",
    "create_site_template": "/open_api/2/tools/site_template/create/",
    "get_site_template": "/open_api/2/tools/site_template/get/",
    "create_site_from_template": "/open_api/2/tools/site_template/site/create/",
    "list_wechat_game": "/open_api/v3.0/tools/wechat_game/list/",
}


def _token_from_config(config: dict[str, Any], *, oauth_opener: OAuthOpener | None = None) -> str:
    token_store = config.get("token_store") if isinstance(config.get("token_store"), dict) else {}
    if bool(token_store.get("enabled", False)):
        store_file = str(token_store.get("store_file") or "").strip()
        if not store_file:
            raise RuntimeError("create HTTP transport token_store requires store_file")
        app_id = str(token_store.get("app_id") or "").strip()
        app_secret = str(token_store.get("app_secret") or "").strip()
        credentials_file = str(token_store.get("credentials_file") or "").strip()
        if credentials_file and (not app_id or not app_secret):
            credentials = json.loads(Path(credentials_file).read_text(encoding="utf-8"))
            if not isinstance(credentials, dict):
                raise RuntimeError("create HTTP transport token_store credentials_file must contain a JSON object")
            app_id = app_id or str(credentials.get("app_id") or "").strip()
            app_secret = app_secret or str(credentials.get("app_secret") or "").strip()
        app_id_env = str(token_store.get("app_id_env") or "").strip()
        app_secret_env = str(token_store.get("app_secret_env") or "").strip()
        if not app_id and app_id_env:
            app_id = os.environ.get(app_id_env, "").strip()
        if not app_secret and app_secret_env:
            app_secret = os.environ.get(app_secret_env, "").strip()
        return get_access_token(
            store_file=store_file,
            user_id=str(token_store.get("user_id") or "default"),
            app_id=app_id,
            app_secret=app_secret,
            auto_refresh=bool(token_store.get("auto_refresh", False)),
            refresh_lead_seconds=int(token_store.get("refresh_lead_seconds") or 900),
            opener=oauth_opener,
            timeout_seconds=float(token_store.get("timeout_seconds") or config.get("timeout_seconds") or 20),
        )
    token_env = str(config.get("token_env") or "").strip()
    token_file = str(config.get("token_file") or "").strip()
    token = os.environ.get(token_env, "").strip() if token_env else ""
    if not token and token_file:
        token = Path(token_file).read_text(encoding="utf-8").strip()
    if not token:
        raise RuntimeError("create HTTP transport requires token_env or token_file with a non-empty token")
    return token


def _default_opener(
    url: str,
    body: dict[str, Any],
    headers: dict[str, str],
    timeout_seconds: float,
    method: str = "POST",
) -> HttpResponse:
    encoded_body = (
        None
        if method == "GET"
        else json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    )
    request = urllib.request.Request(url, data=encoded_body, headers=headers, method=method)
    context = None
    if str(os.environ.get("OCEANENGINE_SSL_VERIFY", "true")).strip().lower() in {"0", "false", "no"}:
        context = ssl._create_unverified_context()
    with urllib.request.urlopen(request, timeout=timeout_seconds, context=context) as response:
        raw_body = response.read().decode("utf-8")
        payload = json.loads(raw_body) if raw_body else {}
        return HttpResponse(int(response.status), payload if isinstance(payload, dict) else {"data": payload})


def _normalize_base_url(config: dict[str, Any]) -> str:
    return str(config.get("base_url") or "https://api.oceanengine.com").rstrip("/")


def _validate_config(config: dict[str, Any]) -> None:
    if not bool(config.get("enabled", False)):
        raise RuntimeError("create HTTP transport is disabled")
    if not bool(config.get("allow_mutation", False)):
        raise RuntimeError("create HTTP transport requires allow_mutation=true")
    if not str(config.get("run_id") or "").strip():
        raise RuntimeError("create HTTP transport requires run_id")


def _validate_request(request: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
    operation = str(request.get("operation") or "")
    endpoint = str(request.get("endpoint") or "")
    if operation not in CREATE_ENDPOINT_ALLOWLIST:
        raise RuntimeError(f"{operation} is not in create endpoint allowlist")
    expected_endpoint = CREATE_ENDPOINT_ALLOWLIST[operation]
    if endpoint != expected_endpoint:
        raise RuntimeError(f"{endpoint} does not match operation {operation}")
    payload = request.get("payload") if isinstance(request.get("payload"), dict) else {}
    return operation, endpoint, payload


def _lookup_target_material_payload(payload: dict[str, Any]) -> dict[str, Any]:
    advertiser_id = str(payload.get("advertiser_id") or payload.get("target_advertiser_id") or "").strip()
    material_id = str(payload.get("material_id") or "").strip()
    material_ids = payload.get("material_ids") if isinstance(payload.get("material_ids"), list) else []
    source_video_id = str(payload.get("source_video_id") or "").strip()
    filtering: dict[str, Any] = {}
    if material_ids:
        filtering["material_ids"] = [
            int(item) if str(item).isdigit() else str(item)
            for item in material_ids
            if str(item).strip()
        ]
    elif material_id:
        filtering["material_ids"] = [int(material_id)] if material_id.isdigit() else [material_id]
    elif source_video_id:
        filtering["video_ids"] = [source_video_id]
    requested_page_size = int(payload.get("page_size") or 0)
    expected_row_count = max(
        len(filtering.get("material_ids") or []),
        len(filtering.get("video_ids") or []),
        10,
    )
    return {
        "advertiser_id": advertiser_id,
        "filtering": filtering,
        "page": int(payload.get("page") or 1),
        "page_size": max(requested_page_size, expected_row_count),
    }


def _request_method(operation: str) -> str:
    return (
        "GET"
        if operation
        in {
            "lookup_target_material",
            "lookup_existing_project",
            "lookup_existing_unit",
            "lookup_project_list",
            "lookup_project_schedule",
            "lookup_disabled_projects",
            "lookup_project_report",
            "read_site",
            "get_site_template",
            "list_wechat_game",
        }
        else "POST"
    )


def _wire_payload(operation: str, payload: dict[str, Any]) -> dict[str, Any]:
    if operation == "lookup_target_material":
        return _lookup_target_material_payload(payload)
    if operation == "lookup_existing_project":
        return {
            "advertiser_id": str(payload.get("advertiser_id") or "").strip(),
            "filtering": {"name": str(payload.get("name") or "")},
            "page": int(payload.get("page") or 1),
            "page_size": int(payload.get("page_size") or 20),
        }
    if operation == "lookup_existing_unit":
        filtering: dict[str, Any] = {"name": str(payload.get("name") or "")}
        project_id = str(payload.get("project_id") or "").strip()
        if project_id:
            filtering["project_id"] = int(project_id) if project_id.isdigit() else project_id
        return {
            "advertiser_id": str(payload.get("advertiser_id") or "").strip(),
            "filtering": filtering,
            "page": int(payload.get("page") or 1),
            "page_size": int(payload.get("page_size") or 20),
        }
    if operation == "lookup_disabled_projects":
        filtering = payload.get("filtering") if isinstance(payload.get("filtering"), dict) else {}
        if not filtering:
            filtering = {"project_status": ["PROJECT_STATUS_DISABLE"]}
        return {
            "advertiser_id": str(payload.get("advertiser_id") or "").strip(),
            "filtering": filtering,
            "page": int(payload.get("page") or 1),
            "page_size": int(payload.get("page_size") or 100),
        }
    return payload


def _url_with_query(url: str, payload: dict[str, Any]) -> str:
    query = urllib.parse.urlencode(
        {
            key: value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, separators=(",", ":"))
            for key, value in payload.items()
        }
    )
    return f"{url}?{query}" if query else url


def _audit_record(
    *,
    request: dict[str, Any],
    url: str,
    headers: dict[str, str],
    status_code: int,
    response_json: dict[str, Any],
    run_id: str,
    operator: str,
    attempt: int = 1,
) -> dict[str, Any]:
    method = str(request.get("method") or _request_method(str(request.get("operation") or "")))
    return {
        "attempt": attempt,
        "request": {
            "operation": str(request.get("operation") or ""),
            "method": method,
            "url": url,
            "endpoint": str(request.get("endpoint") or ""),
            "headers": {
                key: "<redacted>" if key.lower() == "access-token" else value
                for key, value in headers.items()
            },
            "payload": request.get("payload") if isinstance(request.get("payload"), dict) else {},
        },
        "run": {
            "run_id": run_id,
            "operator": operator,
        },
        "status_code": status_code,
        "response_json": response_json,
    }


def _append_audit(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def _http_error_json(exc: urllib.error.HTTPError) -> dict[str, Any]:
    try:
        raw_body = exc.read().decode("utf-8")
    except Exception:
        raw_body = ""
    parsed: Any = {}
    if raw_body:
        try:
            parsed = json.loads(raw_body)
        except json.JSONDecodeError:
            parsed = {"raw_body": raw_body}
    if not isinstance(parsed, dict):
        parsed = {"data": parsed}
    parsed.setdefault("code", int(exc.code))
    parsed.setdefault("message", str(exc))
    parsed.setdefault("error_type", "HTTPError")
    return parsed


def _retry_api_codes(config: dict[str, Any], operation: str) -> set[int]:
    retry_by_operation = config.get("retry_api_codes_by_operation")
    values: list[Any] = []
    if isinstance(retry_by_operation, dict):
        operation_values = retry_by_operation.get(operation)
        if isinstance(operation_values, list):
            values.extend(operation_values)
    global_values = config.get("retry_api_codes")
    if isinstance(global_values, list):
        values.extend(global_values)
    codes: set[int] = set()
    for value in values:
        try:
            codes.add(int(value))
        except (TypeError, ValueError):
            continue
    return codes


def _should_retry_api_code(response_json: dict[str, Any], retry_codes: set[int]) -> bool:
    if not retry_codes:
        return False
    try:
        code = int(response_json.get("code", 0))
    except (TypeError, ValueError):
        return False
    return code in retry_codes


def _retry_transient_operations(config: dict[str, Any]) -> set[str]:
    values = config.get("retry_transient_operations")
    if not isinstance(values, list):
        return set()
    return {str(item) for item in values if str(item) in CREATE_ENDPOINT_ALLOWLIST}


def _retry_sleep_seconds(config: dict[str, Any], operation: str) -> float:
    by_operation = config.get("retry_sleep_seconds_by_operation")
    if isinstance(by_operation, dict) and operation in by_operation:
        try:
            return float(by_operation[operation])
        except (TypeError, ValueError):
            return 0
    return float(config.get("retry_sleep_seconds") or 1)


def _min_interval_seconds(config: dict[str, Any], operation: str) -> float:
    by_operation = config.get("min_interval_seconds_by_operation")
    if isinstance(by_operation, dict) and operation in by_operation:
        try:
            return float(by_operation[operation])
        except (TypeError, ValueError):
            return 0
    return float(config.get("min_interval_seconds") or 0)


def _log_retry_to_stderr(
    config: dict[str, Any],
    *,
    operation: str,
    attempt: int,
    attempts: int,
    sleep_seconds: float,
    reason: str,
) -> None:
    if not bool(config.get("log_retries_to_stderr", False)):
        return
    print(
        "[create_http_transport] "
        f"retry operation={operation} attempt={attempt}/{attempts} "
        f"sleep_seconds={sleep_seconds:g} reason={reason}",
        file=sys.stderr,
        flush=True,
    )


def build_create_http_transport(
    config: dict[str, Any],
    *,
    response_dir: str | Path,
    opener: CreateOpener | None = None,
    oauth_opener: OAuthOpener | None = None,
    sleeper: Sleeper | None = None,
):
    _validate_config(config)
    token = _token_from_config(config, oauth_opener=oauth_opener)
    real_opener = opener or _default_opener
    real_sleeper = sleeper or time.sleep
    timeout_seconds = float(config.get("timeout_seconds") or 20)
    max_retries = int(config.get("max_retries") or 0)
    base_url = _normalize_base_url(config)
    audit_path = Path(response_dir) / "create_http_responses.jsonl"
    run_id = str(config.get("run_id") or "").strip()
    operator = str(config.get("operator") or "").strip()
    state = {"called": False}

    def transport(request: dict[str, Any]) -> dict[str, Any]:
        operation, endpoint, payload = _validate_request(request)
        method = _request_method(operation)
        wire_payload = _wire_payload(operation, payload)
        url = f"{base_url}{endpoint}"
        if method == "GET":
            url = _url_with_query(url, wire_payload)
        headers = {
            "Access-Token": token,
            "Content-Type": "application/json",
        }
        min_interval_seconds = _min_interval_seconds(config, operation)
        if state["called"] and min_interval_seconds > 0:
            real_sleeper(min_interval_seconds)
        state["called"] = True

        retry_codes = _retry_api_codes(config, operation)
        retry_transient_operations = _retry_transient_operations(config)
        retry_sleep_seconds = _retry_sleep_seconds(config, operation)
        attempts = max_retries + 1
        response_json: dict[str, Any] | None = None
        for attempt in range(1, attempts + 1):
            status_code = 0
            try:
                response = real_opener(url, wire_payload, headers, timeout_seconds, method)
                status_code = response.status_code
                response_json = response.json_body
            except urllib.error.HTTPError as exc:
                status_code = int(exc.code)
                response_json = _http_error_json(exc)
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                response_json = {"error_type": type(exc).__name__, "error": str(exc)}
                _append_audit(
                    audit_path,
                    _audit_record(
                        request=request,
                        url=url,
                        headers=headers,
                        status_code=0,
                        response_json=response_json,
                        run_id=run_id,
                        operator=operator,
                        attempt=attempt,
                    ),
                )
                if operation in retry_transient_operations and attempt < attempts:
                    _log_retry_to_stderr(
                        config,
                        operation=operation,
                        attempt=attempt,
                        attempts=attempts,
                        sleep_seconds=retry_sleep_seconds,
                        reason=type(exc).__name__,
                    )
                    real_sleeper(retry_sleep_seconds)
                    continue
                raise RuntimeError(f"create HTTP request failed with transient network error: {exc}") from exc
            _append_audit(
                audit_path,
                _audit_record(
                    request=request,
                    url=url,
                    headers=headers,
                    status_code=status_code,
                    response_json=response_json,
                    run_id=run_id,
                    operator=operator,
                    attempt=attempt,
                ),
            )
            if not _should_retry_api_code(response_json, retry_codes) or attempt == attempts:
                break
            _log_retry_to_stderr(
                config,
                operation=operation,
                attempt=attempt,
                attempts=attempts,
                sleep_seconds=retry_sleep_seconds,
                reason=f"api_code={response_json.get('code')}",
            )
            real_sleeper(retry_sleep_seconds)
        if response_json is None:
            raise RuntimeError("create HTTP transport did not receive a response")
        return response_json

    return transport
