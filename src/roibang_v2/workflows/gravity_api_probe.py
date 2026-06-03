from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from roibang_v2.runs import write_run_artifact

WORKFLOW = "gravity_api_probe"

REQUIRED_AUTH_FIELDS = ("jwt_token", "gravity_cid", "gravity_email", "gravity_id")


def run_gravity_api_probe(*, auth_file: str | Path, runs_dir: str | Path) -> dict[str, Any]:
    auth_path = Path(auth_file)
    blocking_reasons: list[str] = []
    warnings: list[str] = []
    auth_payload = _read_auth(auth_path)
    if auth_payload is None:
        blocking_reasons.append(f"未找到引力 Token 文件：{auth_path}")
        auth_payload = {}
    missing_fields = [field for field in REQUIRED_AUTH_FIELDS if not str(auth_payload.get(field) or "").strip()]
    if missing_fields and not blocking_reasons:
        blocking_reasons.append(f"引力 Token 文件缺少字段：{', '.join(missing_fields)}")
    if str(auth_payload.get("jwt_token") or "").strip():
        warnings.append("已发现本地引力 Token；结果中不会展示 token 明文。")
    if not blocking_reasons:
        warnings.append("v0.2.0 只做本地鉴权文件探测，不上传素材、不创建广告。")

    ok = not blocking_reasons
    payload: dict[str, Any] = {
        "ok": ok,
        "workflow": WORKFLOW,
        "phase": "local_auth_probe",
        "status": "completed" if ok else "blocked",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "execution_enabled": False,
        "external_api_calls": 0,
        "中文摘要": _summary_text(ok=ok, auth_path=auth_path, missing_fields=missing_fields),
        "summary": {
            "auth_file_exists": auth_path.exists(),
            "auth_file": str(auth_path),
            "gravity_cid": str(auth_payload.get("gravity_cid") or ""),
            "gravity_email": str(auth_payload.get("gravity_email") or ""),
            "gravity_id": str(auth_payload.get("gravity_id") or ""),
            "gravity_super": str(auth_payload.get("gravity_super") or "false"),
            "jwt_token_present": bool(str(auth_payload.get("jwt_token") or "").strip()),
            "jwt_token_length": len(str(auth_payload.get("jwt_token") or "")),
            "missing_field_count": len(missing_fields),
        },
        "warnings": warnings,
        "blocking_reasons": blocking_reasons,
        "guardrails": [
            "本探测不上传素材。",
            "本探测不创建广告。",
            "本探测不修改预算、出价或项目状态。",
            "结果中不输出 JWT Token 明文。",
        ],
    }
    payload["artifact_path"] = str(write_run_artifact(runs_dir, WORKFLOW, payload))
    return payload


def _read_auth(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except json.JSONDecodeError as exc:
        return {"_parse_error": str(exc)}
    return value if isinstance(value, dict) else {"_parse_error": "Token 文件不是 JSON 对象"}


def _summary_text(*, ok: bool, auth_path: Path, missing_fields: list[str]) -> str:
    if ok:
        return f"引力素材库本地鉴权探测已完成：{auth_path} 可读取；未执行上传、创建或改投放动作。"
    if missing_fields:
        return f"引力素材库本地鉴权探测被阻止：缺少 {', '.join(missing_fields)}。"
    return f"引力素材库本地鉴权探测被阻止：未找到 {auth_path}。"
