import sqlite3
from pathlib import Path

from roibang_v2.db.bootstrap import bootstrap_database
from roibang_v2.reports.snapshot import import_report_snapshot_file, summarize_materials
from roibang_v2.workflows.data_sync import run_data_sync_request


def test_imports_report_snapshot_and_material_summary(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)

    result = import_report_snapshot_file(
        Path("data/fixtures/report-snapshot.sample.json"),
        db_path=db_path,
    )

    with sqlite3.connect(db_path) as conn:
        project_count = conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
        promotion_count = conn.execute("SELECT COUNT(*) FROM promotions").fetchone()[0]
        binding_count = conn.execute("SELECT COUNT(*) FROM material_bindings").fetchone()[0]
        metric_count = conn.execute("SELECT COUNT(*) FROM metric_snapshots").fetchone()[0]
        operation_log_count = conn.execute("SELECT COUNT(*) FROM operation_logs").fetchone()[0]

    assert result == {
        "ok": True,
        "period": {"start": "2026-05-05", "end": "2026-05-05"},
        "accounts": 1,
        "projects_imported": 1,
        "promotions_imported": 1,
        "material_bindings_imported": 2,
        "promotion_metrics_imported": 1,
        "operation_logs_imported": 3,
        "material_summary_count": 2,
        "external_api_calls": 0,
    }
    assert project_count == 1
    assert promotion_count == 1
    assert binding_count == 2
    assert metric_count == 1
    assert operation_log_count == 3


def test_report_snapshot_import_is_idempotent_for_promotion_metrics(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)

    import_report_snapshot_file("data/fixtures/report-snapshot.sample.json", db_path=db_path)
    import_report_snapshot_file("data/fixtures/report-snapshot.sample.json", db_path=db_path)

    with sqlite3.connect(db_path) as conn:
        metric_count = conn.execute("SELECT COUNT(*) FROM metric_snapshots").fetchone()[0]
        summary_count = conn.execute("SELECT COUNT(*) FROM material_metric_summaries").fetchone()[0]
        operation_log_count = conn.execute("SELECT COUNT(*) FROM operation_logs").fetchone()[0]

    assert metric_count == 1
    assert summary_count == 2
    assert operation_log_count == 3


def test_summarizes_materials_with_cost_weighted_roi():
    rows = [
        {
            "advertiser_id": "1850000000000001",
            "project_id": "p001",
            "promotion_id": "u001",
            "material_kind": "video",
            "material_id": "m001",
            "video_id": "v001",
            "title": "勇者开局强冲",
        }
    ]
    metrics = {
        "u001": {
            "stat_cost": 100,
            "active_register": 4,
            "attribution_convert_cnt": 2,
            "attribution_billing_game_in_app_roi_1day": 0.31,
            "attribution_billing_game_in_app_roi_7days": 0.57,
        }
    }

    summary = summarize_materials(rows, metrics)

    assert summary == [
        {
            "material_kind": "video",
            "material_id": "m001",
            "video_id": "v001",
            "title": "勇者开局强冲",
            "promotion_count": 1,
            "project_count": 1,
            "account_count": 1,
            "stat_cost": 100.0,
            "active_register": 4.0,
            "attribution_convert_cnt": 2.0,
            "roi_1day_cost_weighted": 0.31,
            "roi_7days_cost_weighted": 0.57,
        }
    ]


def test_data_sync_request_writes_phase1_artifact(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)

    result = run_data_sync_request(
        {"data_sync": {"kind": "local_report_snapshot", "snapshot_file": "data/fixtures/report-snapshot.sample.json"}},
        db_path=db_path,
        runs_dir=tmp_path / "runs",
    )

    artifact = Path(result["artifact_path"])
    assert artifact.exists()
    assert result["ok"] is True
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 0
    assert result["import"]["projects_imported"] == 1
    assert result["import"]["material_summary_count"] == 2
    assert result["import"]["operation_logs_imported"] == 3
