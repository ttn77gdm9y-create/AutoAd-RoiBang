from __future__ import annotations

import json
import os
import base64
from datetime import datetime
from datetime import timezone
from pathlib import Path
from typing import Any, Callable

from roibang_v2.fetch.gravity_material_library import validate_gravity_auth
from roibang_v2.runs import write_run_artifact

WORKFLOW = "gravity_token_refresh"
DEFAULT_LOGIN_URL = "https://web.gravity-engine.com/login"
DEFAULT_CAPTURE_URL = "https://web.gravity-engine.com/material-library"
SECRET_KEYS = {"authorization", "Authorization", "jwt_token", "access_token", "password"}

TokenCollector = Callable[[dict[str, Any]], dict[str, Any]]


def run_gravity_token_refresh(
    request: dict[str, Any],
    *,
    runs_dir: str | Path,
    collector: TokenCollector | None = None,
) -> dict[str, Any]:
    cfg = _cfg(request)
    auth_path = Path(_text(cfg.get("auth_file")) or "data/gravity_token.json")
    username_env = _text(cfg.get("username_env")) or "GRAVITY_USERNAME"
    password_env = _text(cfg.get("password_env")) or "GRAVITY_PASSWORD"
    login_url = _text(cfg.get("login_url")) or DEFAULT_LOGIN_URL
    capture_url = _text(cfg.get("capture_url")) or DEFAULT_CAPTURE_URL
    username = _text(os.environ.get(username_env))
    password = _text(os.environ.get(password_env))

    blocking_reasons: list[str] = []
    warnings = [
        "本任务只获取引力接口 Token，不上传素材、不创建广告、不修改投放。",
        "结果中不会展示 Token、密码或 Authorization 明文。",
    ]
    missing_env = [name for name, value in [(username_env, username), (password_env, password)] if not value]
    if missing_env:
        blocking_reasons.append(f"缺少环境变量：{'、'.join(missing_env)}")

    auth_payload: dict[str, Any] = {}
    if not blocking_reasons:
        try:
            auth_payload = (collector or collect_gravity_token_with_browser)(
                {
                    "username": username,
                    "password": password,
                    "login_url": login_url,
                    "capture_url": capture_url,
                }
            )
        except Exception as exc:  # pragma: no cover - exercised by script/runtime, tests use injected collector.
            blocking_reasons.append(f"引力浏览器登录失败：{exc}")
            auth_payload = {}
        missing_fields = validate_gravity_auth(auth_payload)
        if missing_fields:
            blocking_reasons.append(f"引力 Token 采集结果缺少字段：{', '.join(missing_fields)}")
        if not blocking_reasons:
            auth_path.parent.mkdir(parents=True, exist_ok=True)
            auth_path.write_text(json.dumps(_normalized_auth(auth_payload), ensure_ascii=False, indent=2), encoding="utf-8")

    saved_payload = _read_saved_auth(auth_path) if auth_path.exists() else {}
    token_status = token_status_from_auth(saved_payload or auth_payload)
    ok = not blocking_reasons
    payload: dict[str, Any] = {
        "ok": ok,
        "workflow": WORKFLOW,
        "phase": "token_refresh",
        "status": "completed" if ok else "blocked",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "execution_enabled": False,
        "external_api_calls": 0,
        "中文摘要": (
            f"引力 Token 已写入 {auth_path}；Token 状态：{token_status['label']}。"
            if ok
            else "引力 Token 获取/刷新已被阻止：" + "；".join(blocking_reasons)
        ),
        "summary": {
            "auth_file": str(auth_path),
            "auth_file_exists": auth_path.exists(),
            "auth_field_status": "完整" if ok else "缺失",
            "token_present": bool(_auth_token(saved_payload or auth_payload)),
            "token_status": token_status["status"],
            "token_status_label": token_status["label"],
            "token_expires_at": token_status["expires_at"],
            "token_remaining_seconds": token_status["remaining_seconds"],
            "gravity_cid": _text((saved_payload or auth_payload).get("gravity_cid")),
            "gravity_email": _text((saved_payload or auth_payload).get("gravity_email")),
            "gravity_id": _text((saved_payload or auth_payload).get("gravity_id")),
            "gravity_super": _text((saved_payload or auth_payload).get("gravity_super") or "false") or "false",
            "username_env": username_env,
            "password_env": password_env,
        },
        "table": {
            "columns": ["核验项", "结果", "说明"],
            "rows": [
                {"核验项": "账号环境变量", "结果": "已配置" if username else "缺失", "说明": username_env},
                {"核验项": "密码环境变量", "结果": "已配置" if password else "缺失", "说明": password_env},
                {"核验项": "Token 文件", "结果": "已写入" if auth_path.exists() else "未写入", "说明": str(auth_path)},
                {"核验项": "Token 状态", "结果": token_status["label"], "说明": token_status["expires_at"] or "未解析到有效期"},
            ],
        },
        "warnings": warnings,
        "blocking_reasons": blocking_reasons,
        "guardrails": [
            "不上传素材。",
            "不创建广告。",
            "不修改预算、出价或项目状态。",
            "不在结果中输出 Token、密码或 Authorization 明文。",
        ],
        "raw": {
            "auth_file": str(auth_path),
            "login_url": login_url,
            "capture_url": capture_url,
            "captured_fields": _captured_field_status(saved_payload or auth_payload),
        },
    }
    safe_payload = _redacted(payload)
    safe_payload["artifact_path"] = str(write_run_artifact(runs_dir, WORKFLOW, safe_payload))
    return safe_payload


def collect_gravity_token_with_browser(request: dict[str, Any]) -> dict[str, Any]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover - depends on local runtime.
        raise RuntimeError("缺少 Playwright；请先安装浏览器自动化依赖。") from exc

    username = _text(request.get("username"))
    password = _text(request.get("password"))
    login_url = _text(request.get("login_url")) or DEFAULT_LOGIN_URL
    capture_url = _text(request.get("capture_url")) or DEFAULT_CAPTURE_URL
    auth_info: dict[str, Any] = {}

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()

        def capture(api_request: Any) -> None:
            headers = getattr(api_request, "headers", {}) or {}
            if not _text(headers.get("authorization") or headers.get("Authorization")):
                return
            auth_info["authorization"] = _text(headers.get("authorization") or headers.get("Authorization"))
            for field in ("gravity_cid", "gravity_email", "gravity_id", "gravity_super"):
                if _text(headers.get(field)):
                    auth_info[field] = _text(headers.get(field))

        page.on("request", capture)
        page.goto(login_url, wait_until="domcontentloaded", timeout=30000)
        page.fill('input[name="email"], input[type="email"], input[name="username"]', username)
        page.fill('input[name="password"], input[type="password"]', password)
        page.click('button[type="submit"], button:has-text("登录"), button:has-text("Sign in")')
        page.wait_for_load_state("networkidle", timeout=30000)
        page.goto(capture_url, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(3000)
        browser.close()

    if not _text(auth_info.get("authorization")):
        raise RuntimeError("未能从浏览器请求头提取 authorization")
    auth_info.setdefault("gravity_super", "false")
    return auth_info


def token_status_from_auth(auth_payload: dict[str, Any]) -> dict[str, Any]:
    token = _jwt_token_value(auth_payload)
    if not token:
        return {"status": "missing", "label": "缺失", "expires_at": "", "remaining_seconds": None}
    parts = token.split(".")
    if len(parts) < 2:
        return {"status": "unknown_expiry", "label": "有效期待确认", "expires_at": "", "remaining_seconds": None}
    try:
        payload_segment = parts[1] + "=" * (-len(parts[1]) % 4)
        decoded = base64.urlsafe_b64decode(payload_segment.encode("ascii"))
        jwt_payload = json.loads(decoded.decode("utf-8"))
        exp = int(jwt_payload.get("exp"))
    except (ValueError, TypeError, json.JSONDecodeError, UnicodeDecodeError, base64.binascii.Error):
        return {"status": "unknown_expiry", "label": "有效期待确认", "expires_at": "", "remaining_seconds": None}
    now = int(datetime.now(timezone.utc).timestamp())
    remaining = exp - now
    expires_at = datetime.fromtimestamp(exp, tz=timezone.utc).astimezone().isoformat(timespec="seconds")
    if remaining <= 0:
        return {"status": "expired", "label": "已过期", "expires_at": expires_at, "remaining_seconds": remaining}
    return {"status": "valid", "label": "有效", "expires_at": expires_at, "remaining_seconds": remaining}


def _cfg(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("gravity_token_refresh")
    return dict(value) if isinstance(value, dict) else dict(request)


def _normalized_auth(auth_payload: dict[str, Any]) -> dict[str, str]:
    result = {
        "authorization": _auth_token(auth_payload),
        "gravity_cid": _text(auth_payload.get("gravity_cid")),
        "gravity_email": _text(auth_payload.get("gravity_email")),
        "gravity_id": _text(auth_payload.get("gravity_id")),
        "gravity_super": _text(auth_payload.get("gravity_super") or "false") or "false",
    }
    return result


def _read_saved_auth(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _captured_field_status(auth_payload: dict[str, Any]) -> dict[str, bool]:
    return {
        "authorization": bool(_auth_token(auth_payload)),
        "gravity_cid": bool(_text(auth_payload.get("gravity_cid"))),
        "gravity_email": bool(_text(auth_payload.get("gravity_email"))),
        "gravity_id": bool(_text(auth_payload.get("gravity_id"))),
        "gravity_super": bool(_text(auth_payload.get("gravity_super"))),
    }


def _redacted(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            if str(key) in SECRET_KEYS:
                redacted[key] = "***"
            else:
                redacted[key] = _redacted(item)
        return redacted
    if isinstance(value, list):
        return [_redacted(item) for item in value]
    if isinstance(value, str):
        return value.replace(_text(os.environ.get("GRAVITY_PASSWORD")), "***") if _text(os.environ.get("GRAVITY_PASSWORD")) else value
    return value


def _auth_token(auth_payload: dict[str, Any]) -> str:
    for field in ("authorization", "Authorization", "jwt_token"):
        token = _text(auth_payload.get(field))
        if token:
            return token
    return ""


def _jwt_token_value(auth_payload: dict[str, Any]) -> str:
    token = _auth_token(auth_payload)
    if token.lower().startswith("bearer "):
        return token[7:].strip()
    return token


def _text(value: Any) -> str:
    return str(value or "").strip()
