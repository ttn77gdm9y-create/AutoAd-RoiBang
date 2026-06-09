import importlib.util
import json
import sqlite3
from pathlib import Path

from roibang_v2.db.bootstrap import bootstrap_database
from roibang_v2.workflows.create_mode import build_create_mode_request
from roibang_v2.workflows.create_mode import load_create_mode_config
from roibang_v2.workflows.create_mode import load_product_config
from roibang_v2.workflows.create_mode import run_create_mode_request


def _seed_source_materials(db_path: Path, count: int = 80) -> None:
    bootstrap_database(db_path)
    with sqlite3.connect(db_path) as conn:
        for index in range(1, count + 1):
            material_id = f"m-{index:03d}"
            video_id = f"v28033gi0000d7m72bvog65s5f9la{index:03d}"
            conn.execute(
                """
                INSERT INTO materials (
                  material_id, name, material_type, video_id,
                  review_status, cost_lookback, score, source, synced_at
                ) VALUES (?, ?, 'video', ?, 'APPROVED', ?, ?, 'test', 'now')
                """,
                (material_id, f"素材{index:03d}", video_id, 1000 - index, 1000 - index),
            )
            conn.execute(
                """
                INSERT INTO product_source_materials (
                  product, source_advertiser_id, organization_id, material_id,
                  video_id, name, material_type, review_status, is_active,
                  cost_lookback, score, source, synced_at
                ) VALUES ('勇者突进', '1856647522964490', '1851650746645060', ?, ?, ?, 'video', 'APPROVED', 1, ?, ?, 'test', 'now')
                """,
                (material_id, video_id, f"素材{index:03d}", 1000 - index, 1000 - index),
            )
            conn.execute(
                """
                INSERT INTO product_source_material_metric_rollups (
                  product, source_advertiser_id, organization_id, window_key, window_days,
                  period_start, period_end, material_id, material_type, source_video_id,
                  name, review_status, stat_cost, source, synced_at
                ) VALUES ('勇者突进', '1856647522964490', '1851650746645060', 'last_60d', 60,
                  '2026-03-15', '2026-05-13', ?, 'video', ?, ?, 'APPROVED', ?, 'test', 'now')
                """,
                (material_id, video_id, f"素材{index:03d}", 1000 - index),
            )


def _seed_gravity_materials_for_create_plan(db_path: Path) -> None:
    bootstrap_database(db_path)
    with sqlite3.connect(db_path) as conn:
        rows = [
            ("g-001", "引力素材001", "sig-g-001", 5000, 20),
            ("g-002", "引力素材002", "sig-g-002", 3000, 8),
            ("g-003", "引力素材003", "sig-g-003", 2000, 4),
        ]
        for material_id, name, signature, stat_cost, convert_cnt in rows:
            conn.execute(
                """
                INSERT INTO materials (
                  material_id, name, material_type, video_id,
                  review_status, cost_lookback, score, source, synced_at
                ) VALUES (?, ?, 'video', '', 'APPROVED', ?, ?, 'gravity_engine', 'now')
                """,
                (material_id, name, stat_cost, stat_cost),
            )
            conn.execute(
                """
                INSERT INTO product_source_materials (
                  product, source_advertiser_id, organization_id, material_id,
                  video_id, name, material_type, review_status, signature, is_active,
                  cost_lookback, score, source, synced_at
                ) VALUES ('勇者突进', 'gravity_engine_album_1', 'gravity_org', ?, '', ?, 'video', 'APPROVED', ?, 1, ?, ?, 'gravity_engine', 'now')
                """,
                (material_id, name, signature, stat_cost, stat_cost),
            )
            conn.execute(
                """
                INSERT INTO product_source_material_metric_rollups (
                  product, source_advertiser_id, organization_id, window_key, window_days,
                  period_start, period_end, material_id, material_type, source_video_id,
                  name, review_status, signature, stat_cost, convert_cnt, source, synced_at
                ) VALUES ('勇者突进', 'gravity_engine_album_1', 'gravity_org', 'last_60d', 60,
                  '2026-03-15', '2026-05-13', ?, 'video', '', ?, 'APPROVED', ?, ?, ?, 'gravity_engine', 'now')
                """,
                (material_id, name, signature, stat_cost, convert_cnt),
            )
        upload_rows = [
            ("g-001", "acc-1", "账户一", "completed", "vG01000000000001", "account-mat-1"),
            ("g-001", "acc-2", "账户二", "completed", "vG02000000000002", "account-mat-2"),
            ("g-002", "acc-1", "账户一", "uploading", "vG03000000000003", "account-mat-3"),
            ("g-003", "acc-1", "账户一", "completed", "", "account-mat-4"),
        ]
        for material_id, advertiser_id, account_name, status, video_id, material_id_in_account in upload_rows:
            conn.execute(
                """
                INSERT INTO gravity_upload_tasks (
                  product, gravity_material_id, signature, target_advertiser_id, target_account_name,
                  gravity_task_id, status, video_id, material_id_in_account, preview_artifact_path,
                  created_at, updated_at
                ) VALUES ('勇者突进', ?, ?, ?, ?, ?, ?, ?, ?, 'data/runs/gravity_upload_to_account/preview.json', 'now', 'now')
                """,
                (
                    material_id,
                    f"sig-{material_id}",
                    advertiser_id,
                    account_name,
                    f"task-{material_id}-{advertiser_id}",
                    status,
                    video_id,
                    material_id_in_account,
                ),
            )


def _policy() -> dict:
    return {
        "project_naming": {
            "template": "{target_date_mmdd}_{owner}_{product}_{project_template_name}_{batch_code}_{index}",
            "index_width": 2,
            "invalid_char_replacement": "_",
        },
        "candidate_filters": {"allowed_review_statuses": ["APPROVED"]},
    }


def _load_script(name: str):
    script_path = Path(f"scripts/{name}.py")
    spec = importlib.util.spec_from_file_location(name, script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_load_product_config_merges_local_over_example_foundation(tmp_path: Path):
    products_dir = tmp_path / "configs" / "products"
    products_dir.mkdir(parents=True)
    example = {
        "product_key": "demo-game",
        "product": "演示游戏",
        "platform": "WECHAT_GAME",
        "source_advertiser_id": "source-example",
        "organization_id": "org-example",
        "foundation": {
            "effective_touch_url": "https://example.test/click",
            "anchor_id": "anchor-1",
            "anchor_type": "APP_GAME",
            "anchor_related_type": "SELECT",
            "landing_url": "https://example.test/landing",
            "product_image_id": "image-1",
            "fixed_video_cover_id": "cover-1",
            "micro_app_instance_id": "mini-1",
            "micro_promotion_type": "WECHAT_GAME",
        },
        "automation": {"daily_report_sync": {"enabled": True}},
    }
    local = {
        "product_key": "demo-game",
        "product": "演示游戏",
        "platform": "WECHAT_GAME",
        "source_advertiser_id": "source-local",
        "organization_id": "org-local",
        "automation": {"daily_report_sync": {"enabled": False}},
    }
    (products_dir / "demo-game.example.json").write_text(json.dumps(example, ensure_ascii=False), encoding="utf-8")
    (products_dir / "demo-game.local.json").write_text(json.dumps(local, ensure_ascii=False), encoding="utf-8")

    config = load_product_config(
        {"product_config_dir": str(products_dir)},
        {"product_key": "demo-game"},
    )

    assert config["source_advertiser_id"] == "source-local"
    assert config["organization_id"] == "org-local"
    assert config["automation"]["daily_report_sync"]["enabled"] is False
    assert config["foundation"]["landing_url"] == "https://example.test/landing"
    assert config["foundation"]["micro_app_instance_id"] == "mini-1"


def test_create_mode_builds_scale_create_request_from_mode_config():
    mode = {
        "mode_key": "wx_7r_general_scale",
        "display_name": "7R 历史放量",
        "product": "勇者突进",
        "platform": "WECHAT_GAME",
        "template_key": "wx_7r_general",
        "template_name_suffix": "历史放量",
        "source_advertiser_id": "1856647522964490",
        "organization_id": "1851650746645060",
        "defaults": {
            "daily_budget": 88888,
            "cpa_bid": 103,
            "roi_coefficient": 0.419,
            "project_count": 5,
            "units_per_project": 1,
        },
        "material_requirements": {
            "material_type": "video",
            "materials_per_unit": 5,
            "dedupe_scope": "max_account_overlap",
            "max_cross_account_overlap_ratio": 0.3,
            "on_insufficient": "allow_reuse",
        },
        "material_selection": {"lookback_days": 30, "selection_type": "high_spend"},
        "initial_status": {"project_operation": "ENABLE", "unit_operation": "ENABLE"},
    }
    template_catalog = json.loads(Path("configs/create-templates/wx-mini-game.json").read_text(encoding="utf-8"))

    request = build_create_mode_request(
        {
            "mode_key": "wx_7r_general_scale",
            "target_accounts": ["acc-1", "acc-2"],
            "target_date": "2026-05-13",
            "owner": "郭靖",
        },
        mode_config=mode,
        template_catalog=template_catalog,
    )

    assert request["template_key"] == "wx_7r_general"
    assert request["project_template_name"] == "微小每付7R通投历史放量"
    assert request["target_accounts"] == [
        {"advertiser_id": "acc-1", "project_count": 5, "units_per_project": 1, "daily_budget": 88888},
        {"advertiser_id": "acc-2", "project_count": 5, "units_per_project": 1, "daily_budget": 88888},
    ]
    assert request["field_defaults"]["cpa_bid"] == 103
    assert request["field_defaults"]["roi_goal"] == 0.419
    assert request["material_requirements"]["materials_per_unit"] == 5
    assert request["material_requirements"]["dedupe_scope"] == "max_account_overlap"
    assert request["material_requirements"]["max_cross_account_overlap_ratio"] == 0.5
    assert request["material_requirements"]["cross_account_reuse_mode"] == "scale_top_materials"
    assert request["material_requirements"]["allow_reuse_across_accounts"] is True
    assert request["material_selection"]["source_scope"] == "source_material_account"
    assert request["material_selection"]["lookback_days"] == 30
    assert request["material_selection"]["min_stat_cost"] == 1000
    assert request["material_selection"]["sort_by"] == "stat_cost_desc"
    assert request["material_selection"]["random_shuffle"] is True
    assert request["material_selection"]["exclude_recent_used_days"] == 0
    assert request["initial_status"] == {"project_operation": "ENABLE", "unit_operation": "ENABLE"}


def test_create_mode_applies_product_config_to_foundation_fields(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_source_materials(db_path, count=8)
    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE product_source_materials SET product = '新产品', source_advertiser_id = 'source-acc'")
        conn.execute(
            "UPDATE product_source_material_metric_rollups SET product = '新产品', source_advertiser_id = 'source-acc'"
        )
    product_path = tmp_path / "product.json"
    product_path.write_text(
        json.dumps(
            {
                "product_key": "new_product_wechat",
                "product": "新产品",
                "platform": "WECHAT_GAME",
                "source_advertiser_id": "source-acc",
                "organization_id": "org-1",
                "allowed_target_accounts_path": "configs/allowed-create-accounts.local.json",
                "account_remark_pattern": "新产品-微小-郭靖",
                "foundation": {
                    "effective_touch_url": "https://example.com/touch?advertiser_id=__ADVERTISER_ID__",
                    "anchor_id": "anchor-1",
                    "anchor_type": "APP_GAME",
                    "anchor_related_type": "SELECT",
                    "landing_url": "https://example.com/landing",
                    "product_image_id": "product-image-1",
                    "fixed_video_cover_id": "cover-1",
                    "micro_app_instance_id": "micro-app-1",
                    "micro_promotion_type": "WECHAT_GAME",
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    mode_path = tmp_path / "mode.json"
    mode_path.write_text(
        json.dumps(
            {
                "mode_key": "new_product_scale",
                "display_name": "新产品放量",
                "product_key": "new_product_wechat",
                "template_key": "wx_pay_general",
                "template_name_suffix": "历史放量",
                "defaults": {"daily_budget": 88888, "cpa_bid": 103, "project_count": 1, "units_per_project": 1},
                "material_requirements": {
                    "material_type": "video",
                    "materials_per_unit": 5,
                    "dedupe_scope": "max_account_overlap",
                    "max_cross_account_overlap_ratio": 1.0,
                    "cross_account_reuse_mode": "scale_top_materials",
                    "allow_reuse_across_accounts": True,
                    "on_insufficient": "allow_reuse",
                },
                "material_selection": {"lookback_days": 30, "selection_type": "high_spend", "min_stat_cost": 0},
                "initial_status": {"project_operation": "ENABLE", "unit_operation": "ENABLE"},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = run_create_mode_request(
        {
            "create_mode": {
                "mode_config_path": str(mode_path),
                "product_config_path": str(product_path),
                "target_accounts": ["acc-1"],
                "target_date": "2026-05-13",
                "owner": "郭靖",
            }
        },
        db_path=db_path,
        runs_dir=tmp_path / "runs",
        policy={"create_strategy_plan": _policy()},
        template_catalog_path=Path("configs/create-templates/wx-mini-game.json"),
    )

    assert result["ok"] is True
    create_request = result["create_request"]
    assert create_request["product"] == "新产品"
    assert create_request["platform"] == "WECHAT_GAME"
    assert create_request["source_advertiser_id"] == "source-acc"
    assert create_request["organization_id"] == "org-1"
    assert create_request["allowed_target_accounts_path"] == "configs/allowed-create-accounts.local.json"
    assert create_request["field_defaults"]["action_track_url"] == "https://example.com/touch?advertiser_id=__ADVERTISER_ID__"
    template_parameters = create_request["template_parameters"]
    assert template_parameters["anchor_id"] == "anchor-1"
    assert template_parameters["landing_url"] == "https://example.com/landing"
    assert template_parameters["product_image_id"] == "product-image-1"
    assert template_parameters["fixed_video_cover_id"] == "cover-1"
    snapshot = create_request["product_config_snapshot"]
    assert snapshot["product_key"] == "new_product_wechat"
    assert snapshot["allowed_target_accounts_path"] == "configs/allowed-create-accounts.local.json"
    assert snapshot["foundation"]["anchor_id"] == "anchor-1"


def test_create_mode_can_use_product_specific_template_catalog(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_source_materials(db_path, count=8)
    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE product_source_materials SET product = '点点英雄', source_advertiser_id = 'source-acc'")
        conn.execute(
            "UPDATE product_source_material_metric_rollups SET product = '点点英雄', source_advertiser_id = 'source-acc'"
        )
    product_path = tmp_path / "diandian-product.json"
    product_path.write_text(
        json.dumps(
            {
                "product_key": "diandian-hero",
                "product": "点点英雄",
                "platform": "WECHAT_GAME",
                "source_advertiser_id": "source-acc",
                "organization_id": "org-1",
                "allowed_target_accounts_path": "configs/allowed-create-accounts.diandian-hero.local.json",
                "account_remark_pattern": "点点英雄-微小-郭靖",
                "foundation": {
                    "effective_touch_url": "https://example.com/dd-touch",
                    "anchor_id": "dd-anchor",
                    "anchor_type": "APP_GAME",
                    "anchor_related_type": "SELECT",
                    "landing_url": "https://example.com/dd-landing",
                    "product_image_id": "dd-image",
                    "fixed_video_cover_id": "dd-cover",
                    "micro_app_instance_id": "dd-mini",
                    "micro_promotion_type": "WECHAT_GAME",
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    mode_path = tmp_path / "mode.json"
    mode_path.write_text(
        json.dumps(
            {
                "mode_key": "wx_pay_general_scale",
                "display_name": "点点英雄每付通投历史放量",
                "product_key": "diandian-hero",
                "template_key": "wx_pay_general",
                "template_name_suffix": "历史放量",
                "defaults": {"daily_budget": 88888, "cpa_bid": 103, "project_count": 1, "units_per_project": 1},
                "material_requirements": {"material_type": "video", "materials_per_unit": 5},
                "material_selection": {"lookback_days": 30, "selection_type": "high_spend", "min_stat_cost": 0},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    template_path = tmp_path / "diandian-template.json"
    template_path.write_text(
        json.dumps(
            {
                "product_key": "diandian-hero",
                "product": "点点英雄",
                "templates": {
                    "wx_pay_general": {
                        "project_template_name": "点点每付通投",
                        "unit_template_name": "点点每付通投",
                        "title_pool": ["点点专属文案"],
                    }
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = run_create_mode_request(
        {
            "create_mode": {
                "mode_config_path": str(mode_path),
                "product_config_path": str(product_path),
                "template_catalog_path": str(template_path),
                "target_accounts": ["acc-1"],
                "target_date": "2026-05-25",
                "owner": "郭靖",
            }
        },
        db_path=db_path,
        runs_dir=tmp_path / "runs",
        policy={"create_strategy_plan": _policy()},
    )

    assert result["ok"] is True
    assert result["create_request"]["project_template_name"] == "点点每付通投历史放量"
    assert result["create_request"]["template_parameters"]["title_pool"] == ["点点专属文案"]
    assert result["summary"]["template_catalog_path"] == str(template_path)


def test_create_mode_random_materials_ignores_lookback_constraints():
    request = build_create_mode_request(
        {
            "mode_key": "wx_pay_general_random_materials",
            "target_accounts": ["acc-1"],
            "target_date": "2026-05-25",
            "owner": "郭靖",
        },
        mode_config={
            "mode_key": "wx_pay_general_random_materials",
            "display_name": "点点英雄每付通投素材不限",
            "product_key": "diandian-hero",
            "template_key": "wx_pay_general",
            "defaults": {"daily_budget": 88888, "project_count": 1, "units_per_project": 1},
            "material_selection": {
                "selection_type": "random_materials",
                "lookback_days": 30,
                "first_seen_days": 7,
                "min_create_age_days": 3,
                "min_stat_cost": 200,
                "sort_by": "stat_cost_desc",
                "random_shuffle": False,
            },
        },
        template_catalog={"templates": {"wx_pay_general": {"project_template_name": "微小每付通投"}}},
    )

    selection = request["material_selection"]
    assert selection["selection_type"] == "random_materials"
    assert selection["min_stat_cost"] == 0
    assert selection["sort_by"] == "random_stable"
    assert selection["random_shuffle"] is True
    assert "lookback_days" not in selection
    assert "first_seen_days" not in selection
    assert "min_create_age_days" not in selection


def test_create_mode_blocks_incomplete_product_config(tmp_path: Path):
    product_path = tmp_path / "bad-product.json"
    product_path.write_text(
        json.dumps(
            {
                "product_key": "bad_product",
                "product": "坏配置",
                "platform": "WECHAT_GAME",
                "source_advertiser_id": "source-acc",
                "organization_id": "org-1",
                "foundation": {"anchor_id": "anchor-1"},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    mode_path = tmp_path / "mode.json"
    mode_path.write_text(
        json.dumps(
            {
                "mode_key": "bad_product_scale",
                "product_key": "bad_product",
                "template_key": "wx_pay_general",
                "defaults": {"daily_budget": 88888, "cpa_bid": 103, "project_count": 1, "units_per_project": 1},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    try:
        run_create_mode_request(
            {
                "create_mode": {
                    "mode_config_path": str(mode_path),
                    "product_config_path": str(product_path),
                    "target_accounts": ["acc-1"],
                    "target_date": "2026-05-13",
                    "owner": "郭靖",
                }
            },
            db_path=tmp_path / "roibang.sqlite3",
            runs_dir=tmp_path / "runs",
            policy={"create_strategy_plan": _policy()},
            template_catalog_path=Path("configs/create-templates/wx-mini-game.json"),
        )
    except ValueError as exc:
        assert "product config missing required fields" in str(exc)
        assert "foundation.effective_touch_url" in str(exc)
        assert "foundation.landing_url" in str(exc)
    else:
        raise AssertionError("incomplete product config must be blocked")


def test_create_mode_requires_product_specific_mode_when_product_key_is_not_yzt(tmp_path: Path):
    mode_root = tmp_path / "create-modes"
    mode_root.mkdir()
    (mode_root / "wx_pay_general_scale.example.json").write_text(
        json.dumps(
            {
                "mode_key": "wx_pay_general_scale",
                "display_name": "勇者突进每付通投历史放量",
                "product_key": "yzt-wechat-mini-game",
                "template_key": "wx_pay_general",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    try:
        load_create_mode_config(
            {
                "product_key": "diandian-hero",
                "mode": "每付通投历史放量",
                "mode_config_dir": str(mode_root),
            }
        )
    except ValueError as exc:
        assert "product-specific mode config is required" in str(exc)
        assert "diandian-hero" in str(exc)
    else:
        raise AssertionError("new product must not silently reuse legacy create mode")


def test_create_mode_loads_product_specific_mode_when_present(tmp_path: Path):
    mode_root = tmp_path / "create-modes"
    product_mode_dir = mode_root / "diandian-hero"
    product_mode_dir.mkdir(parents=True)
    (product_mode_dir / "wx_pay_general_scale.local.json").write_text(
        json.dumps(
            {
                "mode_key": "wx_pay_general_scale",
                "display_name": "点点英雄每付通投历史放量",
                "product_key": "diandian-hero",
                "template_key": "wx_pay_general",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    mode = load_create_mode_config(
        {
            "product_key": "diandian-hero",
            "mode": "每付通投历史放量",
            "mode_config_dir": str(mode_root),
        }
    )

    assert mode["product_key"] == "diandian-hero"
    assert mode["display_name"] == "点点英雄每付通投历史放量"


def test_create_mode_plan_id_is_unique_per_batch_generated_at():
    mode_config = json.loads(Path("configs/create-modes/wx_pay_general_test_new.example.json").read_text(encoding="utf-8"))
    template_catalog = json.loads(Path("configs/create-templates/wx-mini-game.json").read_text(encoding="utf-8"))
    base_request = {
        "mode_key": "wx_pay_general_test_new",
        "target_accounts": ["acc-1", "acc-2"],
        "target_date": "2026-05-15",
        "owner": "郭靖",
    }

    first = build_create_mode_request(
        {**base_request, "batch_generated_at": "2026-05-15T10:00:00+00:00"},
        mode_config=mode_config,
        template_catalog=template_catalog,
    )
    second = build_create_mode_request(
        {**base_request, "batch_generated_at": "2026-05-15T10:01:00+00:00"},
        mode_config=mode_config,
        template_catalog=template_catalog,
    )

    assert first["batch_code"].startswith("B")
    assert len(first["batch_code"]) == 9
    assert first["batch_code"] != second["batch_code"]
    assert first["request_id"].endswith(first["batch_code"])
    assert second["request_id"].endswith(second["batch_code"])
    assert first["plan_id"] == f"create-plan-{first['request_id']}"
    assert first["plan_id"] != second["plan_id"]


def test_create_mode_omits_bid_and_roi_when_template_does_not_fix_them():
    mode_config = {
        "mode_key": "wx_pay_general_random_materials",
        "display_name": "点点英雄每付通投素材不限",
        "product": "点点英雄",
        "product_key": "diandian-hero",
        "platform": "WECHAT_GAME",
        "template_key": "wx_pay_general",
        "defaults": {"daily_budget": 88888, "project_count": 5, "units_per_project": 1},
        "material_requirements": {"material_type": "video", "materials_per_unit": 5},
        "material_selection": {"selection_type": "random_materials", "min_stat_cost": 0, "random_shuffle": True},
    }
    template_catalog = {
        "templates": {
            "wx_pay_general": {
                "project_template_name": "微小每付通投",
                "project_fixed": {"aigc_dynamic_creative_switch": "OFF"},
            }
        }
    }

    request = build_create_mode_request(
        {"target_accounts": ["acc-1"], "target_date": "2026-05-25", "owner": "郭靖"},
        mode_config=mode_config,
        template_catalog=template_catalog,
    )

    assert "cpa_bid" not in request["field_defaults"]
    assert "roi_goal" not in request["field_defaults"]
    assert request["field_defaults"]["aigc_dynamic_creative_switch"] == "OFF"
    assert request["material_selection"]["selection_type"] == "random_materials"
    assert request["material_selection"]["min_stat_cost"] == 0


def test_create_mode_allows_runtime_bid_and_roi_without_writing_template_defaults():
    mode_config = {
        "mode_key": "wx_7r_general_random_materials",
        "display_name": "点点英雄7R通投素材不限",
        "product": "点点英雄",
        "product_key": "diandian-hero",
        "platform": "WECHAT_GAME",
        "template_key": "wx_7r_general",
        "defaults": {"daily_budget": 88888, "project_count": 5, "units_per_project": 1},
        "material_requirements": {"material_type": "video", "materials_per_unit": 5},
        "material_selection": {"selection_type": "random_materials", "min_stat_cost": 0, "random_shuffle": True},
    }
    template_catalog = {"templates": {"wx_7r_general": {"project_template_name": "微小每付7R通投"}}}

    request = build_create_mode_request(
        {
            "target_accounts": ["acc-1"],
            "target_date": "2026-05-25",
            "owner": "郭靖",
            "cpa_bid": 108,
            "roi_coefficient": 0.41,
        },
        mode_config=mode_config,
        template_catalog=template_catalog,
    )

    assert mode_config["defaults"] == {"daily_budget": 88888, "project_count": 5, "units_per_project": 1}
    assert request["field_defaults"]["cpa_bid"] == 108
    assert request["field_defaults"]["roi_goal"] == 0.41


def test_bundled_create_modes_cover_7r_and_pay_scale_and_test_new():
    template_catalog = json.loads(Path("configs/create-templates/wx-mini-game.json").read_text(encoding="utf-8"))
    expected = {
        "wx_7r_general_scale": ("wx_7r_general", "微小每付7R通投历史放量", 0.419, "7R 通投历史放量", 30),
        "wx_7r_general_recent_scale": ("wx_7r_general", "微小每付7R通投近期放量", 0.419, "7R 通投近期放量", 7),
        "wx_7r_male_scale": ("wx_7r_male", "微小每付7R男历史放量", 0.419, "7R 男历史放量", 30),
        "wx_7r_male_recent_scale": ("wx_7r_male", "微小每付7R男近期放量", 0.419, "7R 男近期放量", 7),
        "wx_pay_general_scale": ("wx_pay_general", "微小每付通投历史放量", None, "每付通投历史放量", 30),
        "wx_pay_general_recent_scale": ("wx_pay_general", "微小每付通投近期放量", None, "每付通投近期放量", 7),
        "wx_pay_general_test_new": ("wx_pay_general", "微小每付通投测新", None, "每付通投测新", 7),
        "wx_pay_general_retest": ("wx_pay_general", "微小每付通投低转化复测", None, "每付通投低转化复测", 30),
        "wx_pay_general_no_conversion_retest": ("wx_pay_general", "微小每付通投无转化复测", None, "每付通投无转化复测", 30),
        "wx_pay_male_scale": ("wx_pay_male", "微小每付男历史放量", None, "每付男历史放量", 30),
        "wx_pay_male_recent_scale": ("wx_pay_male", "微小每付男近期放量", None, "每付男近期放量", 7),
        "wx_pay_male_test_new": ("wx_pay_male", "微小每付男测新", None, "每付男测新", 7),
        "wx_pay_male_retest": ("wx_pay_male", "微小每付男低转化复测", None, "每付男低转化复测", 30),
        "wx_pay_male_no_conversion_retest": ("wx_pay_male", "微小每付男无转化复测", None, "每付男无转化复测", 30),
    }
    for mode_key, (template_key, project_template_name, roi_goal, display_name, lookback_days) in expected.items():
        mode_config = json.loads(Path(f"configs/create-modes/{mode_key}.example.json").read_text(encoding="utf-8"))
        assert mode_config["display_name"] == display_name
        request = build_create_mode_request(
            {
                "mode_key": mode_key,
                "target_accounts": ["acc-1"],
                "target_date": "2026-05-13",
                "owner": "郭靖",
            },
            mode_config=mode_config,
            template_catalog=template_catalog,
        )

        assert request["template_key"] == template_key
        assert request["project_template_name"] == project_template_name
        assert request["material_selection"]["lookback_days"] == lookback_days
        assert request["material_selection"]["source_scope"] == "source_material_account"
        assert request["material_selection"]["exclude_recent_used_days"] == 0
        assert request["field_defaults"]["cpa_bid"] == (103 if mode_key.endswith("_scale") or mode_key.endswith("_recent_scale") else 111)
        if mode_key.endswith("_test_new"):
            assert request["target_accounts"][0]["project_count"] == 5
            assert request["material_selection"]["candidate_pool_limit"] == 200
            assert request["material_selection"]["first_seen_days"] == 7
        if mode_key.endswith("_retest"):
            assert request["target_accounts"][0]["project_count"] == 5
        if mode_key.endswith("_recent_scale"):
            assert request["material_selection"]["min_stat_cost"] == 200
        if mode_key.endswith("_retest") and "no_conversion" not in mode_key:
            assert request["material_selection"]["min_convert_cnt"] == 1
            assert request["material_selection"]["max_convert_cnt"] == 5
        if mode_key.endswith("_no_conversion_retest"):
            assert request["material_selection"]["min_convert_cnt"] == 0
            assert request["material_selection"]["max_convert_cnt"] == 0
            assert request["material_selection"]["max_stat_cost"] == 500
            assert request["material_selection"]["min_create_age_days"] == 7
        assert request["material_requirements"]["dedupe_scope"] == "max_account_overlap"
        assert request["material_requirements"]["allow_reuse_across_accounts"] is True
        if mode_key.endswith("_scale") or mode_key.endswith("_recent_scale"):
            assert request["material_requirements"]["max_cross_account_overlap_ratio"] == 0.5
            assert request["material_requirements"]["cross_account_reuse_mode"] == "scale_top_materials"
        assert request["field_defaults"]["action_track_url"].startswith("https://backend.gravity-engine.com/")
        assert request["product_key"] == "yzt-wechat-mini-game"
        assert request["template_parameters"]["anchor_id"] == "7631055849892465418"
        assert request["template_parameters"]["landing_url"] == "https://www.chengzijianzhan.com/tetris/page/7605144110390951986"
        assert request["template_parameters"]["unit_creative_selection"] == {
            "title_strategy": "deterministic_shuffle_per_unit",
            "cta_min_count": 2,
            "cta_max_count": 3,
            "product_selling_point_min_count": 2,
            "product_selling_point_max_count": 3,
            "aweme_select_count": 1,
        }
        if roi_goal is None:
            assert "roi_goal" not in request["field_defaults"]
        else:
            assert request["field_defaults"]["roi_goal"] == roi_goal


def test_create_mode_resolves_complete_chinese_aliases_and_rejects_ambiguous_names():
    assert load_create_mode_config({"mode_key": "7R 通投历史放量"})["mode_key"] == "wx_7r_general_scale"
    assert load_create_mode_config({"mode_key": "7R 通投近期放量"})["mode_key"] == "wx_7r_general_recent_scale"
    assert load_create_mode_config({"mode_key": "每付通投低转化复测"})["mode_key"] == "wx_pay_general_retest"
    assert load_create_mode_config({"mode_key": "每付通投无转化复测"})["mode_key"] == "wx_pay_general_no_conversion_retest"
    assert load_create_mode_config({"mode_key": "每付男近期放量"})["mode_key"] == "wx_pay_male_recent_scale"

    try:
        load_create_mode_config({"mode_key": "7R 放量"})
    except ValueError as exc:
        assert "需要指定通投或男" in str(exc)
    else:
        raise AssertionError("7R 放量 must be rejected as ambiguous")

    try:
        load_create_mode_config({"mode_key": "7R 通投低转化复测"})
    except ValueError as exc:
        assert "7R 只保留历史放量/近期放量" in str(exc)
    else:
        raise AssertionError("7R 复测 must be rejected")

    try:
        load_create_mode_config({"mode_key": "7R 男测新"})
    except ValueError as exc:
        assert "7R 只保留历史放量/近期放量" in str(exc)
    else:
        raise AssertionError("7R 测新 must be rejected")

    try:
        load_create_mode_config({"mode_key": "每付男放量"})
    except ValueError as exc:
        assert "需要指定历史/近期" in str(exc)
    else:
        raise AssertionError("每付男放量 must be rejected as ambiguous")

    try:
        load_create_mode_config({"mode_key": "每付通投复测"})
    except ValueError as exc:
        assert "低转化/无转化" in str(exc)
    else:
        raise AssertionError("每付通投复测 must be rejected as ambiguous")


def test_create_mode_generates_strategy_plan_with_enabled_initial_status_and_overlap_cap(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_source_materials(db_path, count=40)
    mode_path = tmp_path / "wx_pay_general_test_new.json"
    mode_path.write_text(
        json.dumps(
            {
                "mode_key": "wx_pay_general_test_new",
                "display_name": "每付通投测新",
                "product": "勇者突进",
                "platform": "WECHAT_GAME",
                "template_key": "wx_pay_general",
                "template_name_suffix": "测新",
                "source_advertiser_id": "1856647522964490",
                "organization_id": "1851650746645060",
                "defaults": {
                    "daily_budget": 10000,
                    "cpa_bid": 111,
                    "project_count": 8,
                    "units_per_project": 1,
                },
                "material_requirements": {
                    "material_type": "video",
                    "materials_per_unit": 6,
                    "dedupe_scope": "max_account_overlap",
                    "max_cross_account_overlap_ratio": 0.3,
                    "on_insufficient": "allow_reuse",
                },
                "material_selection": {"lookback_days": 30, "selection_type": "test_new"},
                "initial_status": {"project_operation": "ENABLE", "unit_operation": "ENABLE"},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = run_create_mode_request(
        {
            "create_mode": {
                "mode_config_path": str(mode_path),
                "target_accounts": ["acc-1", "acc-2"],
                "target_date": "2026-05-13",
                "owner": "郭靖",
            }
        },
        db_path=db_path,
        runs_dir=tmp_path / "runs",
        policy={"create_strategy_plan": _policy()},
        template_catalog_path=Path("configs/create-templates/wx-mini-game.json"),
    )

    assert result["ok"] is True
    assert result["summary"]["planned_project_count"] == 16
    assert result["summary"]["planned_unit_count"] == 16
    plan = result["create_strategy_plan"]
    assert plan["request"]["project_template_name"] == "微小每付通投测新"
    assert plan["strategy"]["projects"][0]["operation"] == "ENABLE"
    assert plan["strategy"]["projects"][0]["units"][0]["operation"] == "ENABLE"
    assert "测新" in plan["strategy"]["projects"][0]["project_name"]
    assert Path(result["artifact_path"]).exists()


def test_create_mode_can_use_completed_gravity_uploads_per_target_account(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_gravity_materials_for_create_plan(db_path)
    mode_path = tmp_path / "wx_pay_general_gravity.json"
    mode_path.write_text(
        json.dumps(
            {
                "mode_key": "wx_pay_general_gravity",
                "display_name": "每付通投引力素材",
                "product": "勇者突进",
                "platform": "WECHAT_GAME",
                "template_key": "wx_pay_general",
                "template_name_suffix": "引力素材",
                "source_advertiser_id": "1856647522964490",
                "organization_id": "1851650746645060",
                "defaults": {
                    "daily_budget": 10000,
                    "cpa_bid": 111,
                    "project_count": 1,
                    "units_per_project": 1,
                },
                "material_requirements": {
                    "material_type": "video",
                    "materials_per_unit": 1,
                    "dedupe_scope": "allow_reuse",
                    "on_insufficient": "allow_reuse",
                },
                "material_selection": {"lookback_days": 60, "selection_type": "high_spend", "min_stat_cost": 0},
                "initial_status": {"project_operation": "ENABLE", "unit_operation": "ENABLE"},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = run_create_mode_request(
        {
            "create_mode": {
                "mode_config_path": str(mode_path),
                "target_accounts": ["acc-1", "acc-2"],
                "target_date": "2026-05-13",
                "owner": "郭靖",
                "material_source": "gravity_engine",
            }
        },
        db_path=db_path,
        runs_dir=tmp_path / "runs",
        policy={"create_strategy_plan": _policy()},
        template_catalog_path=Path("configs/create-templates/wx-mini-game.json"),
    )

    assert result["ok"] is True
    plan = result["create_strategy_plan"]
    assert plan["request"]["material_selection"]["source_scope"] == "gravity_engine"
    assert plan["strategy"]["source"] == "gravity_upload_tasks"
    materials_by_account = {}
    for project in plan["strategy"]["projects"]:
        unit_materials = project["units"][0]["materials"]
        assert len(unit_materials) == 1
        materials_by_account[project["advertiser_id"]] = unit_materials[0]
    assert materials_by_account["acc-1"]["material_id"] == "g-001"
    assert materials_by_account["acc-1"]["source_video_id"] == "vG01000000000001"
    assert materials_by_account["acc-1"]["target_account_name"] == "账户一"
    assert materials_by_account["acc-2"]["material_id"] == "g-001"
    assert materials_by_account["acc-2"]["source_video_id"] == "vG02000000000002"
    assert materials_by_account["acc-2"]["target_account_name"] == "账户二"
    selected_ids = {material["material_id"] for material in materials_by_account.values()}
    assert selected_ids == {"g-001"}


def test_create_mode_allows_reuse_without_duplicate_material_inside_one_unit(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_source_materials(db_path, count=1)
    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE product_source_materials SET cost_lookback = 2000, score = 2000 WHERE material_id = 'm-001'")
        conn.execute("UPDATE product_source_material_metric_rollups SET stat_cost = 2000 WHERE material_id = 'm-001'")
    mode_config = json.loads(Path("configs/create-modes/wx_pay_general_scale.example.json").read_text(encoding="utf-8"))
    template_catalog = json.loads(Path("configs/create-templates/wx-mini-game.json").read_text(encoding="utf-8"))

    result = run_create_mode_request(
        {
            "create_mode": {
                "mode_key": "wx_pay_general_scale",
                "mode_config_path": "configs/create-modes/wx_pay_general_scale.example.json",
                "target_accounts": ["acc-1"],
                "target_date": "2026-05-13",
                "owner": "郭靖",
            }
        },
        db_path=db_path,
        runs_dir=tmp_path / "runs",
        policy={"create_strategy_plan": _policy()},
        template_catalog_path=Path("configs/create-templates/wx-mini-game.json"),
    )

    assert result["ok"] is True
    plan = result["create_strategy_plan"]
    unit = plan["strategy"]["projects"][0]["units"][0]
    material_ids = [material["material_id"] for material in unit["materials"]]
    assert material_ids == ["m-001"]
    assert mode_config["material_requirements"]["on_insufficient"] == "allow_reuse"
    assert template_catalog["templates"][mode_config["template_key"]]


def test_create_mode_reuse_shortage_rotates_materials_in_same_account(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_source_materials(db_path, count=65)
    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE product_source_materials SET cost_lookback = 2000, score = 2000")
        conn.execute("UPDATE product_source_material_metric_rollups SET stat_cost = 2000")
    mode_path = tmp_path / "mode.json"
    mode_path.write_text(
        json.dumps(
            {
                "mode_key": "reuse_shortage_rotation",
                "display_name": "复用短缺轮转",
                "product": "勇者突进",
                "platform": "WECHAT_GAME",
                "template_key": "wx_pay_general",
                "template_name_suffix": "测新",
                "source_advertiser_id": "1856647522964490",
                "organization_id": "1851650746645060",
                "defaults": {"daily_budget": 10000, "cpa_bid": 111, "project_count": 5, "units_per_project": 1},
                "material_requirements": {
                    "material_type": "video",
                    "materials_per_unit": 6,
                    "dedupe_scope": "max_account_overlap",
                    "max_cross_account_overlap_ratio": 0.3,
                    "allow_reuse_across_accounts": True,
                    "on_insufficient": "allow_reuse",
                },
                "material_selection": {
                    "lookback_days": 60,
                    "selection_type": "high_spend",
                    "sort_by": "stat_cost_desc",
                    "random_shuffle": True,
                },
                "initial_status": {"project_operation": "ENABLE", "unit_operation": "ENABLE"},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = run_create_mode_request(
        {
            "create_mode": {
                "mode_config_path": str(mode_path),
                "target_accounts": ["acc-1", "acc-2", "acc-3"],
                "target_date": "2026-05-15",
                "owner": "郭靖",
                "batch_generated_at": "2026-05-15T10:00:00+00:00",
            }
        },
        db_path=db_path,
        runs_dir=tmp_path / "runs",
        policy={"create_strategy_plan": _policy()},
        template_catalog_path=Path("configs/create-templates/wx-mini-game.json"),
    )

    assert result["ok"] is True
    third_account_projects = [
        project
        for project in result["create_strategy_plan"]["strategy"]["projects"]
        if project["advertiser_id"] == "acc-3"
    ]
    unit_material_sets = [
        tuple(material["material_id"] for material in project["units"][0]["materials"])
        for project in third_account_projects
    ]
    assert len(unit_material_sets) == 5
    assert len(set(unit_material_sets)) > 2


def test_create_mode_scale_reuses_top_spend_materials_across_accounts(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_source_materials(db_path, count=40)
    with sqlite3.connect(db_path) as conn:
        for index in range(1, 41):
            stat_cost = 100000 - index
            conn.execute(
                "UPDATE product_source_materials SET cost_lookback = ?, score = ? WHERE material_id = ?",
                (stat_cost, stat_cost, f"m-{index:03d}"),
            )
            conn.execute(
                "UPDATE product_source_material_metric_rollups SET stat_cost = ? WHERE material_id = ?",
                (stat_cost, f"m-{index:03d}"),
            )
    mode_config = json.loads(Path("configs/create-modes/wx_pay_general_scale.example.json").read_text(encoding="utf-8"))

    result = run_create_mode_request(
        {
            "create_mode": {
                "mode_key": "wx_pay_general_scale",
                "target_accounts": ["acc-1", "acc-2", "acc-3"],
                "target_date": "2026-05-13",
                "owner": "郭靖",
                "batch_generated_at": "2026-05-13T10:00:00+00:00",
            }
        },
        db_path=db_path,
        runs_dir=tmp_path / "runs",
        policy={"create_strategy_plan": _policy()},
        template_catalog_path=Path("configs/create-templates/wx-mini-game.json"),
    )

    assert result["ok"] is True
    assert mode_config["material_selection"]["selection_type"] == "high_spend"
    projects = result["create_strategy_plan"]["strategy"]["projects"]
    account_materials: dict[str, set[str]] = {}
    for project in projects:
        advertiser_id = project["advertiser_id"]
        account_materials.setdefault(advertiser_id, set())
        for unit in project["units"]:
            material_ids = [material["material_id"] for material in unit["materials"]]
            assert len(material_ids) == len(set(material_ids))
            account_materials[advertiser_id].update(material_ids)

    assert set(account_materials) == {"acc-1", "acc-2", "acc-3"}
    assert all("m-001" in material_ids for material_ids in account_materials.values())


def test_create_mode_excludes_fixture_source_and_fake_video_ids(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_source_materials(db_path, count=12)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE product_source_materials SET source = 'data/fixtures/product-source-materials.sample.json' WHERE material_id = 'm-001'"
        )
        conn.execute("UPDATE product_source_materials SET video_id = 'v001' WHERE material_id = 'm-002'")
        conn.execute("UPDATE product_source_materials SET material_type = 'title' WHERE material_id = 'm-003'")
        conn.execute("UPDATE product_source_materials SET cost_lookback = 2000, score = 2000 WHERE material_id >= 'm-005'")
        conn.execute("UPDATE product_source_material_metric_rollups SET stat_cost = 2000 WHERE material_id >= 'm-005'")
        conn.execute(
            """
            INSERT INTO source_material_bad_videos (
              product, source_advertiser_id, source_video_id, source_material_id,
              reason, status, source_workflow, first_seen_at, last_seen_at
            ) VALUES (
              '勇者突进', '1856647522964490', 'v28033gi0000d7m72bvog65s5f9la004', 'm-004',
              '400170 部分视频无权限或不存在', 'active', 'source_material_preload_to_accounts', 'now', 'now'
            )
            """
        )

    result = run_create_mode_request(
        {
            "create_mode": {
                "mode_key": "wx_pay_general_scale",
                "target_accounts": ["acc-1"],
                "target_date": "2026-05-13",
                "owner": "郭靖",
            }
        },
        db_path=db_path,
        runs_dir=tmp_path / "runs",
        policy={"create_strategy_plan": _policy()},
        template_catalog_path=Path("configs/create-templates/wx-mini-game.json"),
    )

    assert result["ok"] is True
    unit = result["create_strategy_plan"]["strategy"]["projects"][0]["units"][0]
    material_ids = {material["material_id"] for material in unit["materials"]}
    assert "m-001" not in material_ids
    assert "m-002" not in material_ids
    assert "m-003" not in material_ids
    assert "m-004" not in material_ids
    assert all(material["source_video_id"] != "v001" for material in unit["materials"])


def test_create_mode_blocks_when_material_selection_has_no_usable_candidates(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_source_materials(db_path, count=8)
    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE product_source_materials SET cost_lookback = 0, score = 0")
        conn.execute("UPDATE product_source_material_metric_rollups SET stat_cost = 0")

    result = run_create_mode_request(
        {
            "create_mode": {
                "mode_key": "wx_pay_male_recent_scale",
                "target_accounts": ["acc-1"],
                "target_date": "2026-05-13",
                "owner": "郭靖",
            }
        },
        db_path=db_path,
        runs_dir=tmp_path / "runs",
        policy={"create_strategy_plan": _policy()},
        template_catalog_path=Path("configs/create-templates/wx-mini-game.json"),
    )

    assert result["ok"] is False
    assert result["status"] == "blocked"
    assert result["summary"]["source_material_count"] == 0
    assert result["blocking_reasons"] == ["source material account has no usable materials"]


def test_create_mode_treats_blank_source_material_review_status_as_usable(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_source_materials(db_path, count=8)
    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE product_source_materials SET review_status = ''")
        conn.execute("UPDATE product_source_material_metric_rollups SET stat_cost = 2000")

    result = run_create_mode_request(
        {
            "create_mode": {
                "mode_key": "wx_pay_general_scale",
                "target_accounts": ["acc-1"],
                "target_date": "2026-05-13",
                "owner": "郭靖",
            }
        },
        db_path=db_path,
        runs_dir=tmp_path / "runs",
        policy={"create_strategy_plan": _policy()},
        template_catalog_path=Path("configs/create-templates/wx-mini-game.json"),
    )

    assert result["ok"] is True
    unit = result["create_strategy_plan"]["strategy"]["projects"][0]["units"][0]
    assert len(unit["materials"]) == 5


def test_create_mode_low_conversion_retest_filters_convert_range(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_source_materials(db_path, count=12)
    with sqlite3.connect(db_path) as conn:
        for index in range(1, 13):
            stat_cost = 500
            if index <= 2:
                stat_cost = 199
            if index >= 10:
                stat_cost = 1001
            conn.execute(
                "UPDATE product_source_materials SET cost_lookback = ?, score = ? WHERE material_id = ?",
                (stat_cost, stat_cost, f"m-{index:03d}"),
            )
            conn.execute(
                "UPDATE product_source_material_metric_rollups SET stat_cost = ?, convert_cnt = ? WHERE material_id = ?",
                (stat_cost, index - 1, f"m-{index:03d}"),
            )

    result = run_create_mode_request(
        {
            "create_mode": {
                "mode_key": "每付通投低转化复测",
                "target_accounts": ["acc-1"],
                "target_date": "2026-05-13",
                "owner": "郭靖",
            }
        },
        db_path=db_path,
        runs_dir=tmp_path / "runs",
        policy={"create_strategy_plan": _policy()},
        template_catalog_path=Path("configs/create-templates/wx-mini-game.json"),
    )

    assert result["ok"] is True
    unit = result["create_strategy_plan"]["strategy"]["projects"][0]["units"][0]
    convert_cnts = [material["convert_cnt"] for material in unit["materials"]]
    assert convert_cnts
    assert all(1 <= convert_cnt <= 5 for convert_cnt in convert_cnts)


def test_create_mode_no_conversion_retest_filters_old_low_cost_zero_conversion_materials(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_source_materials(db_path, count=12)
    with sqlite3.connect(db_path) as conn:
        for index in range(1, 13):
            stat_cost = 400
            convert_cnt = 0
            create_time = "2026-05-01T12:00:00+08:00"
            if index <= 2:
                convert_cnt = 1
            if 3 <= index <= 4:
                stat_cost = 600
            if 5 <= index <= 6:
                create_time = "2026-05-12T12:00:00+08:00"
            conn.execute(
                "UPDATE product_source_materials SET cost_lookback = ?, score = ?, create_time = ? WHERE material_id = ?",
                (stat_cost, stat_cost, create_time, f"m-{index:03d}"),
            )
            conn.execute(
                "UPDATE product_source_material_metric_rollups SET stat_cost = ?, convert_cnt = ?, create_time = ? WHERE material_id = ?",
                (stat_cost, convert_cnt, create_time, f"m-{index:03d}"),
            )

    result = run_create_mode_request(
        {
            "create_mode": {
                "mode_key": "每付通投无转化复测",
                "target_accounts": ["acc-1"],
                "target_date": "2026-05-13",
                "owner": "郭靖",
            }
        },
        db_path=db_path,
        runs_dir=tmp_path / "runs",
        policy={"create_strategy_plan": _policy()},
        template_catalog_path=Path("configs/create-templates/wx-mini-game.json"),
    )

    assert result["ok"] is True
    unit = result["create_strategy_plan"]["strategy"]["projects"][0]["units"][0]
    assert unit["materials"]
    assert all(material["convert_cnt"] == 0 for material in unit["materials"])
    assert all(material["stat_cost"] <= 500 for material in unit["materials"])
    assert all(material["create_time"].startswith("2026-05-01") for material in unit["materials"])


def test_create_mode_candidate_pool_limit_uses_newest_materials_before_shuffle(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_source_materials(db_path, count=10)
    with sqlite3.connect(db_path) as conn:
        for index in range(1, 11):
            create_time = f"2026-05-{index:02d}T12:00:00+08:00"
            conn.execute(
                "UPDATE product_source_materials SET create_time = ?, cost_lookback = 1000, score = 1000 WHERE material_id = ?",
                (create_time, f"m-{index:03d}"),
            )
            conn.execute(
                "UPDATE product_source_material_metric_rollups SET create_time = ?, stat_cost = 1000 WHERE material_id = ?",
                (create_time, f"m-{index:03d}"),
            )
    mode_path = tmp_path / "mode.json"
    mode_path.write_text(
        json.dumps(
            {
                "mode_key": "test_recent_pool",
                "display_name": "测试最近素材池",
                "product": "勇者突进",
                "platform": "WECHAT_GAME",
                "template_key": "wx_pay_general",
                "template_name_suffix": "测新",
                "source_advertiser_id": "1856647522964490",
                "organization_id": "1851650746645060",
                "defaults": {"daily_budget": 10000, "cpa_bid": 105, "project_count": 1, "units_per_project": 1},
                "material_requirements": {
                    "material_type": "video",
                    "materials_per_unit": 3,
                    "dedupe_scope": "max_account_overlap",
                    "max_cross_account_overlap_ratio": 0.3,
                    "allow_reuse_across_accounts": True,
                    "on_insufficient": "allow_reuse",
                },
                "material_selection": {
                    "lookback_days": 30,
                    "selection_type": "test_new",
                    "sort_by": "create_time_desc",
                    "random_shuffle": True,
                    "candidate_pool_limit": 3,
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = run_create_mode_request(
        {
            "create_mode": {
                "mode_config_path": str(mode_path),
                "target_accounts": ["acc-1"],
                "target_date": "2026-05-13",
                "owner": "郭靖",
            }
        },
        db_path=db_path,
        runs_dir=tmp_path / "runs",
        policy={"create_strategy_plan": _policy()},
        template_catalog_path=Path("configs/create-templates/wx-mini-game.json"),
    )

    unit = result["create_strategy_plan"]["strategy"]["projects"][0]["units"][0]
    selected_ids = {material["material_id"] for material in unit["materials"]}
    assert selected_ids <= {"m-008", "m-009", "m-010"}


def test_create_mode_test_new_uses_effective_create_date_from_rollup(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_source_materials(db_path, count=10)
    with sqlite3.connect(db_path) as conn:
        for index in range(1, 11):
            window_seen_date = "2026-05-13" if index <= 7 else f"2026-05-{index:02d}"
            global_seen_date = f"2026-02-{index:02d}" if index <= 7 else f"2026-05-{index:02d}"
            conn.execute(
                "UPDATE product_source_materials SET create_time = '2026-04-25 12:00:00', cost_lookback = 1000, score = 1000 WHERE material_id = ?",
                (f"m-{index:03d}",),
            )
            conn.execute(
                """
                UPDATE product_source_material_metric_rollups
                SET create_time = '2026-04-25 12:00:00',
                    first_seen_metric_date = ?,
                    effective_create_date = ?,
                    effective_create_date_source = 'material_daily_metrics',
                    stat_cost = 1000
                WHERE material_id = ?
                """,
                (window_seen_date, window_seen_date, f"m-{index:03d}"),
            )
            conn.execute(
                """
                INSERT INTO product_source_material_metric_rollups (
                  product, source_advertiser_id, organization_id, window_key, window_days,
                  period_start, period_end, material_id, material_type, source_video_id,
                  name, review_status, stat_cost, source, synced_at,
                  first_seen_metric_date, effective_create_date, effective_create_date_source
                ) VALUES ('勇者突进', '1856647522964490', '1851650746645060', 'all_history', 0,
                  '2026-02-10', '2026-05-13', ?, 'video', ?, ?, 'APPROVED', 1000, 'test', 'now',
                  ?, ?, 'material_daily_metrics')
                """,
                (
                    f"m-{index:03d}",
                    f"v28033gi0000d7m72bvog65s5f9la{index:03d}",
                    f"素材{index:03d}",
                    global_seen_date,
                    global_seen_date,
                ),
            )
    mode_path = tmp_path / "mode.json"
    mode_path.write_text(
        json.dumps(
            {
                "mode_key": "test_effective_create_date",
                "display_name": "测试有效创建日期",
                "product": "勇者突进",
                "platform": "WECHAT_GAME",
                "template_key": "wx_pay_general",
                "template_name_suffix": "测新",
                "source_advertiser_id": "1856647522964490",
                "organization_id": "1851650746645060",
                "defaults": {"daily_budget": 10000, "cpa_bid": 105, "project_count": 1, "units_per_project": 1},
                "material_requirements": {
                    "material_type": "video",
                    "materials_per_unit": 3,
                    "dedupe_scope": "max_account_overlap",
                    "max_cross_account_overlap_ratio": 0.3,
                    "allow_reuse_across_accounts": True,
                    "on_insufficient": "allow_reuse",
                },
                "material_selection": {
                    "lookback_days": 30,
                    "first_seen_days": 7,
                    "selection_type": "test_new",
                    "sort_by": "create_time_desc",
                    "random_shuffle": True,
                    "candidate_pool_limit": 3,
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = run_create_mode_request(
        {
            "create_mode": {
                "mode_config_path": str(mode_path),
                "target_accounts": ["acc-1"],
                "target_date": "2026-05-13",
                "owner": "郭靖",
            }
        },
        db_path=db_path,
        runs_dir=tmp_path / "runs",
        policy={"create_strategy_plan": _policy()},
        template_catalog_path=Path("configs/create-templates/wx-mini-game.json"),
    )

    unit = result["create_strategy_plan"]["strategy"]["projects"][0]["units"][0]
    selected_ids = {material["material_id"] for material in unit["materials"]}
    assert selected_ids <= {"m-008", "m-009", "m-010"}
    assert all(material["effective_create_date"].startswith("2026-05-") for material in unit["materials"])
    assert "m-001" not in selected_ids


def test_run_create_mode_cli_prints_json_summary(tmp_path: Path, capsys):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_source_materials(db_path, count=12)
    runtime_path = tmp_path / "runtime.json"
    runtime_path.write_text(
        json.dumps(
            {
                "environment": "test",
                "phase": "phase1",
                "database_path": str(db_path),
                "runs_dir": str(tmp_path / "runs"),
                "fixtures_dir": str(tmp_path / "fixtures"),
                "external_api_enabled": False,
                "execution_enabled": False,
            }
        ),
        encoding="utf-8",
    )
    mode_path = tmp_path / "mode.json"
    mode_path.write_text(
        json.dumps(
            {
                "mode_key": "wx_7r_general_scale",
                "display_name": "7R 历史放量",
                "product": "勇者突进",
                "platform": "WECHAT_GAME",
                "template_key": "wx_7r_general",
                "template_name_suffix": "历史放量",
                "source_advertiser_id": "1856647522964490",
                "organization_id": "1851650746645060",
                "defaults": {
                    "daily_budget": 88888,
                    "cpa_bid": 103,
                    "roi_coefficient": 0.419,
                    "project_count": 1,
                    "units_per_project": 1,
                },
                "material_requirements": {"material_type": "video", "materials_per_unit": 5, "dedupe_scope": "allow_reuse"},
                "material_selection": {"lookback_days": 30, "selection_type": "high_spend", "min_stat_cost": 0},
                "initial_status": {"project_operation": "ENABLE", "unit_operation": "ENABLE"},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    request_path = tmp_path / "request.json"
    request_path.write_text(
        json.dumps(
            {
                "create_mode": {
                    "mode_config_path": str(mode_path),
                    "target_accounts": ["acc-1"],
                    "target_date": "2026-05-13",
                    "owner": "郭靖",
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    script = _load_script("run_create_mode")
    code = script.run_from_args(
        [
            "--config",
            str(runtime_path),
            "--request",
            str(request_path),
            "--policy",
            "policies/create-policy.example.json",
            "--template-catalog",
            "configs/create-templates/wx-mini-game.json",
        ]
    )

    captured = capsys.readouterr()
    output = json.loads(captured.out)
    assert code == 0
    assert output["ok"] is True
    assert output["workflow"] == "create_mode"
    assert output["summary"]["planned_project_count"] == 1


def test_run_create_mode_cli_builds_request_from_mode_and_accounts(tmp_path: Path, capsys):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_source_materials(db_path, count=20)
    runtime_path = tmp_path / "runtime.json"
    runtime_path.write_text(
        json.dumps(
            {
                "environment": "test",
                "phase": "phase1",
                "database_path": str(db_path),
                "runs_dir": str(tmp_path / "runs"),
                "fixtures_dir": str(tmp_path / "fixtures"),
                "external_api_enabled": False,
                "execution_enabled": False,
            }
        ),
        encoding="utf-8",
    )

    script = _load_script("run_create_mode")
    code = script.run_from_args(
        [
            "--config",
            str(runtime_path),
            "--mode",
            "每付通投近期放量",
            "--account",
            "acc-1",
            "--accounts",
            "acc-2,acc-3",
            "--target-date",
            "2026-05-13",
            "--owner",
            "郭靖",
            "--policy",
            "policies/create-policy.example.json",
            "--template-catalog",
            "configs/create-templates/wx-mini-game.json",
        ]
    )

    captured = capsys.readouterr()
    output = json.loads(captured.out)
    assert code == 0
    assert output["ok"] is True
    assert output["mode_key"] == "wx_pay_general_recent_scale"
    assert output["summary"]["planned_project_count"] == 15
    assert output["summary"]["planned_unit_count"] == 15
