from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from roibang_v2.config import load_json
from roibang_v2.runs import write_run_artifact

WORKFLOW = "product_config_publish"

REQUIRED_PRODUCT_FIELDS = [
    "product_key",
    "product",
    "platform",
    "source_advertiser_id",
    "organization_id",
    "foundation.effective_touch_url",
    "foundation.anchor_id",
    "foundation.anchor_type",
    "foundation.anchor_related_type",
    "foundation.landing_url",
    "foundation.product_image_id",
    "foundation.fixed_video_cover_id",
    "foundation.micro_app_instance_id",
    "foundation.micro_promotion_type",
]


def _text(value: Any) -> str:
    return str(value or "").strip()


def _filename(value: str) -> str:
    text = _text(value).lower()
    text = re.sub(r"[^a-z0-9_\-]+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-_")
    return text or "product"


def product_config_missing_fields(product_config: dict[str, Any]) -> list[str]:
    foundation = product_config.get("foundation") if isinstance(product_config.get("foundation"), dict) else {}
    missing: list[str] = []
    for field in REQUIRED_PRODUCT_FIELDS:
        if field.startswith("foundation."):
            value = foundation.get(field.split(".", 1)[1])
        else:
            value = product_config.get(field)
        if not _text(value):
            missing.append(field)
    return missing


def _sanitized_product(product_config: dict[str, Any]) -> dict[str, Any]:
    payload = dict(product_config)
    payload.pop("draft", None)
    payload.pop("artifact_path", None)
    return payload


def _readable_reference(product_config: dict[str, Any], *, target_path: Path) -> dict[str, Any]:
    foundation = product_config.get("foundation") if isinstance(product_config.get("foundation"), dict) else {}
    return {
        "product": {
            "product_key": _text(product_config.get("product_key")),
            "product": _text(product_config.get("product")),
            "platform": _text(product_config.get("platform")),
            "source_advertiser_id": _text(product_config.get("source_advertiser_id")),
            "organization_id": _text(product_config.get("organization_id")),
            "allowed_target_accounts_path": _text(product_config.get("allowed_target_accounts_path")),
            "account_remark_pattern": _text(product_config.get("account_remark_pattern")),
            "target_path": str(target_path),
        },
        "foundation": {
            "effective_touch_url": _text(foundation.get("effective_touch_url")),
            "anchor_id": _text(foundation.get("anchor_id")),
            "landing_url": _text(foundation.get("landing_url")),
            "product_image_id": _text(foundation.get("product_image_id")),
            "fixed_video_cover_id": _text(foundation.get("fixed_video_cover_id")),
            "micro_app_instance_id": _text(foundation.get("micro_app_instance_id")),
        },
        "next_step": "创建模式可通过 product_key 读取该产品配置；真实创建仍走固定创建脚本。",
    }


def _artifact(
    *,
    ok: bool,
    status: str,
    draft_path: Path,
    target_path: Path,
    product_config: dict[str, Any],
    blocking_reasons: list[str],
) -> dict[str, Any]:
    missing = product_config_missing_fields(product_config)
    return {
        "ok": ok,
        "workflow": WORKFLOW,
        "phase": "config_publish",
        "execution_enabled": False,
        "external_api_calls": 0,
        "status": status,
        "summary": {
            "product_key": _text(product_config.get("product_key")),
            "product": _text(product_config.get("product")),
            "draft_path": str(draft_path),
            "target_path": str(target_path),
            "missing_field_count": len(missing),
        },
        "blocking_reasons": blocking_reasons,
        "readable_reference": _readable_reference(product_config, target_path=target_path),
        "artifact_path": "",
    }


def _write_artifact(runs_dir: str | Path, payload: dict[str, Any]) -> dict[str, Any]:
    artifact_path = write_run_artifact(runs_dir, WORKFLOW, payload)
    payload["artifact_path"] = str(artifact_path)
    artifact_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def publish_product_config_draft(
    *,
    draft_path: str | Path,
    products_dir: str | Path = "configs/products",
    runs_dir: str | Path = "data/runs",
    replace: bool = False,
) -> dict[str, Any]:
    source = Path(draft_path)
    product_config = _sanitized_product(load_json(source))
    product_key = _text(product_config.get("product_key"))
    target_path = Path(products_dir) / f"{_filename(product_key)}.local.json"
    missing = product_config_missing_fields(product_config)
    blocking_reasons: list[str] = []
    if missing:
        blocking_reasons.append("missing required fields: " + ", ".join(missing))
    if target_path.exists() and not replace:
        blocking_reasons.append("target already exists")
    if blocking_reasons:
        return _write_artifact(
            runs_dir,
            _artifact(
                ok=False,
                status="blocked",
                draft_path=source,
                target_path=target_path,
                product_config=product_config,
                blocking_reasons=blocking_reasons,
            ),
        )

    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(json.dumps(product_config, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return _write_artifact(
        runs_dir,
        _artifact(
            ok=True,
            status="published",
            draft_path=source,
            target_path=target_path,
            product_config=product_config,
            blocking_reasons=[],
        ),
    )
