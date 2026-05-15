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
    material_kind: str = "video",
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
            material_kind,
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
    assert result["summary"]["rollup_rows_written"] == 6
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
        ("all_history", "m-source-2", "source-v2", "源素材二", "", 0.0, 0.0, 50.0, 1.0, 0.0, 0.0, 1),
        ("last_1d", "m-source-1", "source-v1", "源素材一", "sig-source-1", 12.5, 2048.0, 300.0, 6.0, 0.5, 0.8, 1),
        ("last_1d", "m-source-2", "source-v2", "源素材二", "", 0.0, 0.0, 50.0, 1.0, 0.0, 0.0, 1),
        ("last_2d", "m-source-1", "source-v1", "源素材一", "sig-source-1", 12.5, 2048.0, 400.0, 8.0, 0.4, 0.7, 2),
        ("last_2d", "m-source-2", "source-v2", "源素材二", "", 0.0, 0.0, 50.0, 1.0, 0.0, 0.0, 1),
    ]


def test_product_source_rollup_includes_daily_materials_missing_from_source_table(tmp_path: Path):
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
            },
        ],
        source="unit_test_source",
    )
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO account_materials (
              advertiser_id, material_id, video_id, material_type,
              review_status, source, synced_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "target-a",
                "m-daily-only",
                "target-v-daily-only",
                "video",
                "APPROVED",
                "unit_test",
                "2026-05-08T00:00:00+00:00",
            ),
        )
        _insert_metric(
            conn,
            metric_date="2026-05-08",
            advertiser_id="target-a",
            project_id="p1",
            promotion_id="u1",
            material_id="m-daily-only",
            cost=999,
            convert_cnt=9,
            roi_1day=0.3,
        )

    result = run_product_source_material_rollup_request(
        {
            "product_source_material_rollup": {
                "product": "勇者突进",
                "source_advertiser_id": "1856647522964490",
                "organization_id": "1851650746645060",
                "date_range": {"start": "2026-05-08", "end": "2026-05-08"},
                "windows": ["all"],
            }
        },
        db_path=db_path,
        runs_dir=tmp_path / "runs",
    )

    assert result["summary"]["rollup_rows_written"] == 1
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT material_id, source_video_id, review_status, stat_cost,
                   convert_cnt, roi_1day_cost_weighted
            FROM product_source_material_metric_rollups
            WHERE window_key = 'all_history'
            """
        ).fetchone()

    assert row == ("m-daily-only", "target-v-daily-only", "APPROVED", 999.0, 9.0, 0.3)


def test_product_source_rollup_sets_effective_create_date_from_first_metric_date(tmp_path: Path):
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
                "name": "集中导入素材",
                "material_type": "video",
                "review_status": "APPROVED",
                "create_time": "2026-04-25 12:00:00",
            },
        ],
        source="unit_test_source",
    )
    with sqlite3.connect(db_path) as conn:
        _insert_metric(
            conn,
            metric_date="2026-02-12",
            advertiser_id="target-a",
            project_id="p1",
            promotion_id="u1",
            material_id="m-source-1",
            cost=100,
        )
        _insert_metric(
            conn,
            metric_date="2026-05-08",
            advertiser_id="target-b",
            project_id="p2",
            promotion_id="u2",
            material_id="m-source-1",
            cost=200,
        )

    run_product_source_material_rollup_request(
        {
            "product_source_material_rollup": {
                "product": "勇者突进",
                "source_advertiser_id": "1856647522964490",
                "organization_id": "1851650746645060",
                "date_range": {"start": "2026-02-10", "end": "2026-05-08"},
                "windows": ["all"],
            }
        },
        db_path=db_path,
        runs_dir=tmp_path / "runs",
    )

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT create_time, first_seen_metric_date,
                   effective_create_date, effective_create_date_source
            FROM product_source_material_metric_rollups
            WHERE material_id = 'm-source-1'
            """
        ).fetchone()

    assert row == (
        "2026-04-25 12:00:00",
        "2026-02-12",
        "2026-02-12",
        "material_daily_metrics",
    )


def test_product_source_rollup_maps_target_material_spend_back_to_source_material(tmp_path: Path):
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
            },
        ],
        source="unit_test_source",
    )
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO material_source_mappings (
              product, source_advertiser_id, source_material_id, source_video_id,
              target_advertiser_id, target_material_id, target_video_id,
              source_workflow, first_seen_at, last_seen_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "勇者突进",
                "1856647522964490",
                "m-source-1",
                "source-v1",
                "target-a",
                "m-target-1",
                "target-v1",
                "unit_test",
                "2026-05-08T00:00:00+00:00",
                "2026-05-08T00:00:00+00:00",
            ),
        )
        _insert_metric(
            conn,
            metric_date="2026-05-08",
            advertiser_id="target-a",
            project_id="p1",
            promotion_id="u1",
            material_id="m-target-1",
            cost=250,
            convert_cnt=5,
            roi_1day=0.2,
            roi_7days=0.6,
        )

    result = run_product_source_material_rollup_request(
        {
            "product_source_material_rollup": {
                "product": "勇者突进",
                "source_advertiser_id": "1856647522964490",
                "organization_id": "1851650746645060",
                "date_range": {"start": "2026-05-08", "end": "2026-05-08"},
                "windows": ["all"],
            }
        },
        db_path=db_path,
        runs_dir=tmp_path / "runs",
    )

    assert result["summary"]["rollup_rows_written"] == 1
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT material_id, stat_cost, convert_cnt, roi_1day_cost_weighted, account_count
            FROM product_source_material_metric_rollups
            WHERE window_key = 'all_history'
            """
        ).fetchone()

    assert row == ("m-source-1", 250.0, 5.0, 0.2, 1)


def test_product_source_rollup_backfills_mapping_from_create_ledger_and_account_materials(tmp_path: Path):
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
            },
        ],
        source="unit_test_source",
    )
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO create_provider_id_ledger (
              entity_type, local_key, provider_id, plan_id, request_id,
              advertiser_id, parent_local_key, status, source_workflow,
              execution_enabled, first_seen_at, last_seen_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "target_video",
                "target_video:target-a:source-v1",
                "target-v1",
                "plan-1",
                "request-1",
                "",
                "",
                "active",
                "create_live_execute_once",
                1,
                "2026-05-08T00:00:00+00:00",
                "2026-05-08T00:00:00+00:00",
            ),
        )
        conn.execute(
            """
            INSERT INTO account_materials (
              advertiser_id, material_id, video_id, material_type,
              review_status, source, synced_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "target-a",
                "m-target-1",
                "target-v1",
                "video",
                "APPROVED",
                "unit_test",
                "2026-05-08T00:00:00+00:00",
            ),
        )
        _insert_metric(
            conn,
            metric_date="2026-05-08",
            advertiser_id="target-a",
            project_id="p1",
            promotion_id="u1",
            material_id="m-target-1",
            cost=320,
            convert_cnt=8,
            roi_1day=0.25,
        )

    result = run_product_source_material_rollup_request(
        {
            "product_source_material_rollup": {
                "product": "勇者突进",
                "source_advertiser_id": "1856647522964490",
                "organization_id": "1851650746645060",
                "date_range": {"start": "2026-05-08", "end": "2026-05-08"},
                "windows": ["all"],
            }
        },
        db_path=db_path,
        runs_dir=tmp_path / "runs",
    )

    assert result["summary"]["material_source_mappings_backfilled"] == 1
    with sqlite3.connect(db_path) as conn:
        mapping = conn.execute(
            """
            SELECT source_material_id, source_video_id, target_advertiser_id,
                   target_material_id, target_video_id
            FROM material_source_mappings
            """
        ).fetchone()
        row = conn.execute(
            """
            SELECT material_id, stat_cost, convert_cnt, roi_1day_cost_weighted
            FROM product_source_material_metric_rollups
            WHERE window_key = 'all_history'
            """
        ).fetchone()

    assert mapping == ("m-source-1", "source-v1", "target-a", "m-target-1", "target-v1")
    assert row == ("m-source-1", 320.0, 8.0, 0.25)


def test_product_source_rollup_excludes_title_materials_from_video_candidates(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)
    with sqlite3.connect(db_path) as conn:
        _insert_metric(
            conn,
            metric_date="2026-05-08",
            advertiser_id="target-a",
            project_id="p1",
            promotion_id="u1",
            material_id="title-1",
            cost=500,
            convert_cnt=5,
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

    result = run_product_source_material_rollup_request(
        {
            "product_source_material_rollup": {
                "product": "勇者突进",
                "source_advertiser_id": "1856647522964490",
                "organization_id": "1851650746645060",
                "date_range": {"start": "2026-05-08", "end": "2026-05-08"},
                "windows": ["all"],
            }
        },
        db_path=db_path,
        runs_dir=tmp_path / "runs",
    )

    assert result["summary"]["rollup_rows_written"] == 0
    with sqlite3.connect(db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM product_source_material_metric_rollups").fetchone()[0]

    assert count == 0
