import importlib.util
import json
import sqlite3
from pathlib import Path

from roibang_v2.db.bootstrap import bootstrap_database
from roibang_v2.workflows.material_quality_rollup import build_material_quality_report
from roibang_v2.workflows.material_quality_rollup import run_material_quality_rollup_request
from roibang_v2.workflows.material_profile_sync import build_material_profile_sync_preflight
from roibang_v2.workflows.material_profile_sync import run_material_profile_sync_request


def _record_state(
    conn: sqlite3.Connection,
    *,
    sync_date: str,
    status: str = "completed",
    row_count: int = 0,
    product: str = "勇者突进",
    platform: str = "WECHAT_GAME",
) -> None:
    conn.execute(
        """
        INSERT INTO material_sync_state (
          workflow, sync_date, status, product, platform,
          account_count, material_row_count, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "material_history_backfill",
            sync_date,
            status,
            product,
            platform,
            1,
            row_count,
            "2026-05-08T00:00:00+00:00",
        ),
    )


def _insert_metric(
    conn: sqlite3.Connection,
    *,
    metric_date: str,
    advertiser_id: str,
    project_id: str,
    promotion_id: str,
    material_id: str,
    cost: float,
    show_cnt: float = 0,
    click_cnt: float = 0,
    convert_cnt: float = 0,
    active_register: float = 0,
    roi_1day: float = 0,
    roi_7days: float = 0,
) -> None:
    conn.execute(
        """
        INSERT INTO material_daily_metrics (
          metric_date, advertiser_id, project_id, promotion_id,
          material_id, material_kind, stat_cost, show_cnt, click_cnt,
          convert_cnt, active_register, roi_1day, roi_7days, source, synced_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            metric_date,
            advertiser_id,
            project_id,
            promotion_id,
            material_id,
            "video",
            cost,
            show_cnt,
            click_cnt,
            convert_cnt,
            active_register,
            roi_1day,
            roi_7days,
            "unit_test",
            "2026-05-08T00:00:00+00:00",
        ),
    )


def test_material_quality_report_detects_missing_failed_and_row_mismatches(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)
    with sqlite3.connect(db_path) as conn:
        _record_state(conn, sync_date="2026-02-10", row_count=1)
        _record_state(conn, sync_date="2026-02-11", status="failed", row_count=0)
        _insert_metric(
            conn,
            metric_date="2026-02-10",
            advertiser_id="a1",
            project_id="p1",
            promotion_id="u1",
            material_id="m1",
            cost=100,
        )
        _insert_metric(
            conn,
            metric_date="2026-02-12",
            advertiser_id="a1",
            project_id="p1",
            promotion_id="u1",
            material_id="m2",
            cost=50,
        )

    report = build_material_quality_report(
        {
            "material_quality_rollup": {
                "product": "勇者突进",
                "platform": "WECHAT_GAME",
                "date_range": {"start": "2026-02-10", "end": "2026-02-13"},
            }
        },
        db_path=db_path,
    )

    assert report["ok"] is False
    assert report["summary"]["expected_date_count"] == 4
    assert report["summary"]["completed_date_count"] == 1
    assert report["summary"]["failed_date_count"] == 1
    assert report["summary"]["missing_date_count"] == 2
    assert report["sync_quality"]["failed_dates"] == ["2026-02-11"]
    assert report["sync_quality"]["missing_dates"] == ["2026-02-12", "2026-02-13"]
    assert report["metric_quality"]["state_metric_row_mismatches"] == []
    assert report["metric_quality"]["metric_dates_without_completed_state"] == ["2026-02-12"]


def test_material_quality_rollup_writes_window_summaries(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)
    with sqlite3.connect(db_path) as conn:
        for sync_date, row_count in [("2026-02-10", 1), ("2026-02-11", 1), ("2026-02-12", 2)]:
            _record_state(conn, sync_date=sync_date, row_count=row_count)
        _insert_metric(
            conn,
            metric_date="2026-02-10",
            advertiser_id="a1",
            project_id="p1",
            promotion_id="u1",
            material_id="m1",
            cost=100,
            show_cnt=1000,
            click_cnt=10,
            convert_cnt=2,
            active_register=5,
            roi_1day=0.1,
            roi_7days=0.2,
        )
        _insert_metric(
            conn,
            metric_date="2026-02-11",
            advertiser_id="a2",
            project_id="p2",
            promotion_id="u2",
            material_id="m1",
            cost=200,
            show_cnt=2000,
            click_cnt=20,
            convert_cnt=3,
            active_register=7,
            roi_1day=0.4,
            roi_7days=0.6,
        )
        _insert_metric(
            conn,
            metric_date="2026-02-12",
            advertiser_id="a1",
            project_id="p3",
            promotion_id="u3",
            material_id="m1",
            cost=300,
            show_cnt=3000,
            click_cnt=30,
            convert_cnt=4,
            active_register=8,
            roi_1day=0.7,
            roi_7days=0.9,
        )
        _insert_metric(
            conn,
            metric_date="2026-02-12",
            advertiser_id="a1",
            project_id="p3",
            promotion_id="u4",
            material_id="m2",
            cost=50,
            roi_1day=0.5,
            roi_7days=0.8,
        )

    result = run_material_quality_rollup_request(
        {
            "material_quality_rollup": {
                "product": "勇者突进",
                "platform": "WECHAT_GAME",
                "date_range": {"start": "2026-02-10", "end": "2026-02-12"},
                "windows": [1, 3, "all"],
            }
        },
        db_path=db_path,
        runs_dir=tmp_path / "runs",
    )

    assert result["ok"] is True
    assert result["summary"]["rollup_rows_written"] == 6
    assert Path(result["artifact_path"]).exists()
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT window_key, period_start, period_end, material_id, account_count,
                   project_count, promotion_count, stat_cost, show_cnt, click_cnt,
                   convert_cnt, active_register, roi_1day_cost_weighted,
                   roi_7days_cost_weighted
            FROM material_metric_rollups
            ORDER BY window_key, material_id
            """
        ).fetchall()

    assert rows == [
        ("all_history", "2026-02-10", "2026-02-12", "m1", 2, 3, 3, 600.0, 6000.0, 60.0, 9.0, 20.0, 0.5, 0.6833),
        ("all_history", "2026-02-10", "2026-02-12", "m2", 1, 1, 1, 50.0, 0.0, 0.0, 0.0, 0.0, 0.5, 0.8),
        ("last_1d", "2026-02-12", "2026-02-12", "m1", 1, 1, 1, 300.0, 3000.0, 30.0, 4.0, 8.0, 0.7, 0.9),
        ("last_1d", "2026-02-12", "2026-02-12", "m2", 1, 1, 1, 50.0, 0.0, 0.0, 0.0, 0.0, 0.5, 0.8),
        ("last_3d", "2026-02-10", "2026-02-12", "m1", 2, 3, 3, 600.0, 6000.0, 60.0, 9.0, 20.0, 0.5, 0.6833),
        ("last_3d", "2026-02-10", "2026-02-12", "m2", 1, 1, 1, 50.0, 0.0, 0.0, 0.0, 0.0, 0.5, 0.8),
    ]


def test_material_profile_sync_imports_profiles_and_canonical_keys(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    profile_path = tmp_path / "profiles.json"
    bootstrap_database(db_path)
    profile_path.write_text(
        json.dumps(
            {
                "materials": [
                    {
                        "material_id": "m1",
                        "video_id": "v1",
                        "name": "same video a",
                        "review_status": "APPROVED",
                        "duration": 12.5,
                    },
                    {
                        "material_id": "m2",
                        "video_id": "v1",
                        "name": "same video b",
                        "review_status": "APPROVED",
                    },
                    {
                        "material_id": "m3",
                        "name": "no video id",
                        "review_status": "APPROVED",
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = run_material_profile_sync_request(
        {"material_profile_sync": {"kind": "local_profile_file", "profile_file": str(profile_path)}},
        db_path=db_path,
        runs_dir=tmp_path / "runs",
    )

    assert result["ok"] is True
    assert result["summary"]["profiles_imported"] == 3
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT material_id, video_id, canonical_material_key, review_status
            FROM material_profiles
            ORDER BY material_id
            """
        ).fetchall()
    assert rows == [
        ("m1", "v1", "material:m1", "APPROVED"),
        ("m2", "v1", "material:m2", "APPROVED"),
        ("m3", "", "material:m3", "APPROVED"),
    ]


def test_material_profile_sync_openapi_preflight_plans_account_reads(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)
    with sqlite3.connect(db_path) as conn:
        _insert_metric(
            conn,
            metric_date="2026-02-10",
            advertiser_id="a1",
            project_id="p1",
            promotion_id="u1",
            material_id="m1",
            cost=100,
        )
        _insert_metric(
            conn,
            metric_date="2026-02-10",
            advertiser_id="a2",
            project_id="p2",
            promotion_id="u2",
            material_id="m2",
            cost=200,
        )

    preflight = build_material_profile_sync_preflight(
        {
            "material_profile_sync": {
                "kind": "openapi_video_materials",
                "enabled": False,
                "account_source": "material_daily_metrics",
                "date_range": {"start": "2026-02-10", "end": "2026-02-10"},
                "page_size": 100,
                "limits": {"max_accounts": 1},
            }
        },
        db_path=db_path,
    )

    assert preflight["ok"] is True
    assert preflight["external_api_calls"] == 0
    assert preflight["summary"]["source_account_count"] == 1
    assert preflight["summary"]["known_material_count"] == 2
    assert preflight["summary"]["planned_request_count"] == 1
    planned = preflight["plan"]["requests"][0]
    assert planned["endpoint_key"] == "video_material_get"
    assert planned["query_params"]["advertiser_id"] == "a2"


def test_material_profile_sync_openapi_imports_profiles_with_injected_transport(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)
    with sqlite3.connect(db_path) as conn:
        _insert_metric(
            conn,
            metric_date="2026-02-10",
            advertiser_id="a1",
            project_id="p1",
            promotion_id="u1",
            material_id="m1",
            cost=100,
        )

    calls: list[dict] = []

    def transport(request: dict) -> dict:
        calls.append(request)
        return {
            "code": 0,
            "data": {
                "page_info": {"page": 1, "page_size": 100, "total_number": 2, "total_page": 1},
                "list": [
                    {
                        "material_id": "m1",
                        "id": "v1",
                        "filename": "勇者素材1.mp4",
                        "file_type": "video",
                        "review_status": "APPROVED",
                    },
                    {
                        "material_id": "m2",
                        "vid": "v1",
                        "material_name": "勇者素材1-重复上传",
                        "media_review_status": "APPROVED",
                    },
                ],
            },
        }

    result = run_material_profile_sync_request(
        {
            "material_profile_sync": {
                "kind": "openapi_video_materials",
                "enabled": True,
                "account_source": "material_daily_metrics",
                "date_range": {"start": "2026-02-10", "end": "2026-02-10"},
                "page_size": 100,
            }
        },
        db_path=db_path,
        runs_dir=tmp_path / "runs",
        transport=transport,
    )

    assert len(calls) == 1
    assert result["ok"] is True
    assert result["external_api_calls"] == 1
    assert result["summary"]["profiles_imported"] == 2
    assert result["summary"]["canonical_material_count"] == 2
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT material_id, video_id, canonical_material_key, review_status
            FROM material_profiles
            ORDER BY material_id
            """
        ).fetchall()
    assert rows == [
        ("m1", "v1", "material:m1", "APPROVED"),
        ("m2", "v1", "material:m2", "APPROVED"),
    ]


def test_material_quality_rollup_keeps_same_video_material_ids_separate(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    profile_path = tmp_path / "profiles.json"
    bootstrap_database(db_path)
    profile_path.write_text(
        json.dumps(
            {
                "materials": [
                    {"material_id": "m1", "video_id": "v1", "review_status": "APPROVED"},
                    {"material_id": "m2", "video_id": "v1", "review_status": "APPROVED"},
                    {"material_id": "m3", "review_status": "APPROVED"},
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    run_material_profile_sync_request(
        {"material_profile_sync": {"kind": "local_profile_file", "profile_file": str(profile_path)}},
        db_path=db_path,
        runs_dir=tmp_path / "runs",
    )
    with sqlite3.connect(db_path) as conn:
        _record_state(conn, sync_date="2026-02-10", row_count=3)
        _insert_metric(
            conn,
            metric_date="2026-02-10",
            advertiser_id="a1",
            project_id="p1",
            promotion_id="u1",
            material_id="m1",
            cost=100,
            roi_1day=0.2,
            roi_7days=0.4,
        )
        _insert_metric(
            conn,
            metric_date="2026-02-10",
            advertiser_id="a2",
            project_id="p2",
            promotion_id="u2",
            material_id="m2",
            cost=300,
            roi_1day=0.6,
            roi_7days=0.8,
        )
        _insert_metric(
            conn,
            metric_date="2026-02-10",
            advertiser_id="a3",
            project_id="p3",
            promotion_id="u3",
            material_id="m3",
            cost=50,
            roi_1day=1.0,
            roi_7days=1.2,
        )

    result = run_material_quality_rollup_request(
        {
            "material_quality_rollup": {
                "product": "勇者突进",
                "platform": "WECHAT_GAME",
                "date_range": {"start": "2026-02-10", "end": "2026-02-10"},
                "windows": [1],
            }
        },
        db_path=db_path,
        runs_dir=tmp_path / "runs",
    )

    assert result["ok"] is True
    assert result["summary"]["rollup_rows_written"] == 3
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT canonical_material_key, material_id, account_count, project_count,
                   promotion_count, stat_cost, roi_1day_cost_weighted,
                   roi_7days_cost_weighted
            FROM material_metric_rollups
            ORDER BY canonical_material_key
            """
        ).fetchall()
    assert rows == [
        ("material:m1", "m1", 1, 1, 1, 100.0, 0.2, 0.4),
        ("material:m2", "m2", 1, 1, 1, 300.0, 0.6, 0.8),
        ("material:m3", "m3", 1, 1, 1, 50.0, 1.0, 1.2),
    ]


def test_material_quality_rollup_cli_writes_summary(tmp_path: Path, capsys):
    db_path = tmp_path / "roibang.sqlite3"
    request_path = tmp_path / "quality.json"
    runtime_path = tmp_path / "runtime.json"
    bootstrap_database(db_path)
    with sqlite3.connect(db_path) as conn:
        _record_state(conn, sync_date="2026-02-10", row_count=1)
        _insert_metric(
            conn,
            metric_date="2026-02-10",
            advertiser_id="a1",
            project_id="p1",
            promotion_id="u1",
            material_id="m1",
            cost=100,
        )
    request_path.write_text(
        json.dumps(
            {
                "material_quality_rollup": {
                    "product": "勇者突进",
                    "platform": "WECHAT_GAME",
                    "date_range": {"start": "2026-02-10", "end": "2026-02-10"},
                    "windows": [1],
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    runtime_path.write_text(
        json.dumps(
            {
                "environment": "test",
                "phase": "phase1",
                "database_path": str(db_path),
                "runs_dir": str(tmp_path / "runs"),
                "fixtures_dir": str(tmp_path / "fixtures"),
                "external_api_enabled": False,
                "execution_enabled": False,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    script_path = Path("scripts/run_material_quality_rollup.py")
    spec = importlib.util.spec_from_file_location("run_material_quality_rollup", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)

    exit_code = module.run_from_args(
        [
            "--config",
            str(runtime_path),
            "--request",
            str(request_path),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert '"workflow": "material_quality_rollup"' in captured.out
    assert '"rollup_rows_written": 1' in captured.out
