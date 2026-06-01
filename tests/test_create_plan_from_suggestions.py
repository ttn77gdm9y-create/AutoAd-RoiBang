import importlib.util
import json
from pathlib import Path

from roibang_v2.workflows.create_plan_from_suggestions import build_create_plan_from_suggestions
from roibang_v2.workflows.create_plan_from_suggestions import run_create_plan_from_suggestions_request


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _suggestions_artifact() -> dict:
    return {
        "workflow": "rule_suggestions",
        "summary": {"target_date": "2026-05-31"},
        "suggestions": [
            {
                "suggestion_id": "create-1001",
                "suggested_action": "suggest_create_project",
                "suggestion_type": "suggest_create_project",
                "entity_type": "account",
                "target_date": "2026-05-31",
                "product_key": "demo-game",
                "product_name": "演示游戏",
                "advertiser_id": "1001",
                "account_name": "演示账户一",
                "mode_key": "wx_pay_general_recent_scale",
                "strategy_id": "recent-scale-capacity-v1",
                "blocking_reasons": [],
                "evidence": {
                    "recommended_request": {
                        "mode_key": "wx_pay_general_recent_scale",
                        "project_count": 1,
                        "units_per_project": 1,
                    }
                },
            },
            {
                "suggestion_id": "delete-1001",
                "suggested_action": "suggest_delete_project",
                "suggestion_type": "suggest_delete_project",
                "entity_type": "project",
                "target_date": "2026-05-31",
                "product_key": "demo-game",
                "product_name": "演示游戏",
                "advertiser_id": "1001",
                "project_id": "p-1",
            },
        ],
    }


def _seed_template(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "configs" / "create-templates" / "demo-game.local.json",
        {
            "product": "演示游戏",
            "product_key": "demo-game",
            "platform": "WECHAT_GAME",
            "templates": {"wx_pay_general": {"project_template_name": "微小每付通投"}},
        },
    )


def _load_script():
    script_path = Path("scripts/run_create_plan_from_suggestions.py")
    spec = importlib.util.spec_from_file_location("run_create_plan_from_suggestions", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_create_plan_from_suggestions_builds_readonly_create_plan_request(tmp_path: Path):
    _seed_template(tmp_path)

    result = build_create_plan_from_suggestions(
        _suggestions_artifact(),
        {
            "selected_suggestion_ids": ["create-1001"],
            "owner": "运营A",
            "product_key": "demo-game",
        },
        project_root=tmp_path,
        template_dir=tmp_path / "configs" / "create-templates",
    )

    assert result["ok"] is True
    assert result["workflow"] == "create_plan_from_suggestions"
    assert result["status"] == "preview_only"
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 0
    assert result["summary"]["account_count"] == 1
    request = result["create_plan_request"]
    assert request["mode"] == "wx_pay_general_recent_scale"
    assert request["advertiser_ids"] == "1001"
    assert request["owner"] == "运营A"
    assert request["product_key"] == "demo-game"
    assert request["product_name"] == "演示游戏"
    assert request["target_date"] == "2026-05-31"
    assert request["template_catalog"] == "configs/create-templates/demo-game.local.json"


def test_create_plan_from_suggestions_blocks_non_create_suggestion(tmp_path: Path):
    _seed_template(tmp_path)

    result = build_create_plan_from_suggestions(
        _suggestions_artifact(),
        {
            "selected_suggestion_ids": ["delete-1001"],
            "owner": "运营A",
            "product_key": "demo-game",
        },
        project_root=tmp_path,
        template_dir=tmp_path / "configs" / "create-templates",
    )

    assert result["ok"] is False
    assert result["status"] == "blocked"
    assert "建议 delete-1001 不是创建项目建议" in "；".join(result["blocking_reasons"])


def test_create_plan_from_suggestions_splits_cross_mode_create_suggestions(tmp_path: Path):
    _seed_template(tmp_path)
    artifact = _suggestions_artifact()
    artifact["suggestions"].append(
        {
            "suggestion_id": "create-1002",
            "suggested_action": "suggest_create_project",
            "suggestion_type": "suggest_create_project",
            "entity_type": "account",
            "target_date": "2026-05-31",
            "product_key": "demo-game",
            "product_name": "演示游戏",
            "advertiser_id": "1002",
            "account_name": "演示账户二",
            "mode_key": "wx_pay_male_recent_scale",
            "strategy_id": "male-scale-capacity-v1",
            "blocking_reasons": [],
            "metrics": {"project_capacity": 2, "qualified_material_count": 4},
        }
    )

    result = build_create_plan_from_suggestions(
        artifact,
        {
            "selected_suggestion_ids": ["create-1001", "create-1002"],
            "owner": "运营A",
            "product_key": "demo-game",
        },
        project_root=tmp_path,
        template_dir=tmp_path / "configs" / "create-templates",
    )

    assert result["ok"] is True
    assert result["status"] == "split_required"
    assert result["summary"]["split_required"] is True
    assert result["summary"]["suggestion_group_count"] == 2
    assert result["create_plan_request"] == {}
    assert len(result["suggestion_groups"]) == 2
    assert {group["mode_key"] for group in result["suggestion_groups"]} == {
        "wx_pay_general_recent_scale",
        "wx_pay_male_recent_scale",
    }
    assert any("多个创建模式" in reason for reason in result["split_reasons"])


def test_create_plan_from_suggestions_run_writes_artifact(tmp_path: Path):
    _seed_template(tmp_path)
    suggestions_path = tmp_path / "suggestions.json"
    _write_json(suggestions_path, _suggestions_artifact())

    result = run_create_plan_from_suggestions_request(
        {
            "suggestions_artifact_path": str(suggestions_path),
            "selected_suggestion_ids": ["create-1001"],
            "owner": "运营A",
            "product_key": "demo-game",
            "project_root": str(tmp_path),
            "template_dir": str(tmp_path / "configs" / "create-templates"),
        },
        runs_dir=tmp_path / "data" / "runs",
    )

    assert result["ok"] is True
    assert Path(result["artifact_path"]).exists()
    assert result["create_plan_request"]["advertiser_ids"] == "1001"


def test_create_plan_from_suggestions_cli_is_preview_only(tmp_path: Path):
    _seed_template(tmp_path)
    suggestions_path = tmp_path / "suggestions.json"
    _write_json(suggestions_path, _suggestions_artifact())
    runtime_path = tmp_path / "configs" / "runtime.local.json"
    _write_json(
        runtime_path,
        {
            "environment": "test",
            "phase": "phase1",
            "database_path": str(tmp_path / "data" / "roibang_v2.sqlite3"),
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
            "--suggestions-artifact",
            str(suggestions_path),
            "--suggestion-id",
            "create-1001",
            "--project-root",
            str(tmp_path),
            "--template-dir",
            str(tmp_path / "configs" / "create-templates"),
            "--product-key",
            "demo-game",
            "--owner",
            "运营A",
        ]
    )

    assert exit_code == 0
    assert list((tmp_path / "data" / "runs" / "create_plan_from_suggestions").glob("*.json"))
