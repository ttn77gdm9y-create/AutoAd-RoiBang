import importlib.util
import json
import sqlite3
from pathlib import Path

from roibang_v2.workflows.delivery_readonly_report_chain import run_delivery_readonly_report_chain_request


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
          synced_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        INSERT INTO material_daily_metrics (
          metric_date, advertiser_id, project_id, project_name, promotion_id, promotion_name,
          material_id, stat_cost, show_cnt, click_cnt, convert_cnt, active_register, roi_1day,
          source, synced_at
        )
        VALUES (
          '2026-05-20', 'adv-1', 'p-1',
          '0520_郭靖_勇者突进_微小每付通投历史放量_BATCH1_01',
          'u-1', '单元 1', 'm-1', 100, 1000, 20, 1, 2, 0.1,
          'test', '2026-05-20T00:00:00'
        )
        """
    )
    conn.commit()
    conn.close()


def _patrol() -> dict:
    return {
        "ok": True,
        "summary": {
            "target_date": "2026-05-20",
            "account_count": 1,
            "project_count": 1,
            "promotion_count": 1,
            "attention_count": 0,
            "overall_metrics": {"today": {"stat_cost": 100}, "yesterday": {"stat_cost": 80}},
        },
        "accounts": [],
        "projects": [],
        "promotions": [],
    }


def _suggestions() -> dict:
    return {
        "ok": True,
        "summary": {"target_date": "2026-05-20"},
        "suggestions": [],
    }


def _load_script():
    script_path = Path("scripts/run_delivery_readonly_report_chain.py")
    spec = importlib.util.spec_from_file_location("run_delivery_readonly_report_chain", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_run_delivery_readonly_report_chain_writes_all_artifacts(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    patrol_path = tmp_path / "patrol.json"
    suggestions_path = tmp_path / "suggestions.json"
    _init_db(db_path)
    patrol_path.write_text(json.dumps(_patrol(), ensure_ascii=False), encoding="utf-8")
    suggestions_path.write_text(json.dumps(_suggestions(), ensure_ascii=False), encoding="utf-8")

    result = run_delivery_readonly_report_chain_request(
        {
            "db_path": str(db_path),
            "patrol_artifact_path": str(patrol_path),
            "suggestions_artifact_path": str(suggestions_path),
            "recent_days": 1,
            "project_name_contains": "郭靖",
        },
        runs_dir=tmp_path / "runs",
    )

    assert result["workflow"] == "delivery_readonly_report_chain"
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 0
    assert Path(result["artifact_path"]).exists()
    assert Path(result["latest_artifact_path"]).exists()
    assert Path(result["artifacts"]["backtest_latest_artifact_path"]).exists()
    assert Path(result["artifacts"]["create_batch_review_latest_artifact_path"]).exists()
    assert Path(result["artifacts"]["business_report_latest_artifact_path"]).exists()
    assert result["summary"]["create_batch_review"]["batch_count"] == 1
    assert result["delivery"]["feishu"] == {
        "enabled": False,
        "attempted": False,
        "ok": True,
        "reason": "disabled",
    }


def test_run_delivery_readonly_report_chain_can_deliver_feishu_with_injected_sender(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    patrol_path = tmp_path / "patrol.json"
    suggestions_path = tmp_path / "suggestions.json"
    sent: list[tuple[dict, str]] = []
    _init_db(db_path)
    patrol_path.write_text(json.dumps(_patrol(), ensure_ascii=False), encoding="utf-8")
    suggestions_path.write_text(json.dumps(_suggestions(), ensure_ascii=False), encoding="utf-8")

    def fake_sender(feishu: dict, message: str) -> dict:
        sent.append((feishu, message))
        return {"ok": True, "stage": "fake"}

    result = run_delivery_readonly_report_chain_request(
        {
            "db_path": str(db_path),
            "patrol_artifact_path": str(patrol_path),
            "suggestions_artifact_path": str(suggestions_path),
            "recent_days": 1,
            "project_name_contains": "郭靖",
            "delivery": {"feishu": {"enabled": True, "chat_id": "chat"}},
        },
        runs_dir=tmp_path / "runs",
        feishu_sender=fake_sender,
    )

    assert result["delivery"]["feishu"] == {
        "enabled": True,
        "attempted": True,
        "ok": True,
        "stage": "fake",
    }
    assert len(sent) == 1
    assert sent[0][0]["chat_id"] == "chat"
    assert "RoiBang-V2 业务日报" in sent[0][1]


def test_delivery_readonly_report_chain_cli_accepts_request_file(tmp_path: Path, capsys):
    db_path = tmp_path / "roibang.sqlite3"
    patrol_path = tmp_path / "patrol.json"
    suggestions_path = tmp_path / "suggestions.json"
    request_path = tmp_path / "request.json"
    _init_db(db_path)
    patrol_path.write_text(json.dumps(_patrol(), ensure_ascii=False), encoding="utf-8")
    suggestions_path.write_text(json.dumps(_suggestions(), ensure_ascii=False), encoding="utf-8")
    request_path.write_text(
        json.dumps(
            {
                "delivery_readonly_report_chain": {
                    "db_path": str(db_path),
                    "patrol_artifact_path": str(patrol_path),
                    "suggestions_artifact_path": str(suggestions_path),
                    "recent_days": 1,
                    "project_name_contains": "郭靖",
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    module = _load_script()

    exit_code = module.run_from_args(["--request", str(request_path), "--runs-dir", str(tmp_path / "runs")])

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["workflow"] == "delivery_readonly_report_chain"
    assert output["external_api_calls"] == 0
    assert output["summary"]["create_batch_review"]["batch_count"] == 1
    assert output["delivery"]["feishu"]["attempted"] is False
