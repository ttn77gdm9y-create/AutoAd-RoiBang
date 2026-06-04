import sqlite3
from pathlib import Path
import json

from fastapi.testclient import TestClient

from backend.app.main import create_app
from roibang_v2.db.bootstrap import bootstrap_database


def _client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(project_root=tmp_path))


def test_gravity_material_bindings_can_be_saved_listed_and_deleted(tmp_path: Path):
    client = _client(tmp_path)

    save_response = client.post(
        "/api/gravity-materials/bindings",
        json={
            "product": "点点英雄",
            "album_id": "album-1",
            "album_name": "点点英雄专辑",
            "folder_id": "folder-1",
            "folder_name": "6月新素材",
        },
    )

    assert save_response.status_code == 200
    save_payload = save_response.json()
    assert save_payload["summary"]["title"] == "引力素材绑定已保存"
    assert save_payload["summary"]["execution_enabled"] is False
    assert save_payload["table"]["rows"][0]["产品"] == "点点英雄"
    assert save_payload["table"]["rows"][0]["专辑"] == "点点英雄专辑"
    assert save_payload["table"]["rows"][0]["文件夹"] == "6月新素材"

    list_response = client.get("/api/gravity-materials/bindings", params={"product": "点点英雄"})

    assert list_response.status_code == 200
    list_payload = list_response.json()
    assert list_payload["summary"]["title"] == "引力素材绑定"
    assert list_payload["summary"]["items"] == [{"label": "绑定数", "value": 1}]
    binding = list_payload["raw"]["bindings"][0]
    assert binding["id"] > 0
    assert binding["product"] == "点点英雄"
    assert binding["album_id"] == "album-1"
    assert binding["folder_id"] == "folder-1"

    delete_response = client.delete(f"/api/gravity-materials/bindings/{binding['id']}")

    assert delete_response.status_code == 200
    assert delete_response.json()["summary"]["title"] == "引力素材绑定已删除"
    after_delete = client.get("/api/gravity-materials/bindings", params={"product": "点点英雄"}).json()
    assert after_delete["summary"]["items"] == [{"label": "绑定数", "value": 0}]


def test_gravity_materials_list_reads_local_gravity_source_materials(tmp_path: Path):
    db_path = tmp_path / "data" / "roibang_v2.sqlite3"
    bootstrap_database(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO materials (
              material_id, name, material_type, video_id, review_status,
              cost_lookback, score, payload_json, source, synced_at
            ) VALUES ('gravity-m-1', '素材A', 'video', '', '可用', 12.5, 0, '{}', 'gravity_engine', 'now')
            """
        )
        conn.execute(
            """
            INSERT INTO product_source_materials (
              product, source_advertiser_id, organization_id, material_id,
              video_id, name, material_type, review_status, signature,
              duration, file_size, create_time, tag_ids_json, is_active,
              first_seen_at, last_seen_at, cost_lookback, score,
              payload_json, source, synced_at
            ) VALUES (
              '点点英雄', 'gravity_engine_182', '182', 'gravity-m-1',
              '', '素材A', 'video', '可用', 'md5-a',
              15, 2048, '2026-06-01T10:00:00+08:00', '[]', 1,
              'now', 'now', 12.5, 0,
              '{"album_name":"点点英雄专辑","folder_name":"6月新素材","status":1}', 'gravity_engine', 'now'
            )
            """
        )
        conn.execute(
            """
            INSERT INTO product_source_material_metric_rollups (
              product, source_advertiser_id, organization_id, window_key, window_days,
              period_start, period_end, material_id, material_type, source_video_id,
              name, review_status, signature, duration, file_size, create_time,
              tag_ids_json, stat_cost, show_cnt, click_cnt, convert_cnt, source, synced_at
            ) VALUES (
              '点点英雄', 'gravity_engine_182', '182', 'last_30d', 30,
              '2026-05-02', '2026-06-01', 'gravity-m-1', 'video', '',
              '素材A', '可用', 'md5-a', 15, 2048, '2026-06-01T10:00:00+08:00',
              '[]', 12.5, 100, 5, 1, 'gravity_engine', 'now'
            )
            """
        )

    response = _client(tmp_path).get("/api/gravity-materials/materials", params={"product": "点点英雄"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "引力素材库"
    assert {"label": "素材数", "value": 1} in payload["summary"]["items"]
    row = payload["table"]["rows"][0]
    assert row["产品"] == "点点英雄"
    assert row["引力素材 ID"] == "gravity-m-1"
    assert row["MD5"] == "md5-a"
    assert row["状态"] == "可用"
    assert row["资格状态"] == "可用于后续"
    assert row["不可用原因"] == ""
    assert row["媒体素材 ID"] == ""
    assert row["上传状态"] == "未上传"
    assert row["消耗"] == 12.5
    assert row["转化"] == 1
    assert payload["raw"]["materials"][0]["source_advertiser_id"] == "gravity_engine_182"


def test_gravity_materials_list_summarizes_and_filters_qualification(tmp_path: Path):
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
              '点点英雄', 'gravity_engine_182', '182', ?,
              ?, ?, 'video', ?, ?,
              15, 2048, '2026-06-01T10:00:00+08:00', '[]', ?,
              'now', 'now', ?, 0,
              ?, 'gravity_engine', 'now'
            )
            """,
            [
                (
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
                    "gravity-uploaded",
                    "v123456789ABC",
                    "已上传素材",
                    "可用",
                    "md5-uploaded",
                    1,
                    0,
                    '{"album_name":"点点英雄专辑","folder_name":"6月新素材","status":1}',
                ),
            ],
        )

    response = _client(tmp_path).get("/api/gravity-materials/materials", params={"product": "点点英雄"})

    assert response.status_code == 200
    payload = response.json()
    items = {item["label"]: item["value"] for item in payload["summary"]["items"]}
    assert items["素材数"] == 4
    assert items["可用于后续"] == 2
    assert items["不可用"] == 2
    assert items["缺 MD5"] == 1
    assert items["已上传"] == 1
    assert items["未上传"] == 3
    assert items["有表现数据"] == 1
    by_id = {row["引力素材 ID"]: row for row in payload["table"]["rows"]}
    assert by_id["gravity-missing-md5"]["资格状态"] == "不可用"
    assert by_id["gravity-missing-md5"]["不可用原因"] == "缺少 MD5"
    assert by_id["gravity-disabled"]["不可用原因"] == "引力状态为禁用"
    assert by_id["gravity-uploaded"]["上传状态"] == "已上传"
    assert by_id["gravity-uploaded"]["媒体素材 ID"] == "v123456789ABC"

    filtered = _client(tmp_path).get(
        "/api/gravity-materials/materials",
        params={"product": "点点英雄", "status": "missing_md5"},
    )

    assert filtered.status_code == 200
    filtered_payload = filtered.json()
    filtered_items = {item["label"]: item["value"] for item in filtered_payload["summary"]["items"]}
    filtered_rows = filtered_payload["table"]["rows"]
    assert filtered_items["素材数"] == 4
    assert filtered_items["缺 MD5"] == 1
    assert [row["引力素材 ID"] for row in filtered_rows] == ["gravity-missing-md5"]


def test_gravity_album_tree_reads_latest_probe_artifact_for_binding_options(tmp_path: Path):
    runs_dir = tmp_path / "data" / "runs" / "gravity_api_probe"
    runs_dir.mkdir(parents=True)
    (runs_dir / "20260604T010203Z.json").write_text(
        json.dumps(
            {
                "raw": {
                    "endpoint_results": {
                        "album_tree": {
                            "code": 0,
                            "data": [
                                {
                                    "id": "album-1",
                                    "name": "点点英雄专辑",
                                    "children": [{"id": "folder-1", "name": "6月新素材"}],
                                }
                            ],
                        }
                    }
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    response = _client(tmp_path).get("/api/gravity-materials/albums")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "引力专辑树"
    assert payload["summary"]["items"] == [{"label": "节点数", "value": 2}]
    assert payload["raw"]["nodes"] == [
        {
            "专辑/文件夹 ID": "album-1",
            "名称": "点点英雄专辑",
            "层级": 1,
            "album_id": "album-1",
            "album_name": "点点英雄专辑",
            "folder_id": "",
            "folder_name": "",
        },
        {
            "专辑/文件夹 ID": "folder-1",
            "名称": "6月新素材",
            "层级": 2,
            "album_id": "album-1",
            "album_name": "点点英雄专辑",
            "folder_id": "folder-1",
            "folder_name": "6月新素材",
        },
    ]
