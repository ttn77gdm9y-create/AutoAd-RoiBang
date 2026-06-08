import json
import sqlite3
from pathlib import Path

from roibang_v2.db.bootstrap import bootstrap_database
import roibang_v2.workflows.gravity_upload_to_account as gravity_upload_workflow
from roibang_v2.workflows.gravity_upload_to_account import build_gravity_upload_preview
from roibang_v2.workflows.gravity_upload_to_account import run_gravity_upload_execute_request
from roibang_v2.workflows.gravity_upload_to_account import run_gravity_upload_status_poll_request


class FakeGravityUploadClient:
    def __init__(self) -> None:
        self.upload_calls: list[dict] = []

    def upload_material_to_account(self, *, advertiser_id: str, material_ids: list[str]) -> dict:
        self.upload_calls.append({"advertiser_id": advertiser_id, "material_ids": material_ids})
        return {"code": 0, "msg": "成功", "data": {"task_id": f"task-{advertiser_id}"}}


class FakeGravityStatusClient:
    def __init__(self, response: dict) -> None:
        self.response = response
        self.status_calls: list[str] = []

    def get_upload_material_status(self, *, task_id: str) -> dict:
        self.status_calls.append(task_id)
        return self.response


def test_gravity_upload_preview_checks_target_account_without_external_actions(tmp_path: Path):
    db_path = _seed_upload_db(tmp_path)
    result = build_gravity_upload_preview(
        {
            "product": "点点英雄",
            "target_accounts": [{"advertiser_id": "acc-1", "account_name": "点点英雄-账户A"}],
            "material_ids": ["gravity-existing", "gravity-missing"],
        },
        db_path=db_path,
        runs_dir=tmp_path / "data" / "runs",
    )

    assert result["ok"] is True
    assert result["workflow"] == "gravity_upload_to_account_preview"
    assert result["status"] == "ready_for_confirmation"
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 0
    assert result["summary"]["upload_material_called"] is False
    assert result["summary"]["target_account_count"] == 1
    assert result["summary"]["selected_material_count"] == 2
    assert result["summary"]["existing_count"] == 1
    assert result["summary"]["upload_required_count"] == 1
    assert "需要上传 1 条" in result["中文摘要"]
    rows = result["table"]["rows"]
    assert {row["状态"] for row in rows} == {"账户已有", "需上传"}
    assert rows[0]["账户 ID"] == "acc-1"
    assert rows[0]["账户名"] == "点点英雄-账户A"
    upload_item = result["raw"]["upload_items"][0]
    assert upload_item["引力素材 ID"] == "gravity-missing"
    assert upload_item["账户名"] == "点点英雄-账户A"
    assert Path(result["artifact_path"]).exists()


def test_gravity_upload_preview_blocks_ineligible_or_missing_md5_materials(tmp_path: Path):
    db_path = _seed_upload_db(tmp_path)
    result = build_gravity_upload_preview(
        {
            "product": "点点英雄",
            "target_accounts": [{"advertiser_id": "acc-1", "account_name": "点点英雄-账户A"}],
            "material_ids": ["gravity-no-md5"],
        },
        db_path=db_path,
        runs_dir=tmp_path / "data" / "runs",
    )

    assert result["ok"] is False
    assert result["status"] == "blocked"
    assert result["external_api_calls"] == 0
    assert result["summary"]["upload_material_called"] is False
    assert "缺少 MD5" in "；".join(result["blocking_reasons"])


def test_gravity_upload_execute_reads_preview_and_records_async_task(tmp_path: Path):
    db_path = _seed_upload_db(tmp_path)
    preview = build_gravity_upload_preview(
        {
            "product": "点点英雄",
            "target_accounts": [{"advertiser_id": "acc-1", "account_name": "点点英雄-账户A"}],
            "material_ids": ["gravity-missing"],
        },
        db_path=db_path,
        runs_dir=tmp_path / "data" / "runs",
    )
    fake_client = FakeGravityUploadClient()

    result = run_gravity_upload_execute_request(
        {"preview_path": preview["artifact_path"], "auth": _auth()},
        db_path=db_path,
        runs_dir=tmp_path / "data" / "runs",
        client=fake_client,
    )

    assert result["ok"] is True
    assert result["workflow"] == "gravity_upload_to_account"
    assert result["status"] == "submitted"
    assert result["execution_enabled"] is True
    assert result["external_api_calls"] == 1
    assert result["summary"]["upload_material_called"] is True
    assert result["summary"]["submitted_material_count"] == 1
    assert fake_client.upload_calls == [{"advertiser_id": "acc-1", "material_ids": ["gravity-missing"]}]
    assert result["table"]["rows"][0]["账户名"] == "点点英雄-账户A"
    assert result["table"]["rows"][0]["引力任务 ID"] == "task-acc-1"
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT product, gravity_material_id, target_advertiser_id, target_account_name,
                   gravity_task_id, status, video_id
            FROM gravity_upload_tasks
            WHERE gravity_material_id = 'gravity-missing' AND target_advertiser_id = 'acc-1'
            """
        ).fetchone()
    assert row == ("点点英雄", "gravity-missing", "acc-1", "点点英雄-账户A", "task-acc-1", "uploading", "")


def test_gravity_upload_execute_batches_large_preload_preview(tmp_path: Path):
    db_path = _seed_upload_db(tmp_path)
    for material_id in ["gravity-batch-1", "gravity-batch-2", "gravity-batch-3"]:
        _seed_gravity_material(db_path, material_id=material_id, signature=f"md5-{material_id}")
    preview = build_gravity_upload_preview(
        {
            "product": "点点英雄",
            "target_accounts": [{"advertiser_id": "acc-1", "account_name": "点点英雄-账户A"}],
            "material_ids": ["gravity-batch-1", "gravity-batch-2", "gravity-batch-3"],
            "preview_mode": "preload",
            "batch_size": 2,
        },
        db_path=db_path,
        runs_dir=tmp_path / "data" / "runs",
    )
    fake_client = FakeGravityUploadClient()

    result = run_gravity_upload_execute_request(
        {"preview_path": preview["artifact_path"], "auth": _auth()},
        db_path=db_path,
        runs_dir=tmp_path / "data" / "runs",
        client=fake_client,
    )

    assert result["ok"] is True
    assert result["external_api_calls"] == 2
    assert result["summary"]["submitted_material_count"] == 3
    assert result["summary"]["submitted_batch_count"] == 2
    assert fake_client.upload_calls == [
        {"advertiser_id": "acc-1", "material_ids": ["gravity-batch-1", "gravity-batch-2"]},
        {"advertiser_id": "acc-1", "material_ids": ["gravity-batch-3"]},
    ]
    assert {row["引力素材 ID"] for row in result["table"]["rows"]} == {
        "gravity-batch-1",
        "gravity-batch-2",
        "gravity-batch-3",
    }


def test_gravity_preload_preview_blocks_oversized_single_execute_and_caps_rows(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(gravity_upload_workflow, "PRELOAD_SINGLE_EXECUTE_PAIR_LIMIT", 2)
    monkeypatch.setattr(gravity_upload_workflow, "PRELOAD_TABLE_ROW_LIMIT", 2)
    db_path = _seed_upload_db(tmp_path)
    for material_id in ["gravity-large-1", "gravity-large-2", "gravity-large-3"]:
        _seed_gravity_material(db_path, material_id=material_id, signature=f"md5-{material_id}")

    result = build_gravity_upload_preview(
        {
            "product": "点点英雄",
            "target_accounts": [{"advertiser_id": "acc-1", "account_name": "点点英雄-账户A", "account_source": "历史补全"}],
            "material_ids": ["gravity-large-1", "gravity-large-2", "gravity-large-3"],
            "preview_mode": "preload",
            "batch_size": 2,
        },
        db_path=db_path,
        runs_dir=tmp_path / "data" / "runs",
    )

    assert result["ok"] is True
    assert result["status"] == "blocked"
    assert result["summary"]["status"] == "blocked"
    assert "超过单次确认上限 2 条" in "；".join(result["blocking_reasons"])
    assert len(result["table"]["rows"]) == 2
    assert result["summary"]["upload_required_count"] == 3
    assert result["raw"]["upload_items"] == []
    assert result["raw"]["upload_items_omitted"] is True
    assert result["raw"]["upload_item_count"] == 3
    assert result["raw"]["upload_batch_count"] == 2
    assert result["raw"]["display_row_count"] == 2
    assert any(item["label"] == "页面展示" for item in result["summary"]["items"])


def test_gravity_upload_execute_blocks_non_preview_artifact(tmp_path: Path):
    db_path = _seed_upload_db(tmp_path)
    bad_path = tmp_path / "bad.json"
    bad_path.write_text(json.dumps({"workflow": "gravity_material_sync"}, ensure_ascii=False), encoding="utf-8")

    result = run_gravity_upload_execute_request(
        {"preview_path": str(bad_path), "auth": _auth()},
        db_path=db_path,
        runs_dir=tmp_path / "data" / "runs",
        client=FakeGravityUploadClient(),
    )

    assert result["ok"] is False
    assert result["status"] == "blocked"
    assert result["external_api_calls"] == 0
    assert "上传预览文件不合法" in "；".join(result["blocking_reasons"])


def test_gravity_upload_status_poll_backfills_video_id_after_local_material_sync(tmp_path: Path):
    db_path = _seed_upload_db(tmp_path)
    _seed_pending_upload_task(db_path)
    _seed_uploaded_target_material(db_path)
    fake_client = FakeGravityStatusClient({"code": 0, "data": {"status": "completed"}})

    result = run_gravity_upload_status_poll_request(
        {"task_id": "task-acc-1", "auth": _auth()},
        db_path=db_path,
        runs_dir=tmp_path / "data" / "runs",
        client=fake_client,
    )

    assert result["ok"] is True
    assert result["workflow"] == "gravity_upload_status_poll"
    assert result["status"] == "completed"
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 1
    assert fake_client.status_calls == ["task-acc-1"]
    assert result["table"]["rows"][0]["账户名"] == "点点英雄-账户A"
    assert result["table"]["rows"][0]["状态"] == "已完成"
    assert result["table"]["rows"][0]["媒体素材 ID"] == "vUPLOADED123456"
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT status, video_id, material_id_in_account, fail_reason
            FROM gravity_upload_tasks
            WHERE gravity_task_id = 'task-acc-1'
            """
        ).fetchone()
    assert row == ("completed", "vUPLOADED123456", "target-uploaded", "")


def test_gravity_upload_status_poll_keeps_uploading_until_video_id_is_locally_resolved(tmp_path: Path):
    db_path = _seed_upload_db(tmp_path)
    _seed_pending_upload_task(db_path)
    fake_client = FakeGravityStatusClient({"code": 0, "data": {"status": "completed"}})

    result = run_gravity_upload_status_poll_request(
        {"task_id": "task-acc-1", "auth": _auth()},
        db_path=db_path,
        runs_dir=tmp_path / "data" / "runs",
        client=fake_client,
    )

    assert result["ok"] is True
    assert result["status"] == "running"
    assert result["external_api_calls"] == 1
    assert "本地账户素材库还未同步到合法媒体素材 ID" in "；".join(result["warnings"])
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT status, video_id, material_id_in_account, fail_reason
            FROM gravity_upload_tasks
            WHERE gravity_task_id = 'task-acc-1'
            """
        ).fetchone()
    assert row == ("uploading", "", "", "引力任务显示完成，但本地账户素材库还未同步到合法媒体素材 ID")


def _seed_upload_db(tmp_path: Path) -> Path:
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
                ("gravity-no-md5", "缺MD5素材", "", '{}', "gravity_engine"),
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
              ?, 'gravity_engine', 'now'
            )
            """,
            [
                ("gravity-existing", "引力已有素材", "md5-existing", '{"album_name":"点点英雄专辑","folder_name":"6月新素材","status":1}'),
                ("gravity-missing", "引力待上传素材", "md5-missing", '{"album_name":"点点英雄专辑","folder_name":"6月新素材","status":1}'),
                ("gravity-no-md5", "缺MD5素材", "", '{"album_name":"点点英雄专辑","folder_name":"6月新素材","status":1}'),
            ],
        )
    return db_path


def _seed_gravity_material(db_path: Path, *, material_id: str, signature: str) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO materials (
              material_id, name, material_type, video_id, review_status,
              cost_lookback, score, payload_json, source, synced_at
            ) VALUES (?, ?, 'video', '', '可用', 0, 0, ?, 'gravity_engine', 'now')
            """,
            (material_id, material_id, json.dumps({"signature": signature}, ensure_ascii=False)),
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
              '点点英雄', 'gravity_engine_182', '182', ?,
              '', ?, 'video', '可用', ?,
              15, 2048, '2026-06-01T10:00:00+08:00', '[]', 1,
              'now', 'now', 0, 0,
              '{"album_name":"点点英雄专辑","folder_name":"6月新素材","status":1}', 'gravity_engine', 'now'
            )
            """,
            (material_id, material_id, signature),
        )


def _seed_pending_upload_task(db_path: Path) -> None:
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


def _seed_uploaded_target_material(db_path: Path) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO materials (
              material_id, name, material_type, video_id, review_status,
              cost_lookback, score, payload_json, source, synced_at
            ) VALUES (
              'target-uploaded', '目标账户新上传素材', 'video', 'vUPLOADED123456',
              '可用', 0, 0, '{"signature":"md5-missing"}', 'account_materials', 'now'
            )
            """
        )
        conn.execute(
            """
            INSERT INTO account_materials (
              advertiser_id, material_id, video_id, material_type, review_status,
              cost_lookback, score, source, synced_at
            ) VALUES (
              'acc-1', 'target-uploaded', 'vUPLOADED123456',
              'video', '可用', 0, 0, 'account_materials', 'now'
            )
            """
        )


def _auth() -> dict[str, str]:
    return {
        "authorization": "token",
        "gravity_cid": "182",
        "gravity_email": "hongen@example.com",
        "gravity_id": "406",
        "gravity_super": "false",
    }
