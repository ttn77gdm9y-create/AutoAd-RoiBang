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
    assert "引力 Token 获取/刷新" in names
    assert "同步引力素材资料到本地" in names
    assert "引力素材资格汇总" in names
    assert {row["真实投放动作"] for row in rows} == {"否"}
    raw_text = json.dumps(payload["raw"], ensure_ascii=False)
    assert "upload_material" not in raw_text
    assert "create_live_execute" not in raw_text
    assert "project_update_execute" not in raw_text
    assert "upload_material" not in raw_text


def test_workflow_run_catalog_includes_business_controls_and_latest_status(tmp_path):
    runs_dir = tmp_path / "data" / "runs" / "product_automation_job_operation_log_sync"
    runs_dir.mkdir(parents=True)
    artifact_path = runs_dir / "20260603T010203Z.json"
    artifact_path.write_text(
        json.dumps(
            {
                "ok": True,
                "workflow": "product_automation_job_operation_log_sync",
                "status": "completed",
                "external_api_calls": 24,
                "summary": {"job": "operation_log_sync", "product_count": 1, "target_date": "2026-06-02"},
                "results": [
                    {
                        "product_key": "diandian-hero",
                        "product": "点点英雄",
                        "job": "operation_log_sync",
                        "ok": True,
                        "return_code": 0,
                        "parsed_stdout": {
                            "summary": {
                                "planned_request_count": 20,
                                "operation_logs_imported": 214,
                            }
                        },
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    app = create_app(project_root=tmp_path)
    client = TestClient(app)

    response = client.get("/api/workflow-runs/catalog")

    assert response.status_code == 200
    payload = response.json()
    workflows = {item["workflow_id"]: item for item in payload["raw"]["workflows"]}
    material_parameters = {item["name"]: item for item in workflows["material_daily_sync"]["parameters"]}
    assert material_parameters["product_key"]["control"] == "product_select"
    assert material_parameters["target_date"]["control"] == "date_select"

    rows = {row["工作流 ID"]: row for row in payload["table"]["rows"]}
    operation_row = rows["operation_log_sync"]
    assert operation_row["最近状态"] == "已完成"
    assert operation_row["最近结果"] == "点点英雄，目标日期 2026-06-02，计划账户 20，导入日志 214，外部只读调用 24"
    assert operation_row["最近结果文件"] == "data/runs/product_automation_job_operation_log_sync/20260603T010203Z.json"
    assert workflows["operation_log_sync"]["latest_status"]["status_label"] == "已完成"
    assert workflows["operation_log_sync"]["latest_status"]["summary"] == operation_row["最近结果"]


def test_gravity_probe_catalog_uses_business_select_controls(tmp_path):
    app = create_app(project_root=tmp_path)
    client = TestClient(app)

    response = client.get("/api/workflow-runs/catalog")

    assert response.status_code == 200
    payload = response.json()
    workflows = {item["workflow_id"]: item for item in payload["raw"]["workflows"]}
    parameters = {item["name"]: item for item in workflows["gravity_api_probe"]["parameters"]}
    assert parameters["probe_scope"]["control"] == "select"
    assert parameters["probe_scope"]["options"] == [
        {"label": "本地鉴权与文档字段核验", "value": "local_contract"},
        {"label": "外部只读接口探测", "value": "readonly_api"},
    ]
    assert parameters["sample_limit"]["control"] == "select"

    preview = client.post(
        "/api/workflow-runs/gravity_api_probe/preview",
        json={"request": {"probe_scope": "readonly_api", "sample_limit": "5"}},
    )

    assert preview.status_code == 200
    preview_payload = preview.json()
    items = {item["label"]: item["value"] for item in preview_payload["summary"]["items"]}
    assert items["探测范围"] == "外部只读接口探测"
    assert items["样本数量"] == "5 条"
    assert preview_payload["table"]["rows"][0]["参数"] == "引力 Token 文件：data/gravity_token.json；探测范围：外部只读接口探测；样本数量：5 条"
    command = preview_payload["raw"]["command"]
    assert "--probe-scope" in command
    assert "readonly_api" in command
    assert "--sample-limit" in command
    assert "5" in command

    blocked = client.post(
        "/api/workflow-runs/gravity_api_probe/preview",
        json={"request": {"probe_scope": "readonly_api", "sample_limit": "2"}},
    )

    assert blocked.status_code == 200
    blocked_payload = blocked.json()
    assert blocked_payload["summary"]["status"] == "blocked"
    assert "样本数量只能选择" in blocked_payload["summary"]["blocking_reasons"][0]


def test_gravity_token_refresh_workflow_uses_fixed_safe_command(tmp_path):
    app = create_app(project_root=tmp_path)
    client = TestClient(app)

    response = client.post(
        "/api/workflow-runs/gravity_token_refresh/preview",
        json={
            "request": {
                "auth_file": "data/gravity_token.json",
                "username_env": "GRAVITY_USERNAME",
                "password_env": "GRAVITY_PASSWORD",
            }
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "引力 Token 获取/刷新运行预览"
    assert payload["summary"]["risk_level"] == "medium"
    assert payload["summary"]["execution_enabled"] is False
    assert payload["table"]["rows"][0]["真实投放动作"] == "否"
    assert payload["table"]["rows"][0]["AI 自动运行"] == "不允许"
    assert payload["table"]["rows"][0]["参数"] == (
        "引力 Token 文件：data/gravity_token.json；账号环境变量：GRAVITY_USERNAME；密码环境变量：GRAVITY_PASSWORD"
    )
    command = payload["raw"]["command"]
    assert command[1:] == [
        "scripts/run_gravity_token_refresh.py",
        "--auth-file",
        "data/gravity_token.json",
        "--username-env",
        "GRAVITY_USERNAME",
        "--password-env",
        "GRAVITY_PASSWORD",
    ]
    assert "upload_material" not in " ".join(command)
    assert "--execute" not in command
    assert "--password" not in command


def test_gravity_material_sync_workflow_uses_fixed_safe_command(tmp_path):
    app = create_app(project_root=tmp_path)
    client = TestClient(app)

    response = client.post(
        "/api/workflow-runs/gravity_material_sync/preview",
        json={"request": {"product": "点点英雄", "page_size": "100", "max_pages": "20"}},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "同步引力素材资料到本地运行预览"
    assert payload["summary"]["execution_enabled"] is False
    assert payload["table"]["rows"][0]["真实投放动作"] == "否"
    assert payload["table"]["rows"][0]["参数"] == "产品：点点英雄；引力 Token 文件：data/gravity_token.json；每页素材数：100；最多页数：20"
    command = payload["raw"]["command"]
    assert command[1:] == [
        "scripts/run_gravity_material_sync.py",
        "--product",
        "点点英雄",
        "--auth-file",
        "data/gravity_token.json",
        "--page-size",
        "100",
        "--max-pages",
        "20",
    ]
    assert "upload_material" not in " ".join(command)
    assert "--execute" not in command


def test_gravity_material_qualification_workflow_uses_fixed_safe_command(tmp_path):
    app = create_app(project_root=tmp_path)
    client = TestClient(app)

    response = client.post(
        "/api/workflow-runs/gravity_material_qualification/preview",
        json={"request": {"product": "点点英雄"}},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "引力素材资格汇总运行预览"
    assert payload["summary"]["execution_enabled"] is False
    assert payload["table"]["rows"][0]["真实投放动作"] == "否"
    assert payload["table"]["rows"][0]["参数"] == "产品：点点英雄"
    command = payload["raw"]["command"]
    assert command[1:] == [
        "scripts/run_gravity_material_qualification.py",
        "--product",
        "点点英雄",
    ]
    assert "upload_material" not in " ".join(command)
    assert "--execute" not in command


def test_results_catalog_includes_gravity_material_sync(tmp_path):
    app = create_app(project_root=tmp_path)
    client = TestClient(app)

    response = client.get("/api/workflows/catalog")

    assert response.status_code == 200
    labels_by_value = {item["value"]: item["label"] for item in response.json()["raw"]["workflows"]}
    assert labels_by_value["gravity_token_refresh"] == "引力 Token 获取/刷新"
    assert labels_by_value["gravity_material_sync"] == "同步引力素材资料到本地"
    assert labels_by_value["gravity_material_qualification"] == "引力素材资格汇总"


def test_gravity_probe_catalog_latest_status_says_token_state_and_blocking_reason(tmp_path):
    runs_dir = tmp_path / "data" / "runs" / "gravity_api_probe"
    runs_dir.mkdir(parents=True)
    artifact_path = runs_dir / "20260603T154608Z.json"
    artifact_path.write_text(
        json.dumps(
            {
                "ok": False,
                "workflow": "gravity_api_probe",
                "status": "blocked",
                "external_api_calls": 0,
                "summary": {
                    "auth_file_exists": True,
                    "auth_field_status": "完整",
                    "token_status": "expired",
                    "token_status_label": "已过期",
                    "probe_scope_label": "外部只读接口探测",
                },
                "blocking_reasons": ["Token 已过期：2026-06-03T08:00:00+08:00"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    app = create_app(project_root=tmp_path)
    client = TestClient(app)

    response = client.get("/api/workflow-runs/catalog")

    assert response.status_code == 200
    rows = {row["工作流 ID"]: row for row in response.json()["table"]["rows"]}
    assert rows["gravity_api_probe"]["最近状态"] == "已阻止"
    assert rows["gravity_api_probe"]["最近结果"] == (
        "Token 已过期，阻塞原因 Token 已过期：2026-06-03T08:00:00+08:00，外部只读调用 0"
    )


def test_gravity_token_catalog_latest_status_explains_missing_env_plainly(tmp_path):
    runs_dir = tmp_path / "data" / "runs" / "gravity_token_refresh"
    runs_dir.mkdir(parents=True)
    artifact_path = runs_dir / "20260605T025401Z.json"
    artifact_path.write_text(
        json.dumps(
            {
                "ok": False,
                "workflow": "gravity_token_refresh",
                "status": "blocked",
                "external_api_calls": 0,
                "summary": {
                    "auth_file": "data/gravity_token.json",
                    "auth_file_exists": False,
                    "token_status_label": "缺失",
                    "token_present": False,
                },
                "blocking_reasons": ["缺少环境变量：GRAVITY_USERNAME、GRAVITY_PASSWORD"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    app = create_app(project_root=tmp_path)
    client = TestClient(app)

    response = client.get("/api/workflow-runs/catalog")

    assert response.status_code == 200
    rows = {row["工作流 ID"]: row for row in response.json()["table"]["rows"]}
    assert rows["gravity_token_refresh"]["最近状态"] == "已阻塞"
    assert rows["gravity_token_refresh"]["最近结果"] == "缺少引力登录环境变量，未访问引力，未生成 Token，未执行业务动作"


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
    assert labels_by_value["gravity_token_refresh"] == "引力 Token 获取/刷新"
