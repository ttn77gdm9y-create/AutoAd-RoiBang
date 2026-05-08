from __future__ import annotations

import json
import os
import ssl
import time
import urllib.parse
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from roibang_v2.fetch.openapi_readonly import validate_readonly_endpoint
from roibang_v2.integrations.oceanengine.tokens import OAuthOpener, get_access_token


@dataclass(frozen=True)
class HttpResponse:
    status_code: int
    json_body: dict[str, Any]


Opener = Callable[[str, dict[str, str], dict[str, str], float], HttpResponse]
Sleeper = Callable[[float], None]


def _token_from_config(config: dict[str, Any], *, oauth_opener: OAuthOpener | None = None) -> str:
    token_store = config.get("token_store") if isinstance(config.get("token_store"), dict) else {}
    if bool(token_store.get("enabled", False)):
        store_file = str(token_store.get("store_file") or "").strip()
        if not store_file:
            raise RuntimeError("OpenAPI HTTP token_store requires store_file")
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
    token = ""
    if token_env:
        token = os.environ.get(token_env, "").strip()
    if not token and token_file:
        token = Path(token_file).read_text(encoding="utf-8").strip()
    if not token:
        raise RuntimeError("OpenAPI HTTP transport requires token_env or token_file with a non-empty token")
    return token


def _default_opener(
    url: str,
    query_params: dict[str, str],
    headers: dict[str, str],
    timeout_seconds: float,
) -> HttpResponse:
    full_url = url + "?" + urllib.parse.urlencode(query_params)
    request = urllib.request.Request(full_url, headers=headers, method="GET")
    context = None
    if str(os.environ.get("OCEANENGINE_SSL_VERIFY", "true")).strip().lower() in {"0", "false", "no"}:
        context = ssl._create_unverified_context()
    with urllib.request.urlopen(request, timeout=timeout_seconds, context=context) as response:
        body = response.read().decode("utf-8")
        payload = json.loads(body) if body else {}
        return HttpResponse(int(response.status), payload if isinstance(payload, dict) else {"data": payload})


def _audit_record(
    request: dict[str, Any],
    *,
    status_code: int,
    response_json: dict[str, Any],
    attempt: int,
) -> dict[str, Any]:
    return {
        "attempt": attempt,
        "status_code": status_code,
        "request": {
            "endpoint_key": str(request.get("endpoint_key") or ""),
            "method": str(request.get("method") or ""),
            "url": str(request.get("url") or ""),
            "path": str(request.get("path") or ""),
            "headers": {"Access-Token": "<redacted>"},
            "query_params": dict(request.get("query_params") or {}),
        },
        "response_json": response_json,
    }


def _append_audit(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def _should_retry(status_code: int, retry_statuses: set[int]) -> bool:
    return status_code in retry_statuses


def build_http_transport(
    config: dict[str, Any],
    *,
    response_dir: str | Path,
    opener: Opener | None = None,
    oauth_opener: OAuthOpener | None = None,
    sleeper: Sleeper | None = None,
):
    if not bool(config.get("enabled", False)):
        raise RuntimeError("OpenAPI HTTP transport is disabled")
    token = _token_from_config(config, oauth_opener=oauth_opener)
    real_opener = opener or _default_opener
    real_sleeper = sleeper or time.sleep
    timeout_seconds = float(config.get("timeout_seconds") or 20)
    max_retries = int(config.get("max_retries") or 0)
    retry_sleep_seconds = float(config.get("retry_sleep_seconds") or 1)
    min_interval_seconds = float(config.get("min_interval_seconds") or 0)
    retry_statuses = {int(item) for item in config.get("retry_statuses", [429, 500, 502, 503, 504])}
    audit_path = Path(response_dir) / "http_responses.jsonl"
    state = {"called": False}

    def transport(request: dict[str, Any]) -> dict[str, Any]:
        validate_readonly_endpoint(str(request.get("endpoint_key") or ""))
        if str(request.get("method") or "") != "GET":
            raise RuntimeError("OpenAPI HTTP transport only supports GET requests")
        if state["called"] and min_interval_seconds > 0:
            real_sleeper(min_interval_seconds)
        state["called"] = True

        headers = {"Access-Token": token}
        query_params = {str(key): str(value) for key, value in dict(request.get("query_params") or {}).items()}
        attempts = max_retries + 1
        last_response: HttpResponse | None = None
        for attempt in range(1, attempts + 1):
            try:
                response = real_opener(str(request["url"]), query_params, headers, timeout_seconds)
            except (urllib.error.URLError, TimeoutError, ConnectionResetError) as exc:
                _append_audit(
                    audit_path,
                    _audit_record(
                        request,
                        status_code=0,
                        response_json={
                            "error_type": type(exc).__name__,
                            "error": str(exc),
                        },
                        attempt=attempt,
                    ),
                )
                if attempt == attempts:
                    raise RuntimeError(f"OpenAPI HTTP request failed with transient network error: {exc}") from exc
                real_sleeper(retry_sleep_seconds)
                continue
            last_response = response
            _append_audit(
                audit_path,
                _audit_record(
                    request,
                    status_code=response.status_code,
                    response_json=response.json_body,
                    attempt=attempt,
                ),
            )
            if not _should_retry(response.status_code, retry_statuses) or attempt == attempts:
                break
            real_sleeper(retry_sleep_seconds)
        if last_response is None:
            raise RuntimeError("OpenAPI HTTP transport did not receive a response")
        if last_response.status_code >= 400:
            raise RuntimeError(f"OpenAPI HTTP request failed with status {last_response.status_code}")
        return last_response.json_body

    return transport
