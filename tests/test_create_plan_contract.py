import importlib.util
import json
import sqlite3
from pathlib import Path

from roibang_v2.db.bootstrap import bootstrap_database
from roibang_v2.workflows.create_plan_contract import validate_create_plan


def _load_script(name: str):
    script_path = Path(f"scripts/{name}.py")
    spec = importlib.util.spec_from_file_location(name, script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _runtime_config(tmp_path: Path) -> Path:
    path = tmp_path / "runtime.json"
    path.write_text(
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
    return path


def _policy() -> dict:
    return {
        "create_plan": {
            "max_target_accounts": 2,
            "max_projects_per_account": 2,
            "max_units_per_project": 3,
            "max_materials": 5,
            "min_daily_budget": 100,
            "max_daily_budget": 1000,
        }
    }


def _plan() -> dict:
    return {
        "plan_id": "first-live-20260511-001",
        "product": "yzt",
        "platform": "wx-mini-game",
        "launch_mode": "create_only",
        "source_advertiser_id": "source-1",
        "target_accounts": [
            {
                "advertiser_id": "target-1",
                "project_count": 1,
                "unit_count_per_project": 1,
                "daily_budget": 1000,
            }
        ],
        "materials": [{"source_material_id": "material-1", "source_video_id": "video-1"}],
        "reason": "首单链路验证",
    }


def _seed_plan_sources(db_path: Path) -> None:
    bootstrap_database(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO account_pool (
              advertiser_id, account_name, product, platform, historical_spend, source, synced_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("target-1", "Target Account", "yzt", "wx-mini-game", 1000, "test", "2026-05-11T00:00:00Z"),
        )
        conn.execute(
            """
            INSERT INTO product_source_materials (
              product, source_advertiser_id, material_id, video_id, name, source, synced_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("yzt", "source-1", "material-1", "video-1", "Material 1", "test", "2026-05-11T00:00:00Z"),
        )


def _write_allowed_accounts(path: Path, rows: list[dict]) -> Path:
    path.write_text(json.dumps({"allowed_target_accounts": rows}, ensure_ascii=False), encoding="utf-8")
    return path


def test_validate_create_plan_accepts_plan_from_sqlite_sources(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_plan_sources(db_path)

    result = validate_create_plan(_plan(), policy=_policy(), db_path=db_path)

    assert result["ok"] is True
    assert result["workflow"] == "create_plan_validate"
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 0
    assert result["summary"] == {
        "plan_id": "first-live-20260511-001",
        "launch_mode": "create_only",
        "target_account_count": 1,
        "project_count": 1,
        "unit_count": 1,
        "material_count": 1,
    }
    assert result["source_contract"]["target_accounts_in_sqlite"] is True
    assert result["source_contract"]["materials_in_sqlite"] is True
    assert result["violations"] == []
    assert result["actions"] == []


def test_validate_create_plan_accepts_create_strategy_plan_shape(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_plan_sources(db_path)
    strategy_plan = {
        "workflow": "create_strategy_plan",
        "plan_id": "create-plan-mode-001",
        "request_id": "mode-001",
        "target_date": "2026-05-13",
        "request": {
            "product": "yzt",
            "platform": "wx-mini-game",
            "source_advertiser_id": "source-1",
            "target_accounts": [
                {
                    "advertiser_id": "target-1",
                    "project_count": 1,
                    "units_per_project": 1,
                    "daily_budget": 1000,
                }
            ],
        },
        "strategy": {
            "source_advertiser_id": "source-1",
            "projects": [
                {
                    "advertiser_id": "target-1",
                    "units": [
                        {
                            "unit_key": "target-1-p001-u01",
                            "materials": [{"material_id": "material-1", "source_video_id": "video-1"}],
                        }
                    ],
                }
            ],
        },
    }

    result = validate_create_plan(strategy_plan, policy=_policy(), db_path=db_path)

    assert result["ok"] is True
    assert result["summary"] == {
        "plan_id": "create-plan-mode-001",
        "launch_mode": "create_only",
        "target_account_count": 1,
        "project_count": 1,
        "unit_count": 1,
        "material_count": 1,
    }
    assert result["violations"] == []


def test_validate_create_plan_requires_allowed_target_accounts_when_policy_says_so(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_plan_sources(db_path)
    allowlist_path = _write_allowed_accounts(
        tmp_path / "allowed-create-accounts.json",
        [
            {
                "account_name": "Target Account",
                "advertiser_id": "target-1",
                "product": "yzt",
                "enable": True,
                "channel": "wx",
            }
        ],
    )
    policy = _policy()
    policy["create_plan"]["require_allowed_target_accounts"] = True
    policy["create_plan"]["allowed_target_accounts_path"] = str(allowlist_path)

    result = validate_create_plan(_plan(), policy=policy, db_path=db_path)

    assert result["ok"] is True
    assert result["allowed_account_contract"]["checked"] is True
    assert result["allowed_account_contract"]["allowed_target_account_count"] == 1
    assert result["violations"] == []


def test_validate_create_plan_blocks_target_account_not_in_allowed_list(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_plan_sources(db_path)
    allowlist_path = _write_allowed_accounts(
        tmp_path / "allowed-create-accounts.json",
        [
            {
                "account_name": "Other Account",
                "advertiser_id": "target-2",
                "product": "yzt",
                "enable": True,
                "channel": "wx",
            }
        ],
    )
    policy = _policy()
    policy["create_plan"]["require_allowed_target_accounts"] = True
    policy["create_plan"]["allowed_target_accounts_path"] = str(allowlist_path)

    result = validate_create_plan(_plan(), policy=policy, db_path=db_path)

    assert result["ok"] is False
    assert "target account not in allowed create account list: target-1" in result["violations"]


def test_validate_create_strategy_plan_uses_product_specific_allowed_path(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_plan_sources(db_path)
    generic_allowlist = _write_allowed_accounts(
        tmp_path / "generic-allowed-create-accounts.json",
        [
            {
                "account_name": "Other Account",
                "advertiser_id": "target-2",
                "product": "yzt",
                "enable": True,
                "channel": "wx",
            }
        ],
    )
    product_allowlist = _write_allowed_accounts(
        tmp_path / "product-allowed-create-accounts.json",
        [
            {
                "account_name": "Target Account",
                "advertiser_id": "target-1",
                "product": "yzt",
                "enable": True,
                "channel": "wx",
            }
        ],
    )
    strategy_plan = {
        "workflow": "create_strategy_plan",
        "plan_id": "create-plan-mode-001",
        "request_id": "mode-001",
        "request": {
            "product": "yzt",
            "platform": "wx-mini-game",
            "source_advertiser_id": "source-1",
            "product_config_snapshot": {"allowed_target_accounts_path": str(product_allowlist)},
            "target_accounts": [
                {
                    "advertiser_id": "target-1",
                    "project_count": 1,
                    "units_per_project": 1,
                    "daily_budget": 1000,
                }
            ],
        },
        "strategy": {
            "source_advertiser_id": "source-1",
            "projects": [
                {
                    "advertiser_id": "target-1",
                    "units": [
                        {
                            "unit_key": "target-1-p001-u01",
                            "materials": [{"material_id": "material-1", "source_video_id": "video-1"}],
                        }
                    ],
                }
            ],
        },
    }
    policy = _policy()
    policy["create_plan"]["require_allowed_target_accounts"] = True
    policy["create_plan"]["allowed_target_accounts_path"] = str(generic_allowlist)

    result = validate_create_plan(strategy_plan, policy=policy, db_path=db_path)

    assert result["ok"] is True
    assert result["allowed_account_contract"]["allowed_target_accounts_path"] == str(product_allowlist)
    assert result["violations"] == []


def test_validate_create_plan_blocks_disabled_or_mismatched_allowed_account(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_plan_sources(db_path)
    allowlist_path = _write_allowed_accounts(
        tmp_path / "allowed-create-accounts.json",
        [
            {
                "account_name": "Target Account",
                "advertiser_id": "target-1",
                "product": "other-product",
                "enable": False,
                "channel": "byte",
            }
        ],
    )
    policy = _policy()
    policy["create_plan"]["require_allowed_target_accounts"] = True
    policy["create_plan"]["allowed_target_accounts_path"] = str(allowlist_path)

    result = validate_create_plan(_plan(), policy=policy, db_path=db_path)

    assert result["ok"] is False
    assert "target account is disabled in allowed create account list: target-1" in result["violations"]
    assert "target account product does not match create_plan.product: target-1" in result["violations"]
    assert "target account channel does not match create_plan.platform: target-1" in result["violations"]


def test_validate_create_plan_blocks_placeholders_and_policy_limits():
    plan = _plan()
    plan["source_advertiser_id"] = "source-advertiser-id"
    plan["target_accounts"][0]["advertiser_id"] = "target-advertiser-id"
    plan["target_accounts"][0]["project_count"] = 3
    plan["target_accounts"][0]["daily_budget"] = 2000
    plan["launch_mode"] = "activate_after_create"
    plan["materials"] = []

    result = validate_create_plan(plan, policy=_policy())

    assert result["ok"] is False
    assert result["status"] == "blocked"
    assert "source_advertiser_id contains placeholder id" in result["violations"]
    assert "target_accounts[0].advertiser_id contains placeholder id" in result["violations"]
    assert "target_accounts[0].project_count exceeds max_projects_per_account" in result["violations"]
    assert "target_accounts[0].daily_budget exceeds max_daily_budget" in result["violations"]
    assert "launch_mode must be create_only" in result["violations"]
    assert "materials requires at least one item" in result["violations"]


def test_run_create_plan_validate_script_writes_artifact(tmp_path: Path, capsys):
    runtime_path = _runtime_config(tmp_path)
    db_path = tmp_path / "roibang.sqlite3"
    _seed_plan_sources(db_path)
    plan_path = tmp_path / "create-plan.json"
    policy_path = tmp_path / "policy.json"
    plan_path.write_text(json.dumps(_plan(), ensure_ascii=False), encoding="utf-8")
    policy_path.write_text(json.dumps(_policy(), ensure_ascii=False), encoding="utf-8")
    module = _load_script("run_create_plan_validate")

    exit_code = module.run_from_args(
        ["--config", str(runtime_path), "--plan", str(plan_path), "--policy", str(policy_path)]
    )

    output = json.loads(capsys.readouterr().out)
    artifact = json.loads(Path(output["artifact_path"]).read_text(encoding="utf-8"))
    assert exit_code == 0
    assert output["workflow"] == "create_plan_validate"
    assert output["status"] == "passed"
    assert output["external_api_calls"] == 0
    assert artifact["actions"] == []
