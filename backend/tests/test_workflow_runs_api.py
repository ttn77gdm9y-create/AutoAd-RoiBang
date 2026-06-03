import json
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.main import create_app


def test_workflow_run_catalog_exposes_only_safe_business_tasks(tmp_path):
    app = create_app(project_root=tmp_path)
    client = TestClient(app)

    response = client.get("/api/workflow-runs/catalog")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "自动化工作台任务菜单"
    rows = payload["table"]["rows"]
    names = [row["任务名称"] for row in rows]
    assert "素材明细同步" in names
    assert "每日报表同步" in names
    assert "操作日志同步" in names
    assert "同步数据并重算建议" in names
    assert "引力素材库只读探测" in names
    assert {row["真实投放动作"] for row in rows} == {"否"}
    raw_text = json.dumps(payload["raw"], ensure_ascii=False)
    assert "upload_material" not in raw_text
    assert "create_live_execute" not in raw_text
    assert "project_update_execute" not in raw_text


def test_workflow_preview_blocks_unknown_parameters(tmp_path):
    app = create_app(project_root=tmp_path)
    client = TestClient(app)

    response = client.post(
        "/api/workflow-runs/material_daily_sync/preview",
        json={"request": {"product_key": "diandian-hero", "target_date": "2026-06-02", "command": "rm -rf data"}},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["status"] == "blocked"
    assert "未登记参数" in payload["summary"]["blocking_reasons"][0]
    assert "command" in payload["summary"]["blocking_reasons"][0]


def test_workflow_run_writes_fixed_frontend_task_without_mutation_flags(tmp_path, monkeypatch):
    monkeypatch.setattr("backend.app.services.workflow_runner.start_runner", lambda _command, *, cwd: 24680)
    app = create_app(project_root=tmp_path)
    client = TestClient(app)

    response = client.post(
        "/api/workflow-runs/material_daily_sync/run",
        json={"request": {"product_key": "diandian-hero", "target_date": "2026-06-02"}},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "素材明细同步任务已提交"
    assert payload["task"]["pid"] == 24680
    task_path = tmp_path / "data" / "runs" / "frontend_tasks" / f"{payload['task']['task_id']}.json"
    task = json.loads(task_path.read_text(encoding="utf-8"))
    assert task["operation_type"] == "material_daily_sync"
    assert task["request"] == {
        "product_key": "diandian-hero",
        "target_date": "2026-06-02",
    }
    command = task["command"]
    assert command[1:] == [
        "scripts/run_product_automation_job.py",
        "--job",
        "material_daily_sync",
        "--product-key",
        "diandian-hero",
        "--target-date",
        "2026-06-02",
        "--enable-readonly",
    ]
    assert "--execute" not in command
    assert "--yes" not in command


def test_workflow_run_rejects_unregistered_workflow(tmp_path):
    app = create_app(project_root=tmp_path)
    client = TestClient(app)

    response = client.post("/api/workflow-runs/source_material_auto_push/run", json={"request": {}})

    assert response.status_code == 400
    assert "不在自动化工作台任务菜单中" in response.json()["detail"]


def test_results_catalog_includes_workflow_center_result_types(tmp_path):
    app = create_app(project_root=tmp_path)
    client = TestClient(app)

    response = client.get("/api/workflows/catalog")

    assert response.status_code == 200
    labels_by_value = {row["结果类型"]: row["名称"] for row in response.json()["table"]["rows"]}
    assert labels_by_value["product_automation_job_material_daily_sync"] == "素材明细同步"
    assert labels_by_value["product_automation_job_daily_report_sync"] == "每日报表同步"
    assert labels_by_value["product_automation_job_operation_log_sync"] == "操作日志同步"
    assert labels_by_value["product_automation_job_source_material_rollup"] == "源素材表现汇总"
    assert labels_by_value["suggestions_refresh"] == "同步数据并重算建议"
    assert labels_by_value["gravity_api_probe"] == "引力素材库只读探测"
