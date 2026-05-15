import sqlite3
from pathlib import Path

from roibang_v2.db.bootstrap import bootstrap_database
from roibang_v2.workflows.material_kind_reconcile import run_material_kind_reconcile_request


def test_material_kind_reconcile_corrects_report_rows_from_local_bindings(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO material_daily_metrics (
              metric_date, advertiser_id, project_id, promotion_id,
              material_id, material_kind, stat_cost, source, synced_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-05-08",
                "target-a",
                "p1",
                "u1",
                "title-1",
                "video",
                100,
                "unit_test",
                "2026-05-08T00:00:00+00:00",
            ),
        )
        conn.execute(
            """
            INSERT INTO material_bindings (
              advertiser_id, project_id, promotion_id, material_kind,
              material_id, title, source, synced_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "target-a",
                "p1",
                "u1",
                "title",
                "title-1",
                "测试文案",
                "unit_test",
                "2026-05-08T00:00:00+00:00",
            ),
        )

    result = run_material_kind_reconcile_request(
        {
            "material_kind_reconcile": {
                "date_range": {"start": "2026-05-08", "end": "2026-05-08"},
            }
        },
        db_path=db_path,
        runs_dir=tmp_path / "runs",
    )

    assert result["ok"] is True
    assert result["summary"]["rows_updated"] == 1
    assert result["summary"]["material_ids_updated"] == 1
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT material_kind FROM material_daily_metrics WHERE material_id = 'title-1'"
        ).fetchone()

    assert row == ("title",)


def test_material_kind_reconcile_marks_rows_without_video_evidence_unknown(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            """
            INSERT INTO material_daily_metrics (
              metric_date, advertiser_id, project_id, promotion_id,
              material_id, material_kind, stat_cost, source, synced_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("2026-05-08", "target-a", "p1", "u1", "unknown-1", "video", 100, "unit_test", "now"),
                ("2026-05-08", "target-a", "p1", "u1", "video-1", "video", 200, "unit_test", "now"),
            ],
        )
        conn.execute(
            """
            INSERT INTO account_materials (
              advertiser_id, material_id, video_id, material_type,
              review_status, source, synced_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("target-a", "video-1", "v-real", "video", "APPROVED", "unit_test", "now"),
        )

    result = run_material_kind_reconcile_request(
        {
            "material_kind_reconcile": {
                "date_range": {"start": "2026-05-08", "end": "2026-05-08"},
                "mark_unresolved_video_as_unknown": True,
            }
        },
        db_path=db_path,
        runs_dir=tmp_path / "runs",
    )

    assert result["summary"]["rows_updated"] == 1
    assert result["summary"]["updates_by_kind"] == {"unknown": 1}
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT material_id, material_kind FROM material_daily_metrics ORDER BY material_id"
        ).fetchall()

    assert rows == [("unknown-1", "unknown"), ("video-1", "video")]
