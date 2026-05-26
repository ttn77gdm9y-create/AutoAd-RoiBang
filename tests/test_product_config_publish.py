import json
from pathlib import Path

from roibang_v2.workflows.create_mode import load_product_config
from roibang_v2.workflows.product_config_publish import publish_product_config_draft


def _complete_product(product_key: str = "new-product") -> dict:
    return {
        "product_key": product_key,
        "product": "新产品",
        "platform": "WECHAT_GAME",
        "source_advertiser_id": "1850000000000000",
        "organization_id": "1850000000000001",
        "allowed_target_accounts_path": "configs/allowed-create-accounts.local.json",
        "account_remark_pattern": "新产品账户",
        "foundation": {
            "effective_touch_url": "https://example.com/touch",
            "anchor_id": "anchor-1",
            "anchor_type": "MICRO_GAME",
            "anchor_related_type": "GAME",
            "landing_url": "https://example.com/landing",
            "product_image_id": "image-1",
            "fixed_video_cover_id": "cover-1",
            "micro_app_instance_id": "micro-1",
            "micro_promotion_type": "WECHAT_GAME",
        },
    }


def test_publish_product_config_draft_writes_local_product_and_artifact(tmp_path: Path):
    draft_path = tmp_path / "draft.local.json"
    products_dir = tmp_path / "products"
    runs_dir = tmp_path / "runs"
    draft_path.write_text(json.dumps(_complete_product(), ensure_ascii=False), encoding="utf-8")

    result = publish_product_config_draft(
        draft_path=draft_path,
        products_dir=products_dir,
        runs_dir=runs_dir,
    )

    target = products_dir / "new-product.local.json"
    assert result["ok"] is True
    assert result["workflow"] == "product_config_publish"
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 0
    assert result["summary"]["product_key"] == "new-product"
    assert result["summary"]["target_path"] == str(target)
    assert target.exists()
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["product"] == "新产品"
    assert "draft" not in payload
    assert result["readable_reference"]["product"]["product"] == "新产品"
    assert Path(result["artifact_path"]).exists()


def test_publish_product_config_draft_blocks_missing_fields(tmp_path: Path):
    draft_path = tmp_path / "draft.local.json"
    products_dir = tmp_path / "products"
    runs_dir = tmp_path / "runs"
    draft = _complete_product()
    draft["foundation"].pop("landing_url")
    draft_path.write_text(json.dumps(draft, ensure_ascii=False), encoding="utf-8")

    result = publish_product_config_draft(
        draft_path=draft_path,
        products_dir=products_dir,
        runs_dir=runs_dir,
    )

    assert result["ok"] is False
    assert result["status"] == "blocked"
    assert "foundation.landing_url" in result["blocking_reasons"][0]
    assert not (products_dir / "new-product.local.json").exists()


def test_publish_product_config_draft_blocks_existing_target_without_replace(tmp_path: Path):
    draft_path = tmp_path / "draft.local.json"
    products_dir = tmp_path / "products"
    runs_dir = tmp_path / "runs"
    products_dir.mkdir()
    target = products_dir / "new-product.local.json"
    target.write_text(json.dumps({"product_key": "new-product", "product": "旧产品"}), encoding="utf-8")
    draft_path.write_text(json.dumps(_complete_product(), ensure_ascii=False), encoding="utf-8")

    result = publish_product_config_draft(
        draft_path=draft_path,
        products_dir=products_dir,
        runs_dir=runs_dir,
    )

    assert result["ok"] is False
    assert result["status"] == "blocked"
    assert "target already exists" in result["blocking_reasons"]
    assert json.loads(target.read_text(encoding="utf-8"))["product"] == "旧产品"


def test_publish_product_config_draft_allows_replace(tmp_path: Path):
    draft_path = tmp_path / "draft.local.json"
    products_dir = tmp_path / "products"
    runs_dir = tmp_path / "runs"
    products_dir.mkdir()
    target = products_dir / "new-product.local.json"
    target.write_text(json.dumps({"product_key": "new-product", "product": "旧产品"}), encoding="utf-8")
    draft_path.write_text(json.dumps(_complete_product(), ensure_ascii=False), encoding="utf-8")

    result = publish_product_config_draft(
        draft_path=draft_path,
        products_dir=products_dir,
        runs_dir=runs_dir,
        replace=True,
    )

    assert result["ok"] is True
    assert json.loads(target.read_text(encoding="utf-8"))["product"] == "新产品"


def test_create_mode_load_product_config_prefers_local_json(tmp_path: Path):
    product_dir = tmp_path / "products"
    product_dir.mkdir()
    example = _complete_product("new-product")
    local = _complete_product("new-product")
    example["product"] = "示例产品"
    local["product"] = "本地产品"
    (product_dir / "new-product.example.json").write_text(json.dumps(example, ensure_ascii=False), encoding="utf-8")
    (product_dir / "new-product.local.json").write_text(json.dumps(local, ensure_ascii=False), encoding="utf-8")

    product_config = load_product_config(
        {"product_config_dir": str(product_dir)},
        {"product_key": "new-product"},
    )

    assert product_config["product"] == "本地产品"
