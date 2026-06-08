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


def _write_account_remark_update(root: Path, *, executable: bool = False) -> str:
    path = root / "configs" / "account-updates" / "remark-001.local.json"
    path.parent.mkdir(parents=True)
    http = (
        {
            "enabled": True,
            "url": "https://business.oceanengine.com/api/test/update_remark",
            "session": {"cookie": "cookie-value", "csrf_token": "csrf-value"},
        }
        if executable
        else {"enabled": False}
    )
    path.write_text(
        json.dumps(
            {
                "account_remark_update": {
                    "update_id": "remark-001",
                    "remark": "黑旗游戏",
                    "advertiser_ids": ["1001", "1002"],
                    "http": http,
                }
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return "configs/account-updates/remark-001.local.json"


def _write_execute_runtime(root: Path) -> None:
    path = root / "configs" / "project-update-execute.local.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"create_http_transport": {"allow_mutation": True}}, ensure_ascii=False),
        encoding="utf-8",
    )


def test_account_remark_config_preview_returns_chinese_summary(tmp_path):
    accounts_path = tmp_path / "configs" / "accounts" / "product-accounts.local.json"
    accounts_path.parent.mkdir(parents=True)
    accounts_path.write_text(
        json.dumps(
            {
                "accounts": [
                    {"advertiser_id": "1001", "advertiser_name": "账户一", "status": "active"},
                    {"advertiser_id": "1002", "advertiser_name": "账户二", "status": "active"},
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    client = TestClient(create_app(project_root=tmp_path))

    response = client.post("/api/account-remarks/config/preview", json=_account_remark_request())

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "账户备注配置预览"
    assert payload["summary"]["status"] == "planned"
    assert payload["summary"]["execution_enabled"] is False
    assert {"label": "账户数", "value": 2} in payload["summary"]["items"]
    assert payload["table"]["columns"] == ["账户 ID", "账户名", "目标备注", "输出 JSON"]
    assert payload["table"]["rows"][0] == {
        "账户 ID": "1001",
        "账户名": "账户一",
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
    assert "必须明确填写本次账户 ID" in payload["summary"]["blocking_reasons"]


def test_account_remark_config_preview_extracts_chinese_account_id_column(tmp_path):
    client = TestClient(create_app(project_root=tmp_path))

    response = client.post(
        "/api/account-remarks/config/preview",
        json={
            **_account_remark_request(),
            "advertiser_ids": "产品\t账户 ID\t账户名\n点点英雄\t1001\t账户一\n点点英雄\t1002\t账户二",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["status"] == "planned"
    assert {"label": "账户数", "value": 2} in payload["summary"]["items"]
    assert [row["账户 ID"] for row in payload["table"]["rows"]] == ["1001", "1002"]


def test_account_remark_config_preview_blocks_account_names_in_account_id_input(tmp_path):
    client = TestClient(create_app(project_root=tmp_path))

    response = client.post(
        "/api/account-remarks/config/preview",
        json={
            **_account_remark_request(),
            "advertiser_ids": "盛步-点点英雄-微小-至也-151\n盛步-点点英雄-微小-至也-152",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["status"] == "blocked"
    assert payload["table"]["rows"] == []
    assert payload["summary"]["blocking_reasons"] == [
        "账户 ID 必须是数字：第 1 行「盛步-点点英雄-微小-至也-151」、第 2 行「盛步-点点英雄-微小-至也-152」。请粘贴数字账户 ID，或粘贴带“账户 ID”表头的表格。"
    ]


def test_account_remark_config_preview_blocks_missing_required_choices(tmp_path):
    client = TestClient(create_app(project_root=tmp_path))

    response = client.post(
        "/api/account-remarks/config/preview",
        json={"update_id": "", "remark": "", "advertiser_ids": "", "output_path": ""},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["status"] == "blocked"
    assert payload["summary"]["execution_enabled"] is False
    assert payload["summary"]["blocking_reasons"] == [
        "必须明确填写目标备注",
        "必须明确填写本次账户 ID",
    ]
    assert payload["table"]["rows"] == []


def test_account_remark_config_preview_auto_fills_internal_id_and_output_path(tmp_path):
    client = TestClient(create_app(project_root=tmp_path))

    response = client.post(
        "/api/account-remarks/config/preview",
        json={**_account_remark_request(), "update_id": "", "output_path": ""},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["status"] == "planned"
    assert "必须明确填写配置 ID" not in payload["summary"]["blocking_reasons"]
    assert "必须明确填写账户备注 JSON 输出路径" not in payload["summary"]["blocking_reasons"]
    update_id = next(item["value"] for item in payload["summary"]["items"] if item["label"] == "配置 ID")
    output_json = next(item["value"] for item in payload["summary"]["items"] if item["label"] == "输出 JSON")
    assert update_id.startswith("account-remark-")
    assert output_json == f"configs/account-updates/{update_id}.local.json"


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
    assert operations["table"]["rows"][0]["关联任务"] == task["task_id"]
    assert operations["table"]["rows"][0]["操作"] == "账户备注配置生成"
    assert operations["table"]["rows"][0]["状态"] == "排队中"
    assert operations["table"]["rows"][0]["账户数"] == 2
    assert operations["raw"]["rows"][0]["execute_artifact_path"] == "configs/account-updates/remark-001.local.json"


def test_account_remark_execute_preview_reads_config_summary(tmp_path):
    accounts_path = tmp_path / "configs" / "accounts" / "product-accounts.local.json"
    accounts_path.parent.mkdir(parents=True)
    accounts_path.write_text(
        json.dumps(
            {
                "accounts": [
                    {"advertiser_id": "1001", "advertiser_name": "账户一", "status": "active"},
                    {"advertiser_id": "1002", "advertiser_name": "账户二", "status": "active"},
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    account_remark_update_path = _write_account_remark_update(tmp_path, executable=True)
    _write_execute_runtime(tmp_path)
    client = TestClient(create_app(project_root=tmp_path))

    response = client.post(
        "/api/account-remarks/execute/preview",
        json={"account_remark_update_path": account_remark_update_path, "config_source": "current_generated"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "真实修改账户备注预览"
    assert payload["summary"]["status"] == "ready"
    assert payload["summary"]["risk_level"] == "high"
    assert payload["summary"]["execution_enabled"] is True
    assert payload["summary"]["execution_label"] == "待确认真实修改"
    assert {"label": "配置来源", "value": "本页刚生成的新配置"} in payload["summary"]["items"]
    assert {"label": "账户数", "value": 2} in payload["summary"]["items"]
    assert payload["table"]["columns"] == ["账户 ID", "账户名", "目标备注"]
    assert payload["table"]["rows"][0] == {"账户 ID": "1001", "账户名": "账户一", "目标备注": "黑旗游戏"}
    assert payload["raw"]["execute_command"][1] == "scripts/run_account_remark_update.py"
    assert "--execute" in payload["raw"]["execute_command"]
    assert "--yes" in payload["raw"]["execute_command"]


def test_account_remark_execute_preview_blocks_when_real_execute_config_missing(tmp_path):
    account_remark_update_path = _write_account_remark_update(tmp_path)
    client = TestClient(create_app(project_root=tmp_path))

    response = client.post(
        "/api/account-remarks/execute/preview",
        json={"account_remark_update_path": account_remark_update_path, "config_source": "current_generated"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "真实修改账户备注预览"
    assert payload["summary"]["status"] == "blocked"
    assert payload["summary"]["execution_enabled"] is False
    assert payload["summary"]["execution_label"] == "真实修改未执行"
    assert "本次未修改任何账户备注。" in payload["summary"]["warnings"]
    assert "真实修改账户备注前，需要在固定执行配置里开启 create_http_transport.allow_mutation=true。" in payload["summary"]["blocking_reasons"]
    assert "账户备注 JSON 里没有开启 HTTP 执行开关，系统未发起真实修改。" in payload["summary"]["blocking_reasons"]
    assert "缺少工作台登录 Cookie，系统未发起真实修改。" in payload["summary"]["blocking_reasons"]
    assert "缺少工作台 CSRF Token，系统未发起真实修改。" in payload["summary"]["blocking_reasons"]
    assert payload["table"]["rows"][0] == {"账户 ID": "1001", "账户名": "未配置账户名", "目标备注": "黑旗游戏"}


def test_account_remark_execute_preview_blocks_non_numeric_account_ids(tmp_path):
    account_remark_update_path = _write_account_remark_update(tmp_path, executable=True)
    path = tmp_path / account_remark_update_path
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["account_remark_update"]["advertiser_ids"] = ["盛步-点点英雄-微小-至也-151"]
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    _write_execute_runtime(tmp_path)
    client = TestClient(create_app(project_root=tmp_path))

    response = client.post(
        "/api/account-remarks/execute/preview",
        json={"account_remark_update_path": account_remark_update_path, "config_source": "current_generated"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["status"] == "blocked"
    assert payload["summary"]["execution_enabled"] is False
    assert payload["summary"]["blocking_reasons"] == [
        "账户 ID 必须是数字：第 1 行「盛步-点点英雄-微小-至也-151」。请粘贴数字账户 ID，或粘贴带“账户 ID”表头的表格。"
    ]


def test_account_remark_execute_requires_confirmation(tmp_path):
    account_remark_update_path = _write_account_remark_update(tmp_path, executable=True)
    _write_execute_runtime(tmp_path)
    client = TestClient(create_app(project_root=tmp_path))

    response = client.post(
        "/api/account-remarks/execute",
        json={"confirmation": "我已确认", "account_remark_update_path": account_remark_update_path},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "真实执行前必须输入：确认执行"


def test_account_remark_execute_starts_allowlisted_task(tmp_path, monkeypatch):
    account_remark_update_path = _write_account_remark_update(tmp_path, executable=True)
    _write_execute_runtime(tmp_path)
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
    assert payload["summary"]["title"] == "真实修改账户备注任务"
    assert payload["summary"]["status"] == "queued"
    assert payload["summary"]["execution_enabled"] is True
    assert payload["summary"]["execution_label"] == "真实修改任务"
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
    assert operations["table"]["rows"][0]["关联任务"] == task["task_id"]
    assert operations["table"]["rows"][0]["操作"] == "真实修改账户备注"
    assert operations["table"]["rows"][0]["状态"] == "排队中"
    assert operations["table"]["rows"][0]["账户数"] == 2
    assert operations["raw"]["rows"][0]["execute_artifact_path"] == account_remark_update_path
