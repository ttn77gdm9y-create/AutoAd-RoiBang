import json
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.main import create_app


def _create_plan_request() -> dict:
    return {
        "mode": "wx_pay_male_random_materials",
        "advertiser_ids": "1001\n1002",
        "owner": "郭靖",
        "product_key": "diandian-hero",
        "product_name": "点点英雄",
        "target_date": "2026-05-28",
        "template_catalog": "configs/create-templates/wx-mini-game.json",
        "cpa_bid": "103",
        "roi_coefficient": "",
    }


def _create_plan_payload() -> dict:
    return {
        "mode_key": "wx_pay_male_random_materials",
        "summary": {
            "plan_id": "plan-1",
            "planned_project_count": 1,
            "planned_unit_count": 1,
            "planned_material_count": 1,
            "source_material_count": 3,
            "violation_count": 0,
        },
        "create_request": {
            "product": "点点英雄",
            "product_key": "diandian-hero",
            "target_date": "2026-05-28",
            "source_advertiser_id": "source-dd",
            "material_selection": {"selection_type": "random_materials"},
            "template_parameters": {
                "title_pool": ["标题1", "标题2"],
                "cta_pool": ["立即下载"],
                "product_selling_points": ["爆率高"],
                "unit_creative_selection": {
                    "title_strategy": "deterministic_shuffle_per_unit",
                    "cta_min_count": 1,
                    "cta_max_count": 1,
                    "product_selling_point_min_count": 1,
                    "product_selling_point_max_count": 1,
                },
            },
        },
        "create_strategy_plan": {
            "request": {
                "product": "点点英雄",
                "product_key": "diandian-hero",
                "source_advertiser_id": "source-dd",
                "template_parameters": {
                    "title_pool": ["标题1", "标题2"],
                    "cta_pool": ["立即下载"],
                    "product_selling_points": ["爆率高"],
                    "unit_creative_selection": {
                        "title_strategy": "deterministic_shuffle_per_unit",
                        "cta_min_count": 1,
                        "cta_max_count": 1,
                        "product_selling_point_min_count": 1,
                        "product_selling_point_max_count": 1,
                    },
                },
            },
            "strategy": {
                "projects": [
                    {
                        "project_key": "acc-1-p001",
                        "advertiser_id": "acc-1",
                        "project_name": "项目1",
                        "units": [
                            {
                                "unit_key": "acc-1-p001-u01",
                                "promotion_name": "单元1",
                                "materials": [
                                    {
                                        "material_id": "m-1",
                                        "source_video_id": "video-1",
                                        "name": "素材1",
                                        "stat_cost": 123.45,
                                        "convert_cnt": 6,
                                        "rank": 1,
                                        "effective_create_date": "2026-05-25",
                                    }
                                ],
                            }
                        ],
                    }
                ]
            },
        },
    }


def _write_create_plan(root: Path) -> str:
    path = root / "data" / "runs" / "create_mode" / "plan-1.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(_create_plan_payload(), ensure_ascii=False, indent=2), encoding="utf-8")
    return "data/runs/create_mode/plan-1.json"


def test_create_plan_preview_returns_chinese_summary(tmp_path):
    client = TestClient(create_app(project_root=tmp_path))

    response = client.post("/api/create-plans/preview", json=_create_plan_request())

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "创建计划生成预览"
    assert payload["summary"]["status"] == "planned"
    assert payload["summary"]["execution_enabled"] is False
    assert {"label": "创建模式", "value": "wx_pay_male_random_materials"} in payload["summary"]["items"]
    assert {"label": "产品", "value": "点点英雄"} in payload["summary"]["items"]
    assert {"label": "账户数", "value": 2} in payload["summary"]["items"]
    assert payload["table"]["columns"] == ["账户 ID", "账户名", "创建模式", "产品", "负责人", "目标日期", "出价", "ROI 系数"]
    assert payload["table"]["rows"][0]["账户 ID"] == "1001"
    assert payload["table"]["rows"][0]["账户名"] == "未配置账户名"
    assert payload["raw"]["command"][1] == "scripts/run_create_mode.py"
    assert "--execute" not in payload["raw"]["command"]


def test_create_plan_templates_lists_configured_template_catalogs(tmp_path):
    template_dir = tmp_path / "configs" / "create-templates"
    template_dir.mkdir(parents=True)
    (template_dir / "diandian-hero.local.json").write_text(
        json.dumps(
            {
                "product": "点点英雄",
                "product_key": "diandian-hero",
                "platform": "WECHAT_GAME",
                "templates": {"wx_7r_general": {}, "wx_7r_male": {}},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    client = TestClient(create_app(project_root=tmp_path))

    response = client.get("/api/create-plans/templates")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "创建模板列表"
    assert {"label": "模板数", "value": 1} in payload["summary"]["items"]
    assert payload["table"]["rows"][0]["模板"] == "点点英雄 - diandian-hero.local.json"
    assert payload["table"]["rows"][0]["产品 Key"] == "diandian-hero"
    assert payload["table"]["rows"][0]["路径"] == "configs/create-templates/diandian-hero.local.json"


def test_create_plan_template_detail_returns_summary_and_raw_json(tmp_path):
    template_dir = tmp_path / "configs" / "create-templates"
    template_dir.mkdir(parents=True)
    (template_dir / "diandian-hero.local.json").write_text(
        json.dumps(
            {
                "product": "点点英雄",
                "product_key": "diandian-hero",
                "platform": "WECHAT_GAME",
                "templates": {
                    "wx_pay_male": {
                        "project_template_name": "微小每付男",
                        "title_pool": ["标题1", "标题2"],
                        "cta_pool": ["立即下载"],
                        "product_selling_points": ["爆率高"],
                        "requires_roi_goal": False,
                    }
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    client = TestClient(create_app(project_root=tmp_path))

    response = client.get(
        "/api/create-plans/template-detail",
        params={"path": "configs/create-templates/diandian-hero.local.json"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "固定模式模板内容"
    assert {"label": "产品", "value": "点点英雄"} in payload["summary"]["items"]
    assert {"label": "模板文件", "value": "configs/create-templates/diandian-hero.local.json"} in payload["summary"]["items"]
    assert payload["table"]["columns"] == ["模板 Key", "项目模板", "文案数", "CTA 数", "卖点数", "是否 7R"]
    assert payload["table"]["rows"][0]["模板 Key"] == "wx_pay_male"
    assert payload["raw"]["template"]["templates"]["wx_pay_male"]["project_template_name"] == "微小每付男"


def test_create_plan_preview_blocks_missing_accounts(tmp_path):
    client = TestClient(create_app(project_root=tmp_path))

    response = client.post("/api/create-plans/preview", json={**_create_plan_request(), "advertiser_ids": ""})

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["status"] == "blocked"
    assert payload["summary"]["execution_enabled"] is False
    assert "必须明确填写本次账户 ID" in payload["summary"]["blocking_reasons"]
    assert payload["table"]["rows"] == []


def test_create_plan_preview_blocks_missing_required_user_choices(tmp_path):
    client = TestClient(create_app(project_root=tmp_path))

    response = client.post(
        "/api/create-plans/preview",
        json={
            **_create_plan_request(),
            "mode": "",
            "owner": "",
            "template_catalog": "",
            "advertiser_ids": "",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["status"] == "blocked"
    assert payload["summary"]["execution_enabled"] is False
    assert payload["summary"]["blocking_reasons"] == [
        "必须明确选择固定创建模式",
        "必须明确填写负责人",
        "必须明确选择固定模板 JSON",
        "必须明确填写本次账户 ID",
    ]
    assert payload["table"]["rows"] == []


def test_create_plan_preview_blocks_roi_coefficient_for_non_7r_mode(tmp_path):
    client = TestClient(create_app(project_root=tmp_path))

    response = client.post(
        "/api/create-plans/preview",
        json={**_create_plan_request(), "mode": "wx_pay_general_random_materials", "roi_coefficient": "0.41"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["status"] == "blocked"
    assert payload["summary"]["execution_enabled"] is False
    assert "非 7R 创建模式不允许填写 ROI 系数" in payload["summary"]["blocking_reasons"][0]


def test_create_plan_preview_blocks_empty_accounts_even_when_product_has_active_accounts(tmp_path):
    accounts_path = tmp_path / "configs" / "accounts" / "product-accounts.local.json"
    accounts_path.parent.mkdir(parents=True)
    accounts_path.write_text(
        json.dumps(
            {
                "accounts": [
                    {
                        "product_key": "diandian-hero",
                        "product_name": "点点英雄",
                        "advertiser_id": "1001",
                        "advertiser_name": "账户一",
                        "status": "active",
                    },
                    {
                        "product_key": "diandian-hero",
                        "product_name": "点点英雄",
                        "advertiser_id": "1002",
                        "advertiser_name": "账户二",
                        "status": "paused",
                    },
                    {
                        "product_key": "diandian-hero",
                        "product_name": "点点英雄",
                        "advertiser_id": "1003",
                        "advertiser_name": "账户三",
                        "status": "active",
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    client = TestClient(create_app(project_root=tmp_path))

    response = client.post("/api/create-plans/preview", json={**_create_plan_request(), "advertiser_ids": ""})

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["status"] == "blocked"
    assert payload["summary"]["execution_enabled"] is False
    assert "必须明确填写本次账户 ID" in payload["summary"]["blocking_reasons"]
    assert payload["table"]["rows"] == []


def test_create_plan_detail_material_section_shows_assigned_accounts(tmp_path):
    accounts_path = tmp_path / "configs" / "accounts" / "product-accounts.local.json"
    accounts_path.parent.mkdir(parents=True)
    accounts_path.write_text(
        json.dumps(
            {
                "accounts": [
                    {
                        "product_key": "diandian-hero",
                        "product_name": "点点英雄",
                        "advertiser_id": "acc-1",
                        "advertiser_name": "账户一",
                        "status": "active",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    plan_path = _write_create_plan(tmp_path)
    client = TestClient(create_app(project_root=tmp_path))

    response = client.get("/api/create-plans/plan-1", params={"plan_path": plan_path})

    assert response.status_code == 200
    payload = response.json()
    material_section = next(section for section in payload["sections"] if section["title"] == "已选素材")
    assert "分配账户" in material_section["table"]["columns"]
    assert material_section["table"]["rows"][0]["分配账户"] == "账户一（acc-1）"


def test_create_plan_generate_starts_frontend_task(tmp_path, monkeypatch):
    started = {}

    def fake_start_runner(command, *, cwd):
        started["command"] = command
        started["cwd"] = str(cwd)
        return 4321

    monkeypatch.setattr("backend.app.services.create_plans.start_runner", fake_start_runner, raising=False)
    client = TestClient(create_app(project_root=tmp_path))

    response = client.post("/api/create-plans/generate", json=_create_plan_request())

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "创建计划生成任务"
    assert payload["summary"]["status"] == "queued"
    assert payload["summary"]["execution_enabled"] is False
    task = payload["task"]
    assert task["pid"] == 4321
    assert task["operation_type"] == "create_plan_generate"
    assert task["command"][1] == "scripts/run_create_mode.py"
    task_path = tmp_path / "data" / "runs" / task["artifact_path"]
    assert task_path.exists()
    assert started["command"] == ["python3", "scripts/run_frontend_task.py", "--task", str(task_path)]

    tasks = client.get("/api/tasks").json()["items"]
    assert tasks[0]["task_id"] == task["task_id"]
    assert tasks[0]["operation_type"] == "create_plan_generate"
    assert tasks[0]["operation_label"] == "创建计划生成"

    operation_rows = client.get("/api/operations", params={"operation_type": "create_plan_generate"}).json()["table"]["rows"]
    assert len(operation_rows) == 1
    assert operation_rows[0]["关联任务"] == task["task_id"]
    assert operation_rows[0]["操作"] == "创建计划生成"
    assert operation_rows[0]["状态"] == "排队中"
    assert operation_rows[0]["产品 Key"] == "diandian-hero"
    assert operation_rows[0]["账户数"] == 2


def test_create_plan_detail_reads_plan_summary(tmp_path):
    plan_path = _write_create_plan(tmp_path)
    client = TestClient(create_app(project_root=tmp_path))

    response = client.get(f"/api/create-plans/plan-1?plan_path={plan_path}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "创建计划详情"
    assert payload["summary"]["status"] == "ready"
    assert {"label": "计划 ID", "value": "plan-1"} in payload["summary"]["items"]
    assert {"label": "素材分配数", "value": 1} in payload["summary"]["items"]
    assert payload["table"]["rows"][0]["账户 ID"] == "acc-1"
    sections = {section["title"]: section for section in payload["sections"]}
    assert sections["已选素材"]["table"]["rows"][0] == {
        "素材 ID": "m-1",
        "视频 ID": "video-1",
        "素材名": "素材1",
        "产品": "点点英雄",
        "使用次数": 1,
        "分配账户": "未配置账户名（acc-1）",
        "覆盖账户数": 1,
        "覆盖单元数": 1,
        "缺视频 ID": "否",
    }
    assert sections["文案"]["table"]["rows"][0] == {"文案": "标题1", "使用次数": 1, "覆盖单元数": 1}
    assert sections["CTA"]["table"]["rows"][0] == {"CTA": "立即下载", "使用次数": 1, "覆盖单元数": 1}
    assert sections["卖点"]["table"]["rows"][0] == {"卖点": "爆率高", "使用次数": 1, "覆盖单元数": 1}


def test_latest_create_plan_returns_review_ready_summary(tmp_path):
    old_path = tmp_path / "data" / "runs" / "create_mode" / "20260527T010000Z.json"
    new_path = tmp_path / "data" / "runs" / "create_mode" / "20260528T010000Z.json"
    old_path.parent.mkdir(parents=True)
    old_payload = _create_plan_payload()
    old_payload["summary"]["plan_id"] = "old-plan"
    new_payload = _create_plan_payload()
    new_payload["summary"]["plan_id"] = "new-plan"
    old_path.write_text(json.dumps(old_payload, ensure_ascii=False), encoding="utf-8")
    new_path.write_text(json.dumps(new_payload, ensure_ascii=False), encoding="utf-8")
    client = TestClient(create_app(project_root=tmp_path))

    response = client.get("/api/create-plans/latest")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "最近创建计划"
    assert payload["summary"]["status"] == "ready"
    assert {"label": "计划 ID", "value": "new-plan"} in payload["summary"]["items"]
    assert payload["artifact_path"] == "data/runs/create_mode/20260528T010000Z.json"
    assert payload["raw"]["latest_plan_path"] == "data/runs/create_mode/20260528T010000Z.json"
    assert payload["sections"][0]["title"] == "已选素材"


def test_latest_create_plan_blocks_when_missing(tmp_path):
    client = TestClient(create_app(project_root=tmp_path))

    response = client.get("/api/create-plans/latest")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "最近创建计划"
    assert payload["summary"]["status"] == "blocked"
    assert payload["summary"]["execution_enabled"] is False
    assert "还没有生成过创建计划" in payload["summary"]["blocking_reasons"][0]


def test_create_plan_execute_preview_reads_plan_summary(tmp_path):
    plan_path = _write_create_plan(tmp_path)
    client = TestClient(create_app(project_root=tmp_path))

    response = client.post(
        "/api/create-plans/plan-1/execute/preview",
        json={"plan_path": plan_path, "plan_source": "current_generated"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "创建计划执行预览"
    assert payload["summary"]["status"] == "ready"
    assert payload["summary"]["execution_enabled"] is True
    assert {"label": "计划来源", "value": "本页刚生成的新计划"} in payload["summary"]["items"]
    assert {"label": "计划 ID", "value": "plan-1"} in payload["summary"]["items"]
    assert {"label": "固定模式", "value": "wx_pay_male_random_materials"} in payload["summary"]["items"]
    assert {"label": "素材复用规则", "value": "随机素材"} in payload["summary"]["items"]
    assert {"label": "候选素材数", "value": 3} in payload["summary"]["items"]
    assert {"label": "账户数", "value": 1} in payload["summary"]["items"]
    assert payload["table"]["columns"] == ["账户 ID", "账户名", "项目", "单元", "素材数", "文案数", "CTA 数", "卖点数"]
    assert payload["table"]["rows"][0] == {
        "账户 ID": "acc-1",
        "账户名": "未配置账户名",
        "项目": "项目1",
        "单元": "单元1",
        "素材数": 1,
        "文案数": 1,
        "CTA 数": 1,
        "卖点数": 1,
    }
    assert payload["raw"]["execute_command"][1] == "scripts/run_create_live_execute_once.py"
    assert "--check-config-only" not in payload["raw"]["execute_command"]
    assert payload["raw"]["post_command"][1] == "scripts/run_create_live_execute_report.py"
    assert [section["title"] for section in payload["sections"]] == ["已选素材", "文案", "CTA", "卖点", "账户素材分布"]


def test_create_plan_execute_preview_blocks_missing_plan(tmp_path):
    client = TestClient(create_app(project_root=tmp_path))

    response = client.post(
        "/api/create-plans/plan-1/execute/preview",
        json={"plan_path": "data/runs/create_mode/missing.json"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["status"] == "blocked"
    assert payload["summary"]["execution_enabled"] is False
    assert "创建计划 JSON 不存在" in payload["summary"]["blocking_reasons"][0]


def test_create_plan_execute_requires_confirmation(tmp_path):
    plan_path = _write_create_plan(tmp_path)
    client = TestClient(create_app(project_root=tmp_path))

    response = client.post(
        "/api/create-plans/plan-1/execute",
        json={"confirmation": "我已确认", "plan_path": plan_path},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "真实执行前必须输入：确认执行"


def test_create_plan_execute_starts_allowlisted_task(tmp_path, monkeypatch):
    plan_path = _write_create_plan(tmp_path)
    started = {}

    def fake_start_runner(command, *, cwd):
        started["command"] = command
        started["cwd"] = str(cwd)
        return 4321

    monkeypatch.setattr("backend.app.services.create_plans.start_runner", fake_start_runner, raising=False)
    client = TestClient(create_app(project_root=tmp_path))

    response = client.post(
        "/api/create-plans/plan-1/execute",
        json={"confirmation": "确认执行", "plan_path": plan_path, "resume_existing_plan": True},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "创建计划执行任务"
    assert payload["summary"]["status"] == "queued"
    assert payload["summary"]["execution_enabled"] is True
    task = payload["task"]
    assert task["pid"] == 4321
    assert task["operation_type"] == "create_live_execute"
    assert task["command"][1] == "scripts/run_create_live_execute_once.py"
    assert "--resume-existing-plan" in task["command"]
    assert task["post_commands"][0][1] == "scripts/run_create_live_execute_report.py"
    task_path = tmp_path / "data" / "runs" / task["artifact_path"]
    assert task_path.exists()
    assert started["command"] == ["python3", "scripts/run_frontend_task.py", "--task", str(task_path)]

    tasks = client.get("/api/tasks").json()["items"]
    assert tasks[0]["task_id"] == task["task_id"]
    assert tasks[0]["operation_type"] == "create_live_execute"

    operation_payload = client.get("/api/operations", params={"operation_type": "create_live_execute"}).json()
    operation_rows = operation_payload["table"]["rows"]
    assert len(operation_rows) == 1
    assert operation_rows[0]["关联任务"] == task["task_id"]
    assert operation_rows[0]["操作"] == "创建真实执行"
    assert operation_rows[0]["状态"] == "排队中"
    assert operation_rows[0]["产品"] == "点点英雄"
    raw_row = operation_payload["raw"]["rows"][0]
    assert raw_row["material_assignment_count"] == 1
    assert raw_row["unique_material_count"] == 1
