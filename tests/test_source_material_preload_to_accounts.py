import json
import sqlite3
from datetime import date
from pathlib import Path

from roibang_v2.db.bootstrap import bootstrap_database
from roibang_v2.workflows.source_material_preload_to_accounts import (
    build_source_material_preload_plan,
    run_source_material_preload_to_accounts_request,
)


def _seed_source_material(conn: sqlite3.Connection, material_id: str, video_id: str, cost: float = 100) -> None:
    conn.execute(
        """
        INSERT INTO product_source_materials (
          product, source_advertiser_id, organization_id, material_id,
          video_id, name, material_type, review_status, is_active,
          cost_lookback, score, source, synced_at
        ) VALUES ('勇者突进', 'source-1', 'org-1', ?, ?, ?, 'video', 'APPROVED', 1, ?, ?, 'test', 'now')
        """,
        (material_id, video_id, f"素材{material_id}", cost, cost),
    )


def _write_patrol(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "accounts": [
                    {
                        "advertiser_id": "target-1",
                        "account_name": "郭靖账户1",
                        "account_remark": "勇者突进-微小-郭靖",
                        "metrics": {"today": {"stat_cost": 100}},
                    },
                    {
                        "advertiser_id": "target-2",
                        "account_name": "郭靖账户2",
                        "account_remark": "勇者突进-微小-郭靖",
                        "metrics": {"today": {"stat_cost": 50}},
                    },
                    {
                        "advertiser_id": "target-3",
                        "account_name": "鲁班账户",
                        "account_remark": "勇者突进-微小-鲁班",
                        "metrics": {"today": {"stat_cost": 200}},
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _request(patrol_path: Path) -> dict:
    return {
        "product": "勇者突进",
        "source_advertiser_id": "source-1",
        "organization_id": "org-1",
        "target_date": "today",
        "target_accounts": {
            "source": "delivery_patrol_artifact",
            "artifact_path": str(patrol_path),
            "account_remark_equals": "勇者突进-微小-郭靖",
            "spend_window": "today",
            "min_spend": 0,
        },
        "material_source": {"material_type": "video", "max_bind_materials": 0, "batch_size": 2},
        "execute": {"enabled": False, "approved": False, "allow_mutation": False},
    }


def test_builds_preload_plan_from_patrol_remark_and_today_spend(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    patrol_path = tmp_path / "patrol.json"
    bootstrap_database(db_path)
    _write_patrol(patrol_path)
    with sqlite3.connect(db_path) as conn:
        _seed_source_material(conn, "m1", "v1", 300)
        _seed_source_material(conn, "1000000000000000001", "v28033gi0000d7m72bvog65s5f9la001", 300)
        _seed_source_material(conn, "1000000000000000002", "v28033gi0000d7m72bvog65s5f9la002", 200)
        _seed_source_material(conn, "1000000000000000003", "v28033gi0000d7m72bvog65s5f9la003", 100)
        conn.execute(
            """
            INSERT INTO account_materials
              (advertiser_id, material_id, video_id, material_type, review_status, source, synced_at)
            VALUES ('target-1', '1000000000000000001', 'target-v1', 'video', 'APPROVED', 'test', 'now')
            """
        )

    cfg = _request(patrol_path)
    cfg["target_accounts"]["min_spend"] = 90
    plan = build_source_material_preload_plan(
        db_path=db_path,
        cfg=cfg,
        today=date(2026, 5, 15),
    )

    assert plan["summary"]["target_account_count"] == 1
    assert plan["summary"]["source_material_count"] == 3
    assert plan["summary"]["already_exists_count"] == 1
    assert plan["summary"]["planned_bind_material_count"] == 2
    assert plan["summary"]["push_batch_count"] == 1
    assert plan["push_batches"][0]["target_advertiser_id"] == "target-1"
    assert plan["push_batches"][0]["video_ids"] == [
        "v28033gi0000d7m72bvog65s5f9la002",
        "v28033gi0000d7m72bvog65s5f9la003",
    ]


def test_preload_plan_accepts_explicit_new_account_list_without_patrol_artifact(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)
    with sqlite3.connect(db_path) as conn:
        _seed_source_material(conn, "1000000000000000001", "v28033gi0000d7m72bvog65s5f9la001", 300)
    cfg = _request(tmp_path / "missing-patrol.json")
    cfg["target_accounts"] = {"accounts": ["target-new-1", {"advertiser_id": "target-new-2"}]}
    cfg["material_source"]["max_bind_materials"] = 0

    plan = build_source_material_preload_plan(
        db_path=db_path,
        cfg=cfg,
        today=date(2026, 5, 16),
    )

    assert plan["summary"]["target_account_count"] == 2
    assert plan["summary"]["source_material_count"] == 1
    assert plan["summary"]["planned_bind_material_count"] == 2
    assert [batch["target_advertiser_id"] for batch in plan["push_batches"]] == ["target-new-1", "target-new-2"]


def test_preload_plan_excludes_source_account_from_explicit_targets(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)
    with sqlite3.connect(db_path) as conn:
        _seed_source_material(conn, "1000000000000000001", "v28033gi0000d7m72bvog65s5f9la001", 300)
    cfg = _request(tmp_path / "missing-patrol.json")
    cfg["target_accounts"] = {
        "accounts": [
            {"advertiser_id": "source-1", "account_name": "源素材账户"},
            {"advertiser_id": "target-new-1", "account_name": "目标账户"},
        ]
    }

    plan = build_source_material_preload_plan(
        db_path=db_path,
        cfg=cfg,
        today=date(2026, 5, 16),
    )

    assert plan["summary"]["target_account_count"] == 1
    assert plan["target_accounts"][0]["advertiser_id"] == "target-new-1"
    assert [batch["target_advertiser_id"] for batch in plan["push_batches"]] == ["target-new-1"]


def test_preload_limit_round_robins_across_target_accounts(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    patrol_path = tmp_path / "patrol.json"
    bootstrap_database(db_path)
    _write_patrol(patrol_path)
    with sqlite3.connect(db_path) as conn:
        _seed_source_material(conn, "1000000000000000001", "v28033gi0000d7m72bvog65s5f9la001", 300)
        _seed_source_material(conn, "1000000000000000002", "v28033gi0000d7m72bvog65s5f9la002", 200)
        _seed_source_material(conn, "1000000000000000003", "v28033gi0000d7m72bvog65s5f9la003", 100)
        _seed_source_material(conn, "1000000000000000004", "v28033gi0000d7m72bvog65s5f9la004", 50)
    cfg = _request(patrol_path)
    cfg["material_source"]["max_bind_materials"] = 3
    cfg["material_source"]["batch_size"] = 10

    plan = build_source_material_preload_plan(
        db_path=db_path,
        cfg=cfg,
        today=date(2026, 5, 15),
    )

    assert plan["summary"]["target_account_count"] == 2
    assert plan["summary"]["planned_bind_material_count"] == 3
    assert [batch["target_advertiser_id"] for batch in plan["push_batches"]] == ["target-1", "target-2"]
    assert plan["push_batches"][0]["material_ids"] == ["1000000000000000001", "1000000000000000002"]
    assert plan["push_batches"][1]["material_ids"] == ["1000000000000000001"]


def test_preload_caps_bind_material_batch_size_to_platform_limit(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    patrol_path = tmp_path / "patrol.json"
    bootstrap_database(db_path)
    _write_patrol(patrol_path)
    with sqlite3.connect(db_path) as conn:
        for index in range(120):
            _seed_source_material(
                conn,
                f"{1000000000000000000 + index}",
                f"v28033gi0000d7m72bvog65s5f{index:05d}",
                1000 - index,
            )
    cfg = _request(patrol_path)
    cfg["target_accounts"]["min_spend"] = 90
    cfg["material_source"]["batch_size"] = 100

    plan = build_source_material_preload_plan(
        db_path=db_path,
        cfg=cfg,
        today=date(2026, 5, 15),
    )

    assert plan["summary"]["requested_batch_size"] == 100
    assert plan["summary"]["batch_size"] == 50
    assert plan["summary"]["max_bind_material_video_ids"] == 50
    assert plan["summary"]["push_batch_count"] == 3
    assert [batch["material_count"] for batch in plan["push_batches"]] == [50, 50, 20]


def test_preload_execute_uses_source_to_target_bind_material_batches(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    patrol_path = tmp_path / "patrol.json"
    bootstrap_database(db_path)
    _write_patrol(patrol_path)
    with sqlite3.connect(db_path) as conn:
        _seed_source_material(conn, "1000000000000000001", "v28033gi0000d7m72bvog65s5f9la001", 300)
        _seed_source_material(conn, "1000000000000000002", "v28033gi0000d7m72bvog65s5f9la002", 200)
        _seed_source_material(conn, "1000000000000000003", "v28033gi0000d7m72bvog65s5f9la003", 100)

    calls = []

    def mutation_transport(request: dict) -> dict:
        calls.append(request)
        return {"code": 0, "data": {"task_id": "task-1"}}

    cfg = _request(patrol_path)
    cfg["target_accounts"]["min_spend"] = 90
    cfg["execute"] = {"enabled": True, "approved": True, "allow_mutation": True}
    result = run_source_material_preload_to_accounts_request(
        {"source_material_preload_to_accounts": cfg},
        db_path=db_path,
        runs_dir=tmp_path / "runs",
        mutation_transport=mutation_transport,
        today=date(2026, 5, 15),
    )

    assert result["ok"] is True
    assert result["execution_enabled"] is True
    assert result["summary"]["executed_bind_material_count"] == 3
    assert calls == [
        {
            "operation": "bind_material",
            "endpoint": "/open_api/2/file/material/bind/",
            "payload": {
                "advertiser_id": "source-1",
                "target_advertiser_ids": ["target-1"],
                "video_ids": ["v28033gi0000d7m72bvog65s5f9la001", "v28033gi0000d7m72bvog65s5f9la002"],
            },
        },
        {
            "operation": "bind_material",
            "endpoint": "/open_api/2/file/material/bind/",
            "payload": {
                "advertiser_id": "source-1",
                "target_advertiser_ids": ["target-1"],
                "video_ids": ["v28033gi0000d7m72bvog65s5f9la003"],
            },
        },
    ]
    with sqlite3.connect(db_path) as conn:
        ledger_count = conn.execute("SELECT COUNT(*) FROM source_material_preload_ledger").fetchone()[0]
    assert ledger_count == 3


def test_preload_plan_skips_completed_preload_ledger_rows(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    patrol_path = tmp_path / "patrol.json"
    bootstrap_database(db_path)
    _write_patrol(patrol_path)
    with sqlite3.connect(db_path) as conn:
        _seed_source_material(conn, "1000000000000000001", "v28033gi0000d7m72bvog65s5f9la001", 300)
        conn.execute(
            """
            INSERT INTO source_material_preload_ledger (
              product, source_advertiser_id, target_advertiser_id, source_material_id,
              source_video_id, status, batch_key, response_payload_json, first_seen_at, last_seen_at
            ) VALUES (
              '勇者突进', 'source-1', 'target-1', '1000000000000000001',
              'v28033gi0000d7m72bvog65s5f9la001', 'completed', 'batch-1', '{}', 'now', 'now'
            )
            """
        )

    cfg = _request(patrol_path)
    cfg["target_accounts"]["min_spend"] = 90
    plan = build_source_material_preload_plan(
        db_path=db_path,
        cfg=cfg,
        today=date(2026, 5, 15),
    )

    assert plan["summary"]["already_exists_count"] == 1
    assert plan["summary"]["planned_bind_material_count"] == 0
    assert plan["summary"]["push_batch_count"] == 0


def test_preload_execute_records_transport_error_without_crashing(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    patrol_path = tmp_path / "patrol.json"
    bootstrap_database(db_path)
    _write_patrol(patrol_path)
    with sqlite3.connect(db_path) as conn:
        _seed_source_material(conn, "1000000000000000001", "v28033gi0000d7m72bvog65s5f9la001", 300)

    def mutation_transport(_request: dict) -> dict:
        raise RuntimeError("network reset")

    cfg = _request(patrol_path)
    cfg["target_accounts"]["min_spend"] = 90
    cfg["execute"] = {"enabled": True, "approved": True, "allow_mutation": True}
    result = run_source_material_preload_to_accounts_request(
        {"source_material_preload_to_accounts": cfg},
        db_path=db_path,
        runs_dir=tmp_path / "runs",
        mutation_transport=mutation_transport,
        today=date(2026, 5, 15),
    )

    assert result["ok"] is False
    assert result["status"] == "completed_with_errors"
    assert result["summary"]["failed_batch_count"] == 1
    assert result["results"][0]["api_code"] == "transport_error"


def test_preload_execute_splits_400170_batch_and_records_successful_sub_batches(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    patrol_path = tmp_path / "patrol.json"
    bootstrap_database(db_path)
    _write_patrol(patrol_path)
    with sqlite3.connect(db_path) as conn:
        _seed_source_material(conn, "1000000000000000001", "v28033gi0000d7m72bvog65s5f9la001", 300)
        _seed_source_material(conn, "1000000000000000002", "v28033gi0000d7m72bvog65s5f9la002", 200)
        _seed_source_material(conn, "1000000000000000003", "v28033gi0000d7m72bvog65s5f9la003", 100)

    calls: list[list[str]] = []

    def mutation_transport(request: dict) -> dict:
        video_ids = list(request["payload"]["video_ids"])
        calls.append(video_ids)
        if "v28033gi0000d7m72bvog65s5f9la002" in video_ids:
            return {"code": 400170, "message": "部分视频无权限或不存在"}
        return {"code": 0, "message": "OK"}

    cfg = _request(patrol_path)
    cfg["target_accounts"]["min_spend"] = 90
    cfg["material_source"]["batch_size"] = 3
    cfg["execute"] = {
        "enabled": True,
        "approved": True,
        "allow_mutation": True,
        "split_on_api_codes": ["400170"],
    }
    result = run_source_material_preload_to_accounts_request(
        {"source_material_preload_to_accounts": cfg},
        db_path=db_path,
        runs_dir=tmp_path / "runs",
        mutation_transport=mutation_transport,
        today=date(2026, 5, 15),
        sleeper=lambda _seconds: None,
    )

    assert result["ok"] is True
    assert result["summary"]["executed_bind_material_count"] == 2
    assert result["summary"]["failed_batch_count"] == 0
    assert result["summary"]["skipped_bad_video_id_count"] == 1
    assert result["summary"]["bad_video_rows_upserted"] == 1
    assert any(row["status"] == "split_retry" for row in result["results"])
    assert any(row["status"] == "skipped" and row["api_code"] == "400170" for row in result["results"])
    assert calls[0] == [
        "v28033gi0000d7m72bvog65s5f9la001",
        "v28033gi0000d7m72bvog65s5f9la002",
        "v28033gi0000d7m72bvog65s5f9la003",
    ]
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT source_material_id FROM source_material_preload_ledger ORDER BY source_material_id"
        ).fetchall()
        bad_rows = conn.execute(
            """
            SELECT source_material_id, source_video_id, status
            FROM source_material_bad_videos
            WHERE product = '勇者突进' AND source_advertiser_id = 'source-1'
            """
        ).fetchall()
    assert [row[0] for row in rows] == ["1000000000000000001", "1000000000000000003"]
    assert bad_rows == [("1000000000000000002", "v28033gi0000d7m72bvog65s5f9la002", "active")]

    next_plan = build_source_material_preload_plan(
        db_path=db_path,
        cfg=cfg,
        today=date(2026, 5, 15),
    )
    planned_video_ids = {
        video_id
        for batch in next_plan["push_batches"]
        for video_id in batch["video_ids"]
    }
    assert "v28033gi0000d7m72bvog65s5f9la002" not in planned_video_ids
