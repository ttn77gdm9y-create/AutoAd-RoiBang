from __future__ import annotations

import json
import os
import ssl
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable


OAUTH_REFRESH_URL = "https://api.oceanengine.com/open_api/oauth2/refresh_token/"
OAUTH_ACCESS_TOKEN_URL = "https://api.oceanengine.com/open_api/oauth2/access_token/"
DEFAULT_USER_ID = "default"


@dataclass(frozen=True)
class TokenSnapshot:
    access_token: str
    refresh_token: str
    expires_at: datetime | None = None
    refresh_token_expires_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True)
class OAuthResponse:
    status_code: int
    json_body: dict[str, Any]


OAuthOpener = Callable[[str, dict[str, Any], float], OAuthResponse]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _iso(value: datetime | None) -> str:
    return value.astimezone(timezone.utc).isoformat() if value else ""


def _load_store(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    if not source.exists():
        return {"version": 1, "tokens": {}}
    with source.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{source} must contain a JSON object")
    data.setdefault("version", 1)
    data.setdefault("tokens", {})
    if not isinstance(data["tokens"], dict):
        raise ValueError(f"{source} tokens must be an object")
    return data


def load_token_snapshot(store_file: str | Path, *, user_id: str = DEFAULT_USER_ID) -> TokenSnapshot:
    store = _load_store(store_file)
    raw = store.get("tokens", {}).get(str(user_id), {})
    if not isinstance(raw, dict):
        raw = {}
    return TokenSnapshot(
        access_token=str(raw.get("access_token") or "").strip(),
        refresh_token=str(raw.get("refresh_token") or "").strip(),
        expires_at=_parse_dt(raw.get("expires_at")),
        refresh_token_expires_at=_parse_dt(raw.get("refresh_token_expires_at")),
        updated_at=_parse_dt(raw.get("updated_at")),
    )


def save_token_snapshot(
    store_file: str | Path,
    snapshot: TokenSnapshot,
    *,
    user_id: str = DEFAULT_USER_ID,
) -> None:
    target = Path(store_file)
    store = _load_store(target)
    store.setdefault("tokens", {})
    store["tokens"][str(user_id)] = {
        "access_token": snapshot.access_token,
        "refresh_token": snapshot.refresh_token,
        "expires_at": _iso(snapshot.expires_at),
        "refresh_token_expires_at": _iso(snapshot.refresh_token_expires_at),
        "updated_at": _iso(snapshot.updated_at),
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(store, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _expires_in(expires_at: datetime | None, *, now: datetime) -> int | None:
    if expires_at is None:
        return None
    return int((expires_at - now).total_seconds())


def _redacted_snapshot(snapshot: TokenSnapshot, *, now: datetime) -> dict[str, Any]:
    return {
        "access_token_present": bool(snapshot.access_token),
        "refresh_token_present": bool(snapshot.refresh_token),
        "expires_at": _iso(snapshot.expires_at),
        "refresh_token_expires_at": _iso(snapshot.refresh_token_expires_at),
        "updated_at": _iso(snapshot.updated_at),
        "expires_in_seconds": _expires_in(snapshot.expires_at, now=now),
        "refresh_token_expires_in_seconds": _expires_in(snapshot.refresh_token_expires_at, now=now),
    }


def token_health(
    store_file: str | Path,
    *,
    user_id: str = DEFAULT_USER_ID,
    now: datetime | None = None,
    refresh_lead_seconds: int = 900,
) -> dict[str, Any]:
    current = now or _utc_now()
    source = Path(store_file)
    if not source.exists():
        return {
            "ok": False,
            "workflow": "oceanengine_token_health",
            "status": "missing_store",
            "store_file": str(source),
            "user_id": user_id,
            "access_token_present": False,
            "refresh_token_present": False,
        }
    snapshot = load_token_snapshot(source, user_id=user_id)
    redacted = _redacted_snapshot(snapshot, now=current)
    if not snapshot.access_token:
        status = "missing_access_token"
    elif snapshot.expires_at and snapshot.expires_at <= current:
        status = "expired"
    elif snapshot.expires_at and snapshot.expires_at <= current + timedelta(seconds=refresh_lead_seconds):
        status = "refresh_due"
    else:
        status = "valid"
    return {
        "ok": status == "valid",
        "workflow": "oceanengine_token_health",
        "status": status,
        "store_file": str(source),
        "user_id": user_id,
        **redacted,
    }


def _default_oauth_opener(url: str, payload: dict[str, Any], timeout_seconds: float) -> OAuthResponse:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    context = None
    if str(os.environ.get("OCEANENGINE_SSL_VERIFY", "true")).strip().lower() in {"0", "false", "no"}:
        context = ssl._create_unverified_context()
    with urllib.request.urlopen(request, timeout=timeout_seconds, context=context) as response:
        text = response.read().decode("utf-8")
        parsed = json.loads(text) if text else {}
        return OAuthResponse(int(response.status), parsed if isinstance(parsed, dict) else {"data": parsed})


def _require_credential(value: str, name: str) -> str:
    cleaned = str(value or "").strip()
    if not cleaned:
        raise RuntimeError(f"OceanEngine token {name} is required")
    return cleaned


def _snapshot_from_oauth_data(
    data: dict[str, Any],
    *,
    fallback_refresh_token: str = "",
    now: datetime,
) -> TokenSnapshot:
    access = str(data.get("access_token") or "").strip()
    refresh = str(data.get("refresh_token") or fallback_refresh_token).strip()
    if not access:
        raise RuntimeError("OceanEngine OAuth response did not include access_token")
    expires_in = data.get("expires_in")
    refresh_expires_in = data.get("refresh_token_expires_in")

    def add_seconds(value: Any) -> datetime | None:
        if value in (None, ""):
            return None
        try:
            return now + timedelta(seconds=int(value))
        except (TypeError, ValueError):
            return None

    return TokenSnapshot(
        access_token=access,
        refresh_token=refresh,
        expires_at=add_seconds(expires_in),
        refresh_token_expires_at=add_seconds(refresh_expires_in),
        updated_at=now,
    )


def _check_oauth_response(response: OAuthResponse) -> dict[str, Any]:
    if response.status_code >= 400:
        raise RuntimeError(f"OceanEngine OAuth request failed with status {response.status_code}")
    body = response.json_body
    if str(body.get("code", "")) not in {"0", ""}:
        raise RuntimeError(f"OceanEngine OAuth error code={body.get('code')} message={body.get('message')}")
    data = body.get("data")
    if not isinstance(data, dict):
        raise RuntimeError("OceanEngine OAuth response missing data object")
    return data


def _result_payload(
    *,
    workflow: str,
    store_file: str | Path,
    user_id: str,
    snapshot: TokenSnapshot,
    now: datetime,
) -> dict[str, Any]:
    return {
        "ok": True,
        "workflow": workflow,
        "phase": "phase1",
        "execution_enabled": False,
        "external_api_calls": 1,
        "store_file": str(store_file),
        "user_id": user_id,
        "token": _redacted_snapshot(snapshot, now=now),
    }


def exchange_auth_code(
    *,
    store_file: str | Path,
    user_id: str = DEFAULT_USER_ID,
    app_id: str,
    app_secret: str,
    auth_code: str,
    opener: OAuthOpener | None = None,
    timeout_seconds: float = 20,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = now or _utc_now()
    payload = {
        "app_id": _require_credential(app_id, "app id"),
        "secret": _require_credential(app_secret, "app secret"),
        "grant_type": "auth_code",
        "auth_code": _require_credential(auth_code, "auth code"),
    }
    real_opener = opener or _default_oauth_opener
    response = real_opener(OAUTH_ACCESS_TOKEN_URL, payload, timeout_seconds)
    snapshot = _snapshot_from_oauth_data(_check_oauth_response(response), now=current)
    save_token_snapshot(store_file, snapshot, user_id=user_id)
    return _result_payload(
        workflow="oceanengine_token_exchange",
        store_file=store_file,
        user_id=user_id,
        snapshot=snapshot,
        now=current,
    )


def refresh_access_token(
    *,
    store_file: str | Path,
    user_id: str = DEFAULT_USER_ID,
    app_id: str,
    app_secret: str,
    opener: OAuthOpener | None = None,
    timeout_seconds: float = 20,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = now or _utc_now()
    existing = load_token_snapshot(store_file, user_id=user_id)
    refresh_token = _require_credential(existing.refresh_token, "refresh_token")
    payload = {
        "app_id": _require_credential(app_id, "app id"),
        "secret": _require_credential(app_secret, "app secret"),
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }
    real_opener = opener or _default_oauth_opener
    response = real_opener(OAUTH_REFRESH_URL, payload, timeout_seconds)
    snapshot = _snapshot_from_oauth_data(
        _check_oauth_response(response),
        fallback_refresh_token=refresh_token,
        now=current,
    )
    save_token_snapshot(store_file, snapshot, user_id=user_id)
    return _result_payload(
        workflow="oceanengine_token_refresh",
        store_file=store_file,
        user_id=user_id,
        snapshot=snapshot,
        now=current,
    )


def get_access_token(
    *,
    store_file: str | Path,
    user_id: str = DEFAULT_USER_ID,
    app_id: str = "",
    app_secret: str = "",
    auto_refresh: bool = False,
    refresh_lead_seconds: int = 900,
    opener: OAuthOpener | None = None,
    timeout_seconds: float = 20,
    now: datetime | None = None,
) -> str:
    current = now or _utc_now()
    snapshot = load_token_snapshot(store_file, user_id=user_id)
    refresh_due = bool(snapshot.expires_at and snapshot.expires_at <= current + timedelta(seconds=refresh_lead_seconds))
    if snapshot.access_token and not refresh_due:
        return snapshot.access_token
    if auto_refresh:
        refresh_access_token(
            store_file=store_file,
            user_id=user_id,
            app_id=app_id,
            app_secret=app_secret,
            opener=opener,
            timeout_seconds=timeout_seconds,
            now=current,
        )
        return load_token_snapshot(store_file, user_id=user_id).access_token
    if snapshot.access_token:
        return snapshot.access_token
    raise RuntimeError("OceanEngine token store does not contain an access_token")
