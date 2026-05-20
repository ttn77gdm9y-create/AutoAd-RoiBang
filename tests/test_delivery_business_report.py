import importlib.util
import json
from pathlib import Path

from roibang_v2.workflows.delivery_business_report import build_delivery_business_report
from roibang_v2.workflows.delivery_business_report import run_delivery_business_report_request


def _patrol() -> dict:
    return {
        "ok": True,
        "workflow": "delivery_patrol",
        "execution_enabled": False,
        "external_api_calls": 10,
        "summary": {
            "target_date": "2026-05-20",
            "account_count": 2,
            "project_count": 3,
            "promotion_count": 4,
            "attention_count": 2,
            "overall_metrics": {
                "today": {
                    "stat_cost": 1000,
                    "billing_convert_cnt": 2,
                    "billing_1day_pay_roi": 0.04,
                },
                "yesterday": {
                    "stat_cost": 800,
                    "billing_convert_cnt": 3,
                    "billing_1day_pay_roi": 0.08,
                },
            },
            "business_status_counts": {
                "accounts": {"normal": 1, "high_cost_low_return": 1},
                "projects": {"low_roi": 1, "normal": 2},
                "promotions": {"normal": 4},
            },
        },
        "accounts": [
            {
                "advertiser_id": "adv-1",
                "account_name": "账户 A",
                "business_status": "high_cost_low_return",
                "severity": "high",
                "metrics": {"today": {"stat_cost": 600, "billing_convert_cnt": 1, "billing_1day_pay_roi": 0.02}},
                "status_reasons": ["ROI低"],
            },
            {
                "advertiser_id": "adv-2",
                "account_name": "账户 B",
                "business_status": "normal",
                "severity": "none",
                "metrics": {"today": {"stat_cost": 400, "billing_convert_cnt": 1, "billing_1day_pay_roi": 0.1}},
            },
        ],
        "projects": [
            {
                "advertiser_id": "adv-1",
                "project_id": "p-1",
                "project_name": "项目 A",
                "business_status": "low_roi",
                "severity": "high",
                "metrics": {"today": {"stat_cost": 500, "billing_convert_cnt": 1, "billing_1day_pay_roi": 0.02}},
                "status_reasons": ["低ROI"],
            }
        ],
        "promotions": [
            {
                "advertiser_id": "adv-1",
                "project_id": "p-1",
                "promotion_id": "u-1",
                "promotion_name": "单元 A",
                "business_status": "unit_low_roi",
                "severity": "high",
                "metrics": {"today": {"stat_cost": 300, "billing_convert_cnt": 0, "billing_1day_pay_roi": 0}},
                "status_reasons": ["单元低ROI"],
            }
        ],
    }


def _suggestions() -> dict:
    return {
        "ok": True,
        "workflow": "delivery_patrol_suggestions",
        "summary": {
            "target_date": "2026-05-20",
            "suggestion_count": 2,
            "suggest_close_project_count": 1,
            "suggest_lower_bid_count": 1,
        },
        "suggestions": [
            {
                "suggestion_id": "s-close",
                "suggested_action": "suggest_close_project",
                "entity_type": "project",
                "advertiser_id": "adv-1",
                "project_id": "p-1",
                "entity_name": "项目 A",
                "reason": "建议关闭",
                "metrics": {"today": {"stat_cost": 500, "billing_convert_cnt": 0}},
            },
            {
                "suggestion_id": "s-bid",
                "suggested_action": "suggest_lower_bid",
                "entity_type": "project",
                "advertiser_id": "adv-2",
                "project_id": "p-2",
                "entity_name": "项目 B",
                "reason": "建议降出价",
                "adjustment": {"type": "ratio", "value": -0.1},
                "metrics": {"today": {"stat_cost": 700, "billing_convert_cnt": 2, "billing_1day_pay_roi": 0.03}},
            },
        ],
    }


def _backtest() -> dict:
    return {
        "ok": True,
        "workflow": "delivery_suggestion_backtest",
        "summary": {
            "evaluated_suggestion_count": 2,
            "status_counts": {"pending_future_data": 2},
        },
        "evaluations": [],
    }


def _create_batch_review() -> dict:
    return {
        "ok": True,
        "workflow": "create_batch_review",
        "summary": {
            "batch_count": 2,
            "project_count": 10,
            "stat_cost": 1200,
            "convert_cnt": 4,
            "roi_1day": 0.05,
        },
        "mode_summary": [
            {
                "mode_label": "微小每付通投历史放量",
                "project_count": 5,
                "stat_cost": 800,
                "convert_cnt": 3,
                "conversion_cost": 266.6667,
                "roi_1day": 0.06,
            }
        ],
        "batches": [
            {
                "batch_date_code": "0520",
                "mode_label": "微小每付通投历史放量",
                "batch_id": "BATCH1",
                "project_count": 5,
                "stat_cost": 800,
                "convert_cnt": 3,
                "conversion_cost": 266.6667,
                "roi_1day": 0.06,
            }
        ],
    }


def _load_script():
    script_path = Path("scripts/run_delivery_business_report.py")
    spec = importlib.util.spec_from_file_location("run_delivery_business_report", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_build_delivery_business_report_merges_patrol_suggestions_backtest_and_create_review():
    result = build_delivery_business_report(
        patrol=_patrol(),
        suggestions=_suggestions(),
        backtest=_backtest(),
        create_batch_review=_create_batch_review(),
    )

    assert result["workflow"] == "delivery_business_report"
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 0
    assert result["summary"] == {
        "account_count": 2,
        "project_count": 3,
        "promotion_count": 4,
        "attention_count": 2,
        "suggestion_count": 2,
    }
    assert result["suggestions_today"]["counts"] == {
        "suggest_close_project": 1,
        "suggest_lower_bid": 1,
    }
    assert result["suggestions_today"]["counts_labeled"] == {
        "建议关闭项目": 1,
        "建议下调出价": 1,
    }
    assert result["suggestion_backtest"]["status_counts_labeled"] == {"等待后续数据": 2}
    assert result["create_batch_review"]["available"] is True
    assert result["create_batch_review"]["summary"]["batch_count"] == 2
    assert result["create_batch_review"]["mode_summary"][0]["mode_label"] == "微小每付通投历史放量"
    assert [item["type"] for item in result["next_actions"]] == [
        "suggest_lower_bid",
        "suggest_close_project",
        "wait_backtest",
    ]
    assert "RoiBang-V2 投放运营日报 2026-05-20" in result["message"]
    assert "一、整体判断" in result["message"]
    assert "二、今日建议" in result["message"]
    assert "建议关闭项目 1 / 建议下调出价 1" in result["message"]
    assert "三、重点账户" in result["message"]
    assert "四、重点项目" in result["message"]
    assert "五、创建批次复盘" in result["message"]
    assert "批次 2 个，项目 10 个" in result["message"]


def test_run_delivery_business_report_request_writes_artifact(tmp_path: Path):
    patrol_path = tmp_path / "patrol.json"
    suggestions_path = tmp_path / "suggestions.json"
    backtest_path = tmp_path / "backtest.json"
    create_batch_review_path = tmp_path / "create_batch_review.json"
    patrol_path.write_text(json.dumps(_patrol(), ensure_ascii=False), encoding="utf-8")
    suggestions_path.write_text(json.dumps(_suggestions(), ensure_ascii=False), encoding="utf-8")
    backtest_path.write_text(json.dumps(_backtest(), ensure_ascii=False), encoding="utf-8")
    create_batch_review_path.write_text(json.dumps(_create_batch_review(), ensure_ascii=False), encoding="utf-8")

    result = run_delivery_business_report_request(
        {
            "patrol_artifact_path": str(patrol_path),
            "suggestions_artifact_path": str(suggestions_path),
            "backtest_artifact_path": str(backtest_path),
            "create_batch_review_artifact_path": str(create_batch_review_path),
        },
        runs_dir=tmp_path / "runs",
    )

    assert result["ok"] is True
    assert Path(result["artifact_path"]).exists()
    assert Path(result["latest_artifact_path"]).exists()
    assert json.loads(Path(result["latest_artifact_path"]).read_text(encoding="utf-8"))["workflow"] == "delivery_business_report"
    assert result["source"] == {
        "patrol_artifact_path": str(patrol_path),
        "suggestions_artifact_path": str(suggestions_path),
        "backtest_artifact_path": str(backtest_path),
        "create_batch_review_artifact_path": str(create_batch_review_path),
    }


def test_delivery_business_report_cli_accepts_artifact_files(tmp_path: Path, capsys):
    patrol_path = tmp_path / "patrol.json"
    suggestions_path = tmp_path / "suggestions.json"
    patrol_path.write_text(json.dumps(_patrol(), ensure_ascii=False), encoding="utf-8")
    suggestions_path.write_text(json.dumps(_suggestions(), ensure_ascii=False), encoding="utf-8")
    module = _load_script()

    exit_code = module.run_from_args(
        [
            "--patrol-artifact",
            str(patrol_path),
            "--suggestions-artifact",
            str(suggestions_path),
            "--runs-dir",
            str(tmp_path / "runs"),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["workflow"] == "delivery_business_report"
    assert output["execution_enabled"] is False
    assert output["external_api_calls"] == 0
    assert output["summary"]["suggestion_count"] == 2
    assert "message" in output
