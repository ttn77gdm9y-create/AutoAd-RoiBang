import sqlite3
from pathlib import Path

from roibang_v2.db.bootstrap import bootstrap_database
from roibang_v2.materials.product_source import import_product_source_materials
from roibang_v2.workflows.product_source_material_rollup import run_product_source_material_rollup_request
from roibang_v2.workflows.source_material_candidate_pool import run_source_material_candidate_pool_request


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
) -> None:
    conn.execute(
        """
        INSERT INTO material_daily_metrics (
          metric_date, advertiser_id, project_id, promotion_id,
          material_id, material_kind, stat_cost, convert_cnt, source, synced_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            "unit_test",
            "2026-05-08T00:00:00+00:00",
        ),
    )


def _seed_source_materials(db_path: Path) -> None:
    import_product_source_materials(
        db_path=db_path,
        product="勇者突进",
        source_advertiser_id="source-1",
        organization_id="org-1",
        materials=[
            {
                "material_id": "m-high",
                "video_id": "source-v-high",
                "name": "高消耗素材",
                "material_type": "video",
                "review_status": "APPROVED",
                "signature": "sig-high",
                "duration": 15,
            },
            {
                "material_id": "m-low",
                "video_id": "source-v-low",
                "name": "低消耗素材",
                "material_type": "video",
                "review_status": "APPROVED",
                "signature": "sig-low",
                "duration": 12,
            },
            {
                "material_id": "m-image",
                "name": "图片素材",
                "material_type": "image",
                "review_status": "APPROVED",
            },
            {
                "material_id": "m-zero",
                "video_id": "source-v-zero",
                "name": "未消耗素材",
                "material_type": "video",
                "review_status": "APPROVED",
            },
        ],
        source="unit_test_source",
    )


def test_source_material_candidate_pool_writes_ranked_video_candidates(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)
    _seed_source_materials(db_path)
    with sqlite3.connect(db_path) as conn:
        _insert_metric(
            conn,
            metric_date="2026-05-07",
            advertiser_id="target-a",
            project_id="p1",
            promotion_id="u1",
            material_id="m-low",
            cost=100,
            convert_cnt=1,
        )
        _insert_metric(
            conn,
            metric_date="2026-05-07",
            advertiser_id="target-a",
            project_id="p2",
            promotion_id="u2",
            material_id="m-high",
            cost=600,
            convert_cnt=6,
        )
        _insert_metric(
            conn,
            metric_date="2026-05-07",
            advertiser_id="source-1",
            project_id="source-project",
            promotion_id="source-unit",
            material_id="m-zero",
            cost=900,
            convert_cnt=9,
        )

    run_product_source_material_rollup_request(
        {
            "product_source_material_rollup": {
                "product": "勇者突进",
                "source_advertiser_id": "source-1",
                "organization_id": "org-1",
                "date_range": {"start": "2026-05-07", "end": "2026-05-07"},
                "windows": ["all"],
            }
        },
        db_path=db_path,
        runs_dir=tmp_path / "runs",
    )

    result = run_source_material_candidate_pool_request(
        {
            "source_material_candidate_pool": {
                "product": "勇者突进",
                "source_advertiser_id": "source-1",
                "organization_id": "org-1",
                "pool_key": "unit-test-pool",
                "candidate_policy": {
                    "window_key": "all_history",
                    "material_type": "video",
                    "limit": 10,
                    "min_stat_cost": 0,
                    "min_account_count": 1,
                },
            }
        },
        db_path=db_path,
        runs_dir=tmp_path / "runs",
    )

    assert result["ok"] is True
    assert result["external_api_calls"] == 0
    assert result["summary"]["candidate_count"] == 2
    assert result["acceptance"]["source_summary"]["active_source_material_count"] == 4
    assert result["acceptance"]["source_summary"]["active_video_count"] == 3
    assert result["acceptance"]["source_summary"]["active_image_count"] == 1
    assert result["acceptance"]["source_summary"]["active_video_without_spend_count"] == 1
    assert result["top_candidates"][0]["material_id"] == "m-high"
    assert Path(result["artifact_path"]).exists()

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT rank, material_id, name, stat_cost, score, source_video_id
            FROM product_source_material_candidates
            WHERE pool_key = ?
            ORDER BY rank
            """,
            ("unit-test-pool",),
        ).fetchall()

    assert rows == [
        (1, "m-high", "高消耗素材", 600.0, 600.0, "source-v-high"),
        (2, "m-low", "低消耗素材", 100.0, 100.0, "source-v-low"),
    ]


def test_source_material_candidate_pool_handles_missing_rollup_window(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)
    _seed_source_materials(db_path)

    result = run_source_material_candidate_pool_request(
        {
            "source_material_candidate_pool": {
                "product": "勇者突进",
                "source_advertiser_id": "source-1",
                "organization_id": "org-1",
                "pool_key": "empty-pool",
                "candidate_policy": {"window_key": "last_7d", "material_type": "video"},
            }
        },
        db_path=db_path,
        runs_dir=tmp_path / "runs",
    )

    assert result["ok"] is True
    assert result["summary"]["candidate_count"] == 0
    assert result["summary"]["period_start"] == ""
    assert result["acceptance"]["rollup_summary"]["matched_source_material_count"] == 0
    with sqlite3.connect(db_path) as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM product_source_material_candidates WHERE pool_key = ?",
            ("empty-pool",),
        ).fetchone()[0]
    assert count == 0
