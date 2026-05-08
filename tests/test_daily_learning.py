from pathlib import Path

from roibang_v2.db.bootstrap import bootstrap_database
from roibang_v2.reports.snapshot import import_report_snapshot_file
from roibang_v2.workflows.daily_learning import build_daily_learning_artifact, run_daily_learning_request


def test_builds_daily_learning_artifact_from_sqlite_snapshot(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)
    import_report_snapshot_file("data/fixtures/report-snapshot.sample.json", db_path=db_path)

    artifact = build_daily_learning_artifact(
        db_path=db_path,
        policy={
            "target_date": "2026-05-05",
            "min_cost_for_signal": 50,
            "min_conversions_for_signal": 3,
            "low_roi_threshold": 0.4,
            "top_material_limit": 10,
        },
    )

    assert artifact["phase"] == "phase1"
    assert artifact["execution_enabled"] is False
    assert artifact["external_api_calls"] == 0
    assert artifact["summary"] == {
        "target_date": "2026-05-05",
        "promotion_metric_count": 1,
        "account_signal_count": 1,
        "top_material_count": 2,
        "operation_log_count": 3,
        "decision_hint_count": 3,
    }
    assert artifact["account_signals"] == [
        {
            "advertiser_id": "1850000000000001",
            "stat_cost": 100.0,
            "conversions": 2,
            "roi": 0.31,
            "flags": ["high_spend_low_roi", "low_conversion_volume"],
        }
    ]
    assert artifact["material_delta"]["top_materials"][0]["material_id"] == "m001"
    assert artifact["operation_log_summary"] == {
        "target_date": "2026-05-05",
        "total_count": 3,
        "by_entity_type": {"account": 1, "project": 1, "promotion": 1},
        "by_action": {"replace_material": 1, "sync_report": 1, "update_budget": 1},
        "recent_logs": [
            {
                "operation_id": "op-promotion-001",
                "occurred_at": "2026-05-05T11:30:00+08:00",
                "operator": "operator_a",
                "entity_type": "promotion",
                "entity_id": "u001",
                "action": "replace_material",
                "detail": "单元替换为素材m001",
            },
            {
                "operation_id": "op-project-001",
                "occurred_at": "2026-05-05T10:20:00+08:00",
                "operator": "operator_a",
                "entity_type": "project",
                "entity_id": "p001",
                "action": "update_budget",
                "detail": "项目预算从300调整到500",
            },
            {
                "operation_id": "op-account-001",
                "occurred_at": "2026-05-05T09:10:00+08:00",
                "operator": "system",
                "entity_type": "account",
                "entity_id": "1850000000000001",
                "action": "sync_report",
                "detail": "同步账户报表数据",
            },
        ],
    }
    assert artifact["decision_hints"][0]["hint_type"] == "review_account"
    assert artifact["decision_hints"][1]["hint_type"] == "review_material"
    assert artifact["decision_hints"][2]["hint_type"] == "review_operation_logs"
    assert artifact["guardrails"] == [
        "Phase 1 learning artifacts are read-only.",
        "Do not create, pause, delete, push, bind, or update live ad objects.",
        "Future live actions must follow request -> strategy -> preflight -> dry-run -> approve -> execute.",
    ]


def test_daily_learning_request_writes_run_artifact(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)
    import_report_snapshot_file("data/fixtures/report-snapshot.sample.json", db_path=db_path)

    result = run_daily_learning_request(
        {
            "daily_learning": {
                "target_date": "2026-05-05",
                "min_cost_for_signal": 50,
                "min_conversions_for_signal": 3,
                "low_roi_threshold": 0.4,
                "top_material_limit": 10,
            }
        },
        db_path=db_path,
        runs_dir=tmp_path / "runs",
    )

    artifact = Path(result["artifact_path"])
    assert artifact.exists()
    assert result["ok"] is True
    assert result["artifact"]["summary"]["decision_hint_count"] == 3
    assert result["artifact"]["execution_enabled"] is False
