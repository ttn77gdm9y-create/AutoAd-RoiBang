import json
import sqlite3
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from roibang_v2.db.bootstrap import bootstrap_database
from roibang_v2.workflows.scheduler_status import build_scheduler_status_report
from roibang_v2.workflows.scheduler_status import run_scheduler_status_request


def _registry() -> dict:
    return {
        "jobs": [
            {
                "id": "roibang-material-history-yesterday",
                "name": "昨日有消耗账户素材明细同步",
                "enabled": True,
                "schedule": {"type": "cron", "expr": "0 2 * * *", "tz": "Asia/Shanghai"},
                "script": {"command": ["python3", "scripts/run_material_history_backfill.py"], "mode": "foreground"},
                "policy": {},
                "result_contract": {
                    "workflow": "material_history_backfill",
                    "artifact_dir": "data/runs/material_history_backfill",
                    "must_include": ["ok", "workflow", "execution_enabled", "external_api_calls", "summary"],
                    "must_equal": {"execution_enabled": False},
                },
            },
            {
                "id": "roibang-source-material-account-auto-push",
                "name": "源素材账户自动补材",
                "enabled": True,
                "schedule": {"type": "cron", "expr": "0 5 * * *", "tz": "Asia/Shanghai"},
                "script": {"command": ["python3", "scripts/run_source_material_account_auto_push.py"], "mode": "foreground"},
                "policy": {},
                "result_contract": {
                    "workflow": "source_material_account_auto_push",
                    "artifact_dir": "data/runs/source_material_account_auto_push",
                    "must_include": ["ok", "workflow", "execution_enabled", "external_api_calls", "summary"],
                    "must_equal": {"execution_enabled": True},
                },
            },
            {
                "id": "roibang-source-material-preload-to-guojing-spent",
                "name": "源素材预推送到昨日有消耗郭靖账户",
                "enabled": True,
                "schedule": {"type": "cron", "expr": "20 5 * * *", "tz": "Asia/Shanghai"},
                "script": {"command": ["python3", "scripts/run_source_material_preload_to_accounts.py"], "mode": "foreground"},
                "policy": {},
                "result_contract": {
                    "workflow": "source_material_preload_to_accounts",
                    "artifact_dir": "data/runs/source_material_preload_to_accounts",
                    "must_include": ["ok", "workflow", "execution_enabled", "external_api_calls", "summary"],
                    "must_equal": {"execution_enabled": True},
                },
            },
            {
                "id": "roibang-operation-log-yesterday-sync",
                "name": "昨日有消耗账户操作日志同步",
                "enabled": True,
                "schedule": {"type": "cron", "expr": "30 2 * * *", "tz": "Asia/Shanghai"},
                "script": {"command": ["python3", "scripts/run_control_operation_log_history_sync.py"], "mode": "foreground"},
                "policy": {},
                "result_contract": {
                    "workflow": "control_operation_log_history_sync",
                    "artifact_dir": "data/runs/control_operation_log_history_sync",
                    "must_include": ["ok", "workflow", "execution_enabled", "external_api_calls", "summary"],
                    "must_equal": {"execution_enabled": False},
                },
            },
            {
                "id": "roibang-project-schedule-restore-due",
                "name": "项目时段到期恢复",
                "enabled": True,
                "schedule": {"type": "cron", "expr": "10 0 * * *", "tz": "Asia/Shanghai"},
                "script": {"command": ["python3", "scripts/run_project_schedule_restore_due.py"], "mode": "foreground"},
                "policy": {},
                "result_contract": {
                    "workflow": "project_schedule_restore_due",
                    "artifact_dir": "data/runs/project_schedule_restore_due",
                    "must_include": ["ok", "workflow", "execution_enabled", "external_api_calls", "summary"],
                    "must_equal": {"execution_enabled": True},
                },
            },
        ]
    }


def _request() -> dict:
    return {
        "scheduler_status": {
            "project_name": "RoiBang-V2",
            "timezone": "Asia/Shanghai",
            "expected_data_date": {"mode": "yesterday"},
            "jobs": [
                {
                    "job_id": "roibang-material-history-yesterday",
                    "display_name": "02:00 昨日有消耗账户素材明细同步",
                    "data_check": {"type": "material_daily_metrics"},
                },
                {
                    "job_id": "roibang-source-material-account-auto-push",
                    "display_name": "05:00 源素材账户自动补材",
                    "data_check": {
                        "type": "source_material_account",
                        "source_advertiser_id": "src",
                        "product": "勇者突进",
                    },
                },
                {
                    "job_id": "roibang-source-material-preload-to-guojing-spent",
                    "display_name": "05:20 源素材预推送到昨日有消耗郭靖账户",
                    "data_check": {
                        "type": "source_material_preload",
                        "source_advertiser_id": "src",
                        "product": "勇者突进",
                    },
                },
                {
                    "job_id": "roibang-operation-log-yesterday-sync",
                    "display_name": "02:30 昨日有消耗账户操作日志同步",
                    "data_check": {"type": "operation_logs"},
                },
                {
                    "job_id": "roibang-project-schedule-restore-due",
                    "display_name": "00:10 项目时段到期恢复",
                    "data_check": {"type": "project_schedule_restore_queue"},
                },
            ],
            "delivery": {"feishu": {"enabled": False}},
        }
    }


def _write_artifact(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_scheduler_status_reports_data_freshness_and_contracts(tmp_path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO material_daily_metrics
              (metric_date, advertiser_id, project_id, promotion_id, material_id, stat_cost, source, synced_at)
            VALUES ('2026-05-11', '1', 'p1', 'u1', 'm1', 12.3, 'test', 'now')
            """
        )
        conn.execute(
            """
            INSERT INTO product_source_materials
              (product, source_advertiser_id, material_id, video_id, name, material_type, is_active, source, synced_at)
            VALUES ('勇者突进', 'src', 'm1', 'v1', '素材1', 'video', 1, 'test', 'now')
            """
        )
        conn.execute(
            """
            INSERT INTO source_material_preload_ledger (
              product, source_advertiser_id, target_advertiser_id, source_material_id,
              source_video_id, status, batch_key, response_payload_json, first_seen_at, last_seen_at
            ) VALUES (
              '勇者突进', 'src', 'target-1', 'm1',
              'v1', 'completed', 'batch-1', '{}', 'now', 'now'
            )
            """
        )
        conn.execute(
            """
            INSERT INTO operation_logs
              (operation_id, occurred_at, advertiser_id, entity_type, entity_id, action, source, synced_at)
            VALUES ('op1', '2026-05-11 12:00:00', '1', 'project', 'p1', '更新项目', 'test', 'now')
            """
        )
    _write_artifact(
        tmp_path / "data/runs/material_history_backfill/20260512T010000Z.json",
        {"ok": True, "workflow": "material_history_backfill", "execution_enabled": False, "external_api_calls": 1, "summary": {}},
    )
    _write_artifact(
        tmp_path / "data/runs/source_material_account_auto_push/20260512T020000Z.json",
        {"ok": True, "workflow": "source_material_account_auto_push", "execution_enabled": True, "external_api_calls": 1, "summary": {}},
    )
    _write_artifact(
        tmp_path / "data/runs/source_material_preload_to_accounts/20260512T022000Z.json",
        {"ok": True, "workflow": "source_material_preload_to_accounts", "execution_enabled": True, "external_api_calls": 1, "summary": {}},
    )
    _write_artifact(
        tmp_path / "data/runs/control_operation_log_history_sync/20260512T023000Z.json",
        {"ok": True, "workflow": "control_operation_log_history_sync", "execution_enabled": False, "external_api_calls": 1, "summary": {}},
    )
    _write_artifact(
        tmp_path / "data/runs/project_schedule_restore_due/20260512T001000Z.json",
        {
            "ok": True,
            "workflow": "project_schedule_restore_due",
            "execution_enabled": True,
            "external_api_calls": 0,
            "summary": {"queue_item_count": 0},
        },
    )

    result = build_scheduler_status_report(
        _request(),
        registry=_registry(),
        db_path=db_path,
        runs_dir=tmp_path / "data/runs",
        repo_root=tmp_path,
        now=datetime(2026, 5, 12, 6, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
        launchctl_status_reader=lambda job_id: {"loaded": True, "runs": 1, "last_exit_code": "0"},
    )

    assert result["ok"] is True
    assert result["summary"]["expected_data_date"] == "2026-05-11"
    assert [job["status"] for job in result["jobs"]] == ["ok", "ok", "ok", "ok", "ok"]
    assert "RoiBang-V2 定时任务日报 2026-05-12" in result["message"]
    assert "02:30 昨日有消耗账户操作日志同步：正常" in result["message"]
    assert "05:00 源素材账户自动补材：正常" in result["message"]
    assert "05:20 源素材预推送到昨日有消耗郭靖账户：正常" in result["message"]
    assert "已记录预推送 1 条，目标账户 1 个" in result["message"]
    assert "00:10 项目时段到期恢复：正常" in result["message"]
    assert "待恢复 0，已恢复 0，失败待处理 0" in result["message"]


def test_scheduler_status_reports_restore_queue_attention(tmp_path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)
    _write_artifact(
        tmp_path / "data/runs/project_schedule_restore_due/20260512T001000Z.json",
        {
            "ok": True,
            "workflow": "project_schedule_restore_due",
            "execution_enabled": True,
            "external_api_calls": 0,
            "summary": {},
        },
    )
    queue_path = tmp_path / "data/runs/project_schedule_restore_queue.json"
    _write_artifact(
        queue_path,
        {
            "version": 1,
            "items": [
                {
                    "restore_id": "r1",
                    "status": "pending",
                    "project_id": "p1",
                    "restore_at": "2026-05-12T00:10:00+08:00",
                    "last_error": "OpenAPI response code=40001",
                }
            ],
        },
    )
    request = {
        "scheduler_status": {
            "project_name": "RoiBang-V2",
            "timezone": "Asia/Shanghai",
            "expected_data_date": {"mode": "yesterday"},
            "jobs": [
                {
                    "job_id": "roibang-project-schedule-restore-due",
                    "display_name": "00:10 项目时段到期恢复",
                    "data_check": {"type": "project_schedule_restore_queue"},
                }
            ],
            "delivery": {"feishu": {"enabled": False}},
        }
    }

    result = build_scheduler_status_report(
        request,
        registry=_registry(),
        db_path=db_path,
        runs_dir=tmp_path / "data/runs",
        repo_root=tmp_path,
        now=datetime(2026, 5, 12, 6, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
        launchctl_status_reader=lambda job_id: {"loaded": True, "runs": 1, "last_exit_code": "0"},
    )

    assert result["ok"] is False
    assert result["jobs"][0]["data_check"]["retry_pending_item_count"] == 1
    assert "恢复队列需要处理" in result["message"]
    assert "失败待处理 1" in result["message"]


def test_scheduler_status_marks_missing_expected_date_as_attention(tmp_path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)
    _write_artifact(
        tmp_path / "data/runs/material_history_backfill/20260512T010000Z.json",
        {"ok": True, "workflow": "material_history_backfill", "execution_enabled": False, "external_api_calls": 1, "summary": {}},
    )

    result = build_scheduler_status_report(
        _request(),
        registry=_registry(),
        db_path=db_path,
        runs_dir=tmp_path / "data/runs",
        repo_root=tmp_path,
        now=datetime(2026, 5, 12, 6, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
        launchctl_status_reader=lambda job_id: {"loaded": True, "runs": 1, "last_exit_code": "0"},
    )

    assert result["ok"] is False
    assert result["jobs"][0]["data_check"]["status"] == "stale"
    assert "缺数据：2026-05-11" in result["message"]


def test_scheduler_status_writes_artifact_and_optional_feishu_delivery(tmp_path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)
    sent: list[str] = []

    result = run_scheduler_status_request(
        {
            **_request(),
            "scheduler_status": {
                **_request()["scheduler_status"],
                "delivery": {
                    "feishu": {
                        "enabled": True,
                        "runtime_file": "data/secrets/feishu.runtime.local.json",
                        "chat_id": "oc_test",
                    }
                },
            },
        },
        registry=_registry(),
        db_path=db_path,
        runs_dir=tmp_path / "data/runs",
        repo_root=tmp_path,
        now=datetime(2026, 5, 12, 6, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
        launchctl_status_reader=lambda job_id: {"loaded": True, "runs": 1, "last_exit_code": "0"},
        feishu_sender=lambda config, text: sent.append(f"{config['chat_id']}|{text}") or {"ok": True},
    )

    assert result["workflow"] == "scheduler_status"
    assert result["external_api_calls"] == 0
    assert result["delivery"]["feishu"]["attempted"] is True
    assert sent and sent[0].startswith("oc_test|RoiBang-V2 定时任务日报")
    assert Path(result["artifact_path"]).exists()
    assert (tmp_path / "data/runs/scheduler_status/latest.md").read_text(encoding="utf-8").startswith("RoiBang-V2")
