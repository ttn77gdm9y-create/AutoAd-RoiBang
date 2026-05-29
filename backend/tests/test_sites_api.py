import json

from fastapi.testclient import TestClient

from backend.app.main import create_app


def _site_status_request() -> dict:
    return {"advertiser_id": "2001", "site_ids": "9001\n9002", "status": "delete"}


def _site_template_request() -> dict:
    return {
        "source_advertiser_id": "2000",
        "source_site_id": "8000",
        "game_instance_id": "3000",
        "game_path": "?turbo_promoted_object_id=abc",
        "target_advertiser_ids": "2001\n2002",
        "site_name_prefix": "点点英雄本地落地页",
        "edit_existing": False,
        "publish": True,
    }


def _write_accounts(root) -> None:
    accounts_path = root / "configs" / "accounts" / "product-accounts.local.json"
    accounts_path.parent.mkdir(parents=True)
    accounts_path.write_text(
        json.dumps(
            {
                "accounts": [
                    {"advertiser_id": "2000", "advertiser_name": "源账户", "status": "active"},
                    {"advertiser_id": "2001", "advertiser_name": "目标账户一", "status": "active"},
                    {"advertiser_id": "2002", "advertiser_name": "目标账户二", "status": "active"},
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_site_status_preview_returns_chinese_summary(tmp_path):
    _write_accounts(tmp_path)
    client = TestClient(create_app(project_root=tmp_path))

    response = client.post("/api/sites/status/preview", json=_site_status_request())

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "落地页状态更新预览"
    assert payload["summary"]["status"] == "ready"
    assert payload["summary"]["execution_enabled"] is True
    assert {"label": "账户数", "value": 1} in payload["summary"]["items"]
    assert {"label": "落地页数", "value": 2} in payload["summary"]["items"]
    assert payload["table"]["columns"] == ["账户 ID", "账户名", "落地页 ID", "目标状态"]
    assert payload["table"]["rows"][0] == {"账户 ID": "2001", "账户名": "目标账户一", "落地页 ID": "9001", "目标状态": "删除"}
    assert payload["raw"]["execute_command"][1] == "scripts/run_site_status_update.py"
    assert "--execute" in payload["raw"]["execute_command"]


def test_site_status_preview_blocks_missing_target_status(tmp_path):
    client = TestClient(create_app(project_root=tmp_path))

    response = client.post("/api/sites/status/preview", json={"advertiser_id": "2001", "site_ids": "9001", "status": ""})

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["status"] == "blocked"
    assert payload["summary"]["execution_enabled"] is False
    assert payload["summary"]["blocking_reasons"] == ["必须明确选择目标状态"]


def test_site_status_preview_blocks_missing_site_pairs(tmp_path):
    client = TestClient(create_app(project_root=tmp_path))

    response = client.post("/api/sites/status/preview", json={"advertiser_id": "2001", "site_ids": "", "status": "delete"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["status"] == "blocked"
    assert payload["summary"]["execution_enabled"] is False
    assert "missing site pairs" in payload["summary"]["blocking_reasons"]


def test_site_status_execute_requires_confirmation(tmp_path):
    client = TestClient(create_app(project_root=tmp_path))

    response = client.post(
        "/api/sites/status/execute",
        json={"confirmation": "我已确认", **_site_status_request()},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "真实执行前必须输入：确认执行"


def test_site_status_execute_starts_allowlisted_task(tmp_path, monkeypatch):
    started = {}

    def fake_start_runner(command, *, cwd):
        started["command"] = command
        started["cwd"] = str(cwd)
        return 4321

    monkeypatch.setattr("backend.app.services.sites.start_runner", fake_start_runner, raising=False)
    client = TestClient(create_app(project_root=tmp_path))

    response = client.post(
        "/api/sites/status/execute",
        json={"confirmation": "确认执行", **_site_status_request()},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "落地页状态更新任务"
    assert payload["summary"]["status"] == "queued"
    assert payload["summary"]["execution_enabled"] is True
    task = payload["task"]
    assert task["pid"] == 4321
    assert task["operation_type"] == "site_status_update"
    assert task["command"][1] == "scripts/run_site_status_update.py"
    assert "--execute" in task["command"]
    task_path = tmp_path / "data" / "runs" / task["artifact_path"]
    assert task_path.exists()
    assert started["command"] == ["python3", "scripts/run_frontend_task.py", "--task", str(task_path)]

    tasks = client.get("/api/tasks").json()["items"]
    assert tasks[0]["task_id"] == task["task_id"]
    assert tasks[0]["operation_type"] == "site_status_update"

    operations = client.get("/api/operations", params={"operation_type": "site_status_update"}).json()
    assert operations["table"]["rows"][0]["任务 ID"] == task["task_id"]
    assert operations["table"]["rows"][0]["操作"] == "落地页状态更新"
    assert operations["table"]["rows"][0]["状态"] == "排队中"
    assert operations["table"]["rows"][0]["账户数"] == 1
    assert operations["raw"]["rows"][0]["result_status"] == "queued"


def test_site_handsel_results_returns_latest_chinese_summary(tmp_path):
    _write_accounts(tmp_path)
    artifact_dir = tmp_path / "data" / "runs" / "site_handsel"
    artifact_dir.mkdir(parents=True)
    (artifact_dir / "20260527T160000Z.json").write_text(
        json.dumps(
            {
                "workflow": "site_handsel",
                "status": "completed",
                "summary": {
                    "source_advertiser_id": "2000",
                    "site_id": "8000",
                    "target_count": 2,
                    "success_count": 2,
                    "error_count": 0,
                },
                "success_list": [
                    {"target_advertiser_id": "2001", "site_id": "9001", "origin_site_id": "8000"},
                    {"target_advertiser_id": "2002", "site_id": "9002", "origin_site_id": "8000"},
                ],
                "error_list": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    client = TestClient(create_app(project_root=tmp_path))

    response = client.get("/api/sites/handsel-results")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "落地页转赠结果"
    assert {"label": "源账户", "value": "源账户（2000）"} in payload["summary"]["items"]
    assert {"label": "成功数", "value": 2} in payload["summary"]["items"]
    assert payload["table"]["columns"] == ["目标账户 ID", "账户名", "新落地页 ID", "原落地页 ID", "结果"]
    assert payload["table"]["rows"][0] == {
        "目标账户 ID": "2001",
        "账户名": "目标账户一",
        "新落地页 ID": "9001",
        "原落地页 ID": "8000",
        "结果": "成功",
    }


def test_site_template_foundation_preview_returns_chinese_summary(tmp_path):
    _write_accounts(tmp_path)
    client = TestClient(create_app(project_root=tmp_path))

    response = client.post("/api/sites/template-foundation/preview", json=_site_template_request())

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "模板建站预览"
    assert payload["summary"]["status"] == "ready"
    assert payload["summary"]["execution_enabled"] is True
    assert {"label": "源账户", "value": "源账户（2000）"} in payload["summary"]["items"]
    assert {"label": "目标账户数", "value": 2} in payload["summary"]["items"]
    assert payload["table"]["columns"] == ["账户 ID", "账户名", "现有落地页 ID", "动作", "小游戏路径", "发布"]
    assert payload["table"]["rows"][0] == {
        "账户 ID": "2001",
        "账户名": "目标账户一",
        "现有落地页 ID": "",
        "动作": "新建落地页",
        "小游戏路径": "?turbo_promoted_object_id=abc",
        "发布": "是",
    }
    assert payload["raw"]["execute_command"][1] == "scripts/run_site_template_foundation.py"
    assert "--execute" in payload["raw"]["execute_command"]


def test_site_template_foundation_preview_blocks_missing_explicit_mode_and_publish(tmp_path):
    request = dict(_site_template_request())
    request.pop("edit_existing")
    request.pop("publish")
    client = TestClient(create_app(project_root=tmp_path))

    response = client.post("/api/sites/template-foundation/preview", json=request)

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["status"] == "blocked"
    assert payload["summary"]["execution_enabled"] is False
    assert payload["summary"]["blocking_reasons"] == ["必须明确选择目标类型", "必须明确选择执行后是否发布"]


def test_site_template_foundation_execute_starts_allowlisted_task_and_logs(tmp_path, monkeypatch):
    started = {}

    def fake_start_runner(command, *, cwd):
        started["command"] = command
        started["cwd"] = str(cwd)
        return 4321

    monkeypatch.setattr("backend.app.services.sites.start_runner", fake_start_runner, raising=False)
    client = TestClient(create_app(project_root=tmp_path))

    response = client.post(
        "/api/sites/template-foundation/execute",
        json={"confirmation": "确认执行", **_site_template_request()},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "模板建站任务"
    assert payload["summary"]["status"] == "queued"
    task = payload["task"]
    assert task["pid"] == 4321
    assert task["operation_type"] == "site_template_foundation"
    assert task["command"][1] == "scripts/run_site_template_foundation.py"
    assert "--execute" in task["command"]
    task_path = tmp_path / "data" / "runs" / task["artifact_path"]
    assert task_path.exists()
    assert started["command"] == ["python3", "scripts/run_frontend_task.py", "--task", str(task_path)]

    operations = client.get("/api/operations", params={"operation_type": "site_template_foundation"}).json()
    assert operations["table"]["rows"][0]["任务 ID"] == task["task_id"]
    assert operations["table"]["rows"][0]["操作"] == "模板建站"
    assert operations["table"]["rows"][0]["状态"] == "排队中"
    assert operations["table"]["rows"][0]["账户数"] == 2
