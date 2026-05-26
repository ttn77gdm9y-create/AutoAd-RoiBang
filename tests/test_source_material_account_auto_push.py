import sqlite3
from datetime import date
from pathlib import Path

from roibang_v2.db.bootstrap import bootstrap_database
from roibang_v2.workflows.source_material_account_auto_push import (
    build_source_material_account_push_plan,
    normalize_material_name,
    run_source_material_account_auto_push_request,
)


def _seed_material(conn: sqlite3.Connection, material_id: str, *, name: str, video_id: str = "") -> None:
    conn.execute(
        """
        INSERT INTO materials
          (material_id, name, material_type, video_id, review_status, source, synced_at)
        VALUES (?, ?, 'video', ?, 'APPROVED', 'test', 'now')
        """,
        (material_id, name, video_id),
    )


def _seed_daily(conn: sqlite3.Connection, advertiser_id: str, material_id: str, *, cost: float) -> None:
    conn.execute(
        """
        INSERT INTO material_daily_metrics
          (metric_date, advertiser_id, project_id, promotion_id, material_id, material_kind, stat_cost, source, synced_at)
        VALUES ('2026-05-12', ?, 'p1', ?, ?, 'video', ?, 'test', 'now')
        """,
        (advertiser_id, f"u-{advertiser_id}-{material_id}", material_id, cost),
    )


def _request() -> dict:
    return {
        "source_material_account_auto_push": {
            "product": "勇者突进",
            "source_advertiser_id": "1856647522964490",
            "organization_id": "1851650746645060",
            "date_range": {"mode": "yesterday", "base_date": "2026-05-13"},
            "source_account_sync": {"enabled": False},
            "material_source": {"min_stat_cost": 0, "max_materials": 100, "max_video_ids_per_call": 50},
            "material_detail_fetch": {"enabled": False},
            "execute": {"enabled": False, "approved": False, "allow_mutation": False},
        }
    }


def test_normalize_material_name_strips_push_prefix():
    assert normalize_material_name(" 推送视频_勇者素材 A ") == "勇者素材a"
    assert normalize_material_name("推送视频-勇者素材 A") == "勇者素材a"


def test_builds_source_material_account_push_plan_from_daily_metrics(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)
    with sqlite3.connect(db_path) as conn:
        _seed_material(conn, "m-old", name="勇者素材A", video_id="v-old")
        _seed_material(conn, "m-ready", name="勇者素材B", video_id="v-ready")
        _seed_material(conn, "m-missing", name="勇者素材C", video_id="")
        conn.execute(
            """
            INSERT INTO account_materials
              (advertiser_id, material_id, video_id, material_type, review_status, source, synced_at)
            VALUES ('acc1', 'm-ready', 'v-ready', 'video', 'APPROVED', 'test', 'now')
            """
        )
        conn.execute(
            """
            INSERT INTO product_source_materials
              (product, source_advertiser_id, material_id, video_id, name, material_type, is_active, source, synced_at)
            VALUES ('勇者突进', '1856647522964490', 'src-old', 'src-v-old', '推送视频_勇者素材A', 'video', 1, 'test', 'now')
            """
        )
        _seed_daily(conn, "acc1", "m-old", cost=900)
        _seed_daily(conn, "acc1", "m-ready", cost=800)
        _seed_daily(conn, "acc2", "m-missing", cost=700)

    cfg = _request()["source_material_account_auto_push"]
    plan = build_source_material_account_push_plan(
        db_path=db_path,
        cfg=cfg,
        period_start="2026-05-12",
        period_end="2026-05-12",
    )

    assert plan["summary"]["spent_material_count"] == 3
    assert plan["summary"]["duplicate_skipped_count"] == 1
    assert plan["summary"]["new_material_count"] == 2
    assert plan["summary"]["ready_material_count"] == 1
    assert plan["summary"]["missing_video_id_count"] == 1
    assert plan["summary"]["push_batch_count"] == 1
    assert plan["push_batches"][0]["source_advertiser_id"] == "acc1"
    assert plan["push_batches"][0]["target_source_advertiser_id"] == "1856647522964490"
    assert plan["push_batches"][0]["video_ids"] == ["v-ready"]


def test_push_plan_can_filter_spent_materials_by_account_name_keyword(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)
    with sqlite3.connect(db_path) as conn:
        _seed_material(conn, "d-ready", name="点点素材", video_id="v-dd")
        _seed_material(conn, "y-ready", name="勇者素材", video_id="v-yzt")
        conn.execute(
            """
            INSERT INTO account_pool
              (advertiser_id, account_name, product, platform, historical_spend, source, synced_at)
            VALUES
              ('dd-1', '黑旗-点点英雄-微小-郭靖-001', '点点英雄', 'WECHAT_GAME', 100, 'test', 'now'),
              ('yzt-1', '黑旗-勇者突进-微小-郭靖-001', '勇者突进', 'WECHAT_GAME', 100, 'test', 'now')
            """
        )
        _seed_daily(conn, "dd-1", "d-ready", cost=800)
        _seed_daily(conn, "yzt-1", "y-ready", cost=900)

    cfg = _request()["source_material_account_auto_push"]
    cfg["product"] = "点点英雄"
    cfg["source_advertiser_id"] = "dd-source"
    cfg["material_source"]["account_name_keyword"] = "点点英雄"
    plan = build_source_material_account_push_plan(
        db_path=db_path,
        cfg=cfg,
        period_start="2026-05-12",
        period_end="2026-05-12",
    )

    assert plan["summary"]["spent_material_count"] == 1
    assert plan["push_batches"][0]["source_advertiser_id"] == "dd-1"
    assert plan["push_batches"][0]["material_ids"] == ["d-ready"]


def test_builds_push_plan_from_video_material_summaries_first(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)
    with sqlite3.connect(db_path) as conn:
        _seed_material(conn, "title-1", name="勇者文案", video_id="")
        _seed_daily(conn, "acc1", "title-1", cost=900)
        conn.execute(
            """
            INSERT INTO material_bindings
              (advertiser_id, project_id, promotion_id, material_kind, material_id, video_id, image_id, title, source, synced_at)
            VALUES
              ('acc1', 'p1', 'u1', 'title', 'title-1', '', '', '勇者文案', 'test', 'now'),
              ('acc1', 'p1', 'u1', 'video', 'video-1', 'v-source-1', '', '勇者视频', 'test', 'now')
            """
        )
        conn.execute(
            """
            INSERT INTO material_metric_summaries
              (material_kind, material_id, video_id, title, period_start, period_end,
               promotion_count, project_count, account_count, stat_cost, active_register,
               attribution_convert_cnt, roi_1day_cost_weighted, roi_7days_cost_weighted, source, synced_at)
            VALUES
              ('video', 'video-1', 'v-source-1', '勇者视频', '2026-05-12', '2026-05-12',
               1, 1, 1, 800, 0, 0, 0, 0, 'test', 'now')
            """
        )

    cfg = _request()["source_material_account_auto_push"]
    plan = build_source_material_account_push_plan(
        db_path=db_path,
        cfg=cfg,
        period_start="2026-05-12",
        period_end="2026-05-12",
    )

    assert plan["summary"]["spent_material_count"] == 1
    assert plan["summary"]["ready_material_count"] == 1
    assert plan["push_batches"][0]["material_ids"] == ["video-1"]
    assert plan["push_batches"][0]["video_ids"] == ["v-source-1"]


def test_push_plan_filters_summary_materials_by_account_name_keyword(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO account_pool
              (advertiser_id, account_name, product, platform, historical_spend, source, synced_at)
            VALUES
              ('dd-1', '黑旗-点点英雄-微小-郭靖-001', '点点英雄', 'WECHAT_GAME', 100, 'test', 'now'),
              ('yzt-1', '黑旗-勇者突进-微小-郭靖-001', '勇者突进', 'WECHAT_GAME', 100, 'test', 'now')
            """
        )
        conn.execute(
            """
            INSERT INTO material_bindings
              (advertiser_id, project_id, promotion_id, material_kind, material_id, video_id, image_id, title, source, synced_at)
            VALUES
              ('dd-1', 'p1', 'u1', 'video', 'dd-video', 'v-dd', '', '点点视频', 'test', 'now'),
              ('yzt-1', 'p1', 'u1', 'video', 'yzt-video', 'v-yzt', '', '勇者视频', 'test', 'now')
            """
        )
        conn.execute(
            """
            INSERT INTO material_metric_summaries
              (material_kind, material_id, video_id, title, period_start, period_end,
               promotion_count, project_count, account_count, stat_cost, active_register,
               attribution_convert_cnt, roi_1day_cost_weighted, roi_7days_cost_weighted, source, synced_at)
            VALUES
              ('video', 'dd-video', 'v-dd', '点点视频', '2026-05-12', '2026-05-12',
               1, 1, 1, 800, 0, 0, 0, 0, 'test', 'now'),
              ('video', 'yzt-video', 'v-yzt', '勇者视频', '2026-05-12', '2026-05-12',
               1, 1, 1, 900, 0, 0, 0, 0, 'test', 'now')
            """
        )

    cfg = _request()["source_material_account_auto_push"]
    cfg["product"] = "点点英雄"
    cfg["source_advertiser_id"] = "dd-source"
    cfg["material_source"]["account_name_keyword"] = "点点英雄"
    plan = build_source_material_account_push_plan(
        db_path=db_path,
        cfg=cfg,
        period_start="2026-05-12",
        period_end="2026-05-12",
    )

    assert plan["summary"]["spent_material_count"] == 1
    assert plan["push_batches"][0]["source_advertiser_id"] == "dd-1"
    assert plan["push_batches"][0]["material_ids"] == ["dd-video"]


def test_push_plan_prefers_daily_metrics_when_requested_even_if_summaries_exist(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)
    with sqlite3.connect(db_path) as conn:
        _seed_material(conn, "daily-1", name="点点素材1", video_id="v-daily-1")
        _seed_material(conn, "daily-2", name="点点素材2", video_id="v-daily-2")
        conn.execute(
            """
            INSERT INTO account_pool
              (advertiser_id, account_name, product, platform, historical_spend, source, synced_at)
            VALUES
              ('dd-1', '黑旗-点点英雄-微小-郭靖-001', '点点英雄', 'WECHAT_GAME', 100, 'test', 'now'),
              ('dd-2', '黑旗-点点英雄-微小-郭靖-002', '点点英雄', 'WECHAT_GAME', 100, 'test', 'now'),
              ('dd-summary-owner', '黑旗-点点英雄-微小-郭靖-汇总归属', '点点英雄', 'WECHAT_GAME', 100, 'test', 'now')
            """
        )
        conn.execute(
            """
            INSERT INTO account_materials
              (advertiser_id, material_id, video_id, material_type, review_status, source, synced_at)
            VALUES
              ('dd-1', 'daily-1', 'v-daily-1', 'video', 'APPROVED', 'test', 'now'),
              ('dd-2', 'daily-2', 'v-daily-2', 'video', 'APPROVED', 'test', 'now')
            """
        )
        _seed_daily(conn, "dd-1", "daily-1", cost=800)
        _seed_daily(conn, "dd-2", "daily-2", cost=700)
        conn.execute("UPDATE material_daily_metrics SET material_kind = 'unknown'")
        conn.execute(
            """
            INSERT INTO material_bindings
              (advertiser_id, project_id, promotion_id, material_kind, material_id, video_id, image_id, title, source, synced_at)
            VALUES
              ('dd-summary-owner', 'p1', 'u1', 'video', 'summary-1', 'v-summary-1', '', '点点汇总素材', 'test', 'now')
            """
        )
        conn.execute(
            """
            INSERT INTO material_metric_summaries
              (material_kind, material_id, video_id, title, period_start, period_end,
               promotion_count, project_count, account_count, stat_cost, active_register,
               attribution_convert_cnt, roi_1day_cost_weighted, roi_7days_cost_weighted, source, synced_at)
            VALUES
              ('video', 'summary-1', 'v-summary-1', '点点汇总素材', '2026-05-12', '2026-05-12',
               1, 1, 1, 900, 0, 0, 0, 0, 'test', 'now')
            """
        )

    cfg = _request()["source_material_account_auto_push"]
    cfg["product"] = "点点英雄"
    cfg["source_advertiser_id"] = "dd-source"
    cfg["material_source"]["from"] = "material_daily_metrics"
    cfg["material_source"]["account_name_keyword"] = "点点英雄"
    plan = build_source_material_account_push_plan(
        db_path=db_path,
        cfg=cfg,
        period_start="2026-05-12",
        period_end="2026-05-12",
    )

    assert plan["summary"]["spent_account_count"] == 2
    assert plan["summary"]["spent_material_count"] == 2
    assert [batch["source_advertiser_id"] for batch in plan["push_batches"]] == ["dd-1", "dd-2"]
    assert {item for batch in plan["push_batches"] for item in batch["material_ids"]} == {"daily-1", "daily-2"}


def test_material_detail_fetch_uses_top_level_material_ids(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)
    with sqlite3.connect(db_path) as conn:
        _seed_material(conn, "123456", name="勇者素材缺视频", video_id="")
        _seed_daily(conn, "1850000000000001", "123456", cost=800)

    calls = []

    def readonly_transport(request: dict) -> dict:
        calls.append(request)
        assert request["endpoint_key"] == "video_material_get"
        assert request["query_params"]["material_ids"] == "[123456]"
        assert "filtering" not in request["query_params"]
        return {
            "code": 0,
            "data": {
                "page_info": {"page": 1, "page_size": 100, "total_page": 1, "total_count": 1},
                "list": [
                    {
                        "material_id": "123456",
                        "video_id": "v-fetched",
                        "filename": "勇者素材缺视频",
                        "review_status": "APPROVED",
                    }
                ],
            },
        }

    request = _request()
    request["source_material_account_auto_push"]["material_detail_fetch"] = {"enabled": True, "page_size": 100}
    result = run_source_material_account_auto_push_request(
        request,
        db_path=db_path,
        runs_dir=tmp_path / "runs",
        readonly_transport=readonly_transport,
        today=date(2026, 5, 13),
    )

    assert result["ok"] is True
    assert len(calls) == 1
    assert result["summary"]["ready_material_count"] == 1
    assert result["summary"]["missing_video_id_count"] == 0
    assert result["plan"]["push_batches"][0]["video_ids"] == ["v-fetched"]


def test_source_material_account_auto_push_execute_uses_bind_material_batches(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)
    with sqlite3.connect(db_path) as conn:
        _seed_material(conn, "m-ready", name="勇者素材B", video_id="v-ready")
        conn.execute(
            """
            INSERT INTO account_materials
              (advertiser_id, material_id, video_id, material_type, review_status, source, synced_at)
            VALUES ('1850000000000001', 'm-ready', 'v-ready', 'video', 'APPROVED', 'test', 'now')
            """
        )
        _seed_daily(conn, "1850000000000001", "m-ready", cost=800)

    calls = []

    def mutation_transport(request: dict) -> dict:
        calls.append(request)
        return {"code": 0, "data": {"task_id": "task-1"}}

    request = _request()
    request["source_material_account_auto_push"]["execute"] = {
        "enabled": True,
        "approved": True,
        "allow_mutation": True,
    }
    result = run_source_material_account_auto_push_request(
        request,
        db_path=db_path,
        runs_dir=tmp_path / "runs",
        mutation_transport=mutation_transport,
        today=date(2026, 5, 13),
    )

    assert result["ok"] is True
    assert result["execution_enabled"] is True
    assert result["external_api_calls"] == 1
    assert result["summary"]["pushed_video_count"] == 1
    assert calls == [
        {
            "operation": "bind_material",
            "endpoint": "/open_api/2/file/material/bind/",
            "payload": {
                "advertiser_id": 1850000000000001,
                "target_advertiser_ids": [1856647522964490],
                "video_ids": ["v-ready"],
            },
        }
    ]
    assert Path(result["artifact_path"]).exists()
