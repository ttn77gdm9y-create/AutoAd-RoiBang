import importlib.util
import json
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
