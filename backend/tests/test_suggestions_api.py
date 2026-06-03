import json
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.main import create_app
from roibang_v2.db.bootstrap import bootstrap_database


def _client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(project_root=tmp_path))


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _init_backtest_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE material_daily_metrics (
          metric_date TEXT NOT NULL,
          advertiser_id TEXT NOT NULL,
          project_id TEXT NOT NULL DEFAULT '',
          project_name TEXT NOT NULL DEFAULT '',
          promotion_id TEXT NOT NULL DEFAULT '',
          promotion_name TEXT NOT NULL DEFAULT '',
          material_id TEXT NOT NULL,
          material_kind TEXT NOT NULL DEFAULT 'video',
          stat_cost REAL NOT NULL DEFAULT 0,
          show_cnt REAL NOT NULL DEFAULT 0,
          click_cnt REAL NOT NULL DEFAULT 0,
          convert_cnt REAL NOT NULL DEFAULT 0,
          active_register REAL NOT NULL DEFAULT 0,
          roi_1day REAL NOT NULL DEFAULT 0,
          roi_7days REAL NOT NULL DEFAULT 0,
          metric_payload_json TEXT NOT NULL DEFAULT '{}',
          source TEXT NOT NULL,
          synced_at TEXT NOT NULL,
          PRIMARY KEY (metric_date, advertiser_id, project_id, promotion_id, material_id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE operation_logs (
          operation_id TEXT PRIMARY KEY,
          occurred_at TEXT NOT NULL,
          advertiser_id TEXT NOT NULL DEFAULT '',
          entity_type TEXT NOT NULL,
          entity_id TEXT NOT NULL,
          action TEXT NOT NULL,
          operator TEXT NOT NULL DEFAULT '',
          detail TEXT NOT NULL DEFAULT '',
          before_json TEXT NOT NULL DEFAULT '{}',
          after_json TEXT NOT NULL DEFAULT '{}',
          payload_json TEXT NOT NULL DEFAULT '{}',
          source TEXT NOT NULL,
          synced_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def _insert_backtest_metric(
    db_path: Path,
    *,
    date: str,
    advertiser_id: str,
    project_id: str,
    cost: float,
    convert: float,
    roi: float = 0,
) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        INSERT INTO material_daily_metrics (
          metric_date, advertiser_id, project_id, project_name, promotion_id, promotion_name,
          material_id, material_kind, stat_cost, convert_cnt, roi_1day, source, synced_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            date,
            advertiser_id,
            project_id,
            f"项目-{project_id}",
            "unit-1",
            "单元",
            f"material-{project_id}",
            "video",
            cost,
            convert,
            roi,
            "test",
            "now",
        ),
    )
    conn.commit()
    conn.close()


def _insert_backtest_operation(db_path: Path, *, advertiser_id: str, project_id: str, detail: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        INSERT INTO operation_logs (
          operation_id, occurred_at, advertiser_id, entity_type, entity_id, action, detail, source, synced_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (f"op-{advertiser_id}-{project_id}", "2026-05-29 10:00:00", advertiser_id, "project", project_id, "修改", detail, "test", "now"),
    )
    conn.commit()
    conn.close()


def _write_suggestion_fixture(tmp_path: Path) -> Path:
    _write_json(
        tmp_path / "configs" / "accounts" / "product-accounts.local.json",
        {
            "accounts": [
                {
                    "product_key": "demo-game",
                    "product_name": "演示游戏",
                    "advertiser_id": "1001",
                    "advertiser_name": "演示账户一",
                    "channel": "微信",
                    "owner": "运营A",
                    "account_remark": "演示游戏-微小",
                    "status": "active",
                    "notes": "",
                },
                {
                    "product_key": "demo-game",
                    "product_name": "演示游戏",
                    "advertiser_id": "1002",
                    "advertiser_name": "演示账户二",
                    "channel": "微信",
                    "owner": "运营A",
                    "account_remark": "演示游戏-微小",
                    "status": "active",
                    "notes": "",
                },
            ]
        },
    )
    _write_json(
        tmp_path / "configs" / "allowed-create-accounts.demo-game.local.json",
        {
            "product": "演示游戏",
            "product_key": "demo-game",
            "allowed_target_accounts": [
                {"advertiser_id": "1001", "account_name": "演示账户一", "enable": True},
                {"advertiser_id": "1002", "account_name": "演示账户二", "enable": False},
            ],
        },
    )
    _write_json(
        tmp_path / "configs" / "products" / "demo-game.local.json",
        {
            "product_key": "demo-game",
            "product": "演示游戏",
            "platform": "WECHAT_GAME",
            "source_advertiser_id": "source-1",
            "source_advertiser_name": "演示源素材账户",
            "organization_id": "org-1",
            "allowed_target_accounts_path": "configs/allowed-create-accounts.demo-game.local.json",
            "automation": {
                "enabled": True,
                "account_discovery": {
                    "account_name_keyword": "演示游戏",
                    "account_remark_equals": "演示游戏-微小",
                },
                "material_daily_sync": {"enabled": True},
                "operation_log_sync": {"enabled": True},
                "daily_report_sync": {"enabled": True},
                "source_material_rollup": {"enabled": True},
                "delivery_patrol": {"enabled": True},
            },
        },
    )
    suggestions_path = tmp_path / "data" / "runs" / "delivery_patrol_suggestions" / "20260528T100001Z.json"
    _write_json(
        suggestions_path,
        {
            "workflow": "delivery_patrol_suggestions",
            "summary": {"target_date": "2026-05-28", "suggestion_count": 3},
            "suggestions": [
                {
                    "suggestion_id": "delete-1",
                    "suggested_action": "suggest_delete_project",
                    "suggestion_type": "suggest_delete_project",
                    "rule_id": "project_delete_inactive_closed",
                    "target_date": "2026-05-28",
                    "advertiser_id": "1001",
                    "entity_type": "project",
                    "project_id": "p-delete",
                    "entity_name": "演示游戏-旧项目",
                    "status": "PROJECT_STATUS_DISABLE",
                    "reason": "项目已关闭且两天无计费时间转化，建议删除。",
                    "metrics": {"stat_cost": 0, "billing_convert_cnt": 0},
                },
                {
                    "suggestion_id": "close-1",
                    "suggested_action": "suggest_close_project",
                    "suggestion_type": "suggest_close_project",
                    "rule_id": "project_close_zero_convert",
                    "target_date": "2026-05-28",
                    "advertiser_id": "1002",
                    "entity_type": "project",
                    "project_id": "p-close",
                    "entity_name": "演示游戏-关闭候选",
                    "reason": "累计消耗达到阈值但计费时间转化为 0，建议暂停项目。",
                },
                {
                    "suggestion_id": "watch-1",
                    "suggested_action": "watch",
                    "suggestion_type": "watch",
                    "target_date": "2026-05-28",
                    "advertiser_id": "1001",
                    "entity_type": "project",
                    "project_id": "p-watch",
                    "entity_name": "演示游戏-观察候选",
                    "reason": "项目已有消耗但未达到强动作阈值，建议观察。",
                },
            ],
        },
    )
    _write_json(
        tmp_path / "data" / "runs" / "product_automation_job_material_daily_sync" / "20260528T080000Z.json",
        {"workflow": "product_automation_job_material_daily_sync", "summary": {"job": "material_daily_sync", "product_count": 1}},
    )
    _write_json(
        tmp_path / "data" / "runs" / "product_automation_job_daily_report_sync" / "20260528T080001Z.json",
        {"workflow": "product_automation_job_daily_report_sync", "summary": {"job": "daily_report_sync", "product_count": 1}},
    )
    _write_json(
        tmp_path / "data" / "runs" / "product_automation_job_operation_log_sync" / "20260528T080002Z.json",
        {"workflow": "product_automation_job_operation_log_sync", "summary": {"job": "operation_log_sync", "product_count": 1}},
    )
    _write_json(
        tmp_path / "data" / "runs" / "product_automation_job_source_material_rollup" / "20260528T080003Z.json",
        {"workflow": "product_automation_job_source_material_rollup", "summary": {"job": "source_material_rollup", "product_count": 1}},
    )
    patrol_artifact = tmp_path / "data" / "runs" / "delivery_patrol" / "20260529T000000Z-demo-game.json"
    _write_json(
        patrol_artifact,
        {
            "workflow": "delivery_patrol",
            "summary": {"target_date": "2026-05-29", "account_count": 2},
            "accounts": [
                {
                    "advertiser_id": "1001",
                    "account_name": "演示账户一",
                    "metrics": {"today": {"stat_cost": 300}},
                },
                {
                    "advertiser_id": "1002",
                    "account_name": "演示账户二",
                    "metrics": {"today": {"stat_cost": 200}},
                },
            ],
        },
    )
    _write_json(
        tmp_path / "data" / "runs" / "product_automation_job_delivery_patrol" / "20260529T000001Z.json",
        {
            "workflow": "product_automation_job_delivery_patrol",
            "summary": {"job": "delivery_patrol", "product_count": 1, "target_date": "today"},
            "results": [
                {
                    "product_key": "demo-game",
                    "product": "演示游戏",
                    "ok": True,
                    "parsed_stdout": {
                        "workflow": "delivery_patrol",
                        "summary": {"target_date": "2026-05-29", "account_count": 2},
                        "artifact_path": str(patrol_artifact),
                    },
                }
            ],
        },
    )
    return suggestions_path


def _write_local_db_suggestions_fixture(tmp_path: Path) -> None:
    db_path = tmp_path / "data" / "roibang_v2.sqlite3"
    bootstrap_database(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO account_pool (advertiser_id, account_name, product, platform, source, synced_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("1001", "演示账户一", "演示游戏", "WECHAT_GAME", "unit_test", "2026-05-28T00:00:00+08:00"),
        )
        conn.execute(
            """
            INSERT INTO account_pool (advertiser_id, account_name, product, platform, source, synced_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("1003", "名单外账户", "演示游戏", "WECHAT_GAME", "unit_test", "2026-05-28T00:00:00+08:00"),
        )
        conn.execute(
            """
            INSERT INTO projects (project_id, advertiser_id, name, status, source, synced_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("p-local-delete", "1001", "演示游戏-本地关闭项目", "PROJECT_STATUS_DISABLE", "unit_test", "2026-05-28T00:00:00+08:00"),
        )
        metric_rows = [
            ("2026-05-27", "1001", "p-local-delete", "演示游戏-本地关闭项目", "unit-1", "m-delete", 20, 0, 0),
            ("2026-05-28", "1001", "p-local-delete", "演示游戏-本地关闭项目", "unit-1", "m-delete", 10, 0, 0),
            ("2026-05-28", "1001", "p-local-action", "演示游戏-本地动作项目", "unit-action", "m-action", 1200, 3, 0.2),
            ("2026-05-28", "1003", "p-outside", "演示游戏-名单外项目", "unit-2", "m-outside", 300, 0, 0),
        ]
        for row in metric_rows:
            conn.execute(
                """
                INSERT INTO material_daily_metrics (
                  metric_date, advertiser_id, project_id, project_name, promotion_id, promotion_name,
                  material_id, material_kind, stat_cost, convert_cnt, roi_1day, source, synced_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (row[0], row[1], row[2], row[3], row[4], "单元", row[5], "video", row[6], row[7], row[8], "unit_test", "now"),
            )
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
                "演示游戏",
                "source-1",
                "org-1",
                "last_7d",
                7,
                "2026-05-22",
                "2026-05-28",
                "material-risk-1",
                "video",
                "video-risk-1",
                "高频低效素材",
                "审核通过",
                "",
                0,
                0,
                "",
                "[]",
                4,
                8,
                12,
                1500,
                15000,
                1500,
                0,
                0,
                0.01,
                0.01,
                "unit_test",
                "now",
            ),
        )


def _write_learned_control_strategy_fixture(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "configs" / "learned-strategies" / "demo-game.learned.local.json",
        {
            "workflow": "strategy_learning",
            "runtime_contract": {
                "strategy_source": "learned_strategy_only",
                "runtime_metric_source": "realtime_patrol_snapshot",
                "historical_data_usage": "learning_and_evidence_only",
                "allow_builtin_default_project_actions": False,
                "execution_enabled": False,
            },
            "strategies": [
                {
                    "strategy_id": "approved-delete-low-recent",
                    "strategy_version": "2026-06-01",
                    "status": "approved",
                    "enabled": True,
                    "action": "suggest_delete_project",
                    "action_label": "删除项目",
                    "scope": {"type": "product", "product_key": "demo-game", "product": "演示游戏"},
                    "sample_counts": {"total": 120, "product": 20, "with_pre_metrics": 18},
                    "second_stage_learning": {
                        "backtest": {"status": "passed", "positive_outcome_rate": 0.75}
                    },
                    "中文摘要": "演示游戏删除项目策略已人工批准，仅处理已关闭低消耗无转化项目。",
                    "control_strategy_rule": {
                        "rule_id": "delete_project_closed_low_recent",
                        "parameters": {"lookback_days": 2, "max_stat_cost": 100, "max_convert_cnt": 0},
                    },
                },
                {
                    "strategy_id": "approved-pause-low-roi",
                    "strategy_version": "2026-06-01",
                    "status": "approved",
                    "enabled": True,
                    "action": "pause_project",
                    "action_label": "暂停项目",
                    "scope": {"type": "product", "product_key": "demo-game", "product": "演示游戏"},
                    "sample_counts": {"total": 100, "product": 12, "with_pre_metrics": 10},
                    "second_stage_learning": {
                        "backtest": {"status": "passed", "positive_outcome_rate": 0.6}
                    },
                    "中文摘要": "演示游戏暂停项目策略已人工批准，仅处理实时低 ROI 且达到消耗转化门槛项目。",
                    "control_strategy_rule": {
                        "rule_id": "pause_project_low_first_day_roi",
                        "parameters": {"min_cost": 500, "min_conversions": 2, "max_roi_1day": 0.25},
                    },
                },
                {
                    "strategy_id": "approved-budget-low-roi",
                    "strategy_version": "2026-06-01",
                    "status": "approved",
                    "enabled": True,
                    "action": "suggest_lower_budget",
                    "action_label": "下调预算",
                    "scope": {"type": "product", "product_key": "demo-game", "product": "演示游戏"},
                    "sample_counts": {"total": 40, "product": 8, "with_pre_metrics": 8},
                    "second_stage_learning": {
                        "backtest": {"status": "passed", "positive_outcome_rate": 0.55}
                    },
                    "中文摘要": "演示游戏调预算策略已人工批准。",
                    "control_strategy_rule": {
                        "rule_id": "adjust_project_budget_low_roi",
                        "parameters": {
                            "min_cost": 800,
                            "min_conversions": 3,
                            "max_roi_1day": 0.35,
                            "budget_decrease_percent": 20,
                        },
                    },
                },
                {
                    "strategy_id": "approved-bid-high-cpa",
                    "strategy_version": "2026-06-01",
                    "status": "approved",
                    "enabled": True,
                    "action": "suggest_lower_bid",
                    "action_label": "下调出价",
                    "scope": {"type": "product", "product_key": "demo-game", "product": "演示游戏"},
                    "sample_counts": {"total": 45, "product": 9, "with_pre_metrics": 9},
                    "second_stage_learning": {
                        "backtest": {"status": "passed", "positive_outcome_rate": 0.65}
                    },
                    "中文摘要": "演示游戏调出价策略已人工批准。",
                    "control_strategy_rule": {
                        "rule_id": "adjust_project_bid_high_cpa",
                        "parameters": {"min_cost": 1000, "min_conversions": 2, "max_cpa": 300, "bid_decrease_percent": 10},
                    },
                },
                {
                    "strategy_id": "candidate-bid-passed",
                    "strategy_version": "2026-06-01",
                    "status": "candidate_passed_backtest",
                    "enabled": False,
                    "action": "suggest_lower_bid",
                    "action_label": "下调出价",
                    "scope": {"type": "product", "product_key": "demo-game", "product": "演示游戏"},
                    "sample_counts": {"total": 50, "product": 10, "with_pre_metrics": 10},
                    "second_stage_learning": {
                        "backtest": {"status": "passed", "positive_outcome_rate": 0.7}
                    },
                    "中文摘要": "该候选策略回测通过，但尚未人工启用。",
                    "control_strategy_rule": {
                        "rule_id": "adjust_project_bid_high_cpa",
                        "parameters": {"min_cost": 900, "min_conversions": 2, "max_cpa": 320, "bid_decrease_percent": 8},
                    },
                },
                {
                    "strategy_id": "blocked-pause-mixed",
                    "strategy_version": "2026-06-01",
                    "status": "blocked_mixed_high_risk_samples",
                    "enabled": False,
                    "action": "pause_project",
                    "action_label": "暂停项目",
                    "scope": {"type": "product", "product_key": "demo-game", "product": "演示游戏"},
                    "sample_counts": {"total": 90, "product": 11, "with_pre_metrics": 11},
                    "blocking_reasons": ["高风险动作样本中有转化项目，不能自动推导为暂停规则。"],
                    "中文摘要": "暂停候选被高风险样本混杂阻断。",
                },
            ],
        },
    )


def _write_create_project_strategy_fixture(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "configs" / "create-templates" / "demo-game.local.json",
        {
            "product": "演示游戏",
            "product_key": "demo-game",
            "platform": "WECHAT_GAME",
            "templates": {"wx_pay_general": {"project_template_name": "演示游戏 每付通投"}},
        },
    )
    _write_json(
        tmp_path / "configs" / "create-modes" / "demo-game" / "wx_pay_general_recent_scale.local.json",
        {
            "mode_key": "wx_pay_general_recent_scale",
            "display_name": "演示游戏 每付通投近期放量",
            "product_key": "demo-game",
            "product": "演示游戏",
            "template_key": "wx_pay_general",
            "defaults": {"daily_budget": 88888, "project_count": 5, "units_per_project": 1},
        },
    )
    _write_json(
        tmp_path / "configs" / "create-suggestion-strategies" / "demo-game.local.json",
        {
            "strategy_id": "recent-scale-capacity-v1",
            "strategy_version": "2026-05-31",
            "enabled": True,
            "product_key": "demo-game",
            "mode_key": "wx_pay_general_recent_scale",
            "account": {"require_allowed_account": True, "max_active_projects": 5, "cooldown_days_after_create": 0},
            "materials": {
                "window_key": "last_7d",
                "material_type": "video",
                "min_qualified_material_count": 1,
                "min_stat_cost": 1000,
                "min_convert_cnt": 0,
                "min_roi_1day": 0,
            },
            "recommendation": {"project_count": 1, "units_per_project": 1, "daily_budget": 88888},
        },
    )


def _write_create_suggestion_execution_lifecycle(tmp_path: Path, suggestion_id: str) -> None:
    review_path = tmp_path / "data" / "runs" / "create_plan_execution_review" / "review.json"
    _write_json(
        tmp_path / "data" / "runs" / "create_plan_from_suggestions" / "preview.json",
        {
            "workflow": "create_plan_from_suggestions",
            "status": "preview_only",
            "generated_at": "2026-05-31T01:00:00+00:00",
            "source": {"source_suggestion_ids": [suggestion_id]},
            "source_suggestions": [{"suggestion_id": suggestion_id}],
        },
    )
    _write_json(
        review_path,
        {
            "workflow": "create_plan_execution_review",
            "status": "warning_only",
            "generated_at": "2026-05-31T02:00:00+00:00",
            "operation_record": {
                "plan_id": "plan-1",
                "plan_path": "data/runs/create_mode/plan-1.json",
                "source_suggestion_ids": [suggestion_id],
                "source_strategy_ids": ["recent-scale-capacity-v1"],
            },
            "warnings": ["唯一素材数较少"],
        },
    )
    _write_json(
        tmp_path / "data" / "runs" / "frontend_operation_log" / "execute.json",
        {
            "workflow": "frontend_operation_log",
            "operation_type": "create_live_execute",
            "status": "queued",
            "task_id": "task-create-1",
            "created_at": "2026-05-31T03:00:00+00:00",
            "request": {"execution_review_artifact_path": str(review_path)},
            "result": {"plan_id": "plan-1"},
            "details": {"plan_id": "plan-1"},
        },
    )


def _write_completed_create_suggestion_lifecycle(tmp_path: Path, *, suggestion_id: str, advertiser_id: str, project_id: str) -> None:
    review_path = tmp_path / "data" / "runs" / "create_plan_execution_review" / "review-completed.json"
    _write_json(
        tmp_path / "data" / "runs" / "create_plan_from_suggestions" / "preview-completed.json",
        {
            "workflow": "create_plan_from_suggestions",
            "status": "preview_only",
            "generated_at": "2026-05-28T01:00:00+00:00",
            "source": {"source_suggestion_ids": [suggestion_id]},
            "source_suggestions": [{"suggestion_id": suggestion_id}],
        },
    )
    _write_json(
        review_path,
        {
            "workflow": "create_plan_execution_review",
            "status": "warning_only",
            "generated_at": "2026-05-28T02:00:00+00:00",
            "operation_record": {
                "plan_id": "plan-create-completed",
                "plan_path": "data/runs/create_mode/plan-create-completed.json",
                "source_suggestion_ids": [suggestion_id],
                "source_strategy_ids": ["recent-scale-capacity-v1"],
            },
            "warnings": ["唯一素材数较少"],
        },
    )
    _write_json(
        tmp_path / "data" / "runs" / "create_live_execute_once" / "execute-completed.json",
        {
            "workflow": "create_live_execute_once",
            "status": "create_http_completed",
            "generated_at": "2026-05-28T03:00:00+00:00",
            "summary": {"plan_id": "plan-create-completed"},
        },
    )
    with sqlite3.connect(tmp_path / "data" / "roibang_v2.sqlite3") as conn:
        conn.execute(
            """
            INSERT INTO create_provider_id_ledger (
              entity_type, local_key, provider_id, plan_id, request_id, advertiser_id,
              parent_local_key, status, source_workflow, execution_enabled,
              response_payload_json, first_seen_at, last_seen_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "project",
                "target-1-p001",
                project_id,
                "plan-create-completed",
                "request-1",
                advertiser_id,
                "",
                "active",
                "create_live_execute_once",
                1,
                "{}",
                "2026-05-28T03:00:00+00:00",
                "2026-05-28T03:00:00+00:00",
            ),
        )


def test_suggestions_overview_uses_product_config_and_core_data_sources(tmp_path: Path):
    _write_suggestion_fixture(tmp_path)
    client = _client(tmp_path)

    response = client.get("/api/suggestions/overview", params={"product_key": "demo-game"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "投放建议工作台"
    assert payload["summary"]["execution_enabled"] is False
    assert {"label": "产品数", "value": 1} in payload["summary"]["items"]
    assert {"label": "建议事项", "value": 3} in payload["summary"]["items"]
    assert payload["table"]["columns"] == [
        "产品",
        "产品 Key",
        "允许创建账户",
        "产品账户库账户",
        "建议事项",
        "可生成管理配置",
        "最近建议来源",
    ]
    row = payload["table"]["rows"][0]
    assert row["产品"] == "演示游戏"
    assert row["允许创建账户"] == 1
    assert row["产品账户库账户"] == 2
    assert row["建议事项"] == 3
    assert row["可生成管理配置"] == 2
    assert "delivery_patrol_suggestions" in row["最近建议来源"]
    section_titles = [section["title"] for section in payload["sections"]]
    assert "产品数据源" in section_titles
    source_rows = payload["sections"][0]["table"]["rows"]
    assert any(
        row["数据源"] == "每日素材明细同步"
        and row["workflow"] == "product_automation_job_material_daily_sync"
        and row["状态"] == "已找到"
        for row in source_rows
    )
    assert any(
        row["数据源"] == "操作日志同步"
        and row["workflow"] == "product_automation_job_operation_log_sync"
        and row["状态"] == "已找到"
        for row in source_rows
    )
    assert any(
        row["数据源"] == "源素材表现汇总"
        and row["workflow"] == "product_automation_job_source_material_rollup"
        and row["状态"] == "已找到"
        for row in source_rows
    )


def test_suggestions_list_returns_chinese_rows_with_account_names_and_action_json_hint(tmp_path: Path):
    suggestions_path = _write_suggestion_fixture(tmp_path)
    client = _client(tmp_path)

    response = client.get("/api/suggestions", params={"product_key": "demo-game"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "建议列表"
    assert {"label": "建议事项", "value": 3} in payload["summary"]["items"]
    assert {"label": "可生成管理配置", "value": 2} in payload["summary"]["items"]
    assert payload["table"]["columns"][0] == "建议内容"
    rows = payload["table"]["rows"]
    assert rows[0]["建议 ID"] == "delete-1"
    assert rows[0]["建议内容"].startswith("删除项目｜演示游戏")
    assert rows[0]["建议类型"] == "项目管理建议"
    assert rows[0]["下一步"] == "生成项目管理配置"
    assert rows[0]["产品"] == "演示游戏"
    assert rows[0]["账户 ID"] == "1001"
    assert rows[0]["账户名"] == "演示账户一"
    assert rows[0]["建议动作"] == "删除项目"
    assert rows[0]["可转动作 JSON"] == "可生成项目删除配置"
    assert rows[0]["来源文件"] == str(suggestions_path)
    assert rows[1]["账户 ID"] == "1002"
    assert rows[1]["账户名"] == "演示账户二"
    assert rows[1]["建议动作"] == "暂停项目"
    assert rows[2]["建议动作"] == "观察"
    assert rows[2]["可转动作 JSON"] == "观察建议，不生成动作配置"


def test_suggestions_list_uses_guojing_realtime_scope_not_product_all_scope(tmp_path: Path):
    _write_json(
        tmp_path / "configs" / "accounts" / "product-accounts.local.json",
        {
            "accounts": [
                {
                    "product_key": "diandian-hero",
                    "product_name": "点点英雄",
                    "advertiser_id": "guojing-1",
                    "advertiser_name": "黑旗-点点英雄-微小-郭靖-1",
                    "status": "active",
                },
                {
                    "product_key": "diandian-hero",
                    "product_name": "点点英雄",
                    "advertiser_id": "other-hero-1",
                    "advertiser_name": "黑旗-点点英雄-微小-杨过-1",
                    "status": "active",
                },
            ]
        },
    )
    _write_json(
        tmp_path / "configs" / "products" / "diandian-hero.local.json",
        {
            "product_key": "diandian-hero",
            "product": "点点英雄",
            "automation": {
                "enabled": True,
                "delivery_patrol": {
                    "enabled": True,
                    "account_scopes": [
                        {
                            "scope_id": "diandian-hero-guojing",
                            "title": "点点英雄-微小-郭靖",
                            "account_remark_equals": "点点英雄-微小-郭靖",
                        },
                        {
                            "scope_id": "diandian-hero-all",
                            "title": "点点英雄全量账户",
                            "account_name_contains": "点点英雄",
                        },
                    ],
                },
            },
        },
    )
    guojing_suggestions = tmp_path / "data" / "runs" / "delivery_patrol_suggestions" / "20260530T220001Z-guojing.json"
    all_suggestions = tmp_path / "data" / "runs" / "delivery_patrol_suggestions" / "20260530T230001Z-all.json"
    _write_json(
        guojing_suggestions,
        {
            "workflow": "delivery_patrol_suggestions",
            "summary": {"target_date": "2026-05-30", "suggestion_count": 1},
            "suggestions": [
                {
                    "suggestion_id": "guojing-close",
                    "suggested_action": "suggest_close_project",
                    "suggestion_type": "suggest_close_project",
                    "target_date": "2026-05-30",
                    "advertiser_id": "guojing-1",
                    "account_name": "黑旗-点点英雄-微小-郭靖-1",
                    "entity_type": "project",
                    "project_id": "p-guojing",
                    "entity_name": "郭靖低效项目",
                    "reason": "郭靖账户实时低效，建议暂停。",
                }
            ],
        },
    )
    _write_json(
        all_suggestions,
        {
            "workflow": "delivery_patrol_suggestions",
            "summary": {"target_date": "2026-05-30", "suggestion_count": 1},
            "suggestions": [
                {
                    "suggestion_id": "other-close",
                    "suggested_action": "suggest_close_project",
                    "suggestion_type": "suggest_close_project",
                    "target_date": "2026-05-30",
                    "advertiser_id": "other-hero-1",
                    "account_name": "黑旗-点点英雄-微小-杨过-1",
                    "entity_type": "project",
                    "project_id": "p-other",
                    "entity_name": "非郭靖低效项目",
                    "reason": "非郭靖账户建议不应进入建议列表。",
                }
            ],
        },
    )
    _write_json(
        tmp_path / "data" / "runs" / "delivery_patrol" / "20260530T220000Z-guojing.json",
        {
            "workflow": "delivery_patrol",
            "summary": {
                "target_date": "2026-05-30",
                "account_scope": {"account_remark_equals": "点点英雄-微小-郭靖"},
                "suggestion_artifact_path": str(guojing_suggestions),
            },
            "accounts": [
                {
                    "advertiser_id": "guojing-1",
                    "account_name": "黑旗-点点英雄-微小-郭靖-1",
                    "metrics": {"today": {"stat_cost": 100}},
                }
            ],
            "projects": [],
            "promotions": [],
        },
    )
    _write_json(
        tmp_path / "data" / "runs" / "delivery_patrol" / "20260530T230000Z-all.json",
        {
            "workflow": "delivery_patrol",
            "summary": {
                "target_date": "2026-05-30",
                "account_scope": {"account_name_contains": "点点英雄"},
                "suggestion_artifact_path": str(all_suggestions),
            },
            "accounts": [
                {
                    "advertiser_id": "other-hero-1",
                    "account_name": "黑旗-点点英雄-微小-杨过-1",
                    "metrics": {"today": {"stat_cost": 200}},
                }
            ],
            "projects": [],
            "promotions": [],
        },
    )
    client = _client(tmp_path)

    response = client.get("/api/suggestions", params={"product_key": "diandian-hero"})

    assert response.status_code == 200
    payload = response.json()
    rows = payload["table"]["rows"]
    assert [row["建议 ID"] for row in rows] == ["guojing-close"]
    assert rows[0]["账户 ID"] == "guojing-1"
    assert rows[0]["账户名"] == "黑旗-点点英雄-微小-郭靖-1"
    assert payload["artifact_path"] == str(guojing_suggestions)


def test_project_update_preview_blocks_suggestions_outside_guojing_realtime_scope(tmp_path: Path):
    _write_json(
        tmp_path / "configs" / "products" / "diandian-hero.local.json",
        {
            "product_key": "diandian-hero",
            "product": "点点英雄",
            "automation": {
                "enabled": True,
                "delivery_patrol": {
                    "enabled": True,
                    "account_scopes": [
                        {
                            "scope_id": "diandian-hero-guojing",
                            "title": "点点英雄-微小-郭靖",
                            "account_remark_equals": "点点英雄-微小-郭靖",
                        }
                    ],
                },
            },
        },
    )
    _write_json(
        tmp_path / "data" / "runs" / "delivery_patrol" / "20260530T220000Z-guojing.json",
        {
            "workflow": "delivery_patrol",
            "summary": {"target_date": "2026-05-30", "account_scope": {"account_remark_equals": "点点英雄-微小-郭靖"}},
            "accounts": [
                {
                    "advertiser_id": "guojing-1",
                    "account_name": "黑旗-点点英雄-微小-郭靖-1",
                    "metrics": {"today": {"stat_cost": 100}},
                }
            ],
            "projects": [],
            "promotions": [],
        },
    )
    suggestions_path = tmp_path / "data" / "runs" / "rule_suggestions" / "outside-guojing.json"
    _write_json(
        suggestions_path,
        {
            "workflow": "rule_suggestions",
            "summary": {"target_date": "2026-05-30", "suggestion_count": 1},
            "suggestions": [
                {
                    "suggestion_id": "other-close",
                    "suggested_action": "suggest_close_project",
                    "suggestion_type": "suggest_close_project",
                    "target_date": "2026-05-30",
                    "product_key": "diandian-hero",
                    "product_name": "点点英雄",
                    "advertiser_id": "other-hero-1",
                    "account_name": "黑旗-点点英雄-微小-杨过-1",
                    "entity_type": "project",
                    "project_id": "p-other",
                    "entity_name": "非郭靖项目",
                    "reason": "非郭靖账户不应生成项目管理配置。",
                }
            ],
        },
    )
    client = _client(tmp_path)

    response = client.post(
        "/api/suggestions/project-update/preview",
        json={
            "suggestions_artifact_path": str(suggestions_path),
            "selected_suggestion_ids": ["other-close"],
            "product_key": "diandian-hero",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["status"] == "blocked"
    assert "不属于当前建议实时范围" in "；".join(payload["summary"]["blocking_reasons"])


def test_suggestions_list_includes_readonly_create_project_suggestions(tmp_path: Path):
    _write_suggestion_fixture(tmp_path)
    _write_local_db_suggestions_fixture(tmp_path)
    _write_create_project_strategy_fixture(tmp_path)
    client = _client(tmp_path)

    response = client.get("/api/suggestions", params={"product_key": "demo-game"})

    assert response.status_code == 200
    payload = response.json()
    rows = payload["table"]["rows"]
    create_row = next(row for row in rows if row["建议动作"] == "建议创建项目")
    assert create_row["账户 ID"] == "1001"
    assert create_row["账户名"] == "演示账户一"
    assert create_row["推荐模式"] == "wx_pay_general_recent_scale"
    assert create_row["命中策略"] == "recent-scale-capacity-v1"
    assert create_row["数据来源"] == "本地创建策略"
    assert create_row["建议类型"] == "扩量机会"
    assert create_row["下一步"] == "生成创建项目计划"
    assert create_row["可生成管理配置"] == "创建机会，进入创建计划，不生成项目管理配置"
    assert "合格素材 1" in create_row["关键指标"]

    preview_response = client.post(
        "/api/suggestions/project-update/preview",
        json={
            "suggestions_artifact_path": payload["artifact_path"],
            "selected_suggestion_ids": [create_row["建议 ID"]],
            "product_key": "demo-game",
        },
    )

    assert preview_response.status_code == 200
    preview = preview_response.json()
    assert preview["summary"]["status"] == "blocked"
    assert f"建议 {create_row['建议 ID']} 是只读建议，不能生成项目管理配置。" in preview["summary"]["blocking_reasons"]


def test_suggestions_create_strategy_review_endpoint_returns_strategy_operations_table(tmp_path: Path):
    _write_suggestion_fixture(tmp_path)
    _write_local_db_suggestions_fixture(tmp_path)
    _write_create_project_strategy_fixture(tmp_path)
    client = _client(tmp_path)

    response = client.get("/api/suggestions/create-strategies", params={"product_key": "demo-game"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "扩量机会扫描"
    assert payload["summary"]["execution_enabled"] is False
    assert {"label": "策略配置", "value": 1} in payload["summary"]["items"]
    assert {"label": "预计创建建议", "value": 1} in payload["summary"]["items"]
    assert payload["table"]["columns"][:5] == ["策略 ID", "版本", "状态", "启用", "来源"]
    row = payload["table"]["rows"][0]
    assert row["策略 ID"] == "recent-scale-capacity-v1"
    assert row["状态"] == "需关注"
    assert row["启用"] == "是"
    assert row["来源"] == "本地策略"
    assert row["产品 Key"] == "demo-game"
    assert row["推荐模式"] == "wx_pay_general_recent_scale"
    assert row["候选账户"] == 2
    assert row["合格素材"] == 1
    assert row["预计建议"] == 1
    assert row["阻断候选"] == 1
    assert "必须在允许名单" in row["账户阈值"]
    assert "素材≥1" in row["素材阈值"]
    assert "只读扫描账户容量" in payload["summary"]["warnings"][0]
    assert Path(payload["artifact_path"]).exists()
    assert payload["raw"]["execution_enabled"] is False


def test_suggestions_effect_review_endpoint_returns_adoption_and_backtest_summary(tmp_path: Path):
    _write_suggestion_fixture(tmp_path)
    _write_local_db_suggestions_fixture(tmp_path)
    _write_create_project_strategy_fixture(tmp_path)
    client = _client(tmp_path)

    response = client.get("/api/suggestions/effect-review", params={"product_key": "demo-game"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "建议效果复盘"
    assert payload["summary"]["execution_enabled"] is False
    assert any(item["label"] == "评估建议" for item in payload["summary"]["items"])
    assert any(item["label"] == "创建建议" for item in payload["summary"]["items"])
    assert "创建状态" in payload["table"]["columns"]
    assert "回测结论" in payload["table"]["columns"]
    assert Path(payload["artifact_path"]).exists()
    assert payload["raw"]["execution_enabled"] is False
    source_path = Path(payload["raw"]["source_suggestions_artifact_path"])
    assert source_path.exists()
    assert source_path.name != "latest.json"
    assert any(section["title"] == "复盘口径" for section in payload["sections"])


def test_suggestions_daily_operations_endpoint_returns_readonly_checklist(tmp_path: Path):
    _write_suggestion_fixture(tmp_path)
    _write_local_db_suggestions_fixture(tmp_path)
    _write_create_project_strategy_fixture(tmp_path)
    client = _client(tmp_path)

    response = client.get("/api/suggestions/daily-operations", params={"product_key": "demo-game"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "数据更新与建议状态"
    assert payload["summary"]["execution_enabled"] is False
    assert {"label": "产品范围", "value": "demo-game"} in payload["summary"]["items"]
    assert payload["table"]["columns"] == ["步骤", "状态", "关键结果", "下一步"]
    steps = {row["步骤"]: row for row in payload["table"]["rows"]}
    assert "数据同步与建议重算" in steps
    assert "扩量机会扫描" in steps
    assert "生成创建项目计划" in steps
    assert "效果复盘" in steps
    assert "创建建议" in steps["生成创建项目计划"]["关键结果"]
    assert payload["raw"]["overview"]["summary"]["execution_enabled"] is False
    assert payload["raw"]["strategy_review"]["execution_enabled"] is False


def test_create_project_suggestion_can_build_create_plan_preview_and_import_to_create_page(tmp_path: Path):
    _write_suggestion_fixture(tmp_path)
    _write_local_db_suggestions_fixture(tmp_path)
    _write_create_project_strategy_fixture(tmp_path)
    client = _client(tmp_path)
    suggestions_response = client.get("/api/suggestions", params={"product_key": "demo-game"})
    suggestions_payload = suggestions_response.json()
    create_row = next(row for row in suggestions_payload["table"]["rows"] if row["建议动作"] == "建议创建项目")

    preview_response = client.post(
        "/api/suggestions/create-plan/preview",
        json={
            "suggestions_artifact_path": suggestions_payload["artifact_path"],
            "selected_suggestion_ids": [create_row["建议 ID"]],
            "product_key": "demo-game",
            "owner": "运营A",
        },
    )

    assert preview_response.status_code == 200
    preview = preview_response.json()
    assert preview["summary"]["title"] == "生成创建项目计划预览"
    assert preview["summary"]["status"] == "planned"
    assert preview["summary"]["execution_enabled"] is False
    assert {"label": "来源建议", "value": 1} in preview["summary"]["items"]
    assert preview["raw"]["create_plan_request"]["mode"] == "wx_pay_general_recent_scale"
    assert preview["raw"]["create_plan_request"]["advertiser_ids"] == "1001"
    assert preview["raw"]["create_plan_request"]["owner"] == "运营A"
    assert preview["raw"]["create_plan_request"]["template_catalog"] == "configs/create-templates/demo-game.local.json"
    assert preview["artifact_path"].endswith(".json")
    assert Path(preview["artifact_path"]).exists()

    import_response = client.get("/api/create-plans/suggestion-preview", params={"path": preview["artifact_path"]})

    assert import_response.status_code == 200
    imported = import_response.json()
    assert imported["summary"]["title"] == "创建建议预览导入"
    assert imported["summary"]["execution_enabled"] is False
    assert imported["raw"]["create_plan_request"]["advertiser_ids"] == "1001"
    assert imported["table"]["rows"][0]["账户 ID"] == "1001"
    section_titles = [section["title"] for section in imported["sections"]]
    assert "创建建议批次" in section_titles
    assert "来源建议证据" in section_titles
    evidence_section = next(section for section in imported["sections"] if section["title"] == "来源建议证据")
    assert evidence_section["table"]["rows"][0]["命中策略"] == "recent-scale-capacity-v1"
    assert evidence_section["table"]["rows"][0]["合格素材"] == "1"


def test_suggestions_lifecycle_endpoint_and_list_show_execution_status(tmp_path: Path):
    _write_suggestion_fixture(tmp_path)
    _write_local_db_suggestions_fixture(tmp_path)
    _write_create_project_strategy_fixture(tmp_path)
    client = _client(tmp_path)
    suggestions_payload = client.get("/api/suggestions", params={"product_key": "demo-game"}).json()
    create_row = next(row for row in suggestions_payload["table"]["rows"] if row["建议动作"] == "建议创建项目")
    _write_create_suggestion_execution_lifecycle(tmp_path, create_row["建议 ID"])

    lifecycle_response = client.get("/api/suggestions/lifecycle", params={"product_key": "demo-game"})

    assert lifecycle_response.status_code == 200
    lifecycle = lifecycle_response.json()
    assert lifecycle["summary"]["title"] == "创建建议生命周期"
    assert {"label": "已锁定", "value": 1} in lifecycle["summary"]["items"]
    lifecycle_row = next(row for row in lifecycle["table"]["rows"] if row["建议 ID"] == create_row["建议 ID"])
    assert lifecycle_row["创建状态"] == "已提交执行"
    assert lifecycle_row["锁定"] == "是"
    assert lifecycle_row["执行任务"] == "task-create-1"

    list_response = client.get("/api/suggestions", params={"product_key": "demo-game"})

    assert list_response.status_code == 200
    payload = list_response.json()
    row = next(row for row in payload["table"]["rows"] if row["建议 ID"] == create_row["建议 ID"])
    assert row["创建状态"] == "已提交执行"
    assert row["创建建议锁定"] is True
    assert row["执行任务"] == "task-create-1"
    assert "创建状态" in payload["table"]["columns"]


def test_locked_create_project_suggestion_cannot_build_create_plan_preview_again(tmp_path: Path):
    _write_suggestion_fixture(tmp_path)
    _write_local_db_suggestions_fixture(tmp_path)
    _write_create_project_strategy_fixture(tmp_path)
    client = _client(tmp_path)
    suggestions_payload = client.get("/api/suggestions", params={"product_key": "demo-game"}).json()
    create_row = next(row for row in suggestions_payload["table"]["rows"] if row["建议动作"] == "建议创建项目")
    _write_create_suggestion_execution_lifecycle(tmp_path, create_row["建议 ID"])

    response = client.post(
        "/api/suggestions/create-plan/preview",
        json={
            "suggestions_artifact_path": suggestions_payload["artifact_path"],
            "selected_suggestion_ids": [create_row["建议 ID"]],
            "product_key": "demo-game",
            "owner": "运营A",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["status"] == "blocked"
    assert "不能重复生成创建计划" in payload["summary"]["blocking_reasons"][0]


def test_create_project_suggestion_preview_blocks_mixed_action_selection(tmp_path: Path):
    _write_suggestion_fixture(tmp_path)
    _write_local_db_suggestions_fixture(tmp_path)
    _write_learned_control_strategy_fixture(tmp_path)
    _write_create_project_strategy_fixture(tmp_path)
    client = _client(tmp_path)
    suggestions_payload = client.get("/api/suggestions", params={"product_key": "demo-game"}).json()
    create_row = next(row for row in suggestions_payload["table"]["rows"] if row["建议动作"] == "建议创建项目")
    delete_row = next(row for row in suggestions_payload["table"]["rows"] if row["建议动作"] == "删除项目")

    response = client.post(
        "/api/suggestions/create-plan/preview",
        json={
            "suggestions_artifact_path": suggestions_payload["artifact_path"],
            "selected_suggestion_ids": [create_row["建议 ID"], delete_row["建议 ID"]],
            "product_key": "demo-game",
            "owner": "运营A",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["status"] == "blocked"
    assert f"建议 {delete_row['建议 ID']} 不是创建项目建议" in "；".join(payload["summary"]["blocking_reasons"])


def test_create_project_suggestion_preview_returns_split_groups_for_cross_mode_selection(tmp_path: Path):
    _write_create_project_strategy_fixture(tmp_path)
    suggestions_path = tmp_path / "data" / "runs" / "rule_suggestions" / "mixed-create.json"
    _write_json(
        suggestions_path,
        {
            "workflow": "rule_suggestions",
            "summary": {"target_date": "2026-05-31", "suggestion_count": 2},
            "suggestions": [
                {
                    "suggestion_id": "create-general-1001",
                    "suggested_action": "suggest_create_project",
                    "suggestion_type": "suggest_create_project",
                    "entity_type": "account",
                    "target_date": "2026-05-31",
                    "product_key": "demo-game",
                    "product_name": "演示游戏",
                    "advertiser_id": "1001",
                    "account_name": "演示账户一",
                    "mode_key": "wx_pay_general_recent_scale",
                    "strategy_id": "recent-scale-capacity-v1",
                    "metrics": {"project_capacity": 3, "qualified_material_count": 5},
                    "blocking_reasons": [],
                },
                {
                    "suggestion_id": "create-male-1002",
                    "suggested_action": "suggest_create_project",
                    "suggestion_type": "suggest_create_project",
                    "entity_type": "account",
                    "target_date": "2026-05-31",
                    "product_key": "demo-game",
                    "product_name": "演示游戏",
                    "advertiser_id": "1002",
                    "account_name": "演示账户二",
                    "mode_key": "wx_pay_male_recent_scale",
                    "strategy_id": "male-scale-capacity-v1",
                    "metrics": {"project_capacity": 2, "qualified_material_count": 4},
                    "blocking_reasons": [],
                },
            ],
        },
    )
    client = _client(tmp_path)

    response = client.post(
        "/api/suggestions/create-plan/preview",
        json={
            "suggestions_artifact_path": str(suggestions_path),
            "selected_suggestion_ids": ["create-general-1001", "create-male-1002"],
            "product_key": "demo-game",
            "owner": "运营A",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["status"] == "split_required"
    assert {"label": "建议批次", "value": 2} in payload["summary"]["items"]
    assert {"label": "需拆分", "value": "是"} in payload["summary"]["items"]
    assert len(payload["table"]["rows"]) == 2
    assert {row["推荐模式"] for row in payload["table"]["rows"]} == {
        "wx_pay_general_recent_scale",
        "wx_pay_male_recent_scale",
    }
    assert len(payload["raw"]["suggestion_groups"]) == 2
    assert any("多个创建模式" in reason for reason in payload["raw"]["split_reasons"])


def test_suggestions_list_uses_latest_account_pool_name_before_stale_suggestion_name(tmp_path: Path):
    _write_suggestion_fixture(tmp_path)
    (tmp_path / "data" / "runs" / "delivery_patrol" / "20260529T000000Z-demo-game.json").unlink()
    (tmp_path / "data" / "runs" / "product_automation_job_delivery_patrol" / "20260529T000001Z.json").unlink()
    db_path = tmp_path / "data" / "roibang_v2.sqlite3"
    bootstrap_database(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO account_pool (advertiser_id, account_name, product, platform, source, synced_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("1001", "最新账户名", "演示游戏", "WECHAT_GAME", "unit_test", "2026-05-29T00:00:00+08:00"),
        )

    suggestions_path = tmp_path / "data" / "runs" / "delivery_patrol_suggestions" / "20260528T100001Z.json"
    payload = json.loads(suggestions_path.read_text(encoding="utf-8"))
    payload["suggestions"][0]["account_name"] = "建议文件旧名"
    suggestions_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    client = _client(tmp_path)

    response = client.get("/api/suggestions", params={"product_key": "demo-game"})

    assert response.status_code == 200
    payload = response.json()
    row = next(row for row in payload["table"]["rows"] if row["建议 ID"] == "delete-1")
    assert row["账户名"] == "最新账户名"
    assert {"label": "历史证据日期", "value": "2026-05-28"} in payload["summary"]["items"]
    assert any("历史证据日期为 2026-05-28" in warning for warning in payload["summary"]["warnings"])


def test_suggestions_list_prefers_today_patrol_account_name_before_account_pool_name(tmp_path: Path):
    _write_suggestion_fixture(tmp_path)
    _write_local_db_suggestions_fixture(tmp_path)
    _write_learned_control_strategy_fixture(tmp_path)
    db_path = tmp_path / "data" / "roibang_v2.sqlite3"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE account_pool SET account_name = ? WHERE advertiser_id = ?",
            ("账户池旧名", "1001"),
        )
    patrol_path = tmp_path / "data" / "runs" / "delivery_patrol" / "20260529T000000Z-demo-game.json"
    patrol_payload = json.loads(patrol_path.read_text(encoding="utf-8"))
    patrol_payload["accounts"][0]["account_name"] = "平台真实账户名"
    patrol_path.write_text(json.dumps(patrol_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    client = _client(tmp_path)

    response = client.get("/api/suggestions", params={"product_key": "demo-game"})

    assert response.status_code == 200
    payload = response.json()
    row = next(row for row in payload["table"]["rows"] if row["账户 ID"] == "1001" and row["数据来源"] == "本地控制策略")
    assert row["账户名"] == "平台真实账户名"


def test_suggestions_list_prefers_local_db_suggestions_with_evidence_columns(tmp_path: Path):
    _write_suggestion_fixture(tmp_path)
    _write_local_db_suggestions_fixture(tmp_path)
    _write_learned_control_strategy_fixture(tmp_path)
    client = _client(tmp_path)

    response = client.get("/api/suggestions", params={"product_key": "demo-game"})

    assert response.status_code == 200
    payload = response.json()
    artifact_path = Path(payload["artifact_path"])
    latest_path = tmp_path / "data" / "runs" / "rule_suggestions" / "latest.json"
    assert artifact_path.exists()
    assert artifact_path.name != "latest.json"
    assert latest_path.exists()
    assert json.loads(artifact_path.read_text(encoding="utf-8"))["artifact_path"] == str(artifact_path)
    assert json.loads(latest_path.read_text(encoding="utf-8"))["artifact_path"] == str(artifact_path)
    assert "数据来源" in payload["table"]["columns"]
    assert "关键指标" in payload["table"]["columns"]
    assert "学习依据" in payload["table"]["columns"]
    assert "动作取舍" in payload["table"]["columns"]
    rows = payload["table"]["rows"]
    local_delete = next(row for row in rows if row["建议动作"] == "删除项目" and row["数据来源"] == "本地控制策略")
    actions = {row["建议动作"]: row for row in rows if row["数据来源"] == "本地控制策略"}
    assert not [
        row
        for row in rows
        if row["数据来源"] == "投放巡检建议" and row["建议动作"] in {"删除项目", "暂停项目", "调预算", "调出价"}
    ]
    assert local_delete["项目 ID"] == "p-local-delete"
    assert local_delete["账户名"] == "演示账户一"
    assert "消耗" in local_delete["关键指标"]
    assert "approved-delete-low-recent" in local_delete["学习依据"]
    assert "已启用学习策略" in local_delete["动作取舍"]
    assert actions["暂停项目"]["项目名"] == "演示游戏-本地动作项目"
    assert "approved-pause-low-roi" in actions["暂停项目"]["学习依据"]
    assert "调预算" not in actions
    assert "调出价" not in actions
    assert actions["素材复用风险"]["项目 ID"] == "material-risk-1"
    assert actions["素材复用风险"]["可转动作 JSON"] == "只读诊断，不生成动作配置"
    assert actions["账户异常"]["账户 ID"] == "1003"
    assert actions["账户异常"]["账户名"] == "名单外账户"
    assert actions["账户异常"]["可转动作 JSON"] == "只读诊断，不生成动作配置"
    assert {"label": "建议对象账户", "value": 1} in payload["summary"]["items"]
    assert {"label": "今日巡检有消耗账户", "value": 2} in payload["summary"]["items"]


def test_suggestions_quality_endpoint_explains_learning_statuses(tmp_path: Path):
    _write_suggestion_fixture(tmp_path)
    _write_local_db_suggestions_fixture(tmp_path)
    _write_learned_control_strategy_fixture(tmp_path)
    client = _client(tmp_path)

    response = client.get("/api/suggestions/quality", params={"product_key": "demo-game"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "策略学习与建议质量"
    assert payload["summary"]["execution_enabled"] is False
    assert {"label": "学习策略", "value": 6} in payload["summary"]["items"]
    assert {"label": "已启用策略", "value": 4} in payload["summary"]["items"]
    assert {"label": "可进入建议", "value": 4} in payload["summary"]["items"]
    assert any("通过回测但未启用" in warning for warning in payload["summary"]["warnings"])
    rows = payload["table"]["rows"]
    candidate = next(row for row in rows if row["策略"] == "candidate-bid-passed")
    assert candidate["状态"] == "候选：回测通过"
    assert candidate["启用"] == "否"
    assert candidate["可进入建议"] == "否"
    blocked = next(row for row in rows if row["策略"] == "blocked-pause-mixed")
    assert blocked["状态"] == "阻断：高风险样本混杂"
    assert "有转化项目" in blocked["阻断原因"]
    assert payload["raw"]["中文摘要"].startswith("策略学习与建议质量")


def test_suggestions_list_blocks_builtin_local_project_actions_without_learned_strategy(tmp_path: Path):
    _write_suggestion_fixture(tmp_path)
    _write_local_db_suggestions_fixture(tmp_path)
    client = _client(tmp_path)

    response = client.get("/api/suggestions", params={"product_key": "demo-game"})

    assert response.status_code == 200
    payload = response.json()
    rows = payload["table"]["rows"]
    assert not [
        row
        for row in rows
        if row["数据来源"] == "本地控制策略"
        and row["建议动作"] in {"删除项目", "暂停项目", "调预算", "调出价"}
    ]
    assert any(row["数据来源"] == "本地控制策略" and row["建议动作"] == "素材复用风险" for row in rows)
    assert any(row["数据来源"] == "本地控制策略" and row["建议动作"] == "账户异常" for row in rows)


def test_suggestions_list_reuses_snapshot_when_content_is_unchanged(tmp_path: Path):
    _write_suggestion_fixture(tmp_path)
    _write_local_db_suggestions_fixture(tmp_path)
    client = _client(tmp_path)

    first = client.get("/api/suggestions", params={"product_key": "demo-game"}).json()
    second = client.get("/api/suggestions", params={"product_key": "demo-game"}).json()

    assert first["artifact_path"] == second["artifact_path"]
    assert Path(first["artifact_path"]).name != "latest.json"


def test_suggestions_list_limits_project_actions_to_allowed_today_patrol_accounts(tmp_path: Path):
    _write_suggestion_fixture(tmp_path)
    _write_local_db_suggestions_fixture(tmp_path)
    patrol_path = tmp_path / "data" / "runs" / "delivery_patrol" / "20260529T000000Z-demo-game.json"
    patrol_payload = json.loads(patrol_path.read_text(encoding="utf-8"))
    patrol_payload["accounts"] = [
        {
            "advertiser_id": "1002",
            "account_name": "演示账户二",
            "metrics": {"today": {"stat_cost": 200}},
        }
    ]
    patrol_path.write_text(json.dumps(patrol_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    client = _client(tmp_path)

    response = client.get("/api/suggestions", params={"product_key": "demo-game"})

    assert response.status_code == 200
    payload = response.json()
    assert {"label": "今日巡检有消耗账户", "value": 1} in payload["summary"]["items"]
    assert {"label": "建议对象账户", "value": 0} in payload["summary"]["items"]
    rows = payload["table"]["rows"]
    assert not [
        row
        for row in rows
        if row["数据来源"] == "本地控制策略"
        and row["建议动作"] in {"删除项目", "暂停项目", "调预算", "调出价"}
    ]
    assert any(row["数据来源"] == "本地控制策略" and row["建议动作"] == "素材复用风险" for row in rows)


def test_suggestions_project_update_preview_builds_readonly_action_json(tmp_path: Path):
    suggestions_path = _write_suggestion_fixture(tmp_path)
    client = _client(tmp_path)

    response = client.post(
        "/api/suggestions/project-update/preview",
        json={
            "suggestions_artifact_path": str(suggestions_path),
            "project_update_id": "suggestions-demo-001",
            "operator": "运营A",
            "suggested_actions": ["suggest_delete_project", "suggest_close_project"],
            "output_path": "configs/project-updates/suggestions-demo.local.json",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "项目管理配置预览"
    assert payload["summary"]["execution_enabled"] is False
    assert {"label": "动作数", "value": 2} in payload["summary"]["items"]
    assert payload["table"]["columns"] == ["账户 ID", "账户名", "项目 ID", "项目名", "动作", "原因"]
    assert payload["table"]["rows"] == [
        {
            "账户 ID": "1001",
            "账户名": "演示账户一",
            "项目 ID": "p-delete",
            "项目名": "演示游戏-旧项目",
            "动作": "删除项目",
            "原因": "项目已关闭且两天无计费时间转化，建议删除。",
        },
        {
            "账户 ID": "1002",
            "账户名": "演示账户二",
            "项目 ID": "p-close",
            "项目名": "演示游戏-关闭候选",
            "动作": "暂停项目",
            "原因": "累计消耗达到阈值但计费时间转化为 0，建议暂停项目。",
        },
    ]
    assert payload["raw"]["project_update"]["execution"] == {"enabled": False, "status": "planned_only"}
    assert payload["raw"]["project_update"]["actions"][0]["action_type"] == "delete_project"
    assert payload["raw"]["project_update"]["actions"][1]["action_type"] == "status_update"


def test_suggestions_project_update_preview_can_select_rows_and_returns_complete_chinese_action_json(tmp_path: Path):
    suggestions_path = _write_suggestion_fixture(tmp_path)
    client = _client(tmp_path)

    response = client.post(
        "/api/suggestions/project-update/preview",
        json={
            "suggestions_artifact_path": str(suggestions_path),
            "project_update_id": "suggestions-demo-selected-001",
            "operator": "运营A",
            "product_key": "demo-game",
            "selected_suggestion_ids": ["close-1"],
            "output_path": "configs/project-updates/suggestions-demo-selected.local.json",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["status"] == "planned"
    assert {"label": "动作数", "value": 1} in payload["summary"]["items"]
    project_update = payload["raw"]["project_update"]
    assert project_update["中文摘要"] == "根据规则建议生成项目管理动作 JSON，涉及 1 个账户、1 个动作；只生成配置，不执行真实业务动作。"
    assert project_update["product_key"] == "demo-game"
    assert project_update["product_name"] == "演示游戏"
    assert project_update["source_artifact"] == str(suggestions_path)
    assert project_update["operator"] == "运营A"
    assert project_update["dry_run_required"] is True
    assert project_update["execution_allowed"] is False
    assert project_update["accounts"] == [{"account_id": "1002", "account_name": "演示账户二"}]
    assert project_update["risk_summary"] == "包含暂停项目 1 个；执行前必须人工核对账户、项目、动作和来源建议。"
    assert project_update["actions"] == [
        {
            "action_type": "status_update",
            "中文动作": "暂停项目",
            "advertiser_id": "1002",
            "account_name": "演示账户二",
            "entity_type": "project",
            "project_id": "p-close",
            "project_name": "演示游戏-关闭候选",
            "reason": "累计消耗达到阈值但计费时间转化为 0，建议暂停项目。",
            "source_suggestion_id": "close-1",
            "source_rule_id": "project_close_zero_convert",
            "metrics": {},
            "evidence": {},
            "opt_status": "DISABLE",
        }
    ]


def test_suggestions_project_update_preview_blocks_missing_account_name(tmp_path: Path):
    suggestions_path = _write_suggestion_fixture(tmp_path)
    payload = json.loads(suggestions_path.read_text(encoding="utf-8"))
    payload["suggestions"][0]["advertiser_id"] = "9999"
    _write_json(suggestions_path, payload)
    client = _client(tmp_path)

    response = client.post(
        "/api/suggestions/project-update/preview",
        json={
            "suggestions_artifact_path": str(suggestions_path),
            "project_update_id": "suggestions-missing-account-001",
            "operator": "运营A",
            "selected_suggestion_ids": ["delete-1"],
            "output_path": "configs/project-updates/suggestions-missing-account.local.json",
        },
    )

    assert response.status_code == 200
    result = response.json()
    assert result["summary"]["status"] == "blocked"
    assert result["summary"]["blocking_reasons"] == ["建议 delete-1 缺少账户名：9999。"]


def test_suggestions_project_update_preview_blocks_readonly_selected_suggestion(tmp_path: Path):
    suggestions_path = _write_suggestion_fixture(tmp_path)
    client = _client(tmp_path)

    response = client.post(
        "/api/suggestions/project-update/preview",
        json={
            "suggestions_artifact_path": str(suggestions_path),
            "project_update_id": "suggestions-readonly-001",
            "operator": "运营A",
            "selected_suggestion_ids": ["watch-1"],
            "output_path": "configs/project-updates/suggestions-readonly.local.json",
        },
    )

    assert response.status_code == 200
    result = response.json()
    assert result["summary"]["status"] == "blocked"
    assert result["summary"]["blocking_reasons"] == ["建议 watch-1 是只读建议，不能生成项目管理配置。"]


def test_suggestions_project_update_preview_explains_missing_snapshot_suggestion(tmp_path: Path):
    suggestions_path = _write_suggestion_fixture(tmp_path)
    client = _client(tmp_path)

    response = client.post(
        "/api/suggestions/project-update/preview",
        json={
            "suggestions_artifact_path": str(suggestions_path),
            "project_update_id": "suggestions-missing-id-001",
            "operator": "运营A",
            "selected_suggestion_ids": ["missing-suggestion"],
            "output_path": "configs/project-updates/suggestions-missing-id.local.json",
        },
    )

    assert response.status_code == 200
    result = response.json()
    assert result["summary"]["status"] == "blocked"
    assert result["summary"]["blocking_reasons"] == [
        "建议 missing-suggestion 不在当前建议来源快照中；请返回投放建议工作台刷新建议后重新选择。"
    ]


def test_suggestions_project_update_preview_blocks_adjustment_without_ratio(tmp_path: Path):
    suggestions_path = _write_suggestion_fixture(tmp_path)
    payload = json.loads(suggestions_path.read_text(encoding="utf-8"))
    payload["suggestions"].append(
        {
            "suggestion_id": "budget-1",
            "suggested_action": "suggest_lower_budget",
            "suggestion_type": "suggest_lower_budget",
            "rule_id": "project_lower_budget_low_roi",
            "target_date": "2026-05-28",
            "advertiser_id": "1001",
            "entity_type": "project",
            "project_id": "p-budget",
            "entity_name": "演示游戏-预算候选",
            "reason": "ROI 低于阈值，但没有给出明确比例。",
        }
    )
    _write_json(suggestions_path, payload)
    client = _client(tmp_path)

    response = client.post(
        "/api/suggestions/project-update/preview",
        json={
            "suggestions_artifact_path": str(suggestions_path),
            "project_update_id": "suggestions-budget-001",
            "operator": "运营A",
            "selected_suggestion_ids": ["budget-1"],
            "output_path": "configs/project-updates/suggestions-budget.local.json",
        },
    )

    assert response.status_code == 200
    result = response.json()
    assert result["summary"]["status"] == "blocked"
    assert result["summary"]["blocking_reasons"] == ["建议 budget-1 是调预算/调出价动作，但缺少明确比例，不能猜预算或出价。"]


def test_suggestions_project_update_preview_maps_legacy_action_filters_to_local_suggestions(tmp_path: Path):
    _write_suggestion_fixture(tmp_path)
    _write_local_db_suggestions_fixture(tmp_path)
    _write_learned_control_strategy_fixture(tmp_path)
    client = _client(tmp_path)

    suggestions_response = client.get("/api/suggestions", params={"product_key": "demo-game"})
    assert suggestions_response.status_code == 200
    suggestions_payload = suggestions_response.json()

    response = client.post(
        "/api/suggestions/project-update/preview",
        json={
            "suggestions_artifact_path": suggestions_payload["artifact_path"],
            "project_update_id": "suggestions-local-actions-001",
            "operator": "运营A",
            "product_key": "demo-game",
            "suggested_actions": ["suggest_close_project", "suggest_lower_budget", "suggest_lower_bid"],
            "output_path": "configs/project-updates/suggestions-local-actions.local.json",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["status"] == "planned"
    assert {"label": "动作数", "value": 1} in payload["summary"]["items"]
    rows = payload["table"]["rows"]
    assert [row["动作"] for row in rows] == ["暂停项目"]
    local_rows = [row for row in rows if row["项目名"] == "演示游戏-本地动作项目"]
    patrol_rows = [row for row in rows if row["项目名"] == "演示游戏-关闭候选"]
    assert [row["动作"] for row in local_rows] == ["暂停项目"]
    assert patrol_rows == []


def test_suggestions_ai_draft_returns_chinese_explanations_and_draft_json_without_execution(tmp_path: Path):
    suggestions_path = _write_suggestion_fixture(tmp_path)
    client = _client(tmp_path)

    response = client.post(
        "/api/suggestions/ai-draft",
        json={
            "suggestions_artifact_path": str(suggestions_path),
            "project_update_id": "ai-suggestions-demo-001",
            "operator": "运营A",
            "product_key": "demo-game",
            "selected_suggestion_ids": ["delete-1", "watch-1"],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "AI 建议草稿"
    assert payload["summary"]["status"] == "draft_only"
    assert payload["summary"]["execution_enabled"] is False
    assert {"label": "来源建议", "value": 2} in payload["summary"]["items"]
    assert {"label": "项目管理配置草稿", "value": 1} in payload["summary"]["items"]
    assert {"label": "只读建议", "value": 1} in payload["summary"]["items"]
    assert payload["table"]["columns"] == [
        "建议 ID",
        "产品",
        "账户名",
        "账户 ID",
        "项目名",
        "项目 ID",
        "建议动作",
        "AI 中文解释",
        "复核点",
        "草稿状态",
    ]
    delete_row = next(row for row in payload["table"]["rows"] if row["建议 ID"] == "delete-1")
    watch_row = next(row for row in payload["table"]["rows"] if row["建议 ID"] == "watch-1")
    assert delete_row["账户名"] == "演示账户一"
    assert "演示账户一（1001）" in delete_row["AI 中文解释"]
    assert "演示游戏-旧项目" in delete_row["AI 中文解释"]
    assert "消耗 0" in delete_row["AI 中文解释"]
    assert delete_row["草稿状态"] == "可生成项目管理配置草稿"
    assert watch_row["草稿状态"] == "只读建议，不生成项目管理配置草稿"
    assert payload["raw"]["ai_policy"] == {
        "draft_only": True,
        "external_api_calls": 0,
        "execution_enabled": False,
        "note": "AI 建议只解释和生成草稿，不执行真实业务动作。",
    }
    assert payload["raw"]["draft_project_update"]["execution"] == {"enabled": False, "status": "planned_only"}
    assert len(payload["raw"]["draft_project_update"]["actions"]) == 1
    assert payload["raw"]["draft_project_update"]["actions"][0]["account_name"] == "演示账户一"
    assert Path(payload["artifact_path"]).exists()


def test_suggestions_ai_draft_keeps_readonly_suggestions_out_of_action_json(tmp_path: Path):
    suggestions_path = _write_suggestion_fixture(tmp_path)
    client = _client(tmp_path)

    response = client.post(
        "/api/suggestions/ai-draft",
        json={
            "suggestions_artifact_path": str(suggestions_path),
            "project_update_id": "ai-readonly-demo-001",
            "operator": "运营A",
            "product_key": "demo-game",
            "selected_suggestion_ids": ["watch-1"],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["status"] == "draft_only"
    assert {"label": "项目管理配置草稿", "value": 0} in payload["summary"]["items"]
    assert {"label": "只读建议", "value": 1} in payload["summary"]["items"]
    assert payload["raw"]["draft_project_update"]["actions"] == []
    assert payload["table"]["rows"][0]["草稿状态"] == "只读建议，不生成项目管理配置草稿"


def test_suggestions_project_update_generate_starts_fixed_script_task_without_execution(tmp_path: Path):
    suggestions_path = _write_suggestion_fixture(tmp_path)
    client = _client(tmp_path)

    response = client.post(
        "/api/suggestions/project-update/generate",
        json={
            "suggestions_artifact_path": str(suggestions_path),
            "project_update_id": "suggestions-demo-001",
            "operator": "运营A",
            "product_key": "demo-game",
            "selected_suggestion_ids": ["delete-1"],
            "suggested_actions": ["suggest_delete_project"],
            "output_path": "configs/project-updates/suggestions-demo.local.json",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "项目管理配置生成任务"
    assert payload["summary"]["execution_enabled"] is False
    assert payload["task"]["operation_type"] == "suggestions_project_update_generate"
    assert "scripts/run_project_update_from_suggestions.py" in payload["raw"]["task"]["command"]
    assert "--suggestion-id" in payload["raw"]["task"]["command"]
    assert "delete-1" in payload["raw"]["task"]["command"]
    assert "--product-key" in payload["raw"]["task"]["command"]
    assert "--account-name" in payload["raw"]["task"]["command"]
    assert "--execute" not in payload["raw"]["task"]["command"]
    assert "--yes" not in payload["raw"]["task"]["command"]


def test_suggestions_refresh_starts_fixed_readonly_sync_task(tmp_path: Path, monkeypatch):
    _write_suggestion_fixture(tmp_path)

    def fake_start_runner(command, *, cwd):
        assert command[1] == "scripts/run_frontend_task.py"
        assert cwd == tmp_path
        return 4321

    monkeypatch.setattr("backend.app.services.suggestions.start_runner", fake_start_runner, raising=False)
    client = _client(tmp_path)

    response = client.post("/api/suggestions/refresh", json={"product_key": "demo-game"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "同步数据并重算建议任务"
    assert payload["summary"]["status"] == "queued"
    assert payload["summary"]["execution_enabled"] is False
    assert {"label": "产品", "value": "demo-game"} in payload["summary"]["items"]
    assert {"label": "目标日期", "value": "today"} in payload["summary"]["items"]
    assert payload["task"]["pid"] == 4321
    assert payload["task"]["operation_type"] == "suggestions_refresh"
    command = payload["raw"]["task"]["command"]
    assert "scripts/run_suggestions_refresh.py" in command
    assert "--product-key" in command
    assert "demo-game" in command
    assert "--enable-readonly" in command
    assert "--execute" not in command
    assert "--yes" not in command


def test_suggestions_backtest_returns_chinese_evaluation_rows(tmp_path: Path):
    suggestions_path = _write_suggestion_fixture(tmp_path)
    db_path = tmp_path / "data" / "roibang_v2.sqlite3"
    _init_backtest_db(db_path)
    _insert_backtest_metric(db_path, date="2026-05-29", advertiser_id="1002", project_id="p-close", cost=0, convert=0, roi=0)
    _insert_backtest_operation(db_path, advertiser_id="1002", project_id="p-close", detail="项目 启用 -> 暂停")
    client = _client(tmp_path)

    response = client.post(
        "/api/suggestions/backtest",
        json={
            "suggestions_artifact_path": str(suggestions_path),
            "product_key": "demo-game",
            "lookahead_days": 1,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "建议回测"
    assert payload["summary"]["status"] == "completed"
    assert payload["summary"]["execution_enabled"] is False
    assert {"label": "评估建议", "value": 2} in payload["summary"]["items"]
    assert {"label": "已人工处理", "value": 1} in payload["summary"]["items"]
    assert payload["table"]["columns"] == [
        "建议 ID",
        "产品",
        "账户名",
        "账户 ID",
        "项目名",
        "项目 ID",
        "建议动作",
        "创建状态",
        "计划预览",
        "执行前复核",
        "执行任务",
        "创建项目数",
        "建议日期",
        "后续观察窗口",
        "后续消耗",
        "后续转化",
        "后续 ROI",
        "回测结论",
        "中文原因",
        "数据完整性",
    ]
    close_row = next(row for row in payload["table"]["rows"] if row["建议 ID"] == "close-1")
    assert close_row["产品"] == "演示游戏"
    assert close_row["账户名"] == "演示账户二"
    assert close_row["账户 ID"] == "1002"
    assert close_row["项目 ID"] == "p-close"
    assert close_row["建议动作"] == "暂停项目"
    assert close_row["后续观察窗口"] == "2026-05-29 至 2026-05-29"
    assert close_row["回测结论"] == "已被人工处理"
    assert close_row["中文原因"] == "操作日志显示建议后已有对应人工处理；后续窗口低消耗且无转化，支持关闭/删除类建议。"
    assert close_row["数据完整性"] == "完整"
    assert payload["raw"]["workflow"] == "delivery_suggestion_backtest"
    assert payload["artifact_path"].endswith(".json")


def test_suggestions_backtest_includes_create_project_lifecycle_and_future_metrics(tmp_path: Path):
    _write_suggestion_fixture(tmp_path)
    _write_local_db_suggestions_fixture(tmp_path)
    _write_create_project_strategy_fixture(tmp_path)
    client = _client(tmp_path)

    suggestions_response = client.get("/api/suggestions", params={"product_key": "demo-game"})
    assert suggestions_response.status_code == 200
    suggestions_payload = suggestions_response.json()
    create_row = next(row for row in suggestions_payload["table"]["rows"] if row["建议动作"] == "建议创建项目")
    _write_completed_create_suggestion_lifecycle(
        tmp_path,
        suggestion_id=create_row["建议 ID"],
        advertiser_id=create_row["账户 ID"],
        project_id="project-created-1",
    )
    _insert_backtest_metric(
        tmp_path / "data" / "roibang_v2.sqlite3",
        date="2026-05-29",
        advertiser_id=create_row["账户 ID"],
        project_id="project-created-1",
        cost=500,
        convert=4,
        roi=1.2,
    )

    response = client.post(
        "/api/suggestions/backtest",
        json={
            "suggestions_artifact_path": suggestions_payload["artifact_path"],
            "product_key": "demo-game",
            "lookahead_days": 1,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert {"label": "创建建议", "value": 1} in payload["summary"]["items"]
    assert {"label": "创建已采纳", "value": 1} in payload["summary"]["items"]
    assert {"label": "创建已执行", "value": 1} in payload["summary"]["items"]
    assert {"label": "创建有后续数据", "value": 1} in payload["summary"]["items"]
    row = next(row for row in payload["table"]["rows"] if row["建议 ID"] == create_row["建议 ID"])
    assert row["建议动作"] == "建议创建项目"
    assert row["创建状态"] == "执行完成"
    assert row["项目 ID"] == "project-created-1"
    assert row["创建项目数"] == 1
    assert row["后续消耗"] == 500
    assert row["后续转化"] == 4
    assert row["后续 ROI"] == 1.2
    assert row["回测结论"] == "已采纳有后续数据"
    assert row["数据完整性"] == "完整"


def test_suggestions_backtest_blocks_when_local_db_missing(tmp_path: Path):
    suggestions_path = _write_suggestion_fixture(tmp_path)
    client = _client(tmp_path)

    response = client.post(
        "/api/suggestions/backtest",
        json={
            "suggestions_artifact_path": str(suggestions_path),
            "product_key": "demo-game",
            "lookahead_days": 1,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "建议回测"
    assert payload["summary"]["status"] == "blocked"
    assert payload["summary"]["blocking_reasons"] == [f"本地回测数据库不存在：{tmp_path / 'data' / 'roibang_v2.sqlite3'}"]
