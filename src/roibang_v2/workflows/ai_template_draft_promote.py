from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from roibang_v2.config import load_json
from roibang_v2.runs import write_run_artifact

WORKFLOW = "ai_template_draft_promote"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _filename(value: str) -> str:
    text = _text(value).lower()
    text = re.sub(r"[^a-z0-9_\-]+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-_")
    return text or "draft"


def _preview_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if isinstance(payload.get("preview"), dict):
        return dict(payload["preview"])
    raw = payload.get("raw")
    if isinstance(raw, dict) and isinstance(raw.get("preview"), dict):
        return dict(raw["preview"])
    return dict(payload)


def _mode_payload(preview: dict[str, Any]) -> dict[str, Any]:
    value = preview.get("proposed_create_mode")
    return dict(value) if isinstance(value, dict) else {}


def _blocking_reasons(preview: dict[str, Any], mode_payload: dict[str, Any], target_path: Path, *, replace: bool) -> list[str]:
    reasons: list[str] = []
    if _text(preview.get("workflow")) != "ai_template_draft_promotion_preview":
        reasons.append("preview workflow is not ai_template_draft_promotion_preview")
    if _text(preview.get("status")) != "preview_only":
        reasons.append("preview status must be preview_only")
    if bool(preview.get("execution_enabled")):
        reasons.append("preview execution_enabled must be false")
    execution = preview.get("execution") if isinstance(preview.get("execution"), dict) else {}
    if bool(execution.get("enabled")):
        reasons.append("preview execution.enabled must be false")
    if not mode_payload:
        reasons.append("missing proposed_create_mode")
    for field in ["mode_key", "product_key", "product", "template_key"]:
        if not _text(mode_payload.get(field) or preview.get(field)):
            reasons.append(f"missing required field: {field}")
    if target_path.exists() and not replace:
        reasons.append("target already exists")
    return reasons


def _artifact(
    *,
    ok: bool,
    status: str,
    preview_path: Path,
    target_path: Path,
    preview: dict[str, Any],
    blocking_reasons: list[str],
) -> dict[str, Any]:
    product_key = _text(preview.get("product_key"))
    product = _text(preview.get("product"))
    draft_key = _text(preview.get("draft_key"))
    return {
        "ok": ok,
        "workflow": WORKFLOW,
        "phase": "config_promote",
        "execution_enabled": False,
        "external_api_calls": 0,
        "status": status,
        "summary": {
            "title": "AI 模板草稿写入创建模式",
            "中文摘要": f"AI 模板草稿已写入本地创建模式：{product or product_key} / {draft_key}。"
            if ok
            else f"AI 模板草稿未写入创建模式：{product or product_key} / {draft_key}。",
            "product_key": product_key,
            "product": product,
            "draft_key": draft_key,
            "preview_path": str(preview_path),
            "target_path": str(target_path),
            "真实执行": "否",
        },
        "blocking_reasons": blocking_reasons,
        "target_path": str(target_path),
        "preview_path": str(preview_path),
        "actions": [],
        "artifact_path": "",
    }


def _write_artifact(runs_dir: str | Path, payload: dict[str, Any]) -> dict[str, Any]:
    artifact_path = write_run_artifact(runs_dir, WORKFLOW, payload)
    payload["artifact_path"] = str(artifact_path)
    artifact_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def promote_ai_template_draft_preview(
    *,
    preview_path: str | Path,
    mode_dir: str | Path = "configs/create-modes",
    runs_dir: str | Path = "data/runs",
    replace: bool = False,
    expected_product_key: str = "",
) -> dict[str, Any]:
    source = Path(preview_path)
    preview = _preview_payload(load_json(source))
    mode_payload = _mode_payload(preview)
    product_key = _text(mode_payload.get("product_key") or preview.get("product_key"))
    draft_key = _text(mode_payload.get("mode_key") or preview.get("draft_key"))
    if product_key:
        mode_payload["product_key"] = product_key
    if draft_key:
        mode_payload["mode_key"] = draft_key
    target_path = Path(mode_dir) / _filename(product_key) / f"{_filename(draft_key)}.local.json"
    blocking_reasons = _blocking_reasons(preview, mode_payload, target_path, replace=replace)
    expected_product_key_text = _text(expected_product_key)
    if expected_product_key_text and product_key != expected_product_key_text:
        blocking_reasons.append(f"product_key mismatch: expected {expected_product_key_text}, got {product_key}")
    if blocking_reasons:
        return _write_artifact(
            runs_dir,
            _artifact(
                ok=False,
                status="blocked",
                preview_path=source,
                target_path=target_path,
                preview={**preview, "product_key": product_key, "draft_key": draft_key},
                blocking_reasons=blocking_reasons,
            ),
        )

    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(json.dumps(mode_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return _write_artifact(
        runs_dir,
        _artifact(
            ok=True,
            status="promoted",
            preview_path=source,
            target_path=target_path,
            preview={**preview, "product_key": product_key, "draft_key": draft_key},
            blocking_reasons=[],
        ),
    )
