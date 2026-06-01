import importlib.util
import json
import sqlite3
from pathlib import Path

from roibang_v2.db.bootstrap import bootstrap_database
from roibang_v2.workflows.create_project_suggestions import build_create_project_suggestions
from roibang_v2.workflows.create_project_suggestions import run_create_project_suggestions_request


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _seed_project(tmp_path: Path) -> dict[str, Path]:
    db_path = tmp_path / "data" / "roibang_v2.sqlite3"
    bootstrap_database(db_path)
    _write_json(
        tmp_path / "configs" / "products" / "demo-game.local.json",
        {
            "product_key": "demo-game",
            "product": "演示游戏",
            "platform": "WECHAT_GAME",
            "source_advertiser_id": "source-1",
            "organization_id": "org-1",
            "allowed_target_accounts_path": "configs/allowed-create-accounts.demo-game.local.json",
        },
    )
    _write_json(
        tmp_path / "configs" / "allowed-create-accounts.demo-game.local.json",
        {
            "product_key": "demo-game",
            "product": "演示游戏",
            "allowed_target_accounts": [
                {"advertiser_id": "1001", "account_name": "演示账户一", "enable": True},
                {"advertiser_id": "1002", "account_name": "演示账户二", "enable": True},
            ],
        },
    )
    _write_json(
        tmp_path / "configs" / "create-modes" / "demo-game" / "wx_pay_general_recent_scale.local.json",
        {
            "mode_key": "wx_pay_general_recent_scale",
            "display_name": "演示游戏 每付通投近期放量",
            "product_key": "demo-game",
            "product": "演示游戏",
            "template_key": "wx_pay_general",
            "defaults": {"daily_budget": 88888, "project_count": 5, "units_per_project": 1},
        },
    )
    strategy_path = tmp_path / "configs" / "create-suggestion-strategies" / "demo-game.local.json"
    _write_json(
        strategy_path,
        {
            "strategy_id": "recent-scale-capacity-v1",
            "strategy_version": "2026-05-31",
            "enabled": True,
            "product_key": "demo-game",
            "mode_key": "wx_pay_general_recent_scale",
            "target_date": "latest",
            "account": {"require_allowed_account": True, "max_active_projects": 2, "cooldown_days_after_create": 0},
            "materials": {
                "window_key": "last_7d",
                "material_type": "video",
                "min_qualified_material_count": 3,
                "min_stat_cost": 200,
                "min_convert_cnt": 0,
                "min_roi_1day": 0,
            },
            "recommendation": {"project_count": 1, "units_per_project": 1, "daily_budget": 88888},
        },
    )
    with sqlite3.connect(db_path) as conn:
        for account_id, account_name in [("1001", "演示账户一"), ("1002", "演示账户二")]:
            conn.execute(
                """
                INSERT INTO account_pool (advertiser_id, account_name, product, platform, source, synced_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (account_id, account_name, "演示游戏", "WECHAT_GAME", "unit_test", "2026-05-31T00:00:00+08:00"),
            )
        conn.execute(
            """
            INSERT INTO projects (project_id, advertiser_id, name, status, source, synced_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("p-1001-active", "1001", "演示游戏-在跑项目", "PROJECT_STATUS_ENABLE", "unit_test", "now"),
        )
        for index in range(2):
            conn.execute(
                """
                INSERT INTO projects (project_id, advertiser_id, name, status, source, synced_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (f"p-1002-active-{index}", "1002", f"演示游戏-满额项目{index}", "PROJECT_STATUS_ENABLE", "unit_test", "now"),
            )
        for index in range(4):
            conn.execute(
                """
                INSERT INTO product_source_material_metric_rollups (
                  product, source_advertiser_id, organization_id, window_key, window_days,
                  period_start, period_end, material_id, material_type, source_video_id,
                  name, stat_cost, convert_cnt, roi_1day_cost_weighted, roi_7days_cost_weighted,
                  source, synced_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "演示游戏",
                    "source-1",
                    "org-1",
                    "last_7d",
                    7,
                    "2026-05-25",
                    "2026-05-31",
                    f"m-{index}",
                    "video",
                    f"v-{index}",
                    f"素材 {index}",
                    300 + index,
                    index,
                    0.1,
                    0.2,
                    "unit_test",
                    "now",
                ),
            )
    return {"db_path": db_path, "strategy_path": strategy_path}


def _load_script():
    script_path = Path("scripts/run_create_project_suggestions.py")
    spec = importlib.util.spec_from_file_location("run_create_project_suggestions", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_create_project_suggestions_generate_readonly_suggestion_and_block_full_account(tmp_path: Path):
    paths = _seed_project(tmp_path)

    result = build_create_project_suggestions(
        db_path=paths["db_path"],
        project_root=tmp_path,
        products_dir=tmp_path / "configs" / "products",
        mode_dir=tmp_path / "configs" / "create-modes",
        strategy_dir=tmp_path / "configs" / "create-suggestion-strategies",
        product_key="demo-game",
    )

    assert result["workflow"] == "create_project_suggestions"
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 0
    assert result["summary"]["suggestion_count"] == 1
    assert result["summary"]["blocked_suggestion_count"] == 1
    suggestion = result["suggestions"][0]
    assert suggestion["suggested_action"] == "suggest_create_project"
    assert suggestion["advertiser_id"] == "1001"
    assert suggestion["mode_key"] == "wx_pay_general_recent_scale"
    assert suggestion["strategy_id"] == "recent-scale-capacity-v1"
    assert suggestion["execution_enabled"] is False
    assert suggestion["evidence"]["qualified_material_count"] == 4
    blocked = result["blocked_suggestions"][0]
    assert blocked["advertiser_id"] == "1002"
    assert "已达到策略上限" in "；".join(blocked["blocking_reasons"])


def test_create_project_suggestions_filters_recent_spend_candidates_and_applies_limit(tmp_path: Path):
    paths = _seed_project(tmp_path)
    _write_json(
        tmp_path / "configs" / "allowed-create-accounts.demo-game.local.json",
        {
            "product_key": "demo-game",
            "product": "演示游戏",
            "allowed_target_accounts": [
                {"advertiser_id": "1001", "account_name": "演示账户一", "enable": True},
                {"advertiser_id": "1002", "account_name": "演示账户二", "enable": True},
                {"advertiser_id": "1003", "account_name": "演示账户三", "enable": True},
            ],
        },
    )
    _write_json(
        paths["strategy_path"],
        {
            "strategy_id": "recent-spend-scale-v1",
            "strategy_version": "2026-05-31",
            "enabled": True,
            "product_key": "demo-game",
            "mode_key": "wx_pay_general_recent_scale",
            "target_date": "latest",
            "account": {
                "candidate_scope": "allowed_accounts_with_recent_spend",
                "recent_window_days": 1,
                "min_recent_stat_cost": 100,
                "min_recent_convert_cnt": 1,
                "require_allowed_account": True,
                "max_active_projects": 20,
                "cooldown_days_after_create": 0,
            },
            "materials": {
                "window_key": "last_7d",
                "material_type": "video",
                "min_qualified_material_count": 3,
                "min_stat_cost": 200,
                "min_convert_cnt": 0,
                "min_roi_1day": 0,
            },
            "recommendation": {"project_count": 1, "units_per_project": 1, "daily_budget": 88888},
            "limits": {"max_suggestions_per_run": 1},
        },
    )
    with sqlite3.connect(paths["db_path"]) as conn:
        conn.execute(
            """
            INSERT INTO account_pool (advertiser_id, account_name, product, platform, source, synced_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("1003", "演示账户三", "演示游戏", "WECHAT_GAME", "unit_test", "2026-05-31T00:00:00+08:00"),
        )
        for advertiser_id, cost, convert in [("1001", 300, 1), ("1002", 0, 0), ("1003", 500, 2)]:
            conn.execute(
                """
                INSERT INTO material_daily_metrics (
                  metric_date, advertiser_id, project_id, project_name, promotion_id, promotion_name,
                  material_id, material_kind, stat_cost, convert_cnt, source, synced_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "2026-05-31",
                    advertiser_id,
                    f"p-{advertiser_id}",
                    f"演示游戏-{advertiser_id}",
                    "unit-1",
                    "单元",
                    f"metric-{advertiser_id}",
                    "video",
                    cost,
                    convert,
                    "unit_test",
                    "now",
                ),
            )

    result = build_create_project_suggestions(
        db_path=paths["db_path"],
        project_root=tmp_path,
        products_dir=tmp_path / "configs" / "products",
        mode_dir=tmp_path / "configs" / "create-modes",
        strategy_dir=tmp_path / "configs" / "create-suggestion-strategies",
        product_key="demo-game",
    )

    assert result["summary"]["suggestion_count"] == 1
    assert result["summary"]["blocked_suggestion_count"] == 0
    suggestion = result["suggestions"][0]
    assert suggestion["advertiser_id"] == "1003"
    assert suggestion["evidence"]["candidate_scope"] == "allowed_accounts_with_recent_spend"
    assert suggestion["evidence"]["recent_metrics"]["stat_cost"] == 500
    assert suggestion["thresholds"]["min_recent_stat_cost"] == 100


def test_create_project_suggestions_run_writes_artifact_without_execution(tmp_path: Path):
    paths = _seed_project(tmp_path)

    result = run_create_project_suggestions_request(
        {
            "db_path": str(paths["db_path"]),
            "project_root": str(tmp_path),
            "products_dir": str(tmp_path / "configs" / "products"),
            "mode_dir": str(tmp_path / "configs" / "create-modes"),
            "strategy_paths": [str(paths["strategy_path"])],
            "product_key": "demo-game",
        },
        runs_dir=tmp_path / "data" / "runs",
    )

    assert result["ok"] is True
    assert result["artifact_path"].endswith(".json")
    assert Path(result["artifact_path"]).exists()
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 0


def test_create_project_suggestions_cli_is_readonly(tmp_path: Path):
    paths = _seed_project(tmp_path)
    runtime_path = tmp_path / "configs" / "runtime.local.json"
    _write_json(
        runtime_path,
        {
            "environment": "test",
            "phase": "phase1",
            "database_path": str(paths["db_path"]),
            "runs_dir": str(tmp_path / "data" / "runs"),
            "fixtures_dir": str(tmp_path / "fixtures"),
            "external_api_enabled": False,
            "execution_enabled": False,
        },
    )

    module = _load_script()
    exit_code = module.run_from_args(
        [
            "--config",
            str(runtime_path),
            "--project-root",
            str(tmp_path),
            "--products-dir",
            str(tmp_path / "configs" / "products"),
            "--mode-dir",
            str(tmp_path / "configs" / "create-modes"),
            "--strategy",
            str(paths["strategy_path"]),
            "--product-key",
            "demo-game",
        ]
    )

    assert exit_code == 0
    assert list((tmp_path / "data" / "runs" / "create_project_suggestions").glob("*.json"))
