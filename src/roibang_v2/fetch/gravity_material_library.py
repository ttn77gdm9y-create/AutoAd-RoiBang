from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable

BASE_URL = "https://api-insight.gravity-engine.com"
AUTH_TOKEN_FIELDS = ("authorization", "Authorization", "jwt_token")
RETRY_STATUSES = {429, 500, 502, 503, 504}


class GravityMaterialLibraryError(RuntimeError):
    pass


Sleeper = Callable[[float], None]


def load_gravity_auth_file(path: str | Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise GravityMaterialLibraryError(f"未找到引力 Token 文件：{path}") from exc
    except json.JSONDecodeError as exc:
        raise GravityMaterialLibraryError(f"引力 Token 文件格式错误：{exc}") from exc
    if not isinstance(value, dict):
        raise GravityMaterialLibraryError("引力 Token 文件必须是 JSON 对象")
    return value


def auth_summary(auth_payload: dict[str, Any]) -> dict[str, str]:
    return {
        "gravity_cid": _text(auth_payload.get("gravity_cid")),
        "gravity_email": _text(auth_payload.get("gravity_email")),
        "gravity_id": _text(auth_payload.get("gravity_id")),
        "gravity_super": _text(auth_payload.get("gravity_super") or "false") or "false",
    }


def source_advertiser_id_for_auth(auth_payload: dict[str, Any]) -> str:
    gravity_cid = _text(auth_payload.get("gravity_cid"))
    return f"gravity_engine_{gravity_cid}" if gravity_cid else "gravity_engine"


def validate_gravity_auth(auth_payload: dict[str, Any]) -> list[str]:
    missing = []
    if not _auth_token(auth_payload):
        missing.append("authorization 或 jwt_token")
    for field in ("gravity_cid", "gravity_email", "gravity_id"):
        if not _text(auth_payload.get(field)):
            missing.append(field)
    return missing


class GravityMaterialClient:
    def __init__(
        self,
        auth_payload: dict[str, Any],
        *,
        base_url: str = BASE_URL,
        timeout_seconds: float = 20,
        max_retries: int = 1,
        retry_sleep_seconds: float = 1,
        sleeper: Sleeper | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.retry_sleep_seconds = retry_sleep_seconds
        self.sleeper = sleeper or time.sleep
        self.headers = {
            "Authorization": _authorization_header(auth_payload),
            "gravity_cid": _text(auth_payload.get("gravity_cid")),
            "gravity_email": _text(auth_payload.get("gravity_email")),
            "gravity_id": _text(auth_payload.get("gravity_id")),
            "gravity_super": _text(auth_payload.get("gravity_super") or "false") or "false",
            "Content-Type": "application/json",
        }

    def get_album_tree(self) -> dict[str, Any]:
        return self._request("GET", "/turbo_engine/api/v1/asset/material/album/tree/")

    def get_album_material_list(self, *, album_id: str, page: int, page_size: int, folder_id: str = "") -> dict[str, Any]:
        body = {"album_id": album_id, "page": page, "page_size": page_size}
        if folder_id:
            body["folder_id"] = folder_id
        return self._request("POST", "/turbo_engine/api/v1/asset/material/album/list/", body)

    def get_material_detail(self, *, material_id: str) -> dict[str, Any]:
        query = urllib.parse.urlencode({"material_id": material_id})
        return self._request("GET", f"/turbo_engine/api/v1/asset/material/manage/local/detail/?{query}")

    def get_material_report(self, *, material_ids: list[str], date_from: str, date_to: str, metrics: list[str]) -> dict[str, Any]:
        return self._request(
            "POST",
            "/report/api/v3/datareport/material_get/",
            {
                "material_ids": material_ids,
                "date_from": date_from,
                "date_to": date_to,
                "metrics": metrics,
            },
        )

    def upload_material_to_account(self, *, advertiser_id: str, material_ids: list[str]) -> dict[str, Any]:
        return self._request(
            "POST",
            "/turbo_engine/api/v1/task/bytedance/upload_material/",
            {
                "material_list": [
                    {
                        "advertiser_id": advertiser_id,
                        "material_id_list": material_ids,
                    }
                ]
            },
        )

    def get_upload_material_status(self, *, task_id: str) -> dict[str, Any]:
        query = urllib.parse.urlencode({"task_id": task_id})
        return self._request("GET", f"/turbo_engine/api/v1/task/bytedance/upload_material/status/?{query}")

    def _request(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                return self._request_once(method, path, body)
            except GravityMaterialLibraryError:
                raise
            except urllib.error.HTTPError as exc:
                if exc.code not in RETRY_STATUSES or attempt >= self.max_retries:
                    return _payload_from_http_error(exc)
                last_error = exc
                self.sleeper(self.retry_sleep_seconds)
            except urllib.error.URLError as exc:
                if attempt >= self.max_retries:
                    last_error = exc
                    break
                last_error = exc
                self.sleeper(self.retry_sleep_seconds)
        raise GravityMaterialLibraryError(f"引力素材库只读接口请求失败：{last_error}") from last_error

    def _request_once(self, method: str, path: str, body: dict[str, Any] | None) -> dict[str, Any]:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
        request = urllib.request.Request(f"{self.base_url}{path}", data=data, headers=self.headers, method=method)
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            raw = response.read().decode("utf-8")
        try:
            parsed = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            return {"raw": raw}
        return parsed if isinstance(parsed, dict) else {"data": parsed}


def _payload_from_http_error(exc: urllib.error.HTTPError) -> dict[str, Any]:
    raw = exc.read().decode("utf-8", errors="replace")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {"code": exc.code, "msg": raw, "http_status": exc.code}
    if isinstance(parsed, dict):
        parsed.setdefault("http_status", exc.code)
        return parsed
    return {"code": exc.code, "msg": raw, "http_status": exc.code}


def _auth_token(auth_payload: dict[str, Any]) -> str:
    for field in AUTH_TOKEN_FIELDS:
        token = _text(auth_payload.get(field))
        if token:
            return token
    return ""


def _authorization_header(auth_payload: dict[str, Any]) -> str:
    token = _auth_token(auth_payload)
    if not token:
        return "Bearer "
    if token.lower().startswith("bearer "):
        return token
    return f"Bearer {token}"


def _text(value: Any) -> str:
    return str(value or "").strip()
