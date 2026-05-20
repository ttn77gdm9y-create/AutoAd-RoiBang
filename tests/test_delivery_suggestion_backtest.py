import importlib.util
import json
import sqlite3
from pathlib import Path

from roibang_v2.workflows.delivery_suggestion_backtest import run_delivery_suggestion_backtest_request


def _init_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE material_daily_metrics (
          metric_date TEXT NOT NULL,
          advertiser_id TEXT NOT NULL,
          project_id TEXT NOT NULL DEFAULT '',
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
          source TEXT NOT NULL,
          synced_at TEXT NOT NULL,
          PRIMARY KEY (metric_date, advertiser_id, project_id, promotion_id, material_id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE operation_logs (
          operation_id TEXT PRIMARY KEY,
          occurred_at TEXT NOT NULL,
          advertiser_id TEXT NOT NULL DEFAULT '',
          entity_type TEXT NOT NULL,
          entity_id TEXT NOT NULL,
          action TEXT NOT NULL,
          operator TEXT NOT NULL DEFAULT '',
          detail TEXT NOT NULL DEFAULT '',
          before_json TEXT NOT NULL DEFAULT '{}',
          after_json TEXT NOT NULL DEFAULT '{}',
          payload_json TEXT NOT NULL DEFAULT '{}',
          source TEXT NOT NULL,
          synced_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def _insert_metric(path: Path, *, date: str, advertiser_id: str, project_id: str, cost: float, convert: float) -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        """
        INSERT INTO material_daily_metrics (
          metric_date, advertiser_id, project_id, project_name, promotion_id, promotion_name,
          material_id, material_kind, stat_cost, convert_cnt, source, synced_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (date, advertiser_id, project_id, f"项目-{project_id}", "unit-1", "单元", f"m-{project_id}", "video", cost, convert, "test", "now"),
    )
    conn.commit()
    conn.close()


def _insert_operation(path: Path, *, operation_id: str, advertiser_id: str, project_id: str, detail: str) -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        """
        INSERT INTO operation_logs (
          operation_id, occurred_at, advertiser_id, entity_type, entity_id, action, detail, source, synced_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (operation_id, "2026-05-13 10:00:00", advertiser_id, "project", project_id, "修改", detail, "test", "now"),
    )
    conn.commit()
    conn.close()


def _suggestions() -> dict:
    return {
        "ok": True,
        "workflow": "delivery_patrol_suggestions",
        "summary": {"target_date": "2026-05-12"},
        "suggestions": [
            {
                "suggestion_id": "close-1",
                "suggested_action": "suggest_close_project",
                "target_date": "2026-05-12",
                "entity_type": "project",
                "advertiser_id": "adv-1",
                "project_id": "p-close-supported",
                "entity_name": "关闭支持",
            },
            {
                "suggestion_id": "close-2",
                "suggested_action": "suggest_close_project",
                "target_date": "2026-05-12",
                "entity_type": "project",
                "advertiser_id": "adv-1",
                "project_id": "p-close-review",
                "entity_name": "关闭待复核",
            },
            {
                "suggestion_id": "bid-1",
                "suggested_action": "suggest_lower_bid",
                "target_date": "2026-05-12",
                "entity_type": "project",
                "advertiser_id": "adv-2",
                "project_id": "p-bid",
                "entity_name": "降出价",
            },
        ],
    }


def _load_script():
    script_path = Path("scripts/run_delivery_suggestion_backtest.py")
    spec = importlib.util.spec_from_file_location("run_delivery_suggestion_backtest", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_delivery_suggestion_backtest_evaluates_close_and_bid_suggestions(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    _init_db(db_path)
    _insert_metric(db_path, date="2026-05-13", advertiser_id="adv-1", project_id="p-close-supported", cost=0, convert=0)
    _insert_metric(db_path, date="2026-05-13", advertiser_id="adv-1", project_id="p-close-review", cost=600, convert=2)
    _insert_metric(db_path, date="2026-05-13", advertiser_id="adv-2", project_id="p-bid", cost=300, convert=1)
    _insert_operation(db_path, operation_id="op-bid", advertiser_id="adv-2", project_id="p-bid", detail="修改 出价: 103 -> 92.7")

    result = run_delivery_suggestion_backtest_request(
        {
            "suggestions_artifact": _suggestions(),
            "suggestions_artifact_paths": [],
            "db_path": str(db_path),
            "lookahead_days": 1,
        },
        runs_dir=tmp_path / "runs",
    )

    assert result["ok"] is True
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 0
    assert result["summary"]["evaluated_suggestion_count"] == 3
    assert result["summary"]["status_counts"] == {
        "supported": 1,
        "needs_review": 1,
        "execution_observed": 1,
    }
    statuses = {item["suggestion_id"]: item["evaluation_status"] for item in result["evaluations"]}
    assert statuses == {
        "close-1": "supported",
        "close-2": "needs_review",
        "bid-1": "execution_observed",
    }
    assert Path(result["artifact_path"]).exists()
    assert Path(result["latest_artifact_path"]).exists()
    assert json.loads(Path(result["latest_artifact_path"]).read_text(encoding="utf-8"))["workflow"] == "delivery_suggestion_backtest"


def test_delivery_suggestion_backtest_cli_accepts_artifact_file(tmp_path: Path, capsys):
    db_path = tmp_path / "roibang.sqlite3"
    suggestions_path = tmp_path / "suggestions.json"
    _init_db(db_path)
    suggestions_path.write_text(json.dumps(_suggestions(), ensure_ascii=False), encoding="utf-8")
    module = _load_script()

    exit_code = module.run_from_args(
        [
            "--suggestions-artifact",
            str(suggestions_path),
            "--db",
            str(db_path),
            "--lookahead-days",
            "1",
            "--runs-dir",
            str(tmp_path / "runs"),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["workflow"] == "delivery_suggestion_backtest"
    assert output["execution_enabled"] is False
    assert output["external_api_calls"] == 0
    assert output["summary"]["evaluated_suggestion_count"] == 3


def test_delivery_suggestion_backtest_waits_for_complete_future_window(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    _init_db(db_path)
    _insert_metric(db_path, date="2026-05-12", advertiser_id="adv-1", project_id="p-close-supported", cost=500, convert=0)

    result = run_delivery_suggestion_backtest_request(
        {
            "suggestions_artifact": _suggestions(),
            "db_path": str(db_path),
            "lookahead_days": 1,
        },
        runs_dir=tmp_path / "runs",
    )

    assert result["summary"]["max_metric_date"] == "2026-05-12"
    assert result["summary"]["status_counts"] == {"pending_future_data": 3}
    assert {item["evaluation_status"] for item in result["evaluations"]} == {"pending_future_data"}
