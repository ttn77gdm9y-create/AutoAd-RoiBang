import sqlite3
from pathlib import Path

from roibang_v2.db.bootstrap import bootstrap_database
from roibang_v2.workflows.material_profile_coverage import build_material_profile_coverage_report
from roibang_v2.workflows.material_profile_coverage import run_material_profile_coverage_request


def _insert_metric(
    conn: sqlite3.Connection,
    *,
    metric_date: str,
    advertiser_id: str,
    material_id: str,
    cost: float,
) -> None:
    conn.execute(
        """
        INSERT INTO material_daily_metrics (
          metric_date, advertiser_id, project_id, promotion_id,
          material_id, material_kind, stat_cost, source, synced_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            metric_date,
            advertiser_id,
            f"p-{advertiser_id}",
            f"u-{material_id}",
            material_id,
            "video",
            cost,
            "unit_test",
            "2026-05-08T00:00:00+00:00",
        ),
    )


def _insert_profile(
    conn: sqlite3.Connection,
    *,
    material_id: str,
    source_advertiser_id: str = "",
    name: str = "",
) -> None:
    conn.execute(
        """
        INSERT INTO material_profiles (
          material_id, canonical_material_key, material_kind, name,
          source_advertiser_id, payload_json, source, synced_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            material_id,
            f"material:{material_id}",
            "video",
            name,
            source_advertiser_id,
            "{}",
            "unit_test",
            "2026-05-08T00:00:00+00:00",
        ),
    )


def test_material_profile_coverage_reports_missing_top_by_cost(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)
    with sqlite3.connect(db_path) as conn:
        _insert_metric(conn, metric_date="2026-02-10", advertiser_id="a1", material_id="m1", cost=100)
        _insert_metric(conn, metric_date="2026-02-11", advertiser_id="a2", material_id="m1", cost=50)
        _insert_metric(conn, metric_date="2026-02-10", advertiser_id="a1", material_id="m2", cost=300)
        _insert_metric(conn, metric_date="2026-02-12", advertiser_id="a3", material_id="m3", cost=200)
        _insert_metric(conn, metric_date="2026-02-13", advertiser_id="a3", material_id="m4", cost=0)
        _insert_profile(conn, material_id="m1", source_advertiser_id="source-1", name="源素材1")
        _insert_profile(conn, material_id="m3", source_advertiser_id="target-a", name="目标素材3")

    report = build_material_profile_coverage_report(
        {
            "material_profile_coverage": {
                "date_range": {"start": "2026-02-10", "end": "2026-02-13"},
                "source_accounts": [{"source_advertiser_id": "source-1"}],
                "top_missing_limit": 2,
            }
        },
        db_path=db_path,
    )

    assert report["ok"] is True
    assert report["summary"] == {
        "history_material_count": 4,
        "profiled_material_count": 2,
        "missing_profile_count": 2,
        "coverage_rate": 0.5,
        "source_profiled_material_count": 1,
        "source_coverage_rate": 0.25,
        "history_stat_cost": 650.0,
        "missing_stat_cost": 300.0,
        "missing_cost_rate": 0.4615,
    }
    assert report["top_missing_materials"] == [
        {
            "material_id": "m2",
            "stat_cost": 300.0,
            "account_count": 1,
            "first_seen_date": "2026-02-10",
            "last_seen_date": "2026-02-10",
        },
        {
            "material_id": "m4",
            "stat_cost": 0.0,
            "account_count": 1,
            "first_seen_date": "2026-02-13",
            "last_seen_date": "2026-02-13",
        },
    ]
    assert report["top_missing_accounts"] == [
        {
            "advertiser_id": "a1",
            "missing_material_count": 1,
            "missing_stat_cost": 300.0,
        },
        {
            "advertiser_id": "a3",
            "missing_material_count": 1,
            "missing_stat_cost": 0.0,
        },
    ]


def test_material_profile_coverage_writes_run_artifact(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)
    with sqlite3.connect(db_path) as conn:
        _insert_metric(conn, metric_date="2026-02-10", advertiser_id="a1", material_id="m1", cost=100)

    result = run_material_profile_coverage_request(
        {
            "material_profile_coverage": {
                "date_range": {"start": "2026-02-10", "end": "2026-02-10"},
                "top_missing_limit": 5,
            }
        },
        db_path=db_path,
        runs_dir=tmp_path / "runs",
    )

    assert result["ok"] is True
    assert result["workflow"] == "material_profile_coverage"
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 0
    assert result["summary"]["missing_profile_count"] == 1
    assert Path(result["artifact_path"]).exists()
