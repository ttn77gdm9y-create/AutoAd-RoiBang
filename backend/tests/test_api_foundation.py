import json

from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.services.summary_builder import build_json_summary


def test_health_endpoint_returns_ok(tmp_path):
    app = create_app(project_root=tmp_path)
    client = TestClient(app)

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_local_react_dev_ports_are_allowed_by_cors(tmp_path):
    app = create_app(project_root=tmp_path)
    client = TestClient(app)

    response = client.options(
        "/api/sites/status/preview",
        headers={
            "Origin": "http://127.0.0.1:5180",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:5180"


def test_settings_endpoint_exposes_local_paths(tmp_path):
    app = create_app(project_root=tmp_path)
    client = TestClient(app)

    response = client.get("/api/settings")

    assert response.status_code == 200
    payload = response.json()
    assert payload["project_root"] == str(tmp_path)
    assert payload["runs_dir"].endswith("data/runs")
    assert payload["streamlit_status"] == "legacy_retained"


def test_settings_summary_endpoint_returns_chinese_summary(tmp_path):
    app = create_app(project_root=tmp_path)
    client = TestClient(app)

    response = client.get("/api/settings/summary")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "系统设置"
    assert payload["summary"]["execution_enabled"] is False
    assert payload["table"]["columns"] == ["配置项", "值"]
    assert payload["table"]["rows"][0]["配置项"] == "项目目录"
    assert payload["raw"]["settings"]["project_root"] == str(tmp_path)


def test_settings_readiness_endpoint_returns_replacement_acceptance_checklist(tmp_path):
    app = create_app(project_root=tmp_path)
    client = TestClient(app)

    response = client.get("/api/settings/readiness")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "React 替换验收清单"
    assert payload["summary"]["status"] == "trial_ready"
    assert payload["summary"]["execution_enabled"] is False
    assert {"label": "验收项", "value": 10} in payload["summary"]["items"]
    assert {"label": "已满足", "value": 10} in payload["summary"]["items"]
    assert "Streamlit 已标记为旧版保留入口，验收完成前暂不删除。" in payload["summary"]["warnings"]
    assert payload["table"]["columns"] == ["验收项", "状态", "说明"]
    assert payload["table"]["rows"][0] == {
        "验收项": "主要页面不依赖 Streamlit",
        "状态": "ready",
        "说明": "首页、账户库、投放建议工作台、创建计划、项目管理、落地页、账户备注、任务、操作日志、结果中心、产品自动化配置和系统设置均由 React 路由承载。",
    }
    readiness_text = json.dumps(payload["table"]["rows"], ensure_ascii=False)
    assert "任务中心展示业务进度和高级日志" in readiness_text
    assert "操作日志展示业务内容和结果摘要" in readiness_text
    assert "stdout" not in readiness_text
    assert "stderr" not in readiness_text
    assert "结果 artifact" not in readiness_text
    assert "结果文件和报告文件" not in readiness_text
    assert payload["raw"]["streamlit_status"] == "legacy_retained"


def test_build_json_summary_prefers_chinese_business_fields():
    payload = {
        "workflow": "site_status_update",
        "status": "completed",
        "ok": True,
        "summary": {"target_site_count": 1, "success_count": 1, "failure_count": 0},
        "actions": [
            {"advertiser_id": "1866125088740552", "site_id": "7644466520214601766", "status": "DELETED"}
        ],
    }

    result = build_json_summary("落地页删除结果", payload)

    assert result["summary"]["title"] == "落地页删除结果"
    assert result["summary"]["status"] == "completed"
    assert {"label": "成功数", "value": 1} in result["summary"]["items"]
    assert result["table"]["columns"] == ["账户 ID", "账户名", "落地页 ID", "状态"]
    assert result["table"]["rows"][0]["落地页 ID"] == "7644466520214601766"
    assert result["raw"] == payload


def test_latest_workflow_endpoint_returns_chinese_summary(tmp_path):
    artifact_dir = tmp_path / "data" / "runs" / "site_status_update"
    artifact_dir.mkdir(parents=True)
    artifact = artifact_dir / "20260527T124459Z.json"
    artifact.write_text(
        json.dumps(
            {
                "workflow": "site_status_update",
                "status": "completed",
                "summary": {"target_site_count": 1, "success_count": 1, "failure_count": 0},
                "actions": [
                    {
                        "advertiser_id": "1866125088740552",
                        "site_id": "7644466520214601766",
                        "status": "DELETED",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    app = create_app(project_root=tmp_path)
    client = TestClient(app)

    response = client.get("/api/workflows/latest", params={"workflow": "site_status_update"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "落地页状态更新 最新结果"
    assert payload["summary"]["items"][1] == {"label": "成功数", "value": 1}
    assert payload["table"]["rows"][0]["账户 ID"] == "1866125088740552"


def test_latest_workflow_endpoint_returns_chinese_empty_state_when_missing(tmp_path):
    app = create_app(project_root=tmp_path)
    client = TestClient(app)

    response = client.get("/api/workflows/latest", params={"workflow": "create_mode"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "创建计划暂无结果"
    assert payload["summary"]["status"] == "empty"
    assert payload["summary"]["execution_enabled"] is False
    assert {"label": "结果类型", "value": "create_mode"} in payload["summary"]["items"]
    assert "还没有找到创建计划的执行结果，请先完成对应任务。" in payload["summary"]["warnings"]
    assert payload["table"]["columns"] == ["下一步", "说明"]
    assert payload["table"]["rows"][0]["下一步"] == "先执行对应流程"
    assert payload["raw"]["workflow"] == "create_mode"


def test_latest_workflow_endpoint_returns_chinese_blocked_state_for_unknown_workflow(tmp_path):
    app = create_app(project_root=tmp_path)
    client = TestClient(app)

    response = client.get("/api/workflows/latest", params={"workflow": "unknown_workflow"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "结果类型不可用"
    assert payload["summary"]["status"] == "blocked"
    assert "未知结果类型，请从结果类型目录中选择。" in payload["summary"]["blocking_reasons"]
    assert payload["table"]["rows"][0]["下一步"] == "先执行对应流程"


def test_latest_workflow_endpoint_summarizes_create_mode_plan(tmp_path):
    artifact_dir = tmp_path / "data" / "runs" / "create_mode"
    artifact_dir.mkdir(parents=True)
    artifact = artifact_dir / "20260528T010000Z.json"
    artifact.write_text(
        json.dumps(
            {
                "mode_key": "wx_pay_male_random_materials",
                "summary": {
                    "plan_id": "plan-1",
                    "planned_project_count": 1,
                    "planned_unit_count": 1,
                    "planned_material_count": 2,
                    "violation_count": 0,
                },
                "create_request": {"product": "点点英雄", "product_key": "diandian-hero"},
                "create_strategy_plan": {
                    "strategy": {
                        "projects": [
                            {
                                "advertiser_id": "1001",
                                "project_name": "项目A",
                                "units": [
                                    {
                                        "promotion_name": "单元A",
                                        "materials": [{"material_id": "m1"}, {"material_id": "m2"}],
                                    }
                                ],
                            }
                        ]
                    }
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    app = create_app(project_root=tmp_path)
    client = TestClient(app)

    response = client.get("/api/workflows/latest", params={"workflow": "create_mode"})

    assert response.status_code == 200
    payload = response.json()
    assert {"label": "产品", "value": "点点英雄"} in payload["summary"]["items"]
    assert {"label": "计划 ID", "value": "plan-1"} in payload["summary"]["items"]
    assert {"label": "项目数", "value": 1} in payload["summary"]["items"]
    assert {"label": "单元数", "value": 1} in payload["summary"]["items"]
    assert {"label": "素材数", "value": 2} in payload["summary"]["items"]
    assert payload["table"]["columns"] == ["账户 ID", "账户名", "项目", "单元", "素材数"]
    assert payload["table"]["rows"][0] == {
        "账户 ID": "1001",
        "账户名": "未配置账户名",
        "项目": "项目A",
        "单元": "单元A",
        "素材数": 2,
    }


def test_latest_workflow_endpoint_summarizes_account_remark_and_template_results(tmp_path):
    remark_dir = tmp_path / "data" / "runs" / "account_remark_update"
    template_dir = tmp_path / "data" / "runs" / "site_template_foundation"
    account_dir = tmp_path / "configs" / "accounts"
    remark_dir.mkdir(parents=True)
    template_dir.mkdir(parents=True)
    account_dir.mkdir(parents=True)
    (account_dir / "product-accounts.local.json").write_text(
        json.dumps(
            {
                "accounts": [
                    {"advertiser_id": "1001", "advertiser_name": "黑旗账户一", "status": "active"},
                    {"advertiser_id": "2001", "advertiser_name": "目标账户一", "status": "active"},
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (remark_dir / "20260528T010000Z.json").write_text(
        json.dumps(
            {
                "workflow": "account_remark_update",
                "status": "executed",
                "summary": {
                    "update_id": "remark-1",
                    "remark": "黑旗游戏",
                    "account_count": 1,
                    "success_count": 1,
                    "failed_count": 0,
                },
                "readable_reference": {
                    "accounts": [{"advertiser_id": "1001", "target_remark": "黑旗游戏"}]
                },
                "results": [{"advertiser_id": "1001", "ok": True}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (template_dir / "20260528T010000Z.json").write_text(
        json.dumps(
            {
                "workflow": "site_template_foundation",
                "status": "completed",
                "summary": {
                    "source_advertiser_id": "2000",
                    "source_site_id": "8000",
                    "target_count": 1,
                    "game_path": "?turbo_promoted_object_id=abc",
                    "publish": True,
                    "edit_existing": False,
                    "success_count": 1,
                    "error_count": 0,
                },
                "success_list": [
                    {
                        "advertiser_id": "2001",
                        "site_id": "9001",
                        "game_path": "?turbo_promoted_object_id=abc",
                        "published": True,
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    client = TestClient(create_app(project_root=tmp_path))

    remark_response = client.get("/api/workflows/latest", params={"workflow": "account_remark_update"})
    template_response = client.get("/api/workflows/latest", params={"workflow": "site_template_foundation"})

    assert remark_response.status_code == 200
    assert template_response.status_code == 200
    remark_payload = remark_response.json()
    template_payload = template_response.json()
    assert {"label": "目标备注", "value": "黑旗游戏"} in remark_payload["summary"]["items"]
    assert remark_payload["table"]["columns"] == ["账户 ID", "账户名", "目标备注", "结果"]
    assert remark_payload["table"]["rows"][0] == {
        "账户 ID": "1001",
        "账户名": "黑旗账户一",
        "目标备注": "黑旗游戏",
        "结果": "成功",
    }
    assert {"label": "小游戏路径", "value": "?turbo_promoted_object_id=abc"} in template_payload["summary"]["items"]
    assert template_payload["table"]["columns"] == ["账户 ID", "账户名", "新落地页 ID", "动作", "小游戏路径", "发布", "结果"]
    assert template_payload["table"]["rows"][0]["账户名"] == "目标账户一"
    assert template_payload["table"]["rows"][0]["结果"] == "成功"


def test_workflow_catalog_endpoint_returns_chinese_labels(tmp_path):
    app = create_app(project_root=tmp_path)
    client = TestClient(app)

    response = client.get("/api/workflows/catalog")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "结果类型目录"
    assert payload["summary"]["execution_enabled"] is False
    assert payload["table"]["columns"] == ["结果类型", "名称", "说明"]
    assert payload["table"]["rows"][0]["名称"] == "落地页状态更新"
    assert "创建计划" in [row["名称"] for row in payload["table"]["rows"]]
    assert payload["raw"]["workflows"][0]["value"] == "site_status_update"


def test_workflow_catalog_covers_replacement_result_types(tmp_path):
    app = create_app(project_root=tmp_path)
    client = TestClient(app)

    response = client.get("/api/workflows/catalog")

    assert response.status_code == 200
    labels_by_value = {row["结果类型"]: row["名称"] for row in response.json()["table"]["rows"]}
    assert labels_by_value["account_remark_update"] == "账户备注执行"
    assert labels_by_value["site_template_foundation"] == "模板建站"
    assert labels_by_value["site_handsel"] == "落地页转赠结果"
    assert labels_by_value["frontend_operation_log"] == "前端操作日志"


def test_tasks_endpoint_lists_frontend_tasks(tmp_path):
    task_dir = tmp_path / "data" / "runs" / "frontend_tasks"
    task_dir.mkdir(parents=True)
    task = task_dir / "frontend-1.json"
    task.write_text(
        json.dumps(
            {
                "task_id": "frontend-1",
                "operation_type": "dry_run_probe",
                "status": "completed",
                "created_at": "2026-05-27T12:00:00+08:00",
                "updated_at": "2026-05-27T12:01:00+08:00",
                "return_code": 0,
                "stdout_path": "frontend_tasks/frontend-1.stdout.log",
                "stderr_path": "frontend_tasks/frontend-1.stderr.log",
                "result": {"ok": True},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    app = create_app(project_root=tmp_path)
    client = TestClient(app)

    response = client.get("/api/tasks")

    assert response.status_code == 200
    rows = response.json()["items"]
    assert rows[0]["task_id"] == "frontend-1"
    assert rows[0]["operation_type"] == "dry_run_probe"
    assert rows[0]["operation_label"] == "连通性检查"
    assert rows[0]["status_label"] == "已完成"


def test_task_detail_endpoint_returns_stdout_stderr_paths(tmp_path):
    task_dir = tmp_path / "data" / "runs" / "frontend_tasks"
    task_dir.mkdir(parents=True)
    (task_dir / "frontend-1.stdout.log").write_text("hello", encoding="utf-8")
    (task_dir / "frontend-1.stderr.log").write_text("", encoding="utf-8")
    (task_dir / "frontend-1.json").write_text(
        json.dumps(
            {
                "task_id": "frontend-1",
                "status": "completed",
                "stdout_path": "frontend_tasks/frontend-1.stdout.log",
                "stderr_path": "frontend_tasks/frontend-1.stderr.log",
            }
        ),
        encoding="utf-8",
    )
    app = create_app(project_root=tmp_path)
    client = TestClient(app)

    response = client.get("/api/tasks/frontend-1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["task"]["task_id"] == "frontend-1"
    assert payload["stdout"] == "hello"


def test_task_stdout_and_stderr_endpoints_return_plain_logs(tmp_path):
    task_dir = tmp_path / "data" / "runs" / "frontend_tasks"
    task_dir.mkdir(parents=True)
    (task_dir / "frontend-1.stdout.log").write_text("标准输出内容", encoding="utf-8")
    (task_dir / "frontend-1.stderr.log").write_text("标准错误内容", encoding="utf-8")
    (task_dir / "frontend-1.json").write_text(
        json.dumps(
            {
                "task_id": "frontend-1",
                "status": "completed",
                "stdout_path": "frontend_tasks/frontend-1.stdout.log",
                "stderr_path": "frontend_tasks/frontend-1.stderr.log",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    app = create_app(project_root=tmp_path)
    client = TestClient(app)

    stdout_response = client.get("/api/tasks/frontend-1/stdout")
    stderr_response = client.get("/api/tasks/frontend-1/stderr")

    assert stdout_response.status_code == 200
    assert stdout_response.text == "标准输出内容"
    assert "text/plain" in stdout_response.headers["content-type"]
    assert stderr_response.status_code == 200
    assert stderr_response.text == "标准错误内容"


def test_task_detail_endpoint_returns_chinese_summary_before_raw_task(tmp_path):
    task_dir = tmp_path / "data" / "runs" / "frontend_tasks"
    task_dir.mkdir(parents=True)
    (task_dir / "frontend-1.stdout.log").write_text("done", encoding="utf-8")
    (task_dir / "frontend-1.stderr.log").write_text("", encoding="utf-8")
    (task_dir / "frontend-1.json").write_text(
        json.dumps(
            {
                "task_id": "frontend-1",
                "operation_type": "dry_run_probe",
                "status": "completed",
                "created_at": "2026-05-27T12:00:00+08:00",
                "updated_at": "2026-05-27T12:01:00+08:00",
                "return_code": 0,
                "stdout_path": "frontend_tasks/frontend-1.stdout.log",
                "stderr_path": "frontend_tasks/frontend-1.stderr.log",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    app = create_app(project_root=tmp_path)
    client = TestClient(app)

    response = client.get("/api/tasks/frontend-1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "连通性检查"
    assert {"label": "任务 ID", "value": "frontend-1"} in payload["summary"]["items"]
    assert {"label": "任务内容", "value": "连通性检查"} in payload["summary"]["items"]
    assert not any(item["label"] == "标准输出长度" for item in payload["summary"]["items"])
    assert not any(item["label"] == "退出码" for item in payload["summary"]["items"])
    assert payload["table"]["columns"] == ["任务 ID", "任务内容", "业务内容", "当前状态", "业务结果", "结果摘要"]
    assert payload["table"]["rows"][0]["任务内容"] == "连通性检查"
    assert "结果文件" not in payload["table"]["rows"][0]
    assert payload["raw"]["task"]["task_id"] == "frontend-1"


def test_task_detail_surfaces_business_failure_reasons(tmp_path):
    task_dir = tmp_path / "data" / "runs" / "frontend_tasks"
    task_dir.mkdir(parents=True)
    (task_dir / "frontend-1.stdout.log").write_text("failed", encoding="utf-8")
    (task_dir / "frontend-1.stderr.log").write_text("", encoding="utf-8")
    (task_dir / "frontend-1.json").write_text(
        json.dumps(
            {
                "task_id": "frontend-1",
                "operation_type": "create_live_execute",
                "status": "failed",
                "return_code": 1,
                "stdout_path": "frontend_tasks/frontend-1.stdout.log",
                "stderr_path": "frontend_tasks/frontend-1.stderr.log",
                "result": {
                    "ok": False,
                    "status": "blocked",
                    "blocking_reasons": ["本地真实执行配置还缺：create_http_transport.token_value"],
                    "local_config_readiness": {
                        "plain_language": "本地真实执行配置还缺：create_http_transport.token_value"
                    },
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    app = create_app(project_root=tmp_path)
    client = TestClient(app)

    response = client.get("/api/tasks/frontend-1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["risk_level"] == "high"
    assert "本地真实执行配置还缺：create_http_transport.token_value" in payload["summary"]["blocking_reasons"]
    assert {"label": "业务状态", "value": "blocked"} in payload["summary"]["items"]


def test_task_detail_parses_pretty_stdout_business_json_and_account_names(tmp_path):
    account_dir = tmp_path / "configs" / "accounts"
    account_dir.mkdir(parents=True)
    (account_dir / "product-accounts.local.json").write_text(
        json.dumps(
            {
                "accounts": [
                    {
                        "product_key": "diandian-hero",
                        "product_name": "点点英雄",
                        "advertiser_id": "1001",
                        "advertiser_name": "黑旗账户一",
                        "status": "active",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    result_dir = tmp_path / "data" / "runs" / "project_update_execute"
    result_dir.mkdir(parents=True)
    result_path = result_dir / "result.json"
    result_path.write_text(
        json.dumps(
            {
                "workflow": "project_update_execute",
                "status": "completed",
                "summary": {"action_count": 1, "updated_project_count": 1, "account_count": 1},
                "results": [
                    {
                        "advertiser_id": "1001",
                        "action_type": "delete_project",
                        "project_id": "p-1",
                        "project_name": "7R-测试-1",
                        "status": "success",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    task_dir = tmp_path / "data" / "runs" / "frontend_tasks"
    task_dir.mkdir(parents=True)
    stdout_payload = {
        "ok": True,
        "workflow": "project_update_execute",
        "status": "completed",
        "summary": {"action_count": 1, "updated_project_count": 1},
        "artifact_path": "data/runs/project_update_execute/result.json",
    }
    (task_dir / "frontend-1.stdout.log").write_text(json.dumps(stdout_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (task_dir / "frontend-1.stderr.log").write_text("", encoding="utf-8")
    (task_dir / "frontend-1.json").write_text(
        json.dumps(
            {
                "task_id": "frontend-1",
                "operation_type": "project_update_execute",
                "status": "completed",
                "return_code": 0,
                "stdout_path": "frontend_tasks/frontend-1.stdout.log",
                "stderr_path": "frontend_tasks/frontend-1.stderr.log",
                "result": {},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    client = TestClient(create_app(project_root=tmp_path))

    response = client.get("/api/tasks/frontend-1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "项目管理真实执行"
    assert {"label": "业务结果", "value": "已完成"} in payload["summary"]["items"]
    assert {"label": "动作数", "value": 1} in payload["summary"]["items"]
    assert not any(item["label"] == "标准输出长度" for item in payload["summary"]["items"])
    sections = {section["title"]: section for section in payload["sections"]}
    assert sections["项目执行结果"]["table"]["columns"] == ["账户 ID", "账户名", "动作", "项目 ID", "项目名", "项目数", "状态"]
    assert sections["项目执行结果"]["table"]["rows"][0]["账户名"] == "黑旗账户一"


def test_accounts_endpoint_reads_product_account_store(tmp_path):
    account_dir = tmp_path / "configs" / "accounts"
    account_dir.mkdir(parents=True)
    (account_dir / "product-accounts.local.json").write_text(
        json.dumps(
            {
                "accounts": [
                    {
                        "product_key": "diandian-hero",
                        "product_name": "点点英雄",
                        "advertiser_id": "1866125088740552",
                        "advertiser_name": "黑旗游戏",
                        "channel": "微信",
                        "owner": "运营A",
                        "account_remark": "点点英雄-黑旗",
                        "status": "active",
                        "notes": "",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    app = create_app(project_root=tmp_path)
    client = TestClient(app)

    response = client.get("/api/accounts")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["items"][0] == {"label": "账户数", "value": 1}
    assert payload["table"]["rows"][0]["产品"] == "点点英雄"
