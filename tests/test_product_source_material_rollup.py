import sqlite3
from pathlib import Path

from roibang_v2.db.bootstrap import bootstrap_database
from roibang_v2.materials.product_source import import_product_source_materials
from roibang_v2.workflows.product_source_material_rollup import run_product_source_material_rollup_request


def _insert_metric(
    conn: sqlite3.Connection,
    *,
    metric_date: str,
    advertiser_id: str,
    project_id: str,
    promotion_id: str,
    material_id: str,
    cost: float,
    convert_cnt: float = 0,
    roi_1day: float = 0,
    roi_7days: float = 0,
) -> None:
    conn.execute(
        """
        INSERT INTO material_daily_metrics (
          metric_date, advertiser_id, project_id, promotion_id,
          material_id, material_kind, stat_cost, convert_cnt,
          roi_1day, roi_7days, source, synced_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            metric_date,
            advertiser_id,
            project_id,
            promotion_id,
            material_id,
            "video",
            cost,
            convert_cnt,
            roi_1day,
            roi_7days,
            "unit_test",
            "2026-05-08T00:00:00+00:00",
        ),
    )


def test_product_source_rollup_sums_source_material_spend_from_daily_metrics(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)
    import_product_source_materials(
        db_path=db_path,
        product="勇者突进",
        source_advertiser_id="1856647522964490",
        organization_id="1851650746645060",
        materials=[
            {
                "material_id": "m-source-1",
                "video_id": "source-v1",
                "name": "源素材一",
                "material_type": "video",
                "review_status": "APPROVED",
                "signature": "sig-source-1",
                "duration": 12.5,
                "video_size": "2048",
                "create_time": "2026-05-01 10:00:00",
            },
            {
                "material_id": "m-source-2",
                "video_id": "source-v2",
                "name": "源素材二",
                "material_type": "video",
                "review_status": "APPROVED",
            },
            {
                "material_id": "m-source-no-spend",
                "video_id": "source-v3",
                "name": "源素材未消耗",
                "material_type": "video",
                "review_status": "APPROVED",
            },
        ],
        source="unit_test_source",
    )
    with sqlite3.connect(db_path) as conn:
        _insert_metric(
            conn,
            metric_date="2026-05-07",
            advertiser_id="target-a",
            project_id="p1",
            promotion_id="u1",
            material_id="m-source-1",
            cost=100,
            convert_cnt=2,
            roi_1day=0.1,
            roi_7days=0.4,
        )
        _insert_metric(
            conn,
            metric_date="2026-05-08",
            advertiser_id="target-b",
            project_id="p2",
            promotion_id="u2",
            material_id="m-source-1",
            cost=300,
            convert_cnt=6,
            roi_1day=0.5,
            roi_7days=0.8,
        )
        _insert_metric(
            conn,
            metric_date="2026-05-08",
            advertiser_id="target-a",
            project_id="p3",
            promotion_id="u3",
            material_id="m-not-in-source",
            cost=999,
            convert_cnt=9,
        )
        _insert_metric(
            conn,
            metric_date="2026-05-08",
            advertiser_id="1856647522964490",
            project_id="source-project",
            promotion_id="source-unit",
            material_id="m-source-2",
            cost=50,
            convert_cnt=1,
        )

    result = run_product_source_material_rollup_request(
        {
            "product_source_material_rollup": {
                "product": "勇者突进",
                "source_advertiser_id": "1856647522964490",
                "organization_id": "1851650746645060",
                "date_range": {"start": "2026-05-07", "end": "2026-05-08"},
                "windows": [1, 2, "all"],
            }
        },
        db_path=db_path,
        runs_dir=tmp_path / "runs",
    )

    assert result["ok"] is True
    assert result["external_api_calls"] == 0
    assert result["summary"]["source_material_count"] == 3
    assert result["summary"]["rollup_rows_written"] == 3
    assert Path(result["artifact_path"]).exists()
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT window_key, material_id, source_video_id, name, signature,
                   duration, file_size, stat_cost, convert_cnt,
                   roi_1day_cost_weighted, roi_7days_cost_weighted,
                   account_count
            FROM product_source_material_metric_rollups
            ORDER BY window_key, material_id
            """
        ).fetchall()

    assert rows == [
        ("all_history", "m-source-1", "source-v1", "源素材一", "sig-source-1", 12.5, 2048.0, 400.0, 8.0, 0.4, 0.7, 2),
        ("last_1d", "m-source-1", "source-v1", "源素材一", "sig-source-1", 12.5, 2048.0, 300.0, 6.0, 0.5, 0.8, 1),
        ("last_2d", "m-source-1", "source-v1", "源素材一", "sig-source-1", 12.5, 2048.0, 400.0, 8.0, 0.4, 0.7, 2),
    ]
