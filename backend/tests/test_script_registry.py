from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.services.script_registry import build_action_task
from backend.app.services.script_registry import list_action_catalog


def test_build_action_task_rejects_unknown_action(tmp_path):
    result = build_action_task("unknown", {}, project_root=tmp_path)

    assert result["ok"] is False
    assert "不在固定脚本白名单" in result["summary"]["blocking_reasons"][0]


def test_build_action_task_creates_probe_task_without_shell_string(tmp_path):
    result = build_action_task("dry_run_probe", {"message": "hello"}, project_root=tmp_path)

    assert result["ok"] is True
    assert result["task"]["operation_type"] == "dry_run_probe"
    assert result["task"]["command"][:2] == ["python3", "-c"]
    assert isinstance(result["task"]["command"], list)


def test_action_execute_requires_confirmation(tmp_path):
    app = create_app(project_root=tmp_path)
    client = TestClient(app)

    response = client.post(
        "/api/actions/dry_run_probe/execute",
        json={"confirmation": "错了", "request": {"message": "hello"}},
    )

    assert response.status_code == 400
    assert "确认执行" in response.json()["detail"]


def test_action_preview_endpoint_returns_chinese_summary(tmp_path):
    app = create_app(project_root=tmp_path)
    client = TestClient(app)

    response = client.post(
        "/api/actions/dry_run_probe/preview",
        json={"request": {"message": "hello"}},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "链路探针预览"
    assert payload["summary"]["execution_enabled"] is True
    assert payload["table"]["rows"][0]["消息"] == "hello"
    assert payload["raw"]["action"] == "dry_run_probe"


def test_action_catalog_lists_only_allowlisted_fixed_scripts(tmp_path):
    catalog = list_action_catalog()

    assert catalog["summary"]["title"] == "链路探针动作目录"
    assert catalog["summary"]["execution_enabled"] is False
    assert catalog["table"]["columns"] == ["动作", "名称", "风险", "说明"]
    assert catalog["table"]["rows"][0]["动作"] == "dry_run_probe"
    assert "任意命令" not in str(catalog["raw"])


def test_action_catalog_endpoint_returns_chinese_summary(tmp_path):
    app = create_app(project_root=tmp_path)
    client = TestClient(app)

    response = client.get("/api/actions/catalog")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "链路探针动作目录"
    assert payload["table"]["rows"][0]["名称"] == "链路探针"
    assert "不触发真实业务动作" in payload["table"]["rows"][0]["说明"]
