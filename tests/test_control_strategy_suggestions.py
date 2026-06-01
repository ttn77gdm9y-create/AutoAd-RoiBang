import importlib.util
import sqlite3
from pathlib import Path

from roibang_v2.db.bootstrap import bootstrap_database
from roibang_v2.workflows.control_strategy_suggestions import build_control_strategy_suggestions
from roibang_v2.workflows.control_strategy_suggestions import run_control_strategy_suggestions_request


def _load_script():
    script_path = Path("scripts/run_control_strategy_suggestions.py")
    spec = importlib.util.spec_from_file_location("run_control_strategy_suggestions", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _insert_project_metric(
    conn: sqlite3.Connection,
    *,
    metric_date: str,
    advertiser_id: str,
    project_id: str,
    promotion_id: str,
    cost: float,
    conversions: float,
    roi_1day: float,
) -> None:
    conn.execute(
        """
        INSERT INTO material_daily_metrics (
          metric_date, advertiser_id, project_id, project_name,
          promotion_id, promotion_name, material_id, material_kind,
          stat_cost, show_cnt, click_cnt, convert_cnt, roi_1day,
          source, synced_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            metric_date,
            advertiser_id,
            project_id,
            f"{project_id}-name",
            promotion_id,
            f"{promotion_id}-name",
            f"{promotion_id}-material",
            "video",
            cost,
            cost * 10,
            cost,
            conversions,
            roi_1day,
            "unit_test",
            "2026-05-11T00:00:00+08:00",
        ),
    )


def _insert_project_hourly_metric(
    conn: sqlite3.Connection,
    *,
    metric_date: str,
    metric_hour: int,
    advertiser_id: str,
    project_id: str,
    cost: float,
    conversions: float,
    roi_1day: float,
    synced_at: str = "2026-05-12T11:00:00+08:00",
) -> None:
    conn.execute(
        """
        INSERT INTO project_hourly_metrics (
          metric_date, metric_hour, advertiser_id, project_id, project_name,
          stat_cost, show_cnt, click_cnt, convert_cnt, roi_1day,
          source, synced_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            metric_date,
            metric_hour,
            advertiser_id,
            project_id,
            f"{project_id}-name",
            cost,
            cost * 10,
            cost,
            conversions,
            roi_1day,
            "unit_test",
            synced_at,
        ),
    )


def _insert_operation_log(
    conn: sqlite3.Connection,
    *,
    operation_id: str,
    occurred_at: str,
    advertiser_id: str,
    entity_type: str,
    entity_id: str,
    action: str,
    detail: str = "",
) -> None:
    conn.execute(
        """
        INSERT INTO operation_logs (
          operation_id, occurred_at, advertiser_id, entity_type, entity_id,
          action, operator, detail, source, synced_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            operation_id,
            occurred_at,
            advertiser_id,
            entity_type,
            entity_id,
            action,
            "unit-test",
            detail,
            "unit_test",
            "2026-05-11T00:00:00+08:00",
        ),
    )


def _insert_account_pool(
    conn: sqlite3.Connection,
    advertiser_id: str,
    *,
    account_name: str = "黑旗-勇者突进-微小-傲星-1",
    product: str = "勇者突进",
) -> None:
    conn.execute(
        """
        INSERT INTO account_pool (
          advertiser_id, account_name, product, platform, source, synced_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            advertiser_id,
            account_name,
            product,
            "WECHAT_GAME",
            "unit_test",
            "2026-05-11T00:00:00+08:00",
        ),
    )


def _insert_project_state(
    conn: sqlite3.Connection,
    *,
    advertiser_id: str,
    project_id: str,
    name: str,
    status: str,
) -> None:
    conn.execute(
        """
        INSERT INTO projects (project_id, advertiser_id, name, status, source, synced_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (project_id, advertiser_id, name, status, "unit_test", "2026-05-11T00:00:00+08:00"),
    )


def _insert_source_material_rollup(
    conn: sqlite3.Connection,
    *,
    product: str,
    source_advertiser_id: str,
    material_id: str,
    name: str,
    project_count: int,
    promotion_count: int,
    stat_cost: float,
    roi_1day: float,
) -> None:
    conn.execute(
        """
        INSERT INTO product_source_material_metric_rollups (
          product, source_advertiser_id, organization_id, window_key, window_days,
          period_start, period_end, material_id, material_type, source_video_id,
          name, review_status, signature, duration, file_size, create_time,
          tag_ids_json, account_count, project_count, promotion_count, stat_cost,
          show_cnt, click_cnt, convert_cnt, active_register, roi_1day_cost_weighted,
          roi_7days_cost_weighted, source, synced_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            product,
            source_advertiser_id,
            "org-1",
            "last_7d",
            7,
            "2026-05-05",
            "2026-05-11",
            material_id,
            "video",
            f"video-{material_id}",
            name,
            "审核通过",
            "",
            0,
            0,
            "",
            "[]",
            4,
            project_count,
            promotion_count,
            stat_cost,
            stat_cost * 10,
            stat_cost,
            0,
            0,
            roi_1day,
            roi_1day,
            "unit_test",
            "2026-05-11T00:00:00+08:00",
        ),
    )


def test_control_strategy_suggests_pause_for_low_first_day_roi_project(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)
    with sqlite3.connect(db_path) as conn:
        _insert_account_pool(conn, "a1")
        _insert_project_metric(
            conn,
            metric_date="2026-05-11",
            advertiser_id="a1",
            project_id="project-low-roi",
            promotion_id="promotion-1",
            cost=600,
            conversions=3,
            roi_1day=0.21,
        )
        _insert_project_metric(
            conn,
            metric_date="2026-05-11",
            advertiser_id="a1",
            project_id="project-ok",
            promotion_id="promotion-2",
            cost=700,
            conversions=4,
            roi_1day=0.42,
        )

    result = build_control_strategy_suggestions(
        db_path,
        {
            "product_keyword": "勇者突进",
            "target_date": "2026-05-11",
            "rules": {
                "pause_project_low_first_day_roi": {
                    "enabled": True,
                    "min_cost": 500,
                    "min_conversions": 2,
                    "max_roi_1day": 0.25,
                }
            },
        },
    )

    assert result["ok"] is True
    assert result["workflow"] == "control_strategy_suggestions"
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 0
    assert result["summary"]["suggestion_count"] == 1
    assert result["summary"]["pause_project_suggestion_count"] == 1
    assert result["suggestions"] == [
        {
            "suggestion_type": "pause_project",
            "rule_id": "pause_project_low_first_day_roi",
            "target_date": "2026-05-11",
            "advertiser_id": "a1",
            "entity_type": "project",
            "entity_id": "project-low-roi",
            "project_id": "project-low-roi",
            "entity_name": "project-low-roi-name",
            "project_name": "project-low-roi-name",
            "reason": "首日 ROI 低于阈值且消耗/转化达到观察门槛",
            "metrics": {
                "stat_cost": 600,
                "convert_cnt": 3,
                "roi_1day": 0.21,
                "promotion_count": 1,
            },
            "thresholds": {
                "min_cost": 500,
                "min_conversions": 2,
                "max_roi_1day": 0.25,
            },
            "execution": {
                "enabled": False,
                "note": "建议文件只供复核；不会调用暂停、改预算、改时段接口。",
            },
        }
    ]


def test_pause_project_suggestion_includes_configured_historical_operation_evidence(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)
    with sqlite3.connect(db_path) as conn:
        _insert_account_pool(conn, "a1")
        _insert_project_metric(
            conn,
            metric_date="2026-05-01",
            advertiser_id="a1",
            project_id="project-history",
            promotion_id="promotion-before",
            cost=400,
            conversions=2,
            roi_1day=0.12,
        )
        _insert_operation_log(
            conn,
            operation_id="op-pause-1",
            occurred_at="2026-05-02 10:00:00",
            advertiser_id="a1",
            entity_type="project",
            entity_id="project-history",
            action="暂停项目",
            detail="状态: 开启 -> 暂停",
        )
        _insert_project_metric(
            conn,
            metric_date="2026-05-03",
            advertiser_id="a1",
            project_id="project-history",
            promotion_id="promotion-after",
            cost=40,
            conversions=1,
            roi_1day=0.30,
        )
        _insert_project_metric(
            conn,
            metric_date="2026-05-11",
            advertiser_id="a1",
            project_id="project-low-roi",
            promotion_id="promotion-target",
            cost=600,
            conversions=3,
            roi_1day=0.21,
        )

    result = build_control_strategy_suggestions(
        db_path,
        {
            "product_keyword": "勇者突进",
            "target_date": "2026-05-11",
            "operation_evidence": {
                "enabled": True,
                "window_days": 1,
                "lookback_start": "2026-02-10",
                "lookback_end": "2026-05-11",
                "sample_limit": 2,
            },
            "rules": {
                "pause_project_low_first_day_roi": {
                    "enabled": True,
                    "min_cost": 500,
                    "min_conversions": 2,
                    "max_roi_1day": 0.25,
                    "operation_action_keywords": ["暂停"],
                }
            },
        },
    )

    evidence = result["suggestions"][0]["historical_operation_evidence"]
    assert evidence["source"] == "operation_logs + material_daily_metrics"
    assert evidence["operation_count"] == 1
    assert evidence["positive_count"] == 1
    assert evidence["avg_roi_1day_delta"] == 0.18
    assert evidence["avg_stat_cost_delta"] == -360
    assert evidence["samples"][0]["operation_id"] == "op-pause-1"
    assert evidence["samples"][0]["before"]["roi_1day"] == 0.12
    assert evidence["samples"][0]["after"]["stat_cost"] == 40
    assert result["summary"]["operation_evidence_suggestion_count"] == 1


def test_pause_project_rule_uses_project_aggregated_conversions_across_metric_rows(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)
    with sqlite3.connect(db_path) as conn:
        _insert_account_pool(conn, "a1")
        _insert_project_metric(
            conn,
            metric_date="2026-05-11",
            advertiser_id="a1",
            project_id="project-aggregate-low-roi",
            promotion_id="promotion-1",
            cost=300,
            conversions=1,
            roi_1day=0.10,
        )
        _insert_project_metric(
            conn,
            metric_date="2026-05-11",
            advertiser_id="a1",
            project_id="project-aggregate-low-roi",
            promotion_id="promotion-2",
            cost=300,
            conversions=1,
            roi_1day=0.20,
        )

    result = build_control_strategy_suggestions(
        db_path,
        {
            "product_keyword": "勇者突进",
            "target_date": "2026-05-11",
            "rules": {
                "pause_project_low_first_day_roi": {
                    "enabled": True,
                    "min_cost": 500,
                    "min_conversions": 2,
                    "max_roi_1day": 0.25,
                }
            },
        },
    )

    assert result["summary"]["pause_project_suggestion_count"] == 1
    assert result["suggestions"][0]["entity_id"] == "project-aggregate-low-roi"
    assert result["suggestions"][0]["metrics"]["convert_cnt"] == 2


def test_control_strategy_suggests_budget_decrease_without_guessing_budget_amount(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)
    with sqlite3.connect(db_path) as conn:
        _insert_account_pool(conn, "a1")
        _insert_project_metric(
            conn,
            metric_date="2026-05-11",
            advertiser_id="a1",
            project_id="project-budget-down",
            promotion_id="promotion-1",
            cost=900,
            conversions=5,
            roi_1day=0.31,
        )

    result = build_control_strategy_suggestions(
        db_path,
        {
            "product_keyword": "勇者突进",
            "target_date": "2026-05-11",
            "rules": {
                "adjust_project_budget_low_roi": {
                    "enabled": True,
                    "min_cost": 800,
                    "min_conversions": 3,
                    "max_roi_1day": 0.35,
                    "budget_decrease_percent": 20,
                }
            },
        },
    )

    suggestion = result["suggestions"][0]
    assert suggestion["suggestion_type"] == "adjust_project_budget"
    assert suggestion["entity_id"] == "project-budget-down"
    assert suggestion["project_id"] == "project-budget-down"
    assert suggestion["project_name"] == "project-budget-down-name"
    assert suggestion["entity_name"] == "project-budget-down-name"
    assert suggestion["adjustment"] == {
        "field": "budget",
        "direction": "decrease",
        "decrease_percent": 20,
        "requires_current_budget_from_config": True,
        "suggested_budget": None,
    }
    assert result["summary"]["adjust_project_budget_suggestion_count"] == 1


def test_control_strategy_suggests_bid_decrease_from_configured_cpa_threshold(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)
    with sqlite3.connect(db_path) as conn:
        _insert_account_pool(conn, "a1")
        _insert_project_metric(
            conn,
            metric_date="2026-05-11",
            advertiser_id="a1",
            project_id="project-bid-down",
            promotion_id="promotion-1",
            cost=1200,
            conversions=3,
            roi_1day=0.38,
        )

    result = build_control_strategy_suggestions(
        db_path,
        {
            "product_keyword": "勇者突进",
            "target_date": "2026-05-11",
            "rules": {
                "adjust_project_bid_high_cpa": {
                    "enabled": True,
                    "min_cost": 1000,
                    "min_conversions": 2,
                    "max_cpa": 300,
                    "bid_decrease_percent": 10,
                }
            },
        },
    )

    suggestion = result["suggestions"][0]
    assert suggestion["suggestion_type"] == "adjust_project_bid"
    assert suggestion["project_id"] == "project-bid-down"
    assert suggestion["project_name"] == "project-bid-down-name"
    assert suggestion["entity_name"] == "project-bid-down-name"
    assert suggestion["metrics"]["cpa"] == 400
    assert suggestion["adjustment"] == {
        "field": "bid",
        "direction": "decrease",
        "decrease_percent": 10,
        "requires_current_bid_from_config": True,
        "suggested_bid": None,
    }
    assert result["summary"]["adjust_project_bid_suggestion_count"] == 1


def test_control_strategy_adds_delete_material_reuse_and_account_anomaly_suggestions(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    allowlist_path = tmp_path / "allowed.json"
    bootstrap_database(db_path)
    allowlist_path.write_text(
        """
        {
          "allowed_target_accounts": [
            {"advertiser_id": "allowed-account", "enable": true, "product": "勇者突进", "channel": "wx"}
          ]
        }
        """,
        encoding="utf-8",
    )
    with sqlite3.connect(db_path) as conn:
        _insert_account_pool(conn, "allowed-account", account_name="允许账户")
        _insert_account_pool(conn, "outside-account", account_name="名单外账户")
        _insert_project_state(
            conn,
            advertiser_id="allowed-account",
            project_id="closed-project",
            name="已关闭低消耗项目",
            status="PROJECT_STATUS_DISABLE",
        )
        _insert_project_metric(
            conn,
            metric_date="2026-05-10",
            advertiser_id="allowed-account",
            project_id="closed-project",
            promotion_id="promotion-1",
            cost=20,
            conversions=0,
            roi_1day=0,
        )
        _insert_project_metric(
            conn,
            metric_date="2026-05-11",
            advertiser_id="allowed-account",
            project_id="closed-project",
            promotion_id="promotion-1",
            cost=10,
            conversions=0,
            roi_1day=0,
        )
        _insert_project_metric(
            conn,
            metric_date="2026-05-11",
            advertiser_id="outside-account",
            project_id="outside-project",
            promotion_id="promotion-2",
            cost=300,
            conversions=0,
            roi_1day=0,
        )
        _insert_source_material_rollup(
            conn,
            product="勇者突进",
            source_advertiser_id="source-account",
            material_id="material-reused",
            name="高频低效素材",
            project_count=8,
            promotion_count=12,
            stat_cost=1500,
            roi_1day=0.01,
        )

    result = build_control_strategy_suggestions(
        db_path,
        {
            "product_keyword": "勇者突进",
            "target_date": "2026-05-11",
            "allowed_target_accounts_path": str(allowlist_path),
            "rules": {
                "delete_project_closed_low_recent": {
                    "enabled": True,
                    "lookback_days": 2,
                    "max_stat_cost": 100,
                    "max_convert_cnt": 0,
                },
                "material_reuse_risk": {
                    "enabled": True,
                    "window_key": "last_7d",
                    "min_project_count": 5,
                    "min_promotion_count": 10,
                    "min_stat_cost": 1000,
                    "max_roi_1day": 0.05,
                },
                "account_spent_outside_allowlist": {
                    "enabled": True,
                    "min_stat_cost": 100,
                },
            },
        },
    )

    actions = {item["suggestion_type"]: item for item in result["suggestions"]}
    assert result["summary"]["suggest_delete_project_count"] == 1
    assert result["summary"]["material_reuse_risk_count"] == 1
    assert result["summary"]["account_anomaly_count"] == 1
    assert result["summary"]["blocked_by_allowlist_count"] == 0
    assert actions["suggest_delete_project"]["entity_id"] == "closed-project"
    assert actions["suggest_delete_project"]["entity_name"] == "已关闭低消耗项目"
    assert actions["material_reuse_risk"]["entity_type"] == "material"
    assert actions["material_reuse_risk"]["entity_name"] == "高频低效素材"
    assert actions["material_reuse_risk"]["allowlist_exception"] is True
    assert actions["account_spent_outside_allowlist"]["advertiser_id"] == "outside-account"
    assert actions["account_spent_outside_allowlist"]["account_name"] == "名单外账户"
    assert actions["account_spent_outside_allowlist"]["allowlist_exception"] is True


def test_run_control_strategy_suggestions_request_writes_artifact(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)
    with sqlite3.connect(db_path) as conn:
        _insert_account_pool(conn, "a1")
        _insert_project_metric(
            conn,
            metric_date="2026-05-11",
            advertiser_id="a1",
            project_id="project-low-roi",
            promotion_id="promotion-1",
            cost=600,
            conversions=3,
            roi_1day=0.21,
        )

    result = run_control_strategy_suggestions_request(
        {
            "product_keyword": "勇者突进",
            "target_date": "2026-05-11",
            "rules": {
                "pause_project_low_first_day_roi": {
                    "enabled": True,
                    "min_cost": 500,
                    "min_conversions": 2,
                    "max_roi_1day": 0.25,
                }
            },
        },
        db_path=db_path,
        runs_dir=tmp_path / "runs",
    )

    assert result["summary"]["suggestion_count"] == 1
    assert Path(result["artifact_path"]).exists()


def test_control_strategy_blocks_suggestions_outside_allowed_account_file(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    allowlist_path = tmp_path / "allowed.json"
    bootstrap_database(db_path)
    allowlist_path.write_text(
        """
        {
          "allowed_target_accounts": [
            {"advertiser_id": "allowed-account", "enable": true, "product": "勇者突进", "channel": "wx"}
          ]
        }
        """,
        encoding="utf-8",
    )
    with sqlite3.connect(db_path) as conn:
        _insert_account_pool(conn, "blocked-account")
        _insert_project_metric(
            conn,
            metric_date="2026-05-11",
            advertiser_id="blocked-account",
            project_id="project-low-roi",
            promotion_id="promotion-1",
            cost=600,
            conversions=3,
            roi_1day=0.21,
        )

    result = build_control_strategy_suggestions(
        db_path,
        {
            "product_keyword": "勇者突进",
            "target_date": "2026-05-11",
            "allowed_target_accounts_path": str(allowlist_path),
            "rules": {
                "pause_project_low_first_day_roi": {
                    "enabled": True,
                    "min_cost": 500,
                    "min_conversions": 2,
                    "max_roi_1day": 0.25,
                }
            },
        },
    )

    assert result["summary"]["suggestion_count"] == 0
    assert result["summary"]["blocked_by_allowlist_count"] == 1
    assert result["blocked_suggestions"][0]["advertiser_id"] == "blocked-account"
    assert result["blocked_suggestions"][0]["blocked_reason"] == "target account is not in allowlist"


def test_schedule_hollow_requires_today_realtime_hourly_data(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)

    result = build_control_strategy_suggestions(
        db_path,
        {
            "product_keyword": "勇者突进",
            "target_date": "2026-05-12",
            "rules": {
                "schedule_hollow_low_realtime_hour_roi": {
                    "enabled": True,
                    "min_cost": 200,
                    "max_roi_1day": 0.2,
                    "min_fresh_synced_at": "2026-05-12T10:30:00+08:00",
                }
            },
        },
    )

    assert result["summary"]["schedule_hollow_suggestion_count"] == 0
    assert result["summary"]["realtime_hourly_data_ready"] is False
    assert "project_hourly_metrics has no realtime rows for target_date" in result["violations"]


def test_schedule_hollow_suggests_only_allowed_accounts_from_realtime_hourly_data(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    allowlist_path = tmp_path / "allowed.json"
    bootstrap_database(db_path)
    allowlist_path.write_text(
        """
        {
          "allowed_target_accounts": [
            {"advertiser_id": "allowed-account", "enable": true, "product": "勇者突进", "channel": "wx"}
          ]
        }
        """,
        encoding="utf-8",
    )
    with sqlite3.connect(db_path) as conn:
        _insert_account_pool(conn, "allowed-account")
        _insert_account_pool(conn, "blocked-account")
        _insert_project_hourly_metric(
            conn,
            metric_date="2026-05-12",
            metric_hour=13,
            advertiser_id="allowed-account",
            project_id="project-allowed-low",
            cost=260,
            conversions=1,
            roi_1day=0.12,
        )
        _insert_project_hourly_metric(
            conn,
            metric_date="2026-05-12",
            metric_hour=14,
            advertiser_id="blocked-account",
            project_id="project-blocked-low",
            cost=300,
            conversions=1,
            roi_1day=0.10,
        )

    result = build_control_strategy_suggestions(
        db_path,
        {
            "product_keyword": "勇者突进",
            "target_date": "2026-05-12",
            "allowed_target_accounts_path": str(allowlist_path),
            "rules": {
                "schedule_hollow_low_realtime_hour_roi": {
                    "enabled": True,
                    "min_cost": 200,
                    "max_roi_1day": 0.2,
                    "min_fresh_synced_at": "2026-05-12T10:30:00+08:00",
                }
            },
        },
    )

    assert result["summary"]["realtime_hourly_data_ready"] is True
    assert result["summary"]["schedule_hollow_suggestion_count"] == 1
    assert result["summary"]["blocked_by_allowlist_count"] == 1
    assert result["suggestions"][0]["suggestion_type"] == "schedule_hollow"
    assert result["suggestions"][0]["advertiser_id"] == "allowed-account"
    assert result["suggestions"][0]["entity_id"] == "project-allowed-low"
    assert result["suggestions"][0]["hollow_hours"] == [13]
    assert result["suggestions"][0]["restore"] == {
        "required": True,
        "restore_date": "2026-05-13",
        "reason": "当天临时拉空时段，第二天必须恢复原始时段，避免长期影响投放节奏。",
    }
    assert result["blocked_suggestions"][0]["advertiser_id"] == "blocked-account"


def test_control_strategy_suggestions_cli_prints_summary(tmp_path: Path, capsys):
    db_path = tmp_path / "roibang.sqlite3"
    runs_dir = tmp_path / "runs"
    request_path = tmp_path / "request.json"
    bootstrap_database(db_path)
    with sqlite3.connect(db_path) as conn:
        _insert_account_pool(conn, "a1")
        _insert_project_metric(
            conn,
            metric_date="2026-05-11",
            advertiser_id="a1",
            project_id="project-low-roi",
            promotion_id="promotion-1",
            cost=600,
            conversions=3,
            roi_1day=0.21,
        )
    request_path.write_text(
        """
        {
          "control_strategy_suggestions": {
            "product_keyword": "勇者突进",
            "target_date": "2026-05-11",
            "rules": {
              "pause_project_low_first_day_roi": {
                "enabled": true,
                "min_cost": 500,
                "min_conversions": 2,
                "max_roi_1day": 0.25
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )
    module = _load_script()

    exit_code = module.run_from_args(
        [
            "--config",
            "configs/runtime.example.json",
            "--request",
            str(request_path),
            "--db",
            str(db_path),
            "--runs-dir",
            str(runs_dir),
        ]
    )

    output = __import__("json").loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["workflow"] == "control_strategy_suggestions"
    assert output["external_api_calls"] == 0
    assert output["summary"]["suggestion_count"] == 1
    assert Path(output["artifact_path"]).exists()
