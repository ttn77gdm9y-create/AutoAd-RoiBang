from __future__ import annotations

import json
import os
import ssl
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable

from roibang_v2.fetch.openapi_http import HttpResponse
from roibang_v2.integrations.oceanengine.tokens import OAuthOpener, get_access_token

CreateOpener = Callable[[str, dict[str, Any], dict[str, str], float, str], HttpResponse]

CREATE_ENDPOINT_ALLOWLIST = {
    "create_project": "/open_api/2/project/create/",
    "create_unit": "/open_api/2/promotion/create/",
    "bind_material": "/open_api/2/file/material/bind/",
    "lookup_target_material": "/open_api/2/file/video/get/",
}


def _token_from_config(config: dict[str, Any], *, oauth_opener: OAuthOpener | None = None) -> str:
    token_store = config.get("token_store") if isinstance(config.get("token_store"), dict) else {}
    if bool(token_store.get("enabled", False)):
        store_file = str(token_store.get("store_file") or "").strip()
        if not store_file:
            raise RuntimeError("create HTTP transport token_store requires store_file")
        app_id = str(token_store.get("app_id") or "").strip()
        app_secret = str(token_store.get("app_secret") or "").strip()
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
    if not str(config.get("approval_id") or "").strip():
        raise RuntimeError("create HTTP transport requires approval_id")


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
    source_video_id = str(payload.get("source_video_id") or "").strip()
    filtering: dict[str, Any] = {}
    if material_id:
        filtering["material_ids"] = [material_id]
    elif source_video_id:
        filtering["video_ids"] = [source_video_id]
    return {
        "advertiser_id": advertiser_id,
        "filtering": filtering,
        "page": int(payload.get("page") or 1),
        "page_size": int(payload.get("page_size") or 10),
    }


def _request_method(operation: str) -> str:
    return "GET" if operation == "lookup_target_material" else "POST"


def _wire_payload(operation: str, payload: dict[str, Any]) -> dict[str, Any]:
    if operation == "lookup_target_material":
        return _lookup_target_material_payload(payload)
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
    approval_id: str,
    approved_by: str,
) -> dict[str, Any]:
    method = str(request.get("method") or _request_method(str(request.get("operation") or "")))
    return {
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
        "approval": {
            "approval_id": approval_id,
            "approved_by": approved_by,
        },
        "status_code": status_code,
        "response_json": response_json,
    }


def _append_audit(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def build_create_http_transport(
    config: dict[str, Any],
    *,
    response_dir: str | Path,
    opener: CreateOpener | None = None,
    oauth_opener: OAuthOpener | None = None,
):
    _validate_config(config)
    token = _token_from_config(config, oauth_opener=oauth_opener)
    real_opener = opener or _default_opener
    timeout_seconds = float(config.get("timeout_seconds") or 20)
    base_url = _normalize_base_url(config)
    audit_path = Path(response_dir) / "create_http_responses.jsonl"
    approval_id = str(config.get("approval_id") or "").strip()
    approved_by = str(config.get("approved_by") or "").strip()

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
        try:
            response = real_opener(url, wire_payload, headers, timeout_seconds, method)
        except (urllib.error.URLError, TimeoutError, ConnectionResetError) as exc:
            response_json = {"error_type": type(exc).__name__, "error": str(exc)}
            _append_audit(
                audit_path,
                _audit_record(
                    request=request,
                    url=url,
                    headers=headers,
                    status_code=0,
                    response_json=response_json,
                    approval_id=approval_id,
                    approved_by=approved_by,
                ),
            )
            raise RuntimeError(f"create HTTP request failed with transient network error: {exc}") from exc
        _append_audit(
            audit_path,
            _audit_record(
                request=request,
                url=url,
                headers=headers,
                status_code=response.status_code,
                response_json=response.json_body,
                approval_id=approval_id,
                approved_by=approved_by,
            ),
        )
        if response.status_code >= 400:
            raise RuntimeError(f"create HTTP request failed with status {response.status_code}")
        return response.json_body

    return transport
