import importlib.util
import json
from pathlib import Path

from roibang_v2.workflows.project_update_from_suggestions import build_project_update_from_suggestions
from roibang_v2.workflows.project_update_from_suggestions import run_project_update_from_suggestions_request


def _suggestions() -> dict:
    return {
        "ok": True,
        "workflow": "control_strategy_suggestions",
        "execution_enabled": False,
        "external_api_calls": 0,
        "summary": {
            "target_date": "2026-05-12",
            "suggestion_count": 2,
            "schedule_hollow_suggestion_count": 2,
            "allowed_account_count": 15,
        },
        "suggestions": [
            {
                "suggestion_type": "schedule_hollow",
                "rule_id": "schedule_hollow_low_realtime_hour_roi",
                "target_date": "2026-05-12",
                "advertiser_id": "1856647523922953",
                "entity_type": "project",
                "entity_id": "project-1",
                "hollow_hours": [5, 6, 7],
                "reason": "当天实时小时数据 ROI 低于阈值，建议临时拉空这些小时",
                "metrics": {"stat_cost": 100, "convert_cnt": 0, "roi_1day": 0},
                "restore": {
                    "required": True,
                    "restore_date": "2026-05-13",
                    "reason": "当天临时拉空时段，第二天必须恢复原始时段，避免长期影响投放节奏。",
                },
                "execution": {"enabled": False},
            },
            {
                "suggestion_type": "pause_project",
                "target_date": "2026-05-12",
                "advertiser_id": "1856647523922953",
                "entity_type": "project",
                "entity_id": "project-ignored",
            },
            {
                "suggestion_type": "suggest_delete_project",
                "suggested_action": "suggest_delete_project",
                "suggestion_id": "delete-project-1",
                "rule_id": "project_delete_inactive_closed",
                "target_date": "2026-05-12",
                "advertiser_id": "1856647523922953",
                "entity_type": "project",
                "entity_id": "project-delete-1",
                "entity_name": "0512_郭靖勇者突进_旧项目",
                "status": "PROJECT_STATUS_DISABLE",
                "reason": "项目已关闭，今天和昨天低消耗且无计费时间转化，建议作为项目数量清理候选。",
                "metrics": {"stat_cost": 0, "billing_convert_cnt": 0},
                "evidence": {"lifecycle": {"project_age_days": 8}},
            },
            {
                "suggestion_type": "schedule_hollow",
                "rule_id": "schedule_hollow_low_realtime_hour_roi",
                "target_date": "2026-05-12",
                "advertiser_id": "1856647539522568",
                "entity_type": "project",
                "entity_id": "project-2",
                "hollow_hours": [2, 9],
                "reason": "当天实时小时数据 ROI 低于阈值，建议临时拉空这些小时",
                "metrics": {"stat_cost": 80, "convert_cnt": 0, "roi_1day": 0},
                "restore": {
                    "required": True,
                    "restore_date": "2026-05-13",
                    "reason": "当天临时拉空时段，第二天必须恢复原始时段，避免长期影响投放节奏。",
                },
                "execution": {"enabled": False},
            },
        ],
    }


def _management_suggestions() -> dict:
    result = _suggestions()
    result["suggestions"] = [
        *result["suggestions"],
        {
            "suggestion_type": "suggest_close_project",
            "suggested_action": "suggest_close_project",
            "suggestion_id": "close-project-1",
            "rule_id": "project_close_zero_convert",
            "target_date": "2026-05-12",
            "advertiser_id": "1856647523922953",
            "entity_type": "project",
            "project_id": "project-close-1",
            "entity_name": "0512_郭靖勇者突进_关闭候选",
            "reason": "今天和昨天累计消耗达到阈值，但计费时间转化数为 0，建议关闭项目。",
        },
        {
            "suggestion_type": "suggest_lower_budget",
            "suggested_action": "suggest_lower_budget",
            "suggestion_id": "budget-project-1",
            "rule_id": "project_lower_budget_low_roi",
            "target_date": "2026-05-12",
            "advertiser_id": "1856647523922953",
            "entity_type": "project",
            "project_id": "project-budget-1",
            "entity_name": "0512_郭靖勇者突进_降预算候选",
            "reason": "项目有计费时间转化但计费当日 ROI 低于阈值，建议只输出下调预算比例。",
            "adjustment": {"type": "ratio", "value": -0.2},
        },
        {
            "suggestion_type": "suggest_lower_bid",
            "suggested_action": "suggest_lower_bid",
            "suggestion_id": "bid-project-1",
            "rule_id": "project_lower_bid_high_cpa",
            "target_date": "2026-05-12",
            "advertiser_id": "1856647539522568",
            "entity_type": "project",
            "project_id": "project-bid-1",
            "entity_name": "0512_郭靖勇者突进_降出价候选",
            "reason": "计费时间转化成本高于阈值，建议只输出下调出价比例。",
            "adjustment": {"type": "ratio", "value": -0.1},
        },
    ]
    return result


def _load_script():
    script_path = Path("scripts/run_project_update_from_suggestions.py")
    spec = importlib.util.spec_from_file_location("run_project_update_from_suggestions", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_build_project_update_from_schedule_hollow_suggestions_only():
    result = build_project_update_from_suggestions(
        _suggestions(),
        {
            "project_update_id": "project-update-20260512-001",
            "operator": "郭靖",
            "allowed_target_accounts_path": "configs/control-allowed-accounts.local.json",
        },
    )

    assert result["workflow"] == "project_update_from_suggestions"
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 0
    assert result["summary"] == {
        "project_update_id": "project-update-20260512-001",
        "source_suggestion_count": 4,
        "selected_suggestion_count": 4,
        "suggested_actions": [],
        "schedule_hollow_action_count": 2,
        "delete_project_action_count": 1,
        "close_project_action_count": 1,
        "lower_budget_action_count": 0,
        "lower_bid_action_count": 0,
        "action_count": 4,
        "restore_action_count": 2,
        "target_date": "2026-05-12",
        "restore_date": "2026-05-13",
    }
    update = result["project_update"]
    assert update["execution"] == {"enabled": False, "status": "planned_only"}
    assert update["allowed_target_accounts_path"] == "configs/control-allowed-accounts.local.json"
    assert update["actions"][0] == {
        "action_type": "schedule_hollow",
        "advertiser_id": "1856647523922953",
        "entity_type": "project",
        "project_id": "project-1",
        "target_date": "2026-05-12",
        "hollow_hours": [5, 6, 7],
        "preserve_original_schedule_required": True,
        "restore_required": True,
        "restore_date": "2026-05-13",
        "reason": "当天实时小时数据 ROI 低于阈值，建议临时拉空这些小时",
        "metrics": {"stat_cost": 100, "convert_cnt": 0, "roi_1day": 0},
    }
    assert update["restore_actions"][0]["action_type"] == "schedule_restore"
    assert update["restore_actions"][0]["restore_date"] == "2026-05-13"
    assert update["actions"][2] == {
        "action_type": "delete_project",
        "advertiser_id": "1856647523922953",
        "entity_type": "project",
        "project_id": "project-delete-1",
        "project_name": "0512_郭靖勇者突进_旧项目",
        "reason": "项目已关闭，今天和昨天低消耗且无计费时间转化，建议作为项目数量清理候选。",
        "source_suggestion_id": "delete-project-1",
        "source_rule_id": "project_delete_inactive_closed",
        "metrics": {"stat_cost": 0, "billing_convert_cnt": 0},
        "evidence": {"lifecycle": {"project_age_days": 8}},
        "status": "PROJECT_STATUS_DISABLE",
    }


def test_build_project_update_from_suggestions_can_filter_delete_actions_only():
    result = build_project_update_from_suggestions(
        _suggestions(),
        {
            "project_update_id": "delete-from-suggestions-001",
            "operator": "郭靖",
            "suggested_actions": ["suggest_delete_project"],
        },
    )

    assert result["summary"]["source_suggestion_count"] == 4
    assert result["summary"]["selected_suggestion_count"] == 1
    assert result["summary"]["suggested_actions"] == ["suggest_delete_project"]
    assert result["summary"]["schedule_hollow_action_count"] == 0
    assert result["summary"]["delete_project_action_count"] == 1
    assert result["summary"]["close_project_action_count"] == 0
    assert result["summary"]["lower_budget_action_count"] == 0
    assert result["summary"]["lower_bid_action_count"] == 0
    assert result["summary"]["action_count"] == 1
    assert result["project_update"]["actions"][0]["action_type"] == "delete_project"
    assert result["project_update"]["actions"][0]["project_id"] == "project-delete-1"


def test_project_update_from_suggestions_blocks_explicit_create_project_suggestion():
    suggestions = _management_suggestions()
    suggestions["suggestions"].append(
        {
            "suggestion_type": "suggest_create_project",
            "suggested_action": "suggest_create_project",
            "suggestion_id": "create-project-1",
            "target_date": "2026-05-12",
            "advertiser_id": "1856647523922953",
            "entity_type": "account",
            "mode_key": "wx_pay_general_recent_scale",
            "reason": "账户容量和素材供给达标，建议创建项目。",
        }
    )

    try:
        build_project_update_from_suggestions(
            suggestions,
            {
                "project_update_id": "project-update-20260512-001",
                "selected_suggestion_ids": ["create-project-1"],
            },
        )
    except ValueError as exc:
        assert "只读建议不能生成项目管理 JSON：create-project-1" in str(exc)
    else:
        raise AssertionError("create project suggestions must not become project management JSON")


def test_build_project_update_from_suggestions_can_convert_close_budget_and_bid_actions():
    result = build_project_update_from_suggestions(
        _management_suggestions(),
        {
            "project_update_id": "management-from-suggestions-001",
            "operator": "郭靖",
            "suggested_actions": ["suggest_close_project", "suggest_lower_budget", "suggest_lower_bid"],
        },
    )

    assert result["summary"]["source_suggestion_count"] == 7
    assert result["summary"]["selected_suggestion_count"] == 4
    assert result["summary"]["close_project_action_count"] == 2
    assert result["summary"]["lower_budget_action_count"] == 1
    assert result["summary"]["lower_bid_action_count"] == 1
    assert result["summary"]["action_count"] == 4
    assert result["project_update"]["actions"] == [
        {
            "action_type": "status_update",
            "advertiser_id": "1856647523922953",
            "entity_type": "project",
            "project_id": "project-ignored",
            "project_name": "",
            "reason": "",
            "source_suggestion_id": "",
            "source_rule_id": "",
            "metrics": {},
            "evidence": {},
            "opt_status": "DISABLE",
        },
        {
            "action_type": "status_update",
            "advertiser_id": "1856647523922953",
            "entity_type": "project",
            "project_id": "project-close-1",
            "project_name": "0512_郭靖勇者突进_关闭候选",
            "reason": "今天和昨天累计消耗达到阈值，但计费时间转化数为 0，建议关闭项目。",
            "source_suggestion_id": "close-project-1",
            "source_rule_id": "project_close_zero_convert",
            "metrics": {},
            "evidence": {},
            "opt_status": "DISABLE",
        },
        {
            "action_type": "budget_update",
            "advertiser_id": "1856647523922953",
            "entity_type": "project",
            "project_id": "project-budget-1",
            "project_name": "0512_郭靖勇者突进_降预算候选",
            "reason": "项目有计费时间转化但计费当日 ROI 低于阈值，建议只输出下调预算比例。",
            "source_suggestion_id": "budget-project-1",
            "source_rule_id": "project_lower_budget_low_roi",
            "metrics": {},
            "evidence": {},
            "adjustment": {"type": "ratio", "value": -0.2},
            "adjustment_ratio": -0.2,
            "resolve_current_value_at_execute": True,
            "budget_mode": "BUDGET_MODE_DAY",
        },
        {
            "action_type": "bid_update",
            "advertiser_id": "1856647539522568",
            "entity_type": "project",
            "project_id": "project-bid-1",
            "project_name": "0512_郭靖勇者突进_降出价候选",
            "reason": "计费时间转化成本高于阈值，建议只输出下调出价比例。",
            "source_suggestion_id": "bid-project-1",
            "source_rule_id": "project_lower_bid_high_cpa",
            "metrics": {},
            "evidence": {},
            "adjustment": {"type": "ratio", "value": -0.1},
            "adjustment_ratio": -0.1,
            "resolve_current_value_at_execute": True,
        },
    ]


def test_build_project_update_from_suggestions_accepts_control_strategy_action_aliases():
    result = build_project_update_from_suggestions(
        {
            "workflow": "control_strategy_suggestions",
            "summary": {"suggestion_count": 3},
            "suggestions": [
                {
                    "suggestion_type": "pause_project",
                    "rule_id": "pause_project_low_first_day_roi",
                    "target_date": "2026-05-28",
                    "advertiser_id": "1001",
                    "entity_type": "project",
                    "entity_id": "p-pause",
                    "entity_name": "低 ROI 暂停候选",
                    "reason": "首日 ROI 低于阈值。",
                },
                {
                    "suggestion_type": "adjust_project_budget",
                    "rule_id": "adjust_project_budget_low_roi",
                    "target_date": "2026-05-28",
                    "advertiser_id": "1001",
                    "entity_type": "project",
                    "entity_id": "p-budget",
                    "entity_name": "低 ROI 降预算候选",
                    "reason": "首日 ROI 低于预算调整阈值。",
                    "adjustment": {"type": "ratio", "value": -0.2},
                },
                {
                    "suggestion_type": "adjust_project_bid",
                    "rule_id": "adjust_project_bid_high_cpa",
                    "target_date": "2026-05-28",
                    "advertiser_id": "1002",
                    "entity_type": "project",
                    "entity_id": "p-bid",
                    "entity_name": "高成本降出价候选",
                    "reason": "转化成本高于配置阈值。",
                    "adjustment": {"type": "ratio", "value": -0.1},
                },
            ],
        },
        {
            "project_update_id": "control-aliases-001",
            "operator": "运营A",
            "suggested_actions": ["pause_project", "adjust_project_budget", "adjust_project_bid"],
        },
    )

    assert result["summary"]["selected_suggestion_count"] == 3
    assert result["summary"]["close_project_action_count"] == 1
    assert result["summary"]["lower_budget_action_count"] == 1
    assert result["summary"]["lower_bid_action_count"] == 1
    assert [action["action_type"] for action in result["project_update"]["actions"]] == [
        "status_update",
        "budget_update",
        "bid_update",
    ]
    assert result["project_update"]["actions"][0]["opt_status"] == "DISABLE"
    assert result["project_update"]["actions"][1]["adjustment_ratio"] == -0.2
    assert result["project_update"]["actions"][2]["adjustment_ratio"] == -0.1


def test_build_project_update_from_suggestions_maps_legacy_filters_to_control_strategy_actions():
    result = build_project_update_from_suggestions(
        {
            "workflow": "control_strategy_suggestions",
            "summary": {"suggestion_count": 3},
            "suggestions": [
                {
                    "suggestion_type": "pause_project",
                    "rule_id": "pause_project_low_first_day_roi",
                    "target_date": "2026-05-28",
                    "advertiser_id": "1001",
                    "entity_type": "project",
                    "entity_id": "p-pause",
                    "entity_name": "低 ROI 暂停候选",
                    "reason": "首日 ROI 低于阈值。",
                },
                {
                    "suggestion_type": "adjust_project_budget",
                    "rule_id": "adjust_project_budget_low_roi",
                    "target_date": "2026-05-28",
                    "advertiser_id": "1001",
                    "entity_type": "project",
                    "entity_id": "p-budget",
                    "entity_name": "低 ROI 降预算候选",
                    "reason": "首日 ROI 低于预算调整阈值。",
                    "adjustment": {"type": "ratio", "value": -0.2},
                },
                {
                    "suggestion_type": "adjust_project_bid",
                    "rule_id": "adjust_project_bid_high_cpa",
                    "target_date": "2026-05-28",
                    "advertiser_id": "1002",
                    "entity_type": "project",
                    "entity_id": "p-bid",
                    "entity_name": "高成本降出价候选",
                    "reason": "转化成本高于配置阈值。",
                    "adjustment": {"type": "ratio", "value": -0.1},
                },
            ],
        },
        {
            "project_update_id": "control-legacy-filters-001",
            "operator": "运营A",
            "suggested_actions": ["suggest_close_project", "suggest_lower_budget", "suggest_lower_bid"],
        },
    )

    assert result["summary"]["selected_suggestion_count"] == 3
    assert [action["action_type"] for action in result["project_update"]["actions"]] == [
        "status_update",
        "budget_update",
        "bid_update",
    ]


def test_build_project_update_from_suggestions_accepts_control_strategy_decrease_percent_adjustment():
    result = build_project_update_from_suggestions(
        {
            "workflow": "control_strategy_suggestions",
            "summary": {"suggestion_count": 1},
            "suggestions": [
                {
                    "suggestion_type": "adjust_project_budget",
                    "rule_id": "adjust_project_budget_low_roi",
                    "target_date": "2026-05-28",
                    "advertiser_id": "1001",
                    "entity_type": "project",
                    "entity_id": "p-budget",
                    "entity_name": "低 ROI 降预算候选",
                    "reason": "首日 ROI 低于预算调整阈值。",
                    "adjustment": {
                        "field": "budget",
                        "direction": "decrease",
                        "decrease_percent": 20,
                        "requires_current_budget_from_config": True,
                        "suggested_budget": None,
                    },
                }
            ],
        },
        {
            "project_update_id": "control-old-adjustment-001",
            "operator": "运营A",
            "suggested_actions": ["adjust_project_budget"],
        },
    )

    assert result["summary"]["action_count"] == 1
    action = result["project_update"]["actions"][0]
    assert action["action_type"] == "budget_update"
    assert action["adjustment"] == {"type": "ratio", "value": -0.2}
    assert action["adjustment_ratio"] == -0.2
    assert action["resolve_current_value_at_execute"] is True


def test_build_project_update_from_suggestions_can_select_single_suggestion_and_add_chinese_metadata():
    result = build_project_update_from_suggestions(
        _management_suggestions(),
        {
            "project_update_id": "selected-budget-001",
            "operator": "运营A",
            "product_key": "demo-game",
            "product_name": "演示游戏",
            "suggestions_artifact_path": "data/runs/delivery_patrol_suggestions/20260528T100001Z.json",
            "selected_suggestion_ids": ["budget-project-1"],
            "account_names": {"1856647523922953": "演示账户一"},
        },
    )

    assert result["summary"]["selected_suggestion_count"] == 1
    assert result["summary"]["action_count"] == 1
    update = result["project_update"]
    assert update["中文摘要"] == "根据规则建议生成项目管理动作 JSON，涉及 1 个账户、1 个动作；只生成配置，不执行真实业务动作。"
    assert update["product_key"] == "demo-game"
    assert update["product_name"] == "演示游戏"
    assert update["source_artifact"] == "data/runs/delivery_patrol_suggestions/20260528T100001Z.json"
    assert update["dry_run_required"] is True
    assert update["execution_allowed"] is False
    assert update["accounts"] == [{"account_id": "1856647523922953", "account_name": "演示账户一"}]
    assert update["risk_summary"] == "包含调预算 1 个；执行前必须人工核对账户、项目、动作和来源建议。"
    assert update["actions"][0]["中文动作"] == "调预算"
    assert update["actions"][0]["account_name"] == "演示账户一"
    assert update["actions"][0]["project_id"] == "project-budget-1"


def test_run_project_update_from_suggestions_writes_update_file_and_artifact(tmp_path: Path):
    output_path = tmp_path / "project_update.local.json"

    result = run_project_update_from_suggestions_request(
        {
            "suggestions_artifact": _suggestions(),
            "project_update_id": "project-update-20260512-001",
            "operator": "郭靖",
            "allowed_target_accounts_path": "configs/control-allowed-accounts.local.json",
            "output_path": str(output_path),
        },
        runs_dir=tmp_path / "runs",
    )

    saved = json.loads(output_path.read_text(encoding="utf-8"))
    assert result["ok"] is True
    assert result["project_update_path"] == str(output_path)
    assert Path(result["artifact_path"]).exists()
    assert saved["project_update_id"] == "project-update-20260512-001"
    assert len(saved["actions"]) == 4
    assert len(saved["restore_actions"]) == 2


def test_project_update_from_suggestions_cli_accepts_artifact_file(tmp_path: Path, capsys):
    suggestions_path = tmp_path / "suggestions.json"
    output_path = tmp_path / "project_update.local.json"
    suggestions_path.write_text(json.dumps(_suggestions(), ensure_ascii=False), encoding="utf-8")
    module = _load_script()

    exit_code = module.run_from_args(
        [
            "--suggestions-artifact",
            str(suggestions_path),
            "--project-update-id",
            "project-update-20260512-001",
            "--operator",
            "郭靖",
            "--allowed-target-accounts-path",
            "configs/control-allowed-accounts.local.json",
            "--output",
            str(output_path),
            "--runs-dir",
            str(tmp_path / "runs"),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["workflow"] == "project_update_from_suggestions"
    assert output["execution_enabled"] is False
    assert output["external_api_calls"] == 0
    assert output["summary"]["schedule_hollow_action_count"] == 2
    assert output["summary"]["delete_project_action_count"] == 1
    assert output["project_update_path"] == str(output_path)


def test_project_update_from_suggestions_cli_can_filter_to_delete_only(tmp_path: Path, capsys):
    suggestions_path = tmp_path / "suggestions.json"
    output_path = tmp_path / "delete.local.json"
    suggestions_path.write_text(json.dumps(_suggestions(), ensure_ascii=False), encoding="utf-8")
    module = _load_script()

    exit_code = module.run_from_args(
        [
            "--suggestions-artifact",
            str(suggestions_path),
            "--project-update-id",
            "delete-from-suggestions-001",
            "--operator",
            "郭靖",
            "--suggested-action",
            "suggest_delete_project",
            "--output",
            str(output_path),
            "--runs-dir",
            str(tmp_path / "runs"),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    saved = json.loads(output_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert output["summary"]["selected_suggestion_count"] == 1
    assert output["summary"]["action_count"] == 1
    assert saved["actions"][0]["action_type"] == "delete_project"
    assert saved["actions"][0]["project_id"] == "project-delete-1"


def test_project_update_from_suggestions_cli_accepts_selected_ids_and_account_names(tmp_path: Path, capsys):
    suggestions_path = tmp_path / "suggestions.json"
    output_path = tmp_path / "selected.local.json"
    suggestions_path.write_text(json.dumps(_management_suggestions(), ensure_ascii=False), encoding="utf-8")
    module = _load_script()

    exit_code = module.run_from_args(
        [
            "--suggestions-artifact",
            str(suggestions_path),
            "--project-update-id",
            "selected-close-001",
            "--operator",
            "运营A",
            "--product-key",
            "demo-game",
            "--product-name",
            "演示游戏",
            "--suggestion-id",
            "close-project-1",
            "--account-name",
            "1856647523922953=演示账户一",
            "--output",
            str(output_path),
            "--runs-dir",
            str(tmp_path / "runs"),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    saved = json.loads(output_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert output["summary"]["selected_suggestion_count"] == 1
    assert output["summary"]["action_count"] == 1
    assert saved["product_key"] == "demo-game"
    assert saved["accounts"] == [{"account_id": "1856647523922953", "account_name": "演示账户一"}]
    assert saved["actions"][0]["source_suggestion_id"] == "close-project-1"
    assert saved["actions"][0]["中文动作"] == "暂停项目"


def test_project_delete_from_suggestions_wrapper_defaults_to_delete_only(tmp_path: Path, capsys):
    suggestions_path = tmp_path / "20260520T093255Z.json"
    suggestions_path.write_text(json.dumps(_suggestions(), ensure_ascii=False), encoding="utf-8")
    script_path = Path("scripts/run_project_delete_from_suggestions.py")
    spec = importlib.util.spec_from_file_location("run_project_delete_from_suggestions", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)

    exit_code = module.run_from_args(
        [
            "--suggestions-artifact",
            str(suggestions_path),
            "--operator",
            "郭靖",
            "--output",
            str(tmp_path / "delete.local.json"),
            "--runs-dir",
            str(tmp_path / "runs"),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["summary"]["project_update_id"] == "delete-from-suggestions-20260520T093255Z"
    assert output["summary"]["suggested_actions"] == ["suggest_delete_project"]
    assert output["summary"]["action_count"] == 1
    assert output["next_execute_command"].endswith("--execute --yes")
