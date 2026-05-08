import sqlite3
from pathlib import Path

from roibang_v2.db.bootstrap import bootstrap_database
from roibang_v2.fetch.openapi_http import HttpResponse
from roibang_v2.workflows.material_profile_sync import (
    build_material_profile_sync_preflight,
    run_material_profile_sync_request,
)


def _session_file(path: Path) -> Path:
    path.write_text(
        '{"cookie":"sessionid=secret-session","csrf_token":"secret-csrf-token"}',
        encoding="utf-8",
    )
    return path


def test_workbench_material_center_preflight_plans_source_account_pages(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)

    preflight = build_material_profile_sync_preflight(
        {
            "material_profile_sync": {
                "kind": "workbench_material_center",
                "enabled": False,
                "source_accounts": [{"source_advertiser_id": "source-1"}, {"advertiser_id": "source-2"}],
                "statistic_start_time": "2026-05-01 00:00:00",
                "statistic_end_time": "2026-05-08 23:59:59",
                "limit": 100,
                "limits": {"max_accounts": 1, "max_pages": 3},
            }
        },
        db_path=db_path,
    )

    assert preflight["summary"]["kind"] == "workbench_material_center"
    assert preflight["summary"]["source_account_count"] == 1
    assert preflight["summary"]["planned_request_count"] == 3
    assert preflight["plan"]["requests"][0]["advertiser_id"] == "source-1"
    assert preflight["plan"]["requests"][0]["page"] == 1


def test_workbench_material_center_sync_imports_video_profiles(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)
    calls = []

    def opener(url, body, headers, timeout_seconds):
        calls.append({"url": url, "body": body, "headers": headers, "timeout_seconds": timeout_seconds})
        return HttpResponse(
            200,
            {
                "code": 0,
                "data": {
                    "materials": [
                        {
                            "material_id": "7634377721926238234",
                            "title": "推送视频_XX-0428-SP-AI+武将闯关-ZY",
                            "vid": "v02033g10000d7pc492ljht7a62rfm80",
                            "material_type": 3,
                            "audit_result": {"status": 3},
                            "created_at": "2026-05-04T15:15:10+08:00",
                            "head_image_uri": "https://example.com/cover.image",
                            "video_duration": 32.903,
                            "signature": "same-file-signature",
                        }
                    ],
                    "page_info": {"has_more": False, "page": 1, "limit": 100, "total_count": "1"},
                },
            },
        )

    result = run_material_profile_sync_request(
        {
            "material_profile_sync": {
                "kind": "workbench_material_center",
                "enabled": True,
                "product": "勇者突进",
                "organization_id": "1851650746645060",
                "session_file": str(_session_file(tmp_path / "session.json")),
                "source_accounts": [{"source_advertiser_id": "1856647523922953"}],
                "statistic_start_time": "2026-05-01 00:00:00",
                "statistic_end_time": "2026-05-08 23:59:59",
                "limit": 100,
                "limits": {"max_accounts": 1, "max_pages": 1},
                "response_audit_dir": str(tmp_path / "audit"),
            }
        },
        db_path=db_path,
        runs_dir=tmp_path / "runs",
        material_center_opener=opener,
    )

    assert result["summary"]["transport_calls"] == 1
    assert result["summary"]["profiles_imported"] == 1
    assert result["summary"]["accounts"][0]["total_count"] == 1
    assert result["summary"]["accounts"][0]["rows_importable"] == 1
    assert result["summary"]["accounts"][0]["stopped_by_created_at_range"] is False
    assert calls[0]["body"]["statistic_start_time"] == "2026-05-01 00:00:00"
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT material_id, video_id, name, review_status, duration, source_advertiser_id, material_kind, payload_json
            FROM material_profiles
            """
        ).fetchone()
        account_material = conn.execute(
            """
            SELECT advertiser_id, material_id, video_id, material_type, review_status
            FROM account_materials
            """
        ).fetchone()
        source_material = conn.execute(
            """
            SELECT product, source_advertiser_id, material_id, video_id, name,
                   material_type, review_status, signature, duration, create_time,
                   is_active
            FROM product_source_materials
            """
        ).fetchone()
    assert row[0] == "7634377721926238234"
    assert row[1] == "v02033g10000d7pc492ljht7a62rfm80"
    assert row[2] == "推送视频_XX-0428-SP-AI+武将闯关-ZY"
    assert row[3] == "3"
    assert row[4] == 32.903
    assert row[5] == "1856647523922953"
    assert row[6] == "video"
    assert "same-file-signature" in row[7]
    assert account_material == (
        "1856647523922953",
        "7634377721926238234",
        "v02033g10000d7pc492ljht7a62rfm80",
        "video",
        "3",
    )
    assert source_material == (
        "勇者突进",
        "1856647523922953",
        "7634377721926238234",
        "v02033g10000d7pc492ljht7a62rfm80",
        "推送视频_XX-0428-SP-AI+武将闯关-ZY",
        "video",
        "3",
        "same-file-signature",
        32.903,
        "2026-05-04T15:15:10+08:00",
        1,
    )
