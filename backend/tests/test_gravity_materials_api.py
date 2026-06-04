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
