import json
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.main import create_app


def _client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(project_root=tmp_path))


def test_operation_logs_endpoint_returns_chinese_summary(tmp_path):
    log_dir = tmp_path / "data" / "runs" / "frontend_operation_log"
    log_dir.mkdir(parents=True)
    (log_dir / "20260527T120000Z.json").write_text(
        json.dumps(
            {
                "task_id": "ui-test-1",
                "operation_type": "project_management_config_generate",
                "status": "completed",
                "summary": {
                    "operation_type": "project_management_config_generate",
                    "status": "completed",
                    "product": "点点英雄",
                    "product_key": "diandian-hero",
                    "account_count": 3,
                },
                "result": {"artifact_path": "data/runs/project_realtime_filter_config/result.json"},
                "created_at": "2026-05-27T12:00:00+08:00",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    client = _client(tmp_path)

    response = client.get("/api/operations")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "操作日志"
    assert {"label": "日志数", "value": 1} in payload["summary"]["items"]
    assert payload["table"]["columns"] == [
        "任务 ID",
        "操作",
        "业务内容",
        "状态",
        "任务状态",
        "触发人",
        "产品",
        "产品 Key",
        "创建时间",
        "账户数",
        "退出码",
        "结果文件",
        "报告文件",
    ]
    assert payload["table"]["rows"][0]["操作"] == "项目管理配置生成"
    assert payload["table"]["rows"][0]["业务内容"] == "未指定动作"
    assert payload["table"]["rows"][0]["状态"] == "已完成"
    assert payload["table"]["rows"][0]["产品"] == "点点英雄"
    assert payload["raw"]["rows"][0]["task_id"] == "ui-test-1"


def test_operation_logs_endpoint_exposes_task_and_review_fields(tmp_path):
    runs_dir = tmp_path / "data" / "runs"
    log_dir = runs_dir / "frontend_operation_log"
    task_dir = runs_dir / "frontend_tasks"
    log_dir.mkdir(parents=True)
    task_dir.mkdir(parents=True)
    (task_dir / "task-1.json").write_text(
        json.dumps(
            {
                "task_id": "task-1",
                "operation_type": "site_status_update",
                "status": "completed",
                "return_code": 0,
                "stdout_path": "frontend_tasks/task-1.stdout.log",
                "stderr_path": "frontend_tasks/task-1.stderr.log",
                "result": {"artifact_path": "site_status_update/result.json", "status": "completed"},
                "post_results": [{"artifact_path": "create_live_execute_report/report.json"}],
                "updated_at": "2026-05-27T12:03:00+08:00",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (log_dir / "20260527T120000Z.json").write_text(
        json.dumps(
            {
                "task_id": "task-1",
                "operation_type": "site_status_update",
                "status": "queued",
                "actor": "local-ui",
                "summary": {
                    "operation_type": "site_status_update",
                    "status": "queued",
                    "product": "点点英雄",
                    "product_key": "diandian-hero",
                    "account_count": 1,
                },
                "result": {"status": "queued"},
                "created_at": "2026-05-27T12:00:00+08:00",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    client = _client(tmp_path)

    response = client.get("/api/operations")

    assert response.status_code == 200
    row = response.json()["table"]["rows"][0]
    assert row["操作"] == "落地页状态更新"
    assert row["状态"] == "已完成"
    assert row["任务状态"] == "已完成"
    assert row["触发人"] == "local-ui"
    assert row["退出码"] == 0
    assert row["结果文件"] == "site_status_update/result.json"
    assert row["报告文件"] == "create_live_execute_report/report.json"


def test_operation_logs_endpoint_filters_by_operation_and_status(tmp_path):
    log_dir = tmp_path / "data" / "runs" / "frontend_operation_log"
    log_dir.mkdir(parents=True)
    for name, operation_type, status in [
        ("20260527T120000Z.json", "create_plan_generate", "completed"),
        ("20260527T120100Z.json", "project_management_execute", "failed"),
    ]:
        (log_dir / name).write_text(
            json.dumps(
                {
                    "task_id": name.removesuffix(".json"),
                    "operation_type": operation_type,
                    "status": status,
                    "summary": {"operation_type": operation_type, "status": status, "product": "点点英雄"},
                    "created_at": "2026-05-27T12:00:00+08:00",
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    client = _client(tmp_path)

    response = client.get("/api/operations", params={"operation_type": "project_management_execute", "status": "failed"})

    assert response.status_code == 200
    rows = response.json()["table"]["rows"]
    assert len(rows) == 1
    assert rows[0]["操作"] == "项目管理执行"
    assert rows[0]["状态"] == "失败"


def test_operation_log_detail_endpoint_returns_create_review_sections(tmp_path):
    runs_dir = tmp_path / "data" / "runs"
    log_dir = runs_dir / "frontend_operation_log"
    execute_dir = runs_dir / "create_live_execute_once"
    report_dir = runs_dir / "create_live_execute_report"
    log_dir.mkdir(parents=True)
    execute_dir.mkdir(parents=True)
    report_dir.mkdir(parents=True)
    execute_path = execute_dir / "result.json"
    report_path = report_dir / "report.json"
    execute_path.write_text(
        json.dumps(
            {
                "ok": False,
                "status": "create_http_failed",
                "failure": {"operation": "create_project", "code": 40000, "message": "当前优化目标不可用"},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    report_path.write_text(
        json.dumps(
            {
                "delivery": {"feishu": {"attempted": True, "ok": False, "reason": "webhook error"}},
                "message": "真实创建结果：部分失败",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (log_dir / "20260527T120000Z.json").write_text(
        json.dumps(
            {
                "task_id": "task-create",
                "operation_type": "create_live_execute",
                "status": "failed",
                "actor": "郭靖",
                "summary": {
                    "operation_type": "create_live_execute",
                    "status": "failed",
                    "product": "点点英雄",
                    "product_key": "diandian-hero",
                    "account_count": 1,
                    "material_assignment_count": 1,
                    "unique_material_count": 1,
                    "review_status": "passed",
                    "execute_artifact_path": str(execute_path),
                    "report_artifact_path": str(report_path),
                },
                "result": {
                    "execute_artifact_path": str(execute_path),
                    "report_artifact_path": str(report_path),
                    "status": "create_http_failed",
                },
                "details": {
                    "mode_key": "wx_pay_male_random_materials",
                    "display_name": "点点英雄每付男素材不限",
                    "template_key": "wx_pay_male",
                    "project_template_name": "微小每付男素材不限",
                    "template_catalog_path": "configs/create-templates/diandian-hero.local.json",
                    "review": {"can_execute": True, "summary": {"warning_count": 0}, "blocking_reasons": []},
                    "accounts": [
                        {
                            "advertiser_id": "1001",
                            "project_count": 1,
                            "unit_count": 1,
                            "material_assignment_count": 1,
                            "unique_material_count": 1,
                        }
                    ],
                    "materials": [
                        {
                            "material_id": "m-1",
                            "video_id": "video-1",
                            "name": "素材1",
                            "product_stat_cost": 123.45,
                            "product_convert_cnt": 6,
                            "usage_count": 1,
                            "covered_account_count": 1,
                            "covered_unit_count": 1,
                            "covered_accounts": ["1001"],
                        }
                    ],
                    "creative_usage": {
                        "titles": [{"title": "标题1", "usage_count": 1}],
                        "ctas": [{"cta": "立即下载", "usage_count": 1}],
                        "selling_points": [{"selling_point": "爆率高", "usage_count": 1}],
                    },
                    "unit_assignments": [
                        {
                            "advertiser_id": "1001",
                            "project_name": "项目1",
                            "promotion_name": "单元1",
                            "materials": [{"material_id": "m-1"}],
                            "titles": ["标题1"],
                            "ctas": ["立即下载"],
                            "selling_points": ["爆率高"],
                        }
                    ],
                },
                "created_at": "2026-05-27T12:00:00+08:00",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    client = _client(tmp_path)

    response = client.get("/api/operations/task-create")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "操作日志详情"
    assert payload["summary"]["risk_level"] == "high"
    assert {"label": "任务 ID", "value": "task-create"} in payload["summary"]["items"]
    assert {"label": "产品", "value": "点点英雄"} in payload["summary"]["items"]
    assert {"label": "固定模式", "value": "点点英雄每付男素材不限"} in payload["summary"]["items"]
    assert {"label": "基础模板", "value": "微小每付男素材不限"} in payload["summary"]["items"]
    assert {"label": "模板文件", "value": "configs/create-templates/diandian-hero.local.json"} in payload["summary"]["items"]
    assert "真实执行失败：当前优化目标不可用" in payload["summary"]["blocking_reasons"]
    assert [section["title"] for section in payload["sections"]] == ["账户分布", "素材分配", "文案", "CTA", "卖点", "单元分配"]
    assert payload["sections"][0]["table"]["rows"][0]["账户 ID"] == "1001"
    assert "分配账户" in payload["sections"][1]["table"]["columns"]
    assert payload["sections"][1]["table"]["rows"][0]["素材 ID"] == "m-1"
    assert payload["sections"][1]["table"]["rows"][0]["分配账户"] == "未配置账户名（1001）"
    assert payload["sections"][5]["table"]["rows"][0]["文案"] == "标题1"


def test_operation_log_detail_endpoint_returns_project_action_sections(tmp_path):
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
    log_dir = tmp_path / "data" / "runs" / "frontend_operation_log"
    log_dir.mkdir(parents=True)
    (log_dir / "20260527T130000Z.json").write_text(
        json.dumps(
            {
                "task_id": "task-project",
                "operation_type": "project_update_execute",
                "status": "queued",
                "actor": "郭靖",
                "summary": {
                    "operation_type": "project_update_execute",
                    "status": "queued",
                    "account_count": 1,
                    "execute_artifact_path": "configs/project-updates/delete.local.json",
                },
                "result": {"execute_artifact_path": "configs/project-updates/delete.local.json", "status": "queued"},
                "details": {
                    "accounts": [{"advertiser_id": "1001"}],
                    "project_actions": [
                        {
                            "action_type": "delete_project",
                            "advertiser_id": "1001",
                            "project_id": "p-1",
                            "project_name": "7R-测试-1",
                        }
                    ],
                    "review": {
                        "can_execute": True,
                        "summary": {"warning_count": 1},
                        "warnings": ["这是高风险真实执行入口"],
                        "blocking_reasons": [],
                    },
                },
                "created_at": "2026-05-27T13:00:00+08:00",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    client = _client(tmp_path)

    response = client.get("/api/operations/task-project")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["status"] == "queued"
    assert {"label": "操作", "value": "项目管理真实执行"} in payload["summary"]["items"]
    assert {"label": "项目管理动作", "value": "删除项目"} in payload["summary"]["items"]
    assert payload["summary"]["warnings"] == ["这是高风险真实执行入口"]
    sections = {section["title"]: section for section in payload["sections"]}
    assert sections["项目动作"]["table"]["columns"] == ["账户 ID", "账户名", "项目 ID", "项目名", "动作", "目标值"]
    assert sections["项目动作"]["table"]["rows"][0] == {
        "账户 ID": "1001",
        "账户名": "黑旗账户一",
        "项目 ID": "p-1",
        "项目名": "7R-测试-1",
        "动作": "删除项目",
        "目标值": "",
    }


def test_operation_log_detail_endpoint_returns_account_remark_section(tmp_path):
    log_dir = tmp_path / "data" / "runs" / "frontend_operation_log"
    log_dir.mkdir(parents=True)
    (log_dir / "20260527T140000Z.json").write_text(
        json.dumps(
            {
                "task_id": "task-remark",
                "operation_type": "account_remark_update",
                "status": "queued",
                "actor": "郭靖",
                "summary": {
                    "operation_type": "account_remark_update",
                    "status": "queued",
                    "account_count": 2,
                    "execute_artifact_path": "configs/account-updates/remark-001.local.json",
                },
                "result": {"execute_artifact_path": "configs/account-updates/remark-001.local.json", "status": "queued"},
                "details": {
                    "accounts": [{"advertiser_id": "1001"}, {"advertiser_id": "1002"}],
                    "account_remark": {
                        "update_id": "remark-001",
                        "remark": "黑旗游戏",
                    },
                    "review": {
                        "can_execute": True,
                        "summary": {"warning_count": 1},
                        "warnings": ["这是账户备注真实修改入口"],
                        "blocking_reasons": [],
                    },
                },
                "created_at": "2026-05-27T14:00:00+08:00",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    client = _client(tmp_path)

    response = client.get("/api/operations/task-remark")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["warnings"] == ["这是账户备注真实修改入口"]
    sections = {section["title"]: section for section in payload["sections"]}
    assert sections["账户备注"]["table"]["columns"] == ["账户 ID", "账户名", "目标备注", "配置 ID"]
    assert sections["账户备注"]["table"]["rows"] == [
        {"账户 ID": "1001", "账户名": "未配置账户名", "目标备注": "黑旗游戏", "配置 ID": "remark-001"},
        {"账户 ID": "1002", "账户名": "未配置账户名", "目标备注": "黑旗游戏", "配置 ID": "remark-001"},
    ]


def test_operation_log_detail_endpoint_returns_site_status_section(tmp_path):
    log_dir = tmp_path / "data" / "runs" / "frontend_operation_log"
    log_dir.mkdir(parents=True)
    (log_dir / "20260527T150000Z.json").write_text(
        json.dumps(
            {
                "task_id": "task-site",
                "operation_type": "site_status_update",
                "status": "queued",
                "actor": "郭靖",
                "summary": {
                    "operation_type": "site_status_update",
                    "status": "queued",
                    "account_count": 1,
                },
                "result": {"status": "queued"},
                "details": {
                    "accounts": [{"advertiser_id": "2001"}],
                    "sites": [
                        {"advertiser_id": "2001", "site_id": "9001"},
                        {"advertiser_id": "2001", "site_id": "9002"},
                    ],
                    "site_status": {"status": "delete", "status_label": "删除"},
                    "review": {
                        "can_execute": True,
                        "summary": {"warning_count": 1},
                        "warnings": ["这是落地页状态真实修改入口"],
                        "blocking_reasons": [],
                    },
                },
                "created_at": "2026-05-27T15:00:00+08:00",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    client = _client(tmp_path)

    response = client.get("/api/operations/task-site")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["warnings"] == ["这是落地页状态真实修改入口"]
    sections = {section["title"]: section for section in payload["sections"]}
    assert sections["落地页状态"]["table"]["columns"] == ["账户 ID", "账户名", "落地页 ID", "目标状态"]
    assert sections["落地页状态"]["table"]["rows"] == [
        {"账户 ID": "2001", "账户名": "未配置账户名", "落地页 ID": "9001", "目标状态": "删除"},
        {"账户 ID": "2001", "账户名": "未配置账户名", "落地页 ID": "9002", "目标状态": "删除"},
    ]


def test_operation_log_detail_endpoint_returns_site_template_section(tmp_path):
    log_dir = tmp_path / "data" / "runs" / "frontend_operation_log"
    log_dir.mkdir(parents=True)
    (log_dir / "20260527T160000Z.json").write_text(
        json.dumps(
            {
                "task_id": "task-site-template",
                "operation_type": "site_template_foundation",
                "status": "queued",
                "actor": "郭靖",
                "summary": {
                    "operation_type": "site_template_foundation",
                    "status": "queued",
                    "account_count": 2,
                },
                "result": {"status": "queued"},
                "details": {
                    "accounts": [{"advertiser_id": "2001"}, {"advertiser_id": "2002"}],
                    "sites": [{"advertiser_id": "2001", "site_id": ""}, {"advertiser_id": "2002", "site_id": ""}],
                    "site_template_foundation": {
                        "source_advertiser_id": "2000",
                        "source_site_id": "8000",
                        "game_path": "?turbo_promoted_object_id=abc",
                        "publish": True,
                        "edit_existing": False,
                    },
                    "review": {
                        "can_execute": True,
                        "summary": {"warning_count": 1},
                        "warnings": ["这是模板建站真实执行入口"],
                        "blocking_reasons": [],
                    },
                },
                "created_at": "2026-05-27T16:00:00+08:00",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    client = _client(tmp_path)

    response = client.get("/api/operations/task-site-template")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["warnings"] == ["这是模板建站真实执行入口"]
    sections = {section["title"]: section for section in payload["sections"]}
    assert sections["模板建站"]["table"]["columns"] == ["账户 ID", "账户名", "现有落地页 ID", "动作", "小游戏路径", "发布"]
    assert sections["模板建站"]["table"]["rows"] == [
        {
            "账户 ID": "2001",
            "账户名": "未配置账户名",
            "现有落地页 ID": "",
            "动作": "新建落地页",
            "小游戏路径": "?turbo_promoted_object_id=abc",
            "发布": "是",
        },
        {
            "账户 ID": "2002",
            "账户名": "未配置账户名",
            "现有落地页 ID": "",
            "动作": "新建落地页",
            "小游戏路径": "?turbo_promoted_object_id=abc",
            "发布": "是",
        },
    ]
