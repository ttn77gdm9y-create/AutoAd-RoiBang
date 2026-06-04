import sqlite3
from pathlib import Path

from roibang_v2.db.bootstrap import bootstrap_database
from roibang_v2.workflows.gravity_material_qualification import run_gravity_material_qualification_request


def test_gravity_material_qualification_summarizes_local_materials_without_external_actions(tmp_path: Path):
    db_path = tmp_path / "data" / "roibang_v2.sqlite3"
    bootstrap_database(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            """
            INSERT INTO product_source_materials (
              product, source_advertiser_id, organization_id, material_id,
              video_id, name, material_type, review_status, signature,
              duration, file_size, create_time, tag_ids_json, is_active,
              first_seen_at, last_seen_at, cost_lookback, score,
              payload_json, source, synced_at
            ) VALUES (
              ?, 'gravity_engine_182', '182', ?,
              ?, ?, 'video', ?, ?,
              15, 2048, '2026-06-01T10:00:00+08:00', '[]', ?,
              'now', 'now', ?, 0,
              ?, 'gravity_engine', 'now'
            )
            """,
            [
                (
                    "点点英雄",
                    "gravity-ok",
                    "",
                    "可用素材",
                    "可用",
                    "md5-ok",
                    1,
                    12.5,
                    '{"album_name":"点点英雄专辑","folder_name":"6月新素材","status":1}',
                ),
                (
                    "点点英雄",
                    "gravity-missing-md5",
                    "",
                    "缺MD5素材",
                    "可用",
                    "",
                    1,
                    0,
                    '{"album_name":"点点英雄专辑","folder_name":"6月新素材","status":1}',
                ),
                (
                    "点点英雄",
                    "gravity-disabled",
                    "",
                    "禁用素材",
                    "禁用",
                    "md5-disabled",
                    1,
                    0,
                    '{"album_name":"点点英雄专辑","folder_name":"6月新素材","status":2}',
                ),
                (
                    "点点英雄",
                    "gravity-uploaded",
                    "v123456789ABC",
                    "已上传素材",
                    "可用",
                    "md5-uploaded",
                    1,
                    0,
                    '{"album_name":"点点英雄专辑","folder_name":"6月新素材","status":1}',
                ),
                (
                    "其他产品",
                    "gravity-other",
                    "",
                    "其他素材",
                    "可用",
                    "md5-other",
                    1,
                    0,
                    '{"album_name":"其他专辑","folder_name":"","status":1}',
                ),
            ],
        )

    result = run_gravity_material_qualification_request(
        {"product": "点点英雄"},
        db_path=db_path,
        runs_dir=tmp_path / "runs",
    )

    assert result["ok"] is True
    assert result["workflow"] == "gravity_material_qualification"
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 0
    assert result["summary"]["material_count"] == 4
    assert result["summary"]["eligible_count"] == 2
    assert result["summary"]["ineligible_count"] == 2
    assert result["summary"]["missing_md5_count"] == 1
    assert result["summary"]["uploaded_count"] == 1
    assert result["summary"]["not_uploaded_count"] == 3
    assert result["summary"]["has_performance_count"] == 1
    assert result["中文摘要"] == (
        "点点英雄引力素材资格汇总完成：素材 4 个，可用于后续 2 个，不可用 2 个，"
        "缺 MD5 1 个，已上传 1 个，未上传 3 个；未上传素材、未创建广告。"
    )
    assert result["table"]["rows"][0]["产品"] == "点点英雄"
    assert result["table"]["rows"][0]["可用于后续"] == 2
    assert result["table"]["rows"][0]["不可用"] == 2
    raw_text = str(result["raw"])
    assert "upload_material" not in raw_text
    assert result["artifact_path"].endswith(".json")


def test_gravity_material_qualification_blocks_when_no_gravity_materials(tmp_path: Path):
    db_path = tmp_path / "data" / "roibang_v2.sqlite3"
    bootstrap_database(db_path)

    result = run_gravity_material_qualification_request(
        {"product": "点点英雄"},
        db_path=db_path,
        runs_dir=tmp_path / "runs",
    )

    assert result["ok"] is False
    assert result["status"] == "blocked"
    assert result["external_api_calls"] == 0
    assert "还没有本地引力素材" in result["blocking_reasons"][0]
