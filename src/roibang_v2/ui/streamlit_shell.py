from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from roibang_v2.create_mode_rules import normalize_create_mode_config


DEFAULT_UI_CONFIG: dict[str, Any] = {
    "title": "RoiBang-v2 本地工作台",
    "project_root": ".",
    "runs_dir": "data/runs",
    "create_modes_dir": "configs/create-modes",
    "create_mode_drafts_dir": "configs/create-mode-drafts",
    "products_dir": "configs/products",
    "product_drafts_dir": "configs/product-drafts",
    "default_owner": "郭靖",
    "readonly_timeout_seconds": 900,
}

PRODUCT_REQUIRED_FIELDS = [
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


def load_ui_config(path: str | Path = "configs/ui/streamlit-v0.example.json") -> dict[str, Any]:
    source = Path(path)
    if not source.exists():
        return dict(DEFAULT_UI_CONFIG)
    value = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{source} must contain a JSON object")
    config = {**DEFAULT_UI_CONFIG, **value}
    return config


def list_create_modes(mode_dir: str | Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    path = Path(mode_dir)
    if not path.exists():
        return rows
    candidates = [*path.glob("*.json"), *path.glob("*/*.json")]
    for item in sorted(candidates):
        try:
            value = json.loads(item.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if not isinstance(value, dict):
            continue
        stem = item.stem.replace(".example", "").replace(".local", "")
        mode_key = str(value.get("mode_key") or stem).strip()
        display_name = str(value.get("display_name") or mode_key).strip()
        template_key = str(value.get("template_key") or "").strip()
        product_key = str(value.get("product_key") or "").strip()
        rows.append(
            {
                "mode_key": mode_key,
                "display_name": display_name,
                "template_key": template_key,
                "product_key": product_key,
                "path": str(item),
            }
        )
    return rows


def load_create_mode(mode_dir: str | Path, mode_key: str, product_key: str = "") -> dict[str, Any]:
    key = str(mode_key or "").strip()
    if not key:
        return {}
    path = Path(mode_dir)
    product = str(product_key or "").strip()
    candidates = []
    if product:
        candidates.extend(
            [
                path / product / f"{key}.local.json",
                path / product / f"{key}.json",
                path / product / f"{key}.example.json",
            ]
        )
    candidates.extend([path / f"{key}.json", path / f"{key}.example.json"])
    for item in candidates:
        try:
            value = json.loads(item.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            continue
        if isinstance(value, dict):
            return value
    return {}


def list_products(product_dir: str | Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    path = Path(product_dir)
    if not path.exists():
        return rows
    for item in sorted(path.glob("*.json")):
        try:
            value = json.loads(item.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if not isinstance(value, dict):
            continue
        product_key = str(value.get("product_key") or item.stem.replace(".example", "")).strip()
        product = str(value.get("product") or product_key).strip()
        platform = str(value.get("platform") or "").strip()
        source_advertiser_id = str(value.get("source_advertiser_id") or "").strip()
        rows.append(
            {
                "product_key": product_key,
                "product": product,
                "platform": platform,
                "source_advertiser_id": source_advertiser_id,
            }
        )
    return rows


def load_product_config(product_dir: str | Path, product_key: str) -> dict[str, Any]:
    key = str(product_key or "").strip()
    if not key:
        return {}
    path = Path(product_dir)
    candidates = [path / f"{key}.local.json", path / f"{key}.json", path / f"{key}.example.json"]
    for item in candidates:
        try:
            value = json.loads(item.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            continue
        if isinstance(value, dict):
            return value
    return {}


def product_create_template_catalog_path(template_dir: str | Path, product_key: str) -> Path:
    key = str(product_key or "").strip()
    path = Path(template_dir)
    if key:
        for filename in [f"{key}.local.json", f"{key}.json", f"{key}.example.json"]:
            candidate = path / filename
            if candidate.exists():
                return candidate
    return path / "wx-mini-game.json"


def load_create_template_catalog(template_dir: str | Path, product_key: str = "") -> dict[str, Any]:
    source = product_create_template_catalog_path(template_dir, product_key)
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def product_config_missing_fields(product_config: dict[str, Any]) -> list[str]:
    foundation = product_config.get("foundation") if isinstance(product_config.get("foundation"), dict) else {}
    missing: list[str] = []
    for field in PRODUCT_REQUIRED_FIELDS:
        if field.startswith("foundation."):
            key = field.split(".", 1)[1]
            value = foundation.get(key)
        else:
            value = product_config.get(field)
        if not str(value or "").strip():
            missing.append(field)
    return missing


def draft_mode_filename(value: str) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9_\-]+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-_")
    return text or "create-mode-draft"


def draft_product_filename(value: str) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9_\-]+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-_")
    return text or "product-draft"


def save_create_mode_draft(drafts_dir: str | Path, draft: dict[str, Any]) -> Path:
    if not isinstance(draft, dict):
        raise ValueError("create mode draft must be a JSON object")
    draft_key = str(draft.get("mode_key") or draft.get("draft_key") or "").strip()
    if not draft_key:
        raise ValueError("create mode draft requires mode_key")
    path = Path(drafts_dir)
    path.mkdir(parents=True, exist_ok=True)
    output = path / f"{draft_mode_filename(draft_key)}.local.json"
    output.write_text(
        json.dumps(normalize_create_mode_config(draft), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output


def save_product_create_mode_config(mode_dir: str | Path, mode_config: dict[str, Any]) -> Path:
    if not isinstance(mode_config, dict):
        raise ValueError("create mode config must be a JSON object")
    mode_key = str(mode_config.get("mode_key") or "").strip()
    product_key = str(mode_config.get("product_key") or "").strip()
    if not mode_key:
        raise ValueError("create mode config requires mode_key")
    if not product_key:
        raise ValueError("product create mode config requires product_key")
    output_dir = Path(mode_dir) / product_key
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / f"{draft_mode_filename(mode_key)}.local.json"
    payload = normalize_create_mode_config(mode_config)
    payload.pop("draft", None)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output


def save_product_create_template_catalog(template_dir: str | Path, catalog: dict[str, Any]) -> Path:
    if not isinstance(catalog, dict):
        raise ValueError("create template catalog must be a JSON object")
    product_key = str(catalog.get("product_key") or "").strip()
    if not product_key:
        raise ValueError("product create template catalog requires product_key")
    output_dir = Path(template_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / f"{draft_product_filename(product_key)}.local.json"
    output.write_text(json.dumps(catalog, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output


def save_product_draft(drafts_dir: str | Path, draft: dict[str, Any]) -> Path:
    if not isinstance(draft, dict):
        raise ValueError("product draft must be a JSON object")
    product_key = str(draft.get("product_key") or "").strip()
    if not product_key:
        raise ValueError("product draft requires product_key")
    payload = dict(draft)
    payload["draft"] = {
        **(payload.get("draft") if isinstance(payload.get("draft"), dict) else {}),
        "enabled": True,
        "source": "streamlit",
        "note": "产品草稿不参与真实创建；转正前需要固定脚本校验并发布。",
    }
    path = Path(drafts_dir)
    path.mkdir(parents=True, exist_ok=True)
    output = path / f"{draft_product_filename(product_key)}.local.json"
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output


def split_account_ids(raw: str) -> list[str]:
    accounts: list[str] = []
    seen: set[str] = set()
    for part in str(raw or "").replace("\n", ",").split(","):
        value = part.strip()
        if value and value not in seen:
            seen.add(value)
            accounts.append(value)
    return accounts


def build_allowed_create_accounts_config(
    *,
    product: str,
    channel: str,
    account_ids: list[str],
    account_name_prefix: str = "",
    source: str = "streamlit_product_management",
) -> dict[str, Any]:
    product_text = str(product or "").strip()
    channel_text = str(channel or "").strip() or "wx"
    prefix = str(account_name_prefix or "").strip() or product_text
    rows = []
    for index, advertiser_id in enumerate(account_ids, start=1):
        account_id = str(advertiser_id or "").strip()
        if not account_id:
            continue
        rows.append(
            {
                "advertiser_id": account_id,
                "account_name": f"{prefix}-{index:03d}",
                "product": product_text,
                "channel": channel_text,
                "enable": True,
            }
        )
    return {
        "_comment": "本地真实创建允许账户白名单，不提交 Git。真实创建只允许 enable=true 且 product/channel 匹配的账户。",
        "source": source,
        "product": product_text,
        "channel": channel_text,
        "allowed_target_accounts": rows,
    }


def save_allowed_create_accounts_config(output_path: str | Path, config: dict[str, Any]) -> Path:
    if not isinstance(config, dict):
        raise ValueError("allowed create accounts config must be a JSON object")
    rows = config.get("allowed_target_accounts")
    if not isinstance(rows, list) or not rows:
        raise ValueError("allowed create accounts config requires allowed_target_accounts")
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(config, ensure_ascii=False, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    return output


def mode_label(row: dict[str, str]) -> str:
    display_name = row.get("display_name") or row.get("mode_key") or ""
    mode_key = row.get("mode_key") or ""
    return f"{display_name} ({mode_key})"


def product_label(row: dict[str, str]) -> str:
    product = row.get("product") or row.get("product_key") or ""
    product_key = row.get("product_key") or ""
    return f"{product} ({product_key})"
