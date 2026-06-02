import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.services.automation_health import build_automation_health_overview


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _write_fixtures(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "configs" / "scheduler" / "roibang-v2.jobs.example.json",
        {
            "version": 1,
            "timezone": "Asia/Shanghai",
            "jobs": [
                {
                    "id": "daily-success",
                    "name": "每日同步",
                    "category": "readonly_sync",
                    "enabled": True,
                    "schedule": {"type": "cron", "expr": "0 2 * * *", "tz": "Asia/Shanghai"},
                    "script": {"command": ["python3", "scripts/daily.py"], "mode": "foreground"},
                    "policy": {},
                    "result_contract": {
                        "workflow": "demo_daily",
                        "artifact_dir": "data/runs/demo_daily",
                    },
                },
                {
                    "id": "hourly-fail",
                    "name": "小时投放巡检",
                    "category": "delivery_patrol",
                    "enabled": True,
                    "schedule": {"type": "cron", "expr": "30 8-23 * * *", "tz": "Asia/Shanghai"},
                    "script": {"command": ["python3", "scripts/patrol.py"], "mode": "foreground"},
                    "policy": {},
                    "result_contract": {
                        "workflow": "product_automation_job_delivery_patrol",
                        "artifact_dir": "data/runs/product_automation_job_delivery_patrol",
                    },
                },
                {
                    "id": "night-report",
                    "name": "夜间投放日报",
                    "category": "delivery_readonly_report_chain",
                    "enabled": True,
                    "schedule": {"type": "cron", "expr": "50 23 * * *", "tz": "Asia/Shanghai"},
                    "script": {"command": ["python3", "scripts/report.py"], "mode": "foreground"},
                    "policy": {},
                    "result_contract": {
                        "workflow": "delivery_readonly_report_chain",
                        "artifact_dir": "data/runs/delivery_readonly_report_chain",
                    },
                },
                {
                    "id": "disabled-job",
                    "name": "停用任务",
                    "category": "disabled",
                    "enabled": False,
                    "schedule": {"type": "cron", "expr": "0 4 * * *", "tz": "Asia/Shanghai"},
                    "script": {"command": ["python3", "scripts/disabled.py"], "mode": "foreground"},
                    "policy": {},
                    "result_contract": {
                        "workflow": "disabled",
                        "artifact_dir": "data/runs/disabled",
                    },
                },
            ],
        },
    )
    _write_json(
        tmp_path / "configs" / "scheduler-status.local.json",
        {
            "scheduler_status": {
                "timezone": "Asia/Shanghai",
                "jobs": [{"job_id": "daily-success", "display_name": "02:00 每日同步"}],
            }
        },
    )
    _write_json(
        tmp_path / "data" / "runs" / "scheduler_status" / "20260526T220000Z.json",
        {
            "ok": True,
            "workflow": "scheduler_status",
            "summary": {"report_date": "2026-05-27", "expected_data_date": "2026-05-26"},
            "message": "RoiBang-V2 定时任务日报 2026-05-27",
        },
    )
    _write_json(
        tmp_path / "data" / "runs" / "demo_daily" / "20260526T020100Z.json",
        {"ok": True, "workflow": "demo_daily", "summary": {"row_count": 12}},
    )
    _write_json(
        tmp_path / "data" / "runs" / "scheduler" / "daily-success" / "20260526T020100Z.json",
        {
            "ok": True,
            "workflow": "scheduler_job",
            "job_id": "daily-success",
            "started_at": "2026-05-26T02:01:00+08:00",
            "finished_at": "2026-05-26T02:02:00+08:00",
            "duration_seconds": 60,
            "script": {"exit_code": 0},
            "artifact_contract": {
                "ok": True,
                "workflow": "demo_daily",
                "artifact_path": str(tmp_path / "data" / "runs" / "demo_daily" / "20260526T020100Z.json"),
            },
            "violations": [],
        },
    )
    patrol_path = tmp_path / "data" / "runs" / "product_automation_job_delivery_patrol" / "20260526T094500Z.json"
    _write_json(
        patrol_path,
        {
            "ok": False,
            "workflow": "product_automation_job_delivery_patrol",
            "summary": {"job": "delivery_patrol", "product_count": 1},
            "results": [
                {
                    "product": "点点英雄",
                    "product_key": "diandian-hero",
                    "scope_id": "diandian-hero-all",
                    "job": "delivery_patrol",
                    "ok": False,
                    "return_code": 1,
                    "stderr": "RuntimeError: OpenAPI response code=50000: 服务内部错误，请稍后重试",
                }
            ],
        },
    )
    _write_json(
        tmp_path / "data" / "runs" / "scheduler" / "hourly-fail" / "20260526T094500Z.json",
        {
            "ok": False,
            "workflow": "scheduler_job",
            "job_id": "hourly-fail",
            "started_at": "2026-05-26T09:45:00+08:00",
            "finished_at": "2026-05-26T09:46:00+08:00",
            "duration_seconds": 60,
            "script": {"exit_code": 1},
            "artifact_contract": {
                "ok": True,
                "workflow": "product_automation_job_delivery_patrol",
                "artifact_path": str(patrol_path),
            },
            "violations": ["script exited with non-zero status"],
        },
    )


def test_automation_health_builds_readonly_dashboard_rows(tmp_path: Path):
    _write_fixtures(tmp_path)

    payload = build_automation_health_overview(
        project_root=tmp_path,
        configs_dir=tmp_path / "configs",
        runs_dir=tmp_path / "data" / "runs",
        now=datetime(2026, 5, 26, 10, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
    )

    assert payload["summary"]["title"] == "每日自动化健康看板"
    assert payload["summary"]["execution_enabled"] is False
    assert {"label": "启用任务", "value": 3} in payload["summary"]["items"]
    assert {"label": "今日正常", "value": 1} in payload["summary"]["items"]
    assert {"label": "需关注", "value": 1} in payload["summary"]["items"]
    assert {"label": "待今日运行", "value": 1} in payload["summary"]["items"]
    rows = {row["任务"]: row for row in payload["table"]["rows"]}
    assert rows["每日同步"]["今日状态"] == "正常"
    assert rows["小时投放巡检"]["今日状态"] == "需关注"
    assert rows["夜间投放日报"]["今日状态"] == "待今日运行"
    assert rows["小时投放巡检"]["日报检查"] == "未覆盖"
    assert any("未纳入 06:00 定时任务日报检查" in warning for warning in payload["summary"]["warnings"])
    issue_rows = payload["sections"][0]["table"]["rows"]
    assert any("OpenAPI response code=50000" in row["问题"] for row in issue_rows)
    product_rows = payload["sections"][1]["table"]["rows"]
    assert product_rows == [
        {
            "任务": "小时投放巡检",
            "产品": "点点英雄",
            "范围": "点点英雄全量账户",
            "结果": "失败",
            "业务摘要": "失败，OpenAPI response code=50000: 服务内部错误，请稍后重试",
            "结果文件": str(patrol_path := tmp_path / "data" / "runs" / "product_automation_job_delivery_patrol" / "20260526T094500Z.json"),
        }
    ]
    assert str(patrol_path) in product_rows[0]["结果文件"]


def test_automation_health_api_route(tmp_path: Path):
    _write_fixtures(tmp_path)
    client = TestClient(create_app(project_root=tmp_path))

    response = client.get("/api/automation-health/overview")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "每日自动化健康看板"
    assert payload["summary"]["execution_enabled"] is False
