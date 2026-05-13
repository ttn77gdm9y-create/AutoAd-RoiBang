import importlib.util
import json
import sqlite3
from pathlib import Path

import pytest

from roibang_v2.db.bootstrap import bootstrap_database
from roibang_v2.workflows.create_plan_from_strategy import build_create_plans_from_strategy


def _materials(count: int) -> list[dict]:
    return [
        {
            "source_material_id": f"material-{index}",
            "source_video_id": f"video-{index}",
            "name": f"Material {index}",
        }
        for index in range(1, count + 1)
    ]


def _strategy() -> dict:
    return {
        "strategy_id": "strategy-20260511-001",
        "operator": "郭靖",
        "product": "勇者突进",
        "platform": "WECHAT_GAME",
        "target_date": "2026-05-11",
        "batch_generated_at": "2026-05-11T18:00:00+08:00",
        "source_advertiser_id": "1856647522964490",
        "pool_key": "yzt-source-all-history-video",
        "defaults": {
            "daily_budget": 3000,
            "cpa_bid": 103,
            "materials_per_unit": 4,
            "dedupe_scope": "request",
        },
        "materials": _materials(8),
        "plan_groups": [
            {
                "plan_id": "strategy-20260511-001-wx-7r-male",
                "template_key": "wx_7r_male",
                "template_name": "微小每付7R男",
                "roi_coefficient": 0.41,
                "target_accounts": [
                    {
                        "advertiser_id": "1856647523922953",
                        "project_count": 1,
                        "unit_count_per_project": 1,
                    }
                ],
            },
            {
                "plan_id": "strategy-20260511-001-wx-pay-general",
                "template_key": "wx_pay_general",
                "template_name": "微小每付通投",
                "target_accounts": [
                    {
                        "advertiser_id": "1856647524935691",
                        "project_count": 1,
                        "unit_count_per_project": 1,
                    }
                ],
            },
        ],
    }


def _template_catalog() -> dict:
    return {
        "templates": {
            "wx_7r_male": {"project_template_name": "微小每付7R男", "requires_roi_goal": True},
            "wx_pay_general": {"project_template_name": "微小每付通投", "requires_roi_goal": False},
        }
    }


def _seed_preview_db(db_path: Path) -> None:
    bootstrap_database(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO account_pool (
              advertiser_id, account_name, product, platform, historical_spend, source, synced_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("target-1", "目标账户1", "勇者突进", "WECHAT_GAME", 1000, "unit_test", "2026-05-11T00:00:00Z"),
        )
        for index, material_id in enumerate(["m-high", "m-mid", "m-low", "m-extra"], start=1):
            conn.execute(
                """
                INSERT INTO materials (
                  material_id, name, material_type, video_id,
                  review_status, cost_lookback, score, source, synced_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    material_id,
                    f"素材{index}",
                    "video",
                    f"source-video-{index}",
                    "APPROVED",
                    100,
                    100,
                    "unit_test",
                    "2026-05-11T00:00:00Z",
                ),
            )


def _preview_strategy() -> dict:
    strategy = {
        **_strategy(),
        "source_advertiser_id": "source-1",
        "organization_id": "org-1",
        "pool_key": "pool-yzt-wx-7r",
        "materials": [
            {"source_material_id": "m-high", "source_video_id": "source-video-1"},
            {"source_material_id": "m-mid", "source_video_id": "source-video-2"},
            {"source_material_id": "m-low", "source_video_id": "source-video-3"},
            {"source_material_id": "m-extra", "source_video_id": "source-video-4"},
        ],
    }
    strategy["plan_groups"] = [
        {
            "plan_id": "strategy-20260511-001-preview",
            "template_key": "wx_7r_male",
            "template_name": "微小每付7R男",
            "roi_coefficient": 0.41,
            "target_accounts": [
                {
                    "advertiser_id": "target-1",
                    "project_count": 1,
                    "unit_count_per_project": 1,
                    "daily_budget": 300,
                }
            ],
        }
    ]
    return strategy


def _preview_policy() -> dict:
    return {
        "first_live_run": {
            "advertiser_id": "target-1",
            "max_project_count": 1,
            "max_unit_count": 1,
            "max_material_count": 4,
        },
        "create_plan": {
            "max_target_accounts": 2,
            "max_projects_per_account": 3,
            "max_units_per_project": 3,
            "max_materials": 10,
            "min_daily_budget": 100,
            "max_daily_budget": 1000,
        },
        "create_strategy_plan": {
            "project_naming": {
                "template": "{target_date_mmdd}_{owner}_{product}_{project_template_name}_{batch_code}_{index}",
                "index_width": 2,
                "invalid_char_replacement": "_",
            }
        },
        "create_preflight": {
            "require_account_pool": True,
            "reject_existing_project_names": True,
            "min_daily_budget": 100,
            "max_daily_budget": 1000,
            "max_project_name_length": 80,
            "project_name_pattern": "^\\d{4}_.+_.+_.+_B[0-9A-F]{8}_\\d{2}$",
            "required_field_defaults": ["landing_type", "pricing", "inventory_type"],
        },
        "create_dry_run": {
            "max_projects_per_dry_run": 50,
            "max_units_per_dry_run": 500,
            "provider_field_map_path": "configs/provider-field-maps/oceanengine.create.phase1.example.json",
        },
        "create_phase2_template_slot_prep": {
            "product_template_catalog": {
                "product": "勇者突进",
                "platform": "WECHAT_GAME",
                "script_scope": "勇者突进微信小游戏专用",
                "templates": [
                    {
                        "template_key": "wx_7r_male",
                        "project_template_name": "微小每付7R男",
                        "requires_roi_goal": True,
                        "source_name": "勇者突进-福利版",
                        "product_name": "勇者突进-福利版",
                        "title_pool": ["标题1", "标题2", "标题3", "标题4"],
                        "product_selling_points": ["卖点1", "卖点2", "卖点3"],
                        "cta_pool": ["点击即玩", "不用下载", "全场免费"],
                        "delivery_identity": "AWEME",
                        "aweme_ids": ["aweme-1"],
                        "anchor_related_type": "SELECT",
                        "anchor_id": "anchor-fixed",
                        "anchor_type": "APP_GAME",
                    }
                ],
            }
        },
    }


def _load_script(name: str):
    script_path = Path(f"scripts/{name}.py")
    spec = importlib.util.spec_from_file_location(name, script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_strategy_expands_to_separate_create_plans_without_reusing_materials():
    result = build_create_plans_from_strategy(_strategy(), template_catalog=_template_catalog())

    assert result["ok"] is True
    assert result["workflow"] == "create_plan_from_strategy"
    assert result["external_api_calls"] == 0
    assert result["summary"]["create_plan_count"] == 2

    first, second = result["create_plans"]
    assert first["template_key"] == "wx_7r_male"
    assert first["roi_coefficient"] == 0.41
    assert first["cpa_bid"] == 103
    assert first["target_accounts"][0]["daily_budget"] == 3000
    assert [row["source_material_id"] for row in first["materials"]] == [
        "material-1",
        "material-2",
        "material-3",
        "material-4",
    ]

    assert second["template_key"] == "wx_pay_general"
    assert "roi_coefficient" not in second
    assert [row["source_material_id"] for row in second["materials"]] == [
        "material-5",
        "material-6",
        "material-7",
        "material-8",
    ]


def test_strategy_blocks_non_7r_roi_and_short_material_pool():
    strategy = _strategy()
    strategy["materials"] = _materials(2)
    strategy["plan_groups"][1]["roi_coefficient"] = 0.42

    result = build_create_plans_from_strategy(strategy, template_catalog=_template_catalog())

    assert result["ok"] is False
    assert "plan_groups[1].roi_coefficient is only allowed for 7R templates" in result["violations"]
    assert "materials has 2 items, expected at least 8 for dedupe_scope=request" in result["violations"]


def test_create_plan_from_strategy_cli_writes_local_plan_files(tmp_path: Path, capsys):
    strategy_path = tmp_path / "strategy.local.json"
    template_path = tmp_path / "templates.json"
    output_dir = tmp_path / "create-plans"
    runtime_path = tmp_path / "runtime.json"
    policy_path = tmp_path / "policy.json"
    strategy_path.write_text(json.dumps(_strategy(), ensure_ascii=False), encoding="utf-8")
    template_path.write_text(json.dumps(_template_catalog(), ensure_ascii=False), encoding="utf-8")
    runtime_path.write_text(
        json.dumps(
            {
                "environment": "test",
                "phase": "phase2",
                "database_path": str(tmp_path / "roibang.sqlite3"),
                "runs_dir": str(tmp_path / "runs"),
                "fixtures_dir": "data/fixtures",
                "external_api_enabled": False,
                "execution_enabled": False,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    policy_path.write_text(json.dumps({"create_plan": {"max_materials": 20}}, ensure_ascii=False), encoding="utf-8")
    module = _load_script("run_create_plan_from_strategy")

    exit_code = module.run_from_args(
        [
            "--config",
            str(runtime_path),
            "--strategy",
            str(strategy_path),
            "--policy",
            str(policy_path),
            "--template-catalog",
            str(template_path),
            "--output-dir",
            str(output_dir),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["ok"] is True
    assert output["summary"]["create_plan_count"] == 2
    assert len(output["plan_file_paths"]) == 2
    assert (output_dir / "strategy-20260511-001-wx-7r-male.local.json").exists()
    assert (output_dir / "strategy-20260511-001-wx-pay-general.local.json").exists()


def test_create_plan_from_strategy_cli_rejects_removed_local_chain_flag(tmp_path: Path):
    strategy_path = tmp_path / "strategy.local.json"
    template_path = tmp_path / "templates.json"
    output_dir = tmp_path / "create-plans"
    runtime_path = tmp_path / "runtime.json"
    policy_path = tmp_path / "policy.json"
    db_path = tmp_path / "roibang.sqlite3"
    _seed_preview_db(db_path)
    strategy_path.write_text(json.dumps(_preview_strategy(), ensure_ascii=False), encoding="utf-8")
    template_path.write_text(json.dumps(_template_catalog(), ensure_ascii=False), encoding="utf-8")
    runtime_path.write_text(
        json.dumps(
            {
                "environment": "test",
                "phase": "phase2",
                "database_path": str(db_path),
                "runs_dir": str(tmp_path / "runs"),
                "fixtures_dir": "data/fixtures",
                "external_api_enabled": False,
                "execution_enabled": False,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    policy_path.write_text(json.dumps(_preview_policy(), ensure_ascii=False), encoding="utf-8")
    module = _load_script("run_create_plan_from_strategy")

    with pytest.raises(SystemExit) as exc:
        module.run_from_args(
            [
                "--config",
                str(runtime_path),
                "--strategy",
                str(strategy_path),
                "--policy",
                str(policy_path),
                "--template-catalog",
                str(template_path),
                "--output-dir",
                str(output_dir),
                "--run-local-chain",
            ]
        )

    assert exc.value.code == 2
