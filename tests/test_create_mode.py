import importlib.util
import json
import sqlite3
from pathlib import Path

from roibang_v2.db.bootstrap import bootstrap_database
from roibang_v2.workflows.create_mode import build_create_mode_request, load_create_mode_config, run_create_mode_request


def _seed_source_materials(db_path: Path, count: int = 80) -> None:
    bootstrap_database(db_path)
    with sqlite3.connect(db_path) as conn:
        for index in range(1, count + 1):
            material_id = f"m-{index:03d}"
            conn.execute(
                """
                INSERT INTO materials (
                  material_id, name, material_type, video_id,
                  review_status, cost_lookback, score, source, synced_at
                ) VALUES (?, ?, 'video', ?, 'APPROVED', ?, ?, 'test', 'now')
                """,
                (material_id, f"素材{index:03d}", f"v-{index:03d}", 1000 - index, 1000 - index),
            )
            conn.execute(
                """
                INSERT INTO product_source_materials (
                  product, source_advertiser_id, organization_id, material_id,
                  video_id, name, material_type, review_status, is_active,
                  cost_lookback, score, source, synced_at
                ) VALUES ('勇者突进', '1856647522964490', '1851650746645060', ?, ?, ?, 'video', 'APPROVED', 1, ?, ?, 'test', 'now')
                """,
                (material_id, f"v-{index:03d}", f"素材{index:03d}", 1000 - index, 1000 - index),
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
                (material_id, f"v-{index:03d}", f"素材{index:03d}", 1000 - index),
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


def test_create_mode_builds_scale_create_request_from_mode_config():
    mode = {
        "mode_key": "wx_7r_general_scale",
        "display_name": "7R 放量",
        "product": "勇者突进",
        "platform": "WECHAT_GAME",
        "template_key": "wx_7r_general",
        "template_name_suffix": "放量",
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
        "material_selection": {"lookback_days": 60, "selection_type": "high_spend"},
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
    assert request["project_template_name"] == "微小每付7R通投放量"
    assert request["target_accounts"] == [
        {"advertiser_id": "acc-1", "project_count": 5, "units_per_project": 1, "daily_budget": 88888},
        {"advertiser_id": "acc-2", "project_count": 5, "units_per_project": 1, "daily_budget": 88888},
    ]
    assert request["field_defaults"]["cpa_bid"] == 103
    assert request["field_defaults"]["roi_goal"] == 0.419
    assert request["material_requirements"]["materials_per_unit"] == 5
    assert request["material_requirements"]["max_cross_account_overlap_ratio"] == 0.3
    assert request["material_selection"]["source_scope"] == "source_material_account"
    assert request["material_selection"]["min_stat_cost"] == 1000
    assert request["material_selection"]["sort_by"] == "stat_cost_desc"
    assert request["material_selection"]["random_shuffle"] is True
    assert request["material_selection"]["exclude_recent_used_days"] == 0
    assert request["initial_status"] == {"project_operation": "ENABLE", "unit_operation": "ENABLE"}


def test_bundled_create_modes_cover_7r_and_pay_scale_and_test_new():
    template_catalog = json.loads(Path("configs/create-templates/wx-mini-game.json").read_text(encoding="utf-8"))
    expected = {
        "wx_7r_general_scale": ("wx_7r_general", "微小每付7R通投放量", 0.419, "7R 通投放量"),
        "wx_7r_general_test_new": ("wx_7r_general", "微小每付7R通投测新", 0.41, "7R 通投测新"),
        "wx_7r_male_scale": ("wx_7r_male", "微小每付7R男放量", 0.419, "7R 男放量"),
        "wx_7r_male_test_new": ("wx_7r_male", "微小每付7R男测新", 0.41, "7R 男测新"),
        "wx_pay_general_scale": ("wx_pay_general", "微小每付通投放量", None, "每付通投放量"),
        "wx_pay_general_test_new": ("wx_pay_general", "微小每付通投测新", None, "每付通投测新"),
        "wx_pay_male_scale": ("wx_pay_male", "微小每付男放量", None, "每付男放量"),
        "wx_pay_male_test_new": ("wx_pay_male", "微小每付男测新", None, "每付男测新"),
    }
    for mode_key, (template_key, project_template_name, roi_goal, display_name) in expected.items():
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
        assert request["material_selection"]["source_scope"] == "source_material_account"
        assert request["material_selection"]["exclude_recent_used_days"] == 0
        assert request["material_requirements"]["dedupe_scope"] == "max_account_overlap"
        assert request["material_requirements"]["allow_reuse_across_accounts"] is True
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
    assert load_create_mode_config({"mode_key": "7R 通投放量"})["mode_key"] == "wx_7r_general_scale"
    assert load_create_mode_config({"mode_key": "7R 男测新"})["mode_key"] == "wx_7r_male_test_new"
    assert load_create_mode_config({"mode_key": "每付男放量"})["mode_key"] == "wx_pay_male_scale"

    try:
        load_create_mode_config({"mode_key": "7R 放量"})
    except ValueError as exc:
        assert "需要指定通投或男" in str(exc)
    else:
        raise AssertionError("7R 放量 must be rejected as ambiguous")


def test_create_mode_generates_strategy_plan_with_enabled_initial_status_and_overlap_cap(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_source_materials(db_path, count=40)
    mode_path = tmp_path / "wx_7r_general_test_new.json"
    mode_path.write_text(
        json.dumps(
            {
                "mode_key": "wx_7r_general_test_new",
                "display_name": "7R 测新",
                "product": "勇者突进",
                "platform": "WECHAT_GAME",
                "template_key": "wx_7r_general",
                "template_name_suffix": "测新",
                "source_advertiser_id": "1856647522964490",
                "organization_id": "1851650746645060",
                "defaults": {
                    "daily_budget": 10000,
                    "cpa_bid": 105,
                    "roi_coefficient": 0.41,
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
    assert plan["request"]["project_template_name"] == "微小每付7R通投测新"
    assert plan["strategy"]["projects"][0]["operation"] == "ENABLE"
    assert plan["strategy"]["projects"][0]["units"][0]["operation"] == "ENABLE"
    assert "测新" in plan["strategy"]["projects"][0]["project_name"]
    assert Path(result["artifact_path"]).exists()


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
                "display_name": "7R 放量",
                "product": "勇者突进",
                "platform": "WECHAT_GAME",
                "template_key": "wx_7r_general",
                "template_name_suffix": "放量",
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
                "material_selection": {"lookback_days": 60, "selection_type": "high_spend"},
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
