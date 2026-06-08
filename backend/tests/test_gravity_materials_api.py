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
            "album_name": "黑旗-奇门（塔防）",
            "folder_id": "folder-1",
            "folder_name": "6月新素材",
        },
    )

    assert save_response.status_code == 200
    save_payload = save_response.json()
    assert save_payload["summary"]["title"] == "引力素材绑定已保存"
    assert save_payload["summary"]["execution_enabled"] is False
    assert save_payload["table"]["rows"][0]["产品"] == "点点英雄"
    assert save_payload["table"]["rows"][0]["专辑"] == "黑旗-奇门（塔防）"
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


def test_gravity_material_binding_blocks_albums_outside_target_scope(tmp_path: Path):
    client = _client(tmp_path)

    response = client.post(
        "/api/gravity-materials/bindings",
        json={
            "product": "点点英雄",
            "album_id": "album-other",
            "album_name": "其他游戏素材",
            "folder_id": "",
            "folder_name": "",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["status"] == "blocked"
    assert "不在允许同步的引力专辑范围内" in payload["summary"]["blocking_reasons"][0]


def test_gravity_material_sync_readiness_blocks_missing_token_without_external_calls(tmp_path: Path):
    client = _client(tmp_path)
    client.post(
        "/api/gravity-materials/bindings",
        json={
            "product": "点点英雄",
            "album_id": "album-1",
            "album_name": "黑旗-奇门（塔防）",
            "folder_id": "",
            "folder_name": "",
        },
    )

    response = client.get(
        "/api/gravity-materials/sync-readiness",
        params={"product": "点点英雄", "auth_file": "data/missing-gravity-token.json"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "更新引力素材准备检查"
    assert payload["summary"]["status"] == "blocked"
    assert payload["summary"]["execution_enabled"] is False
    assert "未找到引力 Token 文件" in payload["summary"]["blocking_reasons"][0]
    assert payload["raw"]["external_api_calls"] == 0
    assert payload["raw"]["will_download_material_files"] is False
    assert payload["raw"]["will_touch_account_material_sync"] is False
    assert payload["raw"]["next_action"]["title"] == "检查引力 Token"
    assert "先确认引力 Token 文件" in payload["raw"]["next_action"]["description"]
    assert {"label": "下一步", "value": "检查引力 Token"} in payload["summary"]["items"]


def test_gravity_material_sync_readiness_tells_user_to_bind_source_first(tmp_path: Path):
    response = _client(tmp_path).get(
        "/api/gravity-materials/sync-readiness",
        params={"product": "点点英雄", "auth_file": "data/missing-gravity-token.json"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["status"] == "blocked"
    assert payload["raw"]["next_action"] == {
        "title": "绑定素材来源",
        "description": "先在引力素材库页面保存产品和目标专辑绑定，再更新引力素材。",
    }
    assert {"label": "下一步", "value": "绑定素材来源"} in payload["summary"]["items"]


def test_gravity_material_sync_readiness_explains_local_metadata_sync_scope(tmp_path: Path):
    token_path = tmp_path / "data" / "gravity_token.json"
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(
        json.dumps(
            {
                "authorization": "token",
                "gravity_cid": "182",
                "gravity_email": "hongen@example.com",
                "gravity_id": "406",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    client = _client(tmp_path)
    client.post(
        "/api/gravity-materials/bindings",
        json={
            "product": "点点英雄",
            "album_id": "album-1",
            "album_name": "黑旗-奇门（塔防）",
            "folder_id": "folder-1",
            "folder_name": "基础素材",
        },
    )

    response = client.get(
        "/api/gravity-materials/sync-readiness",
        params={"product": "点点英雄", "auth_file": "data/gravity_token.json"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["status"] == "ready"
    items = {item["label"]: item["value"] for item in payload["summary"]["items"]}
    assert items["绑定数"] == 1
    assert items["真实媒体动作"] == "否"
    assert items["下载素材文件"] == "否"
    assert items["影响每日账户素材同步"] == "否"
    assert payload["table"]["rows"][0]["同步内容"] == "素材名、归属专辑/文件夹、引力素材 ID、MD5、状态和表现数据"
    assert payload["raw"]["source"] == "gravity_engine"
    assert payload["raw"]["next_action"] == {
        "title": "更新引力素材",
        "description": "准备检查已通过，可以生成更新预览；确认后只读取引力素材资料并写入本地。",
    }


def test_gravity_materials_list_reads_local_gravity_source_materials(tmp_path: Path):
    db_path = tmp_path / "data" / "roibang_v2.sqlite3"
    bootstrap_database(db_path)
    account_store = tmp_path / "configs" / "accounts" / "product-accounts.local.json"
    account_store.parent.mkdir(parents=True)
    account_store.write_text(
        json.dumps(
            {
                "accounts": [
                    {
                        "product_key": "diandian-hero",
                        "product_name": "点点英雄",
                        "advertiser_id": "acc-1",
                        "advertiser_name": "点点英雄-账户A",
                        "channel": "微信",
                        "owner": "郭靖",
                        "account_remark": "",
                        "status": "active",
                        "notes": "",
                    },
                    {
                        "product_key": "diandian-hero",
                        "product_name": "点点英雄",
                        "advertiser_id": "acc-2",
                        "advertiser_name": "点点英雄-账户B",
                        "channel": "微信",
                        "owner": "郭靖",
                        "account_remark": "",
                        "status": "active",
                        "notes": "",
                    },
                    {
                        "product_key": "diandian-hero",
                        "product_name": "点点英雄",
                        "advertiser_id": "acc-other-owner",
                        "advertiser_name": "点点英雄-非郭靖账户",
                        "channel": "微信",
                        "owner": "任伊",
                        "account_remark": "",
                        "status": "active",
                        "notes": "",
                    },
                    {
                        "product_key": "diandian-hero",
                        "product_name": "点点英雄",
                        "advertiser_id": "acc-disabled",
                        "advertiser_name": "点点英雄-停用账户",
                        "channel": "微信",
                        "owner": "郭靖",
                        "account_remark": "",
                        "status": "disabled",
                        "notes": "",
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
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
        conn.execute(
            """
            INSERT INTO product_source_material_metric_rollups (
              product, source_advertiser_id, organization_id, window_key, window_days,
              period_start, period_end, material_id, material_type, source_video_id,
              name, review_status, signature, duration, file_size, create_time,
              tag_ids_json, stat_cost, show_cnt, click_cnt, convert_cnt, source, synced_at
            ) VALUES (
              '点点英雄', 'gravity_engine_182', '182', 'last_7d', 7,
              '2026-05-26', '2026-06-01', 'gravity-m-1', 'video', '',
              '素材A', '可用', 'md5-a', 15, 2048, '2026-06-01T10:00:00+08:00',
              '[]', 3.5, 70, 4, 1, 'gravity_engine', 'now'
            )
            """
        )
        conn.execute(
            """
            INSERT INTO gravity_upload_tasks (
              product, gravity_material_id, signature, target_advertiser_id,
              target_account_name, gravity_task_id, status, video_id
            ) VALUES (
              '点点英雄', 'gravity-m-1', 'md5-a', 'acc-1',
              '点点英雄-账户A', 'task-1', 'completed', 'v-uploaded'
            )
            """
        )

    response = _client(tmp_path).get(
        "/api/gravity-materials/materials",
        params={"product": "点点英雄", "page": 1, "page_size": 100},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "引力素材库"
    assert {"label": "可铺货素材", "value": 1} in payload["summary"]["items"]
    assert payload["table"]["columns"] == [
        "专辑",
        "素材名",
        "7天消耗",
        "7天转化",
        "30天消耗",
        "30天转化",
        "引力素材 ID",
        "MD5",
        "引力创建时间",
        "最近同步时间",
        "推送覆盖情况",
        "文件夹",
    ]
    row = payload["table"]["rows"][0]
    assert row["专辑"] == "点点英雄专辑"
    assert row["素材名"] == "素材A"
    assert row["7天消耗"] == 3.5
    assert row["7天转化"] == 1
    assert row["30天消耗"] == 12.5
    assert row["30天转化"] == 1
    assert row["引力素材 ID"] == "gravity-m-1"
    assert row["MD5"] == "md5-a"
    assert row["引力创建时间"] == "2026-06-01T10:00:00+08:00"
    assert row["最近同步时间"] == "now"
    assert row["推送覆盖情况"] == "已推送 1/2 个账户"
    assert row["文件夹"] == "6月新素材"
    assert payload["raw"]["materials"][0]["source_advertiser_id"] == "gravity_engine_182"
    assert payload["raw"]["pagination"] == {"page": 1, "page_size": 100, "total": 1, "total_pages": 1}


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
    assert items["可铺货素材"] == 2
    assert items["不可入库/不可铺货"] == 2
    assert items["缺 MD5"] == 1
    assert items["已推送"] == 1
    assert "有表现数据" not in items
    by_id = {row["引力素材 ID"]: row for row in payload["table"]["rows"]}
    assert set(by_id) == {"gravity-ok", "gravity-uploaded"}
    assert "gravity-missing-md5" not in by_id
    assert "gravity-disabled" not in by_id
    assert all("资格状态" not in row for row in payload["table"]["rows"])
    assert payload["raw"]["pagination"]["total"] == 2


def test_gravity_materials_list_paginates_and_sorts_on_backend(tmp_path: Path):
    db_path = tmp_path / "data" / "roibang_v2.sqlite3"
    bootstrap_database(db_path)
    with sqlite3.connect(db_path) as conn:
        for material_id, name, cost in [
            ("gravity-low", "素材低消耗", 1.0),
            ("gravity-mid", "素材中消耗", 5.0),
            ("gravity-high", "素材高消耗", 9.0),
        ]:
            conn.execute(
                """
                INSERT INTO product_source_materials (
                  product, source_advertiser_id, organization_id, material_id,
                  video_id, name, material_type, review_status, signature,
                  duration, file_size, create_time, tag_ids_json, is_active,
                  first_seen_at, last_seen_at, cost_lookback, score,
                  payload_json, source, synced_at
                ) VALUES (
                  '点点英雄', 'gravity_engine_182', '182', ?,
                  '', ?, 'video', '可用', ?,
                  15, 2048, '2026-06-01T10:00:00+08:00', '[]', 1,
                  'now', 'now', 0, 0,
                  '{"album_name":"点点英雄专辑","folder_name":"6月新素材","status":1}', 'gravity_engine', 'now'
                )
                """,
                (material_id, name, f"md5-{material_id}"),
            )
            conn.execute(
                """
                INSERT INTO product_source_material_metric_rollups (
                  product, source_advertiser_id, organization_id, window_key, window_days,
                  period_start, period_end, material_id, material_type, source_video_id,
                  name, review_status, signature, duration, file_size, create_time,
                  tag_ids_json, stat_cost, show_cnt, click_cnt, convert_cnt, source, synced_at
                ) VALUES (
                  '点点英雄', 'gravity_engine_182', '182', 'last_7d', 7,
                  '2026-05-26', '2026-06-01', ?, 'video', '',
                  ?, '可用', ?, 15, 2048, '2026-06-01T10:00:00+08:00',
                  '[]', ?, 100, 5, 1, 'gravity_engine', 'now'
                )
                """,
                (material_id, name, f"md5-{material_id}", cost),
            )

    response = _client(tmp_path).get(
        "/api/gravity-materials/materials",
        params={
            "product": "点点英雄",
            "page": 2,
            "page_size": 2,
            "sort_by": "7天消耗",
            "sort_order": "descend",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["raw"]["pagination"] == {"page": 2, "page_size": 2, "total": 3, "total_pages": 2}
    assert [row["引力素材 ID"] for row in payload["table"]["rows"]] == ["gravity-low"]


def test_gravity_preload_preview_uses_active_accounts_and_usable_materials(tmp_path: Path):
    db_path = tmp_path / "data" / "roibang_v2.sqlite3"
    bootstrap_database(db_path)
    account_store = tmp_path / "configs" / "accounts" / "product-accounts.local.json"
    account_store.parent.mkdir(parents=True)
    account_store.write_text(
        json.dumps(
            {
                "accounts": [
                    {
                        "product_key": "diandian-hero",
                        "product_name": "点点英雄",
                        "advertiser_id": "acc-1",
                        "advertiser_name": "点点英雄-人工账户",
                        "channel": "微信",
                        "owner": "郭靖",
                        "account_remark": "",
                        "status": "active",
                        "notes": "",
                    },
                    {
                        "product_key": "diandian-hero",
                        "product_name": "点点英雄",
                        "advertiser_id": "acc-2",
                        "advertiser_name": "点点英雄-历史账户",
                        "channel": "微信",
                        "owner": "郭靖",
                        "account_remark": "",
                        "status": "active",
                        "notes": "历史数据自动补全",
                    },
                    {
                        "product_key": "diandian-hero",
                        "product_name": "点点英雄",
                        "advertiser_id": "acc-disabled",
                        "advertiser_name": "点点英雄-停用账户",
                        "channel": "微信",
                        "owner": "郭靖",
                        "account_remark": "",
                        "status": "disabled",
                        "notes": "",
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
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
              '', ?, 'video', ?, ?,
              15, 2048, '2026-06-01T10:00:00+08:00', '[]', ?,
              'now', 'now', 0, 0,
              ?, 'gravity_engine', 'now'
            )
            """,
            [
                ("gravity-ok", "可铺货素材", "可用", "md5-ok", 1, '{"album_name":"目标专辑","folder_name":"文件夹A","status":1}'),
                ("gravity-disabled", "禁用素材", "禁用", "md5-disabled", 1, '{"album_name":"目标专辑","folder_name":"文件夹A","status":2}'),
                ("gravity-missing-md5", "缺 MD5 素材", "可用", "", 1, '{"album_name":"目标专辑","folder_name":"文件夹A","status":1}'),
            ],
        )
        conn.execute(
            """
            INSERT INTO account_materials (
              advertiser_id, material_id, video_id, material_type, review_status,
              cost_lookback, score, source, synced_at
            ) VALUES ('acc-1', 'already-1', 'vUploaded123456', 'video', '可用', 0, 0, 'account_materials', 'now')
            """
        )
        conn.execute(
            """
            INSERT INTO materials (
              material_id, name, material_type, video_id, review_status,
              payload_json, source, synced_at
            ) VALUES (
              'already-1', '账户已有素材', 'video', 'vUploaded123456', '可用',
              '{"md5":"md5-ok"}', 'account_materials', 'now'
            )
            """
        )

    response = _client(tmp_path).post(
        "/api/gravity-materials/preload-preview",
        json={"product": "点点英雄", "batch_size": 50},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "引力素材提前铺货预览"
    assert payload["summary"]["execution_enabled"] is False
    items = {item["label"]: item["value"] for item in payload["summary"]["items"]}
    assert items["郭靖启用账户"] == 2
    assert items["目标负责人"] == "郭靖"
    assert items["可铺货素材"] == 1
    assert items["账户已有/已覆盖"] == 1
    assert items["需铺货"] == 1
    assert items["批次数"] == 1
    assert payload["raw"]["upload_material_called"] is False
    assert payload["raw"]["batch_size"] == 50
    assert payload["raw"]["upload_batches"] == [
        {
            "batch_key": "点点英雄_acc-2_1",
            "target_advertiser_id": "acc-2",
            "target_account_name": "点点英雄-历史账户",
            "target_account_source": "历史补全",
            "material_ids": ["gravity-ok"],
            "material_count": 1,
        }
    ]
    assert payload["table"]["rows"] == [
        {
            "账户名": "点点英雄-人工账户",
            "账户 ID": "acc-1",
            "账户来源": "人工导入",
            "素材名": "可铺货素材",
            "引力素材 ID": "gravity-ok",
            "MD5": "md5-ok",
            "状态": "账户已有",
            "媒体素材 ID": "vUploaded123456",
        },
        {
            "账户名": "点点英雄-历史账户",
            "账户 ID": "acc-2",
            "账户来源": "历史补全",
            "素材名": "可铺货素材",
            "引力素材 ID": "gravity-ok",
            "MD5": "md5-ok",
            "状态": "需铺货",
            "媒体素材 ID": "",
        },
    ]


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
                            "data": {
                                "tree": [
                                    {
                                        "id": "album-1",
                                        "label": "黑旗-奇门（塔防）",
                                        "children": [{"id": "folder-1", "label": "6月新素材"}],
                                    }
                                ]
                            },
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
    assert {"label": "原始专辑/文件夹", "value": 2} in payload["summary"]["items"]
    assert payload["raw"]["nodes"] == [
        {
            "专辑/文件夹 ID": "album-1",
            "名称": "黑旗-奇门（塔防）",
            "层级": 1,
            "album_id": "album-1",
            "album_name": "黑旗-奇门（塔防）",
            "folder_id": "",
            "folder_name": "",
        },
        {
            "专辑/文件夹 ID": "folder-1",
            "名称": "6月新素材",
            "层级": 2,
            "album_id": "album-1",
            "album_name": "黑旗-奇门（塔防）",
            "folder_id": "folder-1",
            "folder_name": "6月新素材",
        },
    ]


def test_gravity_album_tree_marks_required_target_album_scope(tmp_path: Path):
    runs_dir = tmp_path / "data" / "runs" / "gravity_api_probe"
    runs_dir.mkdir(parents=True)
    (runs_dir / "20260604T010203Z.json").write_text(
        json.dumps(
            {
                "raw": {
                    "endpoint_results": {
                        "album_tree": {
                            "code": 0,
                            "data": {
                                "tree": [
                                    {
                                        "id": "target-1",
                                        "label": "黑旗-奇门(塔防)",
                                        "children": [
                                            {"id": "target-1-folder-1", "label": "基础素材"},
                                            {"id": "target-1-folder-2", "label": "外包"},
                                        ],
                                    },
                                    {
                                        "id": "target-2",
                                        "label": "魔兽开箱子",
                                        "children": [
                                            {"id": "target-2-folder-1", "label": "基础物料"},
                                            {"id": "target-2-folder-2", "label": "咕哒子"},
                                        ],
                                    },
                                    {
                                        "id": "target-3",
                                        "label": "黑旗-6480咸鱼-微小合集",
                                        "children": [
                                            {"id": "target-3-folder-1", "label": "点点英雄基础素材"},
                                            {"id": "target-3-folder-2", "label": "郭靖"},
                                        ],
                                    },
                                    {"id": "other-1", "label": "其他游戏素材", "children": []},
                                ]
                            },
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
    items = {item["label"]: item["value"] for item in payload["summary"]["items"]}
    assert items["原始专辑/文件夹"] == 10
    assert items["目标专辑"] == 3
    assert items["已匹配目标"] == 3
    target_rows = payload["raw"]["target_albums"]
    assert [row["目标专辑"] for row in target_rows] == [
        "黑旗-奇门（塔防）",
        "魔兽开箱子",
        "黑旗-6480咸鱼-微小合集",
    ]
    assert {row["匹配状态"] for row in target_rows} == {"已匹配"}
    assert [row["专辑/文件夹 ID"] for row in target_rows] == ["target-1", "target-2", "target-3"]
    assert [row["匹配数量"] for row in target_rows] == [1, 1, 1]
    assert [row["可自动绑定"] for row in target_rows] == ["是", "是", "是"]


def test_gravity_upload_preview_api_returns_chinese_confirmation_plan(tmp_path: Path):
    _seed_upload_api_db(tmp_path)
    client = _client(tmp_path)

    response = client.post(
        "/api/gravity-materials/upload-preview",
        json={
            "product": "点点英雄",
            "target_accounts": [{"advertiser_id": "acc-1", "account_name": "点点英雄-账户A"}],
            "material_ids": ["gravity-existing", "gravity-missing"],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "引力素材上传预览"
    assert payload["summary"]["status"] == "ready_for_confirmation"
    assert payload["summary"]["execution_enabled"] is False
    assert {"label": "需上传", "value": 1} in payload["summary"]["items"]
    assert payload["table"]["columns"] == ["账户名", "账户 ID", "素材名", "引力素材 ID", "MD5", "状态", "媒体素材 ID"]
    assert {row["状态"] for row in payload["table"]["rows"]} == {"账户已有", "需上传"}
    assert payload["raw"]["upload_material_called"] is False
    assert "upload_items" in payload["raw"]


def test_gravity_upload_execute_api_requires_confirmation(tmp_path: Path):
    _seed_upload_api_db(tmp_path)
    client = _client(tmp_path)
    preview = client.post(
        "/api/gravity-materials/upload-preview",
        json={
            "product": "点点英雄",
            "target_accounts": [{"advertiser_id": "acc-1", "account_name": "点点英雄-账户A"}],
            "material_ids": ["gravity-missing"],
        },
    ).json()

    response = client.post(
        "/api/gravity-materials/upload-execute",
        json={"preview_path": preview["artifact_path"], "confirmation": "我确认"},
    )

    assert response.status_code == 400
    assert "真实执行前必须输入" in response.json()["detail"]


def test_gravity_upload_execute_api_starts_fixed_script_task(tmp_path: Path, monkeypatch):
    _seed_upload_api_db(tmp_path)
    calls = []

    def fake_start_runner(command, *, cwd):
        calls.append({"command": command, "cwd": str(cwd)})
        return 4321

    monkeypatch.setattr("backend.app.services.gravity_materials.start_runner", fake_start_runner, raising=False)
    client = _client(tmp_path)
    preview = client.post(
        "/api/gravity-materials/upload-preview",
        json={
            "product": "点点英雄",
            "target_accounts": [{"advertiser_id": "acc-1", "account_name": "点点英雄-账户A"}],
            "material_ids": ["gravity-missing"],
        },
    ).json()

    response = client.post(
        "/api/gravity-materials/upload-execute",
        json={
            "preview_path": preview["artifact_path"],
            "auth_file": "data/gravity_token.json",
            "confirmation": "确认执行",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "引力素材上传任务"
    assert payload["summary"]["status"] == "queued"
    assert payload["summary"]["execution_enabled"] is True
    assert payload["task"]["pid"] == 4321
    task_command = payload["task"]["command"]
    assert task_command[1:] == [
        "scripts/run_gravity_upload_to_account.py",
        "--preview-path",
        preview["artifact_path"],
        "--auth-file",
        "data/gravity_token.json",
        "--execute",
    ]
    assert "--material-ids" not in task_command
    assert calls and calls[0]["cwd"] == str(tmp_path)


def test_gravity_upload_status_and_result_api_show_account_names(tmp_path: Path):
    _seed_upload_api_db(tmp_path)
    db_path = tmp_path / "data" / "roibang_v2.sqlite3"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO gravity_upload_tasks (
              product, gravity_material_id, signature, target_advertiser_id,
              target_account_name, gravity_task_id, status, video_id,
              material_id_in_account, fail_reason, preview_artifact_path,
              response_payload_json
            ) VALUES (
              '点点英雄', 'gravity-missing', 'md5-missing', 'acc-1',
              '点点英雄-账户A', 'task-acc-1', 'uploading', '',
              '', '', 'data/runs/gravity_upload_to_account_preview/demo.json',
              '{"code":0}'
            )
            """
        )
    client = _client(tmp_path)

    status_response = client.get("/api/gravity-materials/upload-status/task-acc-1")
    result_response = client.get("/api/gravity-materials/upload-result/task-acc-1")

    assert status_response.status_code == 200
    status_payload = status_response.json()
    assert status_payload["summary"]["title"] == "引力素材上传状态"
    assert {"label": "上传记录", "value": 1} in status_payload["summary"]["items"]
    assert status_payload["table"]["rows"][0]["账户 ID"] == "acc-1"
    assert status_payload["table"]["rows"][0]["账户名"] == "点点英雄-账户A"
    assert result_response.status_code == 200
    assert result_response.json()["summary"]["title"] == "引力素材上传结果"


def test_gravity_upload_status_refresh_api_starts_fixed_readonly_script(tmp_path: Path, monkeypatch):
    _seed_upload_api_db(tmp_path)
    calls = []

    def fake_start_runner(command, *, cwd):
        calls.append({"command": command, "cwd": str(cwd)})
        return 5432

    monkeypatch.setattr("backend.app.services.gravity_materials.start_runner", fake_start_runner, raising=False)
    client = _client(tmp_path)

    response = client.post(
        "/api/gravity-materials/upload-status-refresh",
        json={"task_id": "task-acc-1", "auth_file": "data/gravity_token.json"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "引力素材上传状态刷新任务"
    assert payload["summary"]["status"] == "queued"
    assert payload["summary"]["execution_enabled"] is False
    assert payload["task"]["pid"] == 5432
    task_command = payload["task"]["command"]
    assert task_command[1:] == [
        "scripts/run_gravity_upload_status_poll.py",
        "--task-id",
        "task-acc-1",
        "--auth-file",
        "data/gravity_token.json",
    ]
    assert "--execute" not in task_command
    assert calls and calls[0]["cwd"] == str(tmp_path)


def _seed_upload_api_db(tmp_path: Path) -> None:
    db_path = tmp_path / "data" / "roibang_v2.sqlite3"
    bootstrap_database(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            """
            INSERT INTO materials (
              material_id, name, material_type, video_id, review_status,
              cost_lookback, score, payload_json, source, synced_at
            ) VALUES (?, ?, 'video', ?, '可用', 0, 0, ?, ?, 'now')
            """,
            [
                ("target-existing", "目标账户已有素材", "vEXISTING123456", '{"signature":"md5-existing"}', "account_materials"),
                ("gravity-existing", "引力已有素材", "", '{"signature":"md5-existing"}', "gravity_engine"),
                ("gravity-missing", "引力待上传素材", "", '{"signature":"md5-missing"}', "gravity_engine"),
            ],
        )
        conn.execute(
            """
            INSERT INTO account_materials (
              advertiser_id, material_id, video_id, material_type, review_status,
              cost_lookback, score, source, synced_at
            ) VALUES ('acc-1', 'target-existing', 'vEXISTING123456', 'video', '可用', 0, 0, 'account_materials', 'now')
            """
        )
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
              '', ?, 'video', '可用', ?,
              15, 2048, '2026-06-01T10:00:00+08:00', '[]', 1,
              'now', 'now', 0, 0,
              '{"album_name":"点点英雄专辑","folder_name":"6月新素材","status":1}', 'gravity_engine', 'now'
            )
            """,
            [
                ("gravity-existing", "引力已有素材", "md5-existing"),
                ("gravity-missing", "引力待上传素材", "md5-missing"),
            ],
        )
