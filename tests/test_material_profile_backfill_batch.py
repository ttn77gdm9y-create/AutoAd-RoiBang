import sqlite3
from pathlib import Path

from roibang_v2.db.bootstrap import bootstrap_database
from roibang_v2.workflows.material_profile_sync import build_material_profile_sync_preflight
from roibang_v2.workflows.material_profile_backfill_batch import run_material_profile_backfill_batch_request


def _insert_metric(
    conn: sqlite3.Connection,
    *,
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
            "2026-02-10",
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


def test_profile_backfill_batch_reselects_missing_accounts_and_runs_duplicate_analysis(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)
    with sqlite3.connect(db_path) as conn:
        _insert_metric(conn, advertiser_id="a1", material_id="m1", cost=100)
        _insert_metric(conn, advertiser_id="a2", material_id="m2", cost=300)

    calls: list[str] = []

    def transport(request: dict) -> dict:
        advertiser_id = str(request["query_params"]["advertiser_id"])
        calls.append(advertiser_id)
        material_id = "m2" if advertiser_id == "a2" else "m1"
        return {
            "code": 0,
            "data": {
                "page_info": {"page": 1, "page_size": 100, "total_number": 1, "total_page": 1},
                "list": [
                    {
                        "material_id": material_id,
                        "id": f"video-{material_id}",
                        "filename": f"{material_id}.mp4",
                        "signature": "same-sig",
                        "duration": 12.0,
                    }
                ],
            },
        }

    result = run_material_profile_backfill_batch_request(
        {
            "material_profile_backfill_batch": {
                "max_batches": 3,
                "material_profile_sync": {
                    "kind": "openapi_video_materials",
                    "enabled": True,
                    "account_source": "material_daily_metrics",
                    "date_range": {"start": "2026-02-10", "end": "2026-02-10"},
                    "page_size": 100,
                    "limits": {"max_accounts": 1, "max_pages": 1},
                    "skip_profiled_materials": True,
                },
                "material_duplicate_analysis": {"rules": ["signature"], "min_group_size": 2},
            }
        },
        db_path=db_path,
        runs_dir=tmp_path / "runs",
        transport=transport,
    )

    assert result["ok"] is True
    assert calls == ["a2", "a1"]
    assert result["summary"]["batches_run"] == 2
    assert result["summary"]["profiles_imported"] == 2
    assert result["summary"]["missing_material_count_after"] == 0
    assert result["duplicate_analysis"]["summary"]["duplicate_group_count"] == 1
    with sqlite3.connect(db_path) as conn:
        profiles = conn.execute("SELECT COUNT(*) FROM material_profiles").fetchone()[0]
        duplicates = conn.execute("SELECT COUNT(*) FROM material_duplicate_candidates").fetchone()[0]
    assert profiles == 2
    assert duplicates == 2


def test_profile_sync_preflight_can_plan_missing_material_id_lookup_chunks(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)
    with sqlite3.connect(db_path) as conn:
        _insert_metric(conn, advertiser_id="a1", material_id="1001", cost=100)
        _insert_metric(conn, advertiser_id="a1", material_id="1002", cost=50)
        _insert_metric(conn, advertiser_id="a2", material_id="1003", cost=300)
        conn.execute(
            """
            INSERT INTO material_profiles (
              material_id, canonical_material_key, material_kind, payload_json, source, synced_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("1001", "material:1001", "video", "{}", "unit_test", "2026-05-08T00:00:00+00:00"),
        )

    preflight = build_material_profile_sync_preflight(
        {
            "material_profile_sync": {
                "kind": "openapi_video_materials",
                "enabled": False,
                "account_source": "material_daily_metrics",
                "lookup_mode": "missing_material_ids",
                "date_range": {"start": "2026-02-10", "end": "2026-02-10"},
                "limits": {"max_accounts": 2},
                "material_id_chunk_size": 1,
            }
        },
        db_path=db_path,
    )

    requests = preflight["plan"]["requests"]
    assert preflight["summary"]["source_account_count"] == 2
    assert preflight["summary"]["planned_request_count"] == 2
    assert requests[0]["query_params"]["advertiser_id"] == "a2"
    assert requests[0]["query_params"]["filtering"] == "{\"material_ids\":[1003]}"
    assert requests[1]["query_params"]["advertiser_id"] == "a1"
    assert requests[1]["query_params"]["filtering"] == "{\"material_ids\":[1002]}"


def test_profile_sync_preflight_can_plan_organization_video_lookup_first(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)
    with sqlite3.connect(db_path) as conn:
        _insert_metric(conn, advertiser_id="a1", material_id="1001", cost=100)

    preflight = build_material_profile_sync_preflight(
        {
            "material_profile_sync": {
                "kind": "openapi_video_materials",
                "enabled": False,
                "account_source": "material_daily_metrics",
                "lookup_mode": "missing_material_ids",
                "endpoint_sequence": ["ebp_video_material_get", "video_material_get", "material_attributes_list"],
                "date_range": {"start": "2026-02-10", "end": "2026-02-10"},
                "limits": {"max_accounts": 1},
                "material_id_chunk_size": 100,
            }
        },
        db_path=db_path,
    )

    requests = preflight["plan"]["requests"]
    assert [request["endpoint_key"] for request in requests] == [
        "ebp_video_material_get",
        "video_material_get",
        "material_attributes_list",
    ]
    assert requests[0]["query_params"]["filtering"] == "{\"material_ids\":[1001]}"
    assert requests[1]["query_params"]["filtering"] == "{\"material_ids\":[1001]}"
    assert requests[2]["query_params"]["account_id"] == "a1"
    assert requests[2]["query_params"]["account_type"] == "AD"
    assert requests[2]["query_params"]["filtering"] == "{\"material_ids\":[1001]}"


def test_profile_sync_preflight_can_lookup_missing_material_ids_from_source_accounts(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)
    with sqlite3.connect(db_path) as conn:
        _insert_metric(conn, advertiser_id="target-a1", material_id="1001", cost=100)
        _insert_metric(conn, advertiser_id="target-a2", material_id="1002", cost=300)

    preflight = build_material_profile_sync_preflight(
        {
            "material_profile_sync": {
                "kind": "openapi_video_materials",
                "enabled": False,
                "account_source": "material_daily_metrics",
                "lookup_mode": "missing_material_ids",
                "lookup_accounts_from": "source_accounts",
                "source_accounts": [{"source_advertiser_id": "source-1"}],
                "endpoint_sequence": ["video_material_get", "material_attributes_list"],
                "date_range": {"start": "2026-02-10", "end": "2026-02-10"},
                "limits": {"max_accounts": 10},
                "material_id_chunk_size": 100,
            }
        },
        db_path=db_path,
    )

    requests = preflight["plan"]["requests"]
    assert [request["endpoint_key"] for request in requests] == [
        "video_material_get",
        "material_attributes_list",
        "material_attributes_list",
    ]
    assert requests[0]["query_params"]["advertiser_id"] == "source-1"
    assert requests[0]["account"]["lookup_account_role"] == "source_account"
    assert requests[0]["query_params"]["filtering"] == "{\"material_ids\":[1002,1001]}"
    assert {request["query_params"]["account_id"] for request in requests[1:]} == {"target-a1", "target-a2"}


def test_profile_sync_tiered_lookup_imports_attributes_without_marking_profiles_complete(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)
    with sqlite3.connect(db_path) as conn:
        _insert_metric(conn, advertiser_id="a1", material_id="1001", cost=300)
        _insert_metric(conn, advertiser_id="a1", material_id="1002", cost=200)
        _insert_metric(conn, advertiser_id="a1", material_id="1003", cost=100)

    calls: list[tuple[str, str]] = []

    def transport(request: dict) -> dict:
        endpoint_key = str(request["endpoint_key"])
        query_params = request["query_params"]
        calls.append((endpoint_key, query_params.get("filter_param") or query_params.get("filtering")))
        if endpoint_key == "ebp_video_material_get":
            return {
                "code": 0,
                "data": {
                    "page_info": {"page": 1, "page_size": 100, "total_number": 1, "total_page": 1},
                    "list": [
                        {
                            "material_id": 1001,
                            "video_id": "org-video-1001",
                            "file_name": "1001.mp4",
                            "signature": "sig-1001",
                            "duration": 11,
                        },
                        {
                            "material_id": 9999,
                            "video_id": "org-video-9999",
                            "file_name": "9999.mp4",
                            "signature": "sig-9999",
                            "duration": 99,
                        }
                    ],
                },
            }
        if endpoint_key == "video_material_get":
            return {
                "code": 0,
                "data": {
                    "page_info": {"page": 1, "page_size": 100, "total_number": 1, "total_page": 1},
                    "list": [
                        {
                            "material_id": 1002,
                            "id": "account-video-1002",
                            "filename": "1002.mp4",
                            "signature": "sig-1002",
                            "duration": 12,
                        }
                    ],
                },
            }
        return {
            "code": 0,
            "data": {
                "page": {"page": 1, "page_size": 100, "total_number": 3, "total_page": 1},
                "materials": [
                    {"material_id": 1001},
                    {"material_id": 1002},
                    {
                        "material_id": 1003,
                        "is_ad_high_quality_material": True,
                        "is_first_publish_material": True,
                    }
                ],
            },
        }

    result = run_material_profile_backfill_batch_request(
        {
            "material_profile_backfill_batch": {
                "max_batches": 1,
                "material_profile_sync": {
                    "kind": "openapi_video_materials",
                    "enabled": True,
                    "account_source": "material_daily_metrics",
                    "lookup_mode": "missing_material_ids",
                    "endpoint_sequence": ["ebp_video_material_get", "video_material_get", "material_attributes_list"],
                    "date_range": {"start": "2026-02-10", "end": "2026-02-10"},
                    "material_id_chunk_size": 100,
                    "limits": {"max_accounts": 1, "max_pages": 1},
                },
            }
        },
        db_path=db_path,
        runs_dir=tmp_path / "runs",
        transport=transport,
    )

    assert result["summary"]["profiles_imported"] == 2
    assert result["summary"]["attributes_imported"] == 3
    assert result["summary"]["missing_material_count_after"] == 1
    assert result["batches"][0]["stages"][0]["rows_skipped_unrequested"] == 1
    assert calls == [
        ("ebp_video_material_get", "{\"material_ids\":[1001,1002,1003]}"),
        ("video_material_get", "{\"material_ids\":[1002,1003]}"),
        ("material_attributes_list", "{\"material_ids\":[1001,1002,1003]}"),
    ]
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT material_id, video_id, name
            FROM material_profiles
            ORDER BY material_id
            """
        ).fetchall()
        attributes = conn.execute(
            """
            SELECT material_id, is_ad_high_quality_material, is_first_publish_material
            FROM material_attribute_snapshots
            ORDER BY material_id
            """
        ).fetchall()
    assert rows == [
        ("1001", "org-video-1001", "1001.mp4"),
        ("1002", "account-video-1002", "1002.mp4"),
    ]
    assert attributes == [
        ("1001", 0, 0),
        ("1002", 0, 0),
        ("1003", 1, 1),
    ]


def test_profile_backfill_batch_stops_when_no_progress(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)
    with sqlite3.connect(db_path) as conn:
        _insert_metric(conn, advertiser_id="a1", material_id="m1", cost=100)

    def transport(_request: dict) -> dict:
        return {
            "code": 0,
            "data": {"page_info": {"page": 1, "page_size": 100, "total_number": 0, "total_page": 1}, "list": []},
        }

    result = run_material_profile_backfill_batch_request(
        {
            "material_profile_backfill_batch": {
                "max_batches": 5,
                "stop_on_no_progress": True,
                "material_profile_sync": {
                    "kind": "openapi_video_materials",
                    "enabled": True,
                    "account_source": "material_daily_metrics",
                    "date_range": {"start": "2026-02-10", "end": "2026-02-10"},
                    "limits": {"max_accounts": 1, "max_pages": 1},
                },
            }
        },
        db_path=db_path,
        runs_dir=tmp_path / "runs",
        transport=transport,
    )

    assert result["ok"] is True
    assert result["summary"]["batches_run"] == 1
    assert result["summary"]["missing_material_count_after"] == 1
    assert result["summary"]["stop_reason"] == "no_import_progress"
