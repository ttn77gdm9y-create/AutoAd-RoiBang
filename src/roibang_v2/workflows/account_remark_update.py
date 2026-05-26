from __future__ import annotations

import json
import ssl
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

from roibang_v2.fetch.openapi_http import HttpResponse
from roibang_v2.runs import write_run_artifact

WORKFLOW = "account_remark_update"
DEFAULT_ACCOUNT_REMARK_URL = (
    "https://business.oceanengine.com/api/ebp/promotion/common/edit_account_remark?ebpid=1851650746645060"
)
Opener = Callable[[str, dict[str, Any], dict[str, str], float], HttpResponse]
Sleeper = Callable[[float], None]


def _text(value: Any) -> str:
    return str(value or "").strip()


def _rows(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    seen: set[str] = set()
    rows: list[str] = []
    for item in value:
        text = _text(item)
        if text and text not in seen:
            seen.add(text)
            rows.append(text)
    return rows


def _unwrap(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("account_remark_update")
    return dict(value) if isinstance(value, dict) else dict(request)


def build_account_remark_update_config(
    *,
    update_id: str,
    advertiser_ids: list[str],
    remark: str,
) -> dict[str, Any]:
    return {
        "account_remark_update": {
            "update_id": _text(update_id),
            "remark": _text(remark),
            "advertiser_ids": _rows(advertiser_ids),
            "http": {
                "enabled": False,
                "url": DEFAULT_ACCOUNT_REMARK_URL,
                "method": "POST",
                "session_file": "data/secrets/workbench-session.local.json",
                "body_template": {
                    "accountId": "__ADVERTISER_ID__",
                    "remark": "__REMARK__",
                },
                "success_code_field": "code",
                "success_code": 0,
                "timeout_seconds": 20,
                "max_retries": 1,
                "retry_sleep_seconds": 1,
            },
        }
    }


def _session(http: dict[str, Any]) -> dict[str, str]:
    inline = http.get("session") if isinstance(http.get("session"), dict) else {}
    cookie = _text(inline.get("cookie"))
    csrf_token = _text(inline.get("csrf_token") or inline.get("csrftoken"))
    if cookie and csrf_token:
        return {"cookie": cookie, "csrf_token": csrf_token}
    session_file = _text(http.get("session_file"))
    if not session_file:
        return {"cookie": "", "csrf_token": ""}
    try:
        payload = json.loads(Path(session_file).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"cookie": "", "csrf_token": ""}
    if not isinstance(payload, dict):
        return {"cookie": "", "csrf_token": ""}
    return {
        "cookie": _text(payload.get("cookie")),
        "csrf_token": _text(payload.get("csrf_token") or payload.get("csrftoken")),
    }


def _headers(http: dict[str, Any]) -> dict[str, str]:
    session = _session(http)
    headers = {
        "accept": "application/json, text/plain, */*",
        "content-type": "application/json",
        "origin": "https://business.oceanengine.com",
        "referer": _text(http.get("referer")) or "https://business.oceanengine.com/",
        "user-agent": _text(http.get("user_agent")) or "RoiBang-v2 account remark update",
        "Cookie": session["cookie"],
        "x-csrftoken": session["csrf_token"],
    }
    extra = http.get("headers") if isinstance(http.get("headers"), dict) else {}
    for key, value in extra.items():
        if str(key).lower() in {"cookie", "x-csrftoken", "x-csrf-token"}:
            continue
        headers[str(key)] = str(value)
    return headers


def _render_template(value: Any, *, advertiser_id: str, remark: str) -> Any:
    if isinstance(value, dict):
        return {str(key): _render_template(item, advertiser_id=advertiser_id, remark=remark) for key, item in value.items()}
    if isinstance(value, list):
        return [_render_template(item, advertiser_id=advertiser_id, remark=remark) for item in value]
    if isinstance(value, str):
        return value.replace("__ADVERTISER_ID__", advertiser_id).replace("__REMARK__", remark)
    return value


def _body(http: dict[str, Any], *, advertiser_id: str, remark: str) -> dict[str, Any]:
    template = http.get("body_template") if isinstance(http.get("body_template"), dict) else {}
    if not template:
        template = {"accountId": "__ADVERTISER_ID__", "remark": "__REMARK__"}
    body = _render_template(template, advertiser_id=advertiser_id, remark=remark)
    return dict(body) if isinstance(body, dict) else {}


def _default_opener(url: str, body: dict[str, Any], headers: dict[str, str], timeout_seconds: float) -> HttpResponse:
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


def _api_ok(response: dict[str, Any], http: dict[str, Any]) -> bool:
    field = _text(http.get("success_code_field")) or "code"
    expected = http.get("success_code", 0)
    return str(response.get(field, 0)) == str(expected)


def _blocking_reasons(cfg: dict[str, Any], *, execute: bool) -> list[str]:
    reasons: list[str] = []
    if not _text(cfg.get("update_id")):
        reasons.append("update_id is required")
    if not _text(cfg.get("remark")):
        reasons.append("remark is required")
    if not _rows(cfg.get("advertiser_ids")):
        reasons.append("advertiser_ids is required")
    http = cfg.get("http") if isinstance(cfg.get("http"), dict) else {}
    if execute:
        if not bool(http.get("enabled", False)):
            reasons.append("http.enabled must be true for execute")
        if not _text(http.get("url")):
            reasons.append("http.url is required for execute")
        session = _session(http)
        if not _text(session.get("cookie")):
            reasons.append("workbench session cookie is required for execute")
        if not _text(session.get("csrf_token")):
            reasons.append("workbench csrf_token is required for execute")
    return reasons


def _readable_reference(cfg: dict[str, Any], *, results: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    accounts = [
        {
            "advertiser_id": advertiser_id,
            "target_remark": _text(cfg.get("remark")),
        }
        for advertiser_id in _rows(cfg.get("advertiser_ids"))
    ]
    return {
        "update_id": _text(cfg.get("update_id")),
        "remark": _text(cfg.get("remark")),
        "account_count": len(accounts),
        "accounts": accounts[:100],
        "results": list(results or []),
    }


def _write_artifact(runs_dir: str | Path, payload: dict[str, Any]) -> dict[str, Any]:
    artifact_path = write_run_artifact(runs_dir, WORKFLOW, payload)
    payload["artifact_path"] = str(artifact_path)
    artifact_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def _base_payload(
    cfg: dict[str, Any],
    *,
    status: str,
    ok: bool,
    execute: bool,
    blocking_reasons: list[str],
    external_api_calls: int,
    results: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    result_rows = list(results or [])
    success_count = sum(1 for row in result_rows if bool(row.get("ok", False)))
    failed_count = sum(1 for row in result_rows if not bool(row.get("ok", False)))
    return {
        "ok": ok,
        "workflow": WORKFLOW,
        "phase": "account_management",
        "status": status,
        "execution_enabled": bool(execute and not blocking_reasons),
        "external_api_calls": external_api_calls,
        "summary": {
            "update_id": _text(cfg.get("update_id")),
            "remark": _text(cfg.get("remark")),
            "account_count": len(_rows(cfg.get("advertiser_ids"))),
            "success_count": success_count,
            "failed_count": failed_count,
        },
        "blocking_reasons": blocking_reasons,
        "results": result_rows,
        "readable_reference": _readable_reference(cfg, results=result_rows),
        "artifact_path": "",
    }


def run_account_remark_update(
    request: dict[str, Any],
    *,
    runs_dir: str | Path = "data/runs",
    execute: bool = False,
    opener: Opener | None = None,
    sleeper: Sleeper | None = None,
) -> dict[str, Any]:
    cfg = _unwrap(request)
    reasons = _blocking_reasons(cfg, execute=execute)
    if reasons:
        return _write_artifact(
            runs_dir,
            _base_payload(
                cfg,
                status="blocked",
                ok=False,
                execute=execute,
                blocking_reasons=reasons,
                external_api_calls=0,
            ),
        )
    if not execute:
        return _write_artifact(
            runs_dir,
            _base_payload(
                cfg,
                status="preview_ready",
                ok=True,
                execute=False,
                blocking_reasons=[],
                external_api_calls=0,
            ),
        )

    http = cfg.get("http") if isinstance(cfg.get("http"), dict) else {}
    real_opener = opener or _default_opener
    real_sleeper = sleeper or time.sleep
    url = _text(http.get("url"))
    headers = _headers(http)
    timeout_seconds = float(http.get("timeout_seconds") or 20)
    max_retries = int(http.get("max_retries") or 0)
    retry_sleep_seconds = float(http.get("retry_sleep_seconds") or 1)
    external_api_calls = 0
    results: list[dict[str, Any]] = []
    for advertiser_id in _rows(cfg.get("advertiser_ids")):
        body = _body(http, advertiser_id=advertiser_id, remark=_text(cfg.get("remark")))
        response: HttpResponse | None = None
        error = ""
        for attempt in range(1, max_retries + 2):
            external_api_calls += 1
            try:
                response = real_opener(url, body, headers, timeout_seconds)
                break
            except (OSError, TimeoutError, urllib.error.URLError) as exc:
                error = f"{type(exc).__name__}: {exc}"
                if attempt <= max_retries:
                    real_sleeper(retry_sleep_seconds)
        if response is None:
            results.append({"advertiser_id": advertiser_id, "ok": False, "error": error})
            continue
        response_ok = response.status_code < 400 and _api_ok(response.json_body, http)
        results.append(
            {
                "advertiser_id": advertiser_id,
                "ok": response_ok,
                "status_code": response.status_code,
                "code": response.json_body.get(_text(http.get("success_code_field")) or "code"),
                "message": _text(response.json_body.get("message") or response.json_body.get("msg")),
            }
        )
    failed_count = sum(1 for row in results if not bool(row.get("ok", False)))
    return _write_artifact(
        runs_dir,
        _base_payload(
            cfg,
            status="executed" if failed_count == 0 else "partial_failed",
            ok=failed_count == 0,
            execute=True,
            blocking_reasons=[],
            external_api_calls=external_api_calls,
            results=results,
        ),
    )
