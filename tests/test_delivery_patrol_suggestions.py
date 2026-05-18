import importlib.util
import json
import sqlite3
from pathlib import Path

from roibang_v2.workflows.delivery_patrol_suggestions import build_delivery_patrol_suggestions
from roibang_v2.workflows.delivery_patrol_suggestions import run_delivery_patrol_suggestions_request


def _patrol_artifact() -> dict:
    return {
        "ok": True,
        "workflow": "delivery_patrol",
        "execution_enabled": False,
        "external_api_calls": 8,
        "windows": {"today": "2026-05-15", "yesterday": "2026-05-14"},
        "accounts": [
            {
                "advertiser_id": "1856647523922953",
                "account_name": "黑旗-勇者突进-微小-傲星-153",
                "account_remark": "勇者突进-微小-郭靖",
                "metrics": {
                    "today": {
                        "stat_cost": 1200,
                        "billing_convert_cnt": 0,
                        "billing_1day_pay_roi": 0,
                        "billing_conversion_cost": None,
                    },
                    "yesterday": {"stat_cost": 600, "billing_convert_cnt": 1, "billing_1day_pay_roi": 0.08},
                },
            }
        ],
        "projects": [
            {
                "advertiser_id": "1856647523922953",
                "project_id": "project-1",
                "project_name": "0515_郭靖勇者突进_项目",
                "status": "PROJECT_STATUS_ENABLE",
                "metrics": {
                    "today": {
                        "stat_cost": 900,
                        "billing_convert_cnt": 0,
                        "billing_1day_pay_roi": 0,
                        "billing_conversion_cost": None,
                    },
                    "yesterday": {"stat_cost": 100, "billing_convert_cnt": 0, "billing_1day_pay_roi": 0},
                },
            },
            {
                "advertiser_id": "1856647523922953",
                "project_id": "project-2",
                "project_name": "0515_郭靖勇者突进_好项目",
                "status": "PROJECT_STATUS_ENABLE",
                "metrics": {
                    "today": {
                        "stat_cost": 700,
                        "billing_convert_cnt": 2,
                        "billing_1day_pay_roi": 0.03,
                        "billing_conversion_cost": 350,
                    },
                    "yesterday": {"stat_cost": 300, "billing_convert_cnt": 1, "billing_1day_pay_roi": 0.1},
                },
            },
        ],
        "promotions": [
            {
                "advertiser_id": "1856647523922953",
                "project_id": "project-1",
                "promotion_id": "promotion-1",
                "promotion_name": "0515_郭靖勇者突进_单元",
                "status": "PROMOTION_STATUS_ENABLE",
                "metrics": {
                    "today": {
                        "stat_cost": 500,
                        "billing_convert_cnt": 0,
                        "billing_1day_pay_roi": 0,
                        "billing_conversion_cost": None,
                    },
                    "yesterday": {"stat_cost": 50, "billing_convert_cnt": 0, "billing_1day_pay_roi": 0},
                },
            }
        ],
    }


def _load_script():
    script_path = Path("scripts/run_delivery_patrol_suggestions.py")
    spec = importlib.util.spec_from_file_location("run_delivery_patrol_suggestions", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _suggestion_request() -> dict:
    return {
        "target_date": "2026-05-15",
        "rules": {
            "project": {
                "continue_running": {
                    "enabled": True,
                    "min_stat_cost": 500,
                    "min_billing_convert_cnt": 1,
                    "min_billing_1day_pay_roi": 0.05,
                },
                "watch": {
                    "enabled": True,
                    "min_stat_cost": 300,
                    "max_stat_cost": 800,
                    "max_billing_convert_cnt": 0,
                },
                "close_zero_convert": {
                    "enabled": True,
                    "min_two_day_stat_cost": 1000,
                    "max_two_day_billing_convert_cnt": 0,
                },
                "close_low_roi": {
                    "enabled": True,
                    "min_stat_cost": 800,
                    "roi_lt": 0.05,
                },
                "delete_inactive_closed": {
                    "enabled": True,
                    "max_today_stat_cost": 100,
                    "max_yesterday_stat_cost": 100,
                    "max_two_day_billing_convert_cnt": 0,
                    "min_project_age_days": 3,
                },
                "lower_budget": {
                    "enabled": True,
                    "min_stat_cost": 1000,
                    "min_billing_convert_cnt": 1,
                    "roi_lt": 0.05,
                    "adjustment_ratio": -0.2,
                },
                "lower_bid": {
                    "enabled": True,
                    "min_stat_cost": 1000,
                    "min_billing_convert_cnt": 2,
                    "min_billing_conversion_cost": 400,
                    "adjustment_ratio": -0.1,
                },
            },
            "promotion": {
                "bad_signal": {"enabled": True, "min_stat_cost": 300, "max_billing_convert_cnt": 0},
                "good_signal": {
                    "enabled": True,
                    "min_stat_cost": 300,
                    "min_billing_convert_cnt": 1,
                    "min_billing_1day_pay_roi": 0.05,
                },
            },
        },
        "account_health": {
            "can_scale": {"enabled": True, "min_stat_cost": 1000, "min_billing_1day_pay_roi": 0.05},
            "pause_creation": {"enabled": True, "min_stat_cost": 1000, "roi_lt": 0.05},
        },
        "evidence": {"operation_logs": {"enabled": True, "sample_limit": 3}, "project_lifecycle": {"enabled": True}},
    }


def _rich_patrol_artifact() -> dict:
    artifact = _patrol_artifact()
    artifact["accounts"] = [
        {
            "advertiser_id": "1856647523922953",
            "account_name": "黑旗-勇者突进-微小-傲星-153",
            "metrics": {
                "today": {"stat_cost": 1500, "billing_convert_cnt": 3, "billing_1day_pay_roi": 0.08},
                "yesterday": {"stat_cost": 900, "billing_convert_cnt": 1, "billing_1day_pay_roi": 0.05},
            },
        },
        {
            "advertiser_id": "1856647524935691",
            "account_name": "黑旗-勇者突进-微小-傲星-155",
            "metrics": {
                "today": {"stat_cost": 1600, "billing_convert_cnt": 1, "billing_1day_pay_roi": 0.02},
                "yesterday": {"stat_cost": 1200, "billing_convert_cnt": 1, "billing_1day_pay_roi": 0.04},
            },
        },
    ]
    artifact["projects"] = [
        {
            "advertiser_id": "1856647523922953",
            "project_id": "project-close",
            "project_name": "0515_郭靖勇者突进_建议关闭",
            "status": "PROJECT_STATUS_ENABLE",
            "metrics": {
                "today": {"stat_cost": 900, "billing_convert_cnt": 0, "billing_1day_pay_roi": 0},
                "yesterday": {"stat_cost": 200, "billing_convert_cnt": 0, "billing_1day_pay_roi": 0},
            },
        },
        {
            "advertiser_id": "1856647523922953",
            "project_id": "project-good",
            "project_name": "0515_郭靖勇者突进_继续跑",
            "status": "PROJECT_STATUS_ENABLE",
            "metrics": {
                "today": {
                    "stat_cost": 700,
                    "billing_convert_cnt": 2,
                    "billing_conversion_cost": 350,
                    "billing_1day_pay_roi": 0.08,
                },
                "yesterday": {"stat_cost": 500, "billing_convert_cnt": 1, "billing_1day_pay_roi": 0.07},
            },
        },
        {
            "advertiser_id": "1856647523922953",
            "project_id": "project-budget",
            "project_name": "0515_郭靖勇者突进_下调预算",
            "status": "PROJECT_STATUS_ENABLE",
            "metrics": {
                "today": {
                    "stat_cost": 1200,
                    "billing_convert_cnt": 1,
                    "billing_conversion_cost": 1200,
                    "billing_1day_pay_roi": 0.03,
                },
                "yesterday": {"stat_cost": 300, "billing_convert_cnt": 1, "billing_1day_pay_roi": 0.06},
            },
        },
        {
            "advertiser_id": "1856647523922953",
            "project_id": "project-bid",
            "project_name": "0515_郭靖勇者突进_下调出价",
            "status": "PROJECT_STATUS_ENABLE",
            "metrics": {
                "today": {
                    "stat_cost": 1400,
                    "billing_convert_cnt": 3,
                    "billing_conversion_cost": 466.67,
                    "billing_1day_pay_roi": 0.07,
                },
                "yesterday": {"stat_cost": 600, "billing_convert_cnt": 2, "billing_1day_pay_roi": 0.08},
            },
        },
        {
            "advertiser_id": "1856647523922953",
            "project_id": "project-delete",
            "project_name": "0508_郭靖勇者突进_旧项目",
            "status": "PROJECT_STATUS_DISABLE",
            "metrics": {
                "today": {"stat_cost": 0, "billing_convert_cnt": 0, "billing_1day_pay_roi": None},
                "yesterday": {"stat_cost": 0, "billing_convert_cnt": 0, "billing_1day_pay_roi": None},
            },
        },
    ]
    artifact["promotions"] = [
        {
            "advertiser_id": "1856647523922953",
            "project_id": "project-close",
            "promotion_id": "promotion-bad",
            "promotion_name": "0515_郭靖勇者突进_单元差",
            "status": "PROMOTION_STATUS_ENABLE",
            "metrics": {
                "today": {"stat_cost": 400, "billing_convert_cnt": 0, "billing_1day_pay_roi": 0},
                "yesterday": {"stat_cost": 50, "billing_convert_cnt": 0, "billing_1day_pay_roi": 0},
            },
        },
        {
            "advertiser_id": "1856647523922953",
            "project_id": "project-good",
            "promotion_id": "promotion-good",
            "promotion_name": "0515_郭靖勇者突进_单元好",
            "status": "PROMOTION_STATUS_ENABLE",
            "metrics": {
                "today": {"stat_cost": 500, "billing_convert_cnt": 2, "billing_1day_pay_roi": 0.08},
                "yesterday": {"stat_cost": 200, "billing_convert_cnt": 1, "billing_1day_pay_roi": 0.07},
            },
        },
    ]
    return artifact


def _write_evidence_db(db_path: Path) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE operation_logs (
              operation_id TEXT PRIMARY KEY,
              occurred_at TEXT NOT NULL,
              advertiser_id TEXT NOT NULL,
              entity_type TEXT NOT NULL,
              entity_id TEXT NOT NULL,
              action TEXT NOT NULL,
              operator TEXT NOT NULL DEFAULT '',
              detail TEXT NOT NULL DEFAULT '',
              before_json TEXT NOT NULL DEFAULT '{}',
              after_json TEXT NOT NULL DEFAULT '{}',
              payload_json TEXT NOT NULL DEFAULT '{}',
              source TEXT NOT NULL DEFAULT 'test',
              synced_at TEXT NOT NULL DEFAULT ''
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE material_daily_metrics (
              metric_date TEXT NOT NULL,
              advertiser_id TEXT NOT NULL,
              project_id TEXT NOT NULL,
              project_name TEXT NOT NULL DEFAULT '',
              promotion_id TEXT NOT NULL DEFAULT '',
              promotion_name TEXT NOT NULL DEFAULT '',
              material_id TEXT NOT NULL,
              material_kind TEXT NOT NULL DEFAULT 'video',
              stat_cost REAL NOT NULL DEFAULT 0,
              show_cnt REAL NOT NULL DEFAULT 0,
              click_cnt REAL NOT NULL DEFAULT 0,
              convert_cnt REAL NOT NULL DEFAULT 0,
              active_register REAL NOT NULL DEFAULT 0,
              roi_1day REAL NOT NULL DEFAULT 0,
              roi_7days REAL NOT NULL DEFAULT 0,
              metric_payload_json TEXT NOT NULL DEFAULT '{}',
              source TEXT NOT NULL DEFAULT 'test',
              synced_at TEXT NOT NULL DEFAULT ''
            )
            """
        )
        conn.execute(
            """
            INSERT INTO operation_logs (
              operation_id, occurred_at, advertiser_id, entity_type, entity_id, action, detail
            ) VALUES (
              'op-1', '2026-05-14 18:00:00', '1856647523922953', 'project', 'project-close', '修改', '修改 启停状态: 启用 -> 暂停'
            )
            """
        )
        for metric_date, cost, conv in [
            ("2026-05-11", 10, 0),
            ("2026-05-12", 80, 0),
            ("2026-05-13", 100, 0),
            ("2026-05-14", 200, 0),
        ]:
            conn.execute(
                """
                INSERT INTO material_daily_metrics (
                  metric_date, advertiser_id, project_id, project_name, promotion_id, material_id, material_kind, stat_cost, convert_cnt, roi_1day
                ) VALUES (?, '1856647523922953', 'project-close', '0515_郭靖勇者突进_建议关闭', 'promotion-bad', ?, 'video', ?, ?, 0)
                """,
                (metric_date, f"m-{metric_date}", cost, conv),
            )
        conn.execute(
            """
            INSERT INTO material_daily_metrics (
              metric_date, advertiser_id, project_id, project_name, promotion_id, material_id, material_kind, stat_cost, convert_cnt, roi_1day
            ) VALUES ('2026-05-08', '1856647523922953', 'project-delete', '0508_郭靖勇者突进_旧项目', 'promotion-old', 'm-old', 'video', 20, 0, 0)
            """
        )


def test_build_delivery_patrol_suggestions_from_patrol_artifact():
    result = build_delivery_patrol_suggestions(
        _patrol_artifact(),
        {
            "target_date": "2026-05-15",
            "rules": {
                "zero_billing_convert": {"enabled": True, "min_stat_cost": 400},
                "low_billing_roi": {"enabled": True, "min_stat_cost": 500, "roi_lt": 0.05},
            },
        },
    )

    assert result["workflow"] == "delivery_patrol_suggestions"
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 0
    assert result["summary"]["suggestion_count"] == 4
    assert result["summary"]["project_suggestion_count"] == 2
    assert result["summary"]["promotion_suggestion_count"] == 1
    assert result["suggestions"][0]["execution"] == {"enabled": False, "status": "suggestion_only"}
    assert result["suggestions"][0]["suggestion_type"] == "attention_zero_billing_convert"
    assert result["suggestions"][0]["entity_type"] == "account"
    assert result["suggestions"][1]["entity_type"] == "project"


def test_delivery_patrol_suggestions_outputs_actionable_advice_with_evidence(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    _write_evidence_db(db_path)

    result = build_delivery_patrol_suggestions(
        _rich_patrol_artifact(),
        {**_suggestion_request(), "db_path": str(db_path)},
    )

    suggestions = {item["entity_id"]: item for item in result["suggestions"]}
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 0
    assert result["summary"]["suggest_close_project_count"] == 1
    assert result["summary"]["suggest_delete_project_count"] == 1
    assert result["summary"]["suggest_lower_budget_count"] == 1
    assert result["summary"]["suggest_lower_bid_count"] == 1
    assert result["summary"]["continue_running_count"] == 1
    assert result["summary"]["unit_good_signal_count"] == 1
    assert result["summary"]["unit_bad_signal_count"] == 1
    assert suggestions["project-close"]["suggested_action"] == "suggest_close_project"
    assert suggestions["project-close"]["confidence"] == "high"
    assert suggestions["project-close"]["suggestion_id"] == "2026-05-15:project:1856647523922953:project-close:suggest_close_project"
    assert suggestions["project-close"]["evidence"]["operation_history"]["same_entity_operation_count"] == 1
    assert suggestions["project-close"]["evidence"]["operation_history"]["action_counts"] == {"pause_project": 1}
    assert suggestions["project-close"]["evidence"]["lifecycle"]["first_active_date"] == "2026-05-11"
    assert suggestions["project-close"]["evidence"]["lifecycle"]["project_age_days"] == 5
    assert suggestions["project-delete"]["suggested_action"] == "suggest_delete_project"
    assert suggestions["project-delete"]["evidence"]["lifecycle"]["project_age_days"] == 8
    assert suggestions["project-budget"]["suggested_action"] == "suggest_lower_budget"
    assert suggestions["project-budget"]["adjustment"] == {"type": "ratio", "value": -0.2}
    assert suggestions["project-bid"]["suggested_action"] == "suggest_lower_bid"
    assert suggestions["project-bid"]["adjustment"] == {"type": "ratio", "value": -0.1}
    assert suggestions["project-good"]["suggested_action"] == "continue_running"
    assert suggestions["promotion-bad"]["suggested_action"] == "unit_bad_signal"
    assert suggestions["promotion-good"]["suggested_action"] == "unit_good_signal"
    assert result["account_health"][0]["health_status"] == "can_scale"
    assert result["account_health"][1]["health_status"] == "pause_creation"
    assert all(item["execution"] == {"enabled": False, "status": "suggestion_only"} for item in result["suggestions"])


def test_run_delivery_patrol_suggestions_writes_artifact(tmp_path: Path):
    patrol_path = tmp_path / "patrol.json"
    patrol_path.write_text(json.dumps(_patrol_artifact(), ensure_ascii=False), encoding="utf-8")

    result = run_delivery_patrol_suggestions_request(
        {
            "patrol_artifact_path": str(patrol_path),
            "target_date": "2026-05-15",
            "rules": {"zero_billing_convert": {"enabled": True, "min_stat_cost": 400}},
        },
        runs_dir=tmp_path / "runs",
    )

    assert result["ok"] is True
    assert Path(result["artifact_path"]).exists()
    assert result["summary"]["suggestion_count"] == 3


def test_delivery_patrol_suggestions_cli_accepts_artifact_file(tmp_path: Path, capsys):
    patrol_path = tmp_path / "patrol.json"
    patrol_path.write_text(json.dumps(_patrol_artifact(), ensure_ascii=False), encoding="utf-8")
    module = _load_script()

    exit_code = module.run_from_args(
        [
            "--patrol-artifact",
            str(patrol_path),
            "--target-date",
            "2026-05-15",
            "--runs-dir",
            str(tmp_path / "runs"),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["workflow"] == "delivery_patrol_suggestions"
    assert output["external_api_calls"] == 0
    assert output["summary"]["suggestion_count"] >= 1


def test_delivery_patrol_suggestions_cli_accepts_db_path(tmp_path: Path, capsys):
    patrol_path = tmp_path / "patrol.json"
    request_path = tmp_path / "request.json"
    db_path = tmp_path / "roibang.sqlite3"
    _write_evidence_db(db_path)
    patrol_path.write_text(json.dumps(_rich_patrol_artifact(), ensure_ascii=False), encoding="utf-8")
    request_path.write_text(
        json.dumps({"delivery_patrol_suggestions": _suggestion_request()}, ensure_ascii=False),
        encoding="utf-8",
    )
    module = _load_script()

    exit_code = module.run_from_args(
        [
            "--patrol-artifact",
            str(patrol_path),
            "--request",
            str(request_path),
            "--db",
            str(db_path),
            "--runs-dir",
            str(tmp_path / "runs"),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    artifact = json.loads(Path(output["artifact_path"]).read_text(encoding="utf-8"))
    suggestions = {item["entity_id"]: item for item in artifact["suggestions"]}
    assert exit_code == 0
    assert output["external_api_calls"] == 0
    assert suggestions["project-close"]["evidence"]["operation_history"]["same_entity_operation_count"] == 1
