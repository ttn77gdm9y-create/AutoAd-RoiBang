import json
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.main import create_app


def _project_management_request() -> dict:
    return {
        "project_update_id": "delete-p2",
        "advertiser_ids": "1001\n1002",
        "action_type": "delete_project",
        "name_contains": "7R",
        "spend_window": "last_3_days",
        "metric_field": "stat_cost",
        "metric_op": "lte",
        "metric_value": "100",
        "output_path": "configs/project-updates/delete-p2.local.json",
    }


def _write_project_update(root: Path) -> str:
    path = root / "configs" / "project-updates" / "delete-p2.local.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "project_update_id": "delete-p2",
                "operator": "郭靖",
                "allowed_target_accounts_path": "configs/control-allowed-accounts.local.json",
                "actions": [
                    {
                        "action_type": "delete_project",
                        "advertiser_id": "1001",
                        "entity_type": "project",
                        "project_id": "p-1",
                        "project_name": "7R-测试-1",
                    },
                    {
                        "action_type": "delete_project",
                        "advertiser_id": "1002",
                        "entity_type": "project",
                        "project_id": "p-2",
                        "project_name": "7R-测试-2",
                    },
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return "configs/project-updates/delete-p2.local.json"


def test_project_management_config_preview_returns_chinese_summary(tmp_path):
    client = TestClient(create_app(project_root=tmp_path))

    response = client.post(
        "/api/project-management/config/preview",
        json=_project_management_request(),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "项目管理配置预览"
    assert payload["summary"]["status"] == "planned"
    assert payload["summary"]["execution_enabled"] is False
    assert {"label": "动作", "value": "删除项目"} in payload["summary"]["items"]
    assert {"label": "账户数", "value": 2} in payload["summary"]["items"]
    assert {"label": "输出 JSON", "value": "configs/project-updates/delete-p2.local.json"} in payload["summary"]["items"]
    assert payload["table"]["columns"] == ["账户 ID", "账户名", "动作", "项目名包含", "数据窗口", "筛选条件", "目标值", "输出 JSON"]
    assert payload["table"]["rows"][0] == {
        "账户 ID": "1001",
        "账户名": "未配置账户名",
        "动作": "删除项目",
        "项目名包含": "7R",
        "数据窗口": "近 3 天",
        "筛选条件": "消耗 小于等于 100",
        "目标值": "",
        "输出 JSON": "configs/project-updates/delete-p2.local.json",
    }
    assert isinstance(payload["raw"]["command"], list)
    assert payload["raw"]["command"][1] == "scripts/run_project_realtime_filter_config.py"
    assert "--execute" not in payload["raw"]["command"]


def test_project_management_config_preview_blocks_missing_accounts(tmp_path):
    client = TestClient(create_app(project_root=tmp_path))

    response = client.post(
        "/api/project-management/config/preview",
        json={"project_update_id": "bad", "advertiser_ids": "", "action_type": "delete_project"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "项目管理配置预览"
    assert payload["summary"]["status"] == "blocked"
    assert payload["summary"]["execution_enabled"] is False
    assert "至少填写一个账户 ID" in payload["summary"]["blocking_reasons"]
    assert payload["table"]["rows"] == []


def test_project_management_config_generate_starts_frontend_task(tmp_path, monkeypatch):
    started = {}

    def fake_start_runner(command, *, cwd):
        started["command"] = command
        started["cwd"] = str(cwd)
        return 4321

    monkeypatch.setattr("backend.app.services.project_management.start_runner", fake_start_runner, raising=False)
    client = TestClient(create_app(project_root=tmp_path))

    response = client.post("/api/project-management/config/generate", json=_project_management_request())

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "项目管理配置生成任务"
    assert payload["summary"]["status"] == "queued"
    assert payload["summary"]["execution_enabled"] is False
    assert {"label": "动作", "value": "删除项目"} in payload["summary"]["items"]
    assert {"label": "账户数", "value": 2} in payload["summary"]["items"]
    task = payload["task"]
    assert task["pid"] == 4321
    assert task["operation_type"] == "project_management_config_generate"
    assert task["command"][1] == "scripts/run_project_realtime_filter_config.py"
    assert "--execute" not in task["command"]
    task_path = tmp_path / "data" / "runs" / task["artifact_path"]
    assert task_path.exists()
    assert started["command"] == ["python3", "scripts/run_frontend_task.py", "--task", str(task_path)]

    tasks = client.get("/api/tasks").json()["items"]
    assert tasks[0]["task_id"] == task["task_id"]
    assert tasks[0]["operation_type"] == "project_management_config_generate"

    operation_payload = client.get(
        "/api/operations",
        params={"operation_type": "project_management_config_generate"},
    ).json()
    operation_rows = operation_payload["table"]["rows"]
    assert len(operation_rows) == 1
    assert operation_rows[0]["任务 ID"] == task["task_id"]
    assert operation_rows[0]["操作"] == "项目管理配置生成"
    assert operation_rows[0]["状态"] == "排队中"
    assert operation_rows[0]["账户数"] == 2
    assert operation_payload["raw"]["rows"][0]["result_status"] == "queued"


def test_project_management_config_generate_keeps_blocked_summary_without_task(tmp_path):
    client = TestClient(create_app(project_root=tmp_path))

    response = client.post(
        "/api/project-management/config/generate",
        json={"project_update_id": "bad", "advertiser_ids": "", "action_type": "delete_project"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["status"] == "blocked"
    assert "task" not in payload
    assert not (tmp_path / "data" / "runs" / "frontend_tasks").exists()


def test_project_management_execute_preview_reads_project_update_summary(tmp_path):
    project_update_path = _write_project_update(tmp_path)
    client = TestClient(create_app(project_root=tmp_path))

    response = client.post(
        "/api/project-management/execute/preview",
        json={"project_update_path": project_update_path},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "项目管理执行预览"
    assert payload["summary"]["status"] == "ready"
    assert payload["summary"]["execution_enabled"] is True
    assert {"label": "配置 ID", "value": "delete-p2"} in payload["summary"]["items"]
    assert {"label": "动作数", "value": 2} in payload["summary"]["items"]
    assert payload["table"]["columns"] == ["账户 ID", "账户名", "项目 ID", "项目名", "动作", "目标值"]
    assert payload["table"]["rows"][0] == {
        "账户 ID": "1001",
        "账户名": "未配置账户名",
        "项目 ID": "p-1",
        "项目名": "7R-测试-1",
        "动作": "删除项目",
        "目标值": "",
    }
    assert payload["raw"]["execute_command"][1] == "scripts/run_project_update_execute.py"
    assert "--execute" in payload["raw"]["execute_command"]
    assert "--yes" in payload["raw"]["execute_command"]


def test_project_management_execute_preview_blocks_missing_config(tmp_path):
    client = TestClient(create_app(project_root=tmp_path))

    response = client.post(
        "/api/project-management/execute/preview",
        json={"project_update_path": "configs/project-updates/missing.local.json"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["status"] == "blocked"
    assert payload["summary"]["execution_enabled"] is False
    assert "项目管理 JSON 不存在" in payload["summary"]["blocking_reasons"][0]


def test_project_management_execute_preview_blocks_missing_project_id(tmp_path):
    project_update_path = tmp_path / "configs" / "project-updates" / "delete-missing-project.local.json"
    project_update_path.parent.mkdir(parents=True)
    project_update_path.write_text(
        json.dumps(
            {
                "project_update_id": "delete-missing-project",
                "actions": [
                    {
                        "action_type": "delete_project",
                        "advertiser_id": "1001",
                        "project_name": "7R-测试",
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    client = TestClient(create_app(project_root=tmp_path))

    response = client.post(
        "/api/project-management/execute/preview",
        json={"project_update_path": "configs/project-updates/delete-missing-project.local.json"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["status"] == "blocked"
    assert payload["summary"]["execution_enabled"] is False
    assert "第 1 条删除项目缺少项目 ID" in payload["summary"]["blocking_reasons"]


def test_project_management_execute_requires_confirmation(tmp_path):
    project_update_path = _write_project_update(tmp_path)
    client = TestClient(create_app(project_root=tmp_path))

    response = client.post(
        "/api/project-management/execute",
        json={"confirmation": "我已确认", "project_update_path": project_update_path},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "真实执行前必须输入：确认执行"


def test_project_management_execute_starts_allowlisted_task(tmp_path, monkeypatch):
    project_update_path = _write_project_update(tmp_path)
    started = {}

    def fake_start_runner(command, *, cwd):
        started["command"] = command
        started["cwd"] = str(cwd)
        return 4321

    monkeypatch.setattr("backend.app.services.project_management.start_runner", fake_start_runner, raising=False)
    client = TestClient(create_app(project_root=tmp_path))

    response = client.post(
        "/api/project-management/execute",
        json={"confirmation": "确认执行", "project_update_path": project_update_path},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "项目管理执行任务"
    assert payload["summary"]["status"] == "queued"
    assert payload["summary"]["execution_enabled"] is True
    task = payload["task"]
    assert task["pid"] == 4321
    assert task["operation_type"] == "project_update_execute"
    assert task["command"][1] == "scripts/run_project_update_execute.py"
    assert "--execute" in task["command"]
    assert "--yes" in task["command"]
    task_path = tmp_path / "data" / "runs" / task["artifact_path"]
    assert task_path.exists()
    assert started["command"] == ["python3", "scripts/run_frontend_task.py", "--task", str(task_path)]

    tasks = client.get("/api/tasks").json()["items"]
    assert tasks[0]["task_id"] == task["task_id"]
    assert tasks[0]["operation_type"] == "project_update_execute"

    operation_payload = client.get("/api/operations", params={"operation_type": "project_update_execute"}).json()
    operation_rows = operation_payload["table"]["rows"]
    assert len(operation_rows) == 1
    assert operation_rows[0]["任务 ID"] == task["task_id"]
    assert operation_rows[0]["操作"] == "项目管理真实执行"
    assert operation_rows[0]["状态"] == "排队中"
    assert operation_rows[0]["账户数"] == 2
    raw_row = operation_payload["raw"]["rows"][0]
    assert raw_row["result_status"] == "queued"
    assert raw_row["execute_artifact_path"] == project_update_path
