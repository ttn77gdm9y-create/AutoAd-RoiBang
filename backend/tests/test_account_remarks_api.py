import json
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.main import create_app


def _account_remark_request() -> dict:
    return {
        "update_id": "remark-001",
        "remark": "黑旗游戏",
        "advertiser_ids": "1001\n1002",
        "output_path": "configs/account-updates/remark-001.local.json",
    }


def _write_account_remark_update(root: Path) -> str:
    path = root / "configs" / "account-updates" / "remark-001.local.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "account_remark_update": {
                    "update_id": "remark-001",
                    "remark": "黑旗游戏",
                    "advertiser_ids": ["1001", "1002"],
                    "http": {"enabled": False},
                }
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return "configs/account-updates/remark-001.local.json"


def test_account_remark_config_preview_returns_chinese_summary(tmp_path):
    client = TestClient(create_app(project_root=tmp_path))

    response = client.post("/api/account-remarks/config/preview", json=_account_remark_request())

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "账户备注配置预览"
    assert payload["summary"]["status"] == "planned"
    assert payload["summary"]["execution_enabled"] is False
    assert {"label": "账户数", "value": 2} in payload["summary"]["items"]
    assert payload["table"]["columns"] == ["账户 ID", "目标备注", "输出 JSON"]
    assert payload["table"]["rows"][0] == {
        "账户 ID": "1001",
        "目标备注": "黑旗游戏",
        "输出 JSON": "configs/account-updates/remark-001.local.json",
    }
    assert payload["raw"]["command"][1] == "scripts/run_account_remark_update_config.py"
    assert "--execute" not in payload["raw"]["command"]


def test_account_remark_config_preview_blocks_missing_accounts(tmp_path):
    client = TestClient(create_app(project_root=tmp_path))

    response = client.post(
        "/api/account-remarks/config/preview",
        json={"update_id": "bad", "remark": "黑旗游戏", "advertiser_ids": ""},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["status"] == "blocked"
    assert "至少填写一个账户 ID" in payload["summary"]["blocking_reasons"]


def test_account_remark_config_generate_starts_frontend_task(tmp_path, monkeypatch):
    started = {}

    def fake_start_runner(command, *, cwd):
        started["command"] = command
        started["cwd"] = str(cwd)
        return 4321

    monkeypatch.setattr("backend.app.services.account_remarks.start_runner", fake_start_runner, raising=False)
    client = TestClient(create_app(project_root=tmp_path))

    response = client.post("/api/account-remarks/config/generate", json=_account_remark_request())

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "账户备注配置生成任务"
    assert payload["summary"]["status"] == "queued"
    task = payload["task"]
    assert task["pid"] == 4321
    assert task["operation_type"] == "account_remark_config_generate"
    assert task["command"][1] == "scripts/run_account_remark_update_config.py"
    task_path = tmp_path / "data" / "runs" / task["artifact_path"]
    assert task_path.exists()
    assert started["command"] == ["python3", "scripts/run_frontend_task.py", "--task", str(task_path)]

    operations = client.get("/api/operations", params={"operation_type": "account_remark_config_generate"}).json()
    assert operations["table"]["rows"][0]["任务 ID"] == task["task_id"]
    assert operations["table"]["rows"][0]["操作"] == "account_remark_config_generate"
    assert operations["table"]["rows"][0]["状态"] == "queued"
    assert operations["table"]["rows"][0]["账户数"] == 2
    assert operations["raw"]["rows"][0]["execute_artifact_path"] == "configs/account-updates/remark-001.local.json"


def test_account_remark_execute_preview_reads_config_summary(tmp_path):
    account_remark_update_path = _write_account_remark_update(tmp_path)
    client = TestClient(create_app(project_root=tmp_path))

    response = client.post(
        "/api/account-remarks/execute/preview",
        json={"account_remark_update_path": account_remark_update_path},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "账户备注执行预览"
    assert payload["summary"]["status"] == "ready"
    assert payload["summary"]["execution_enabled"] is True
    assert {"label": "账户数", "value": 2} in payload["summary"]["items"]
    assert payload["table"]["columns"] == ["账户 ID", "目标备注"]
    assert payload["table"]["rows"][0] == {"账户 ID": "1001", "目标备注": "黑旗游戏"}
    assert payload["raw"]["execute_command"][1] == "scripts/run_account_remark_update.py"
    assert "--execute" in payload["raw"]["execute_command"]
    assert "--yes" in payload["raw"]["execute_command"]


def test_account_remark_execute_requires_confirmation(tmp_path):
    account_remark_update_path = _write_account_remark_update(tmp_path)
    client = TestClient(create_app(project_root=tmp_path))

    response = client.post(
        "/api/account-remarks/execute",
        json={"confirmation": "我已确认", "account_remark_update_path": account_remark_update_path},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "真实执行前必须输入：确认执行"


def test_account_remark_execute_starts_allowlisted_task(tmp_path, monkeypatch):
    account_remark_update_path = _write_account_remark_update(tmp_path)
    started = {}

    def fake_start_runner(command, *, cwd):
        started["command"] = command
        started["cwd"] = str(cwd)
        return 4321

    monkeypatch.setattr("backend.app.services.account_remarks.start_runner", fake_start_runner, raising=False)
    client = TestClient(create_app(project_root=tmp_path))

    response = client.post(
        "/api/account-remarks/execute",
        json={"confirmation": "确认执行", "account_remark_update_path": account_remark_update_path},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "账户备注执行任务"
    assert payload["summary"]["status"] == "queued"
    assert payload["summary"]["execution_enabled"] is True
    task = payload["task"]
    assert task["pid"] == 4321
    assert task["operation_type"] == "account_remark_update"
    assert task["command"][1] == "scripts/run_account_remark_update.py"
    assert "--execute" in task["command"]
    assert "--yes" in task["command"]
    task_path = tmp_path / "data" / "runs" / task["artifact_path"]
    assert task_path.exists()
    assert started["command"] == ["python3", "scripts/run_frontend_task.py", "--task", str(task_path)]

    tasks = client.get("/api/tasks").json()["items"]
    assert tasks[0]["task_id"] == task["task_id"]
    assert tasks[0]["operation_type"] == "account_remark_update"

    operations = client.get("/api/operations", params={"operation_type": "account_remark_update"}).json()
    assert operations["table"]["rows"][0]["任务 ID"] == task["task_id"]
    assert operations["table"]["rows"][0]["操作"] == "account_remark_update"
    assert operations["table"]["rows"][0]["状态"] == "queued"
    assert operations["table"]["rows"][0]["账户数"] == 2
    assert operations["raw"]["rows"][0]["execute_artifact_path"] == account_remark_update_path
