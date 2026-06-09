import json
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.main import create_app
from roibang_v2.db.bootstrap import bootstrap_database


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


def _write_create_suggestion_preview(root: Path) -> str:
    path = root / "data" / "runs" / "create_plan_from_suggestions" / "source.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "workflow": "create_plan_from_suggestions",
                "status": "preview_only",
                "summary": {"source_suggestion_count": 1, "account_count": 1},
                "suggestion_groups": [
                    {
                        "group_id": "create-plan-group-1",
                        "strategy_ids": ["stage4-capacity-v1"],
                        "account_count": 1,
                    }
                ],
                "source_suggestions": [
                    {
                        "suggestion_id": "create-acc-1",
                        "suggested_action": "suggest_create_project",
                        "product_key": "diandian-hero",
                        "product_name": "点点英雄",
                        "advertiser_id": "acc-1",
                        "account_name": "账户一",
                        "mode_key": "wx_pay_male_random_materials",
                        "strategy_id": "stage4-capacity-v1",
                        "metrics": {
                            "project_capacity": 1,
                            "qualified_material_count": 3,
                            "convert_cnt": 6,
                            "roi_1day": 1.2,
                        },
                        "reason": "账户容量和素材满足扩量条件。",
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return "data/runs/create_plan_from_suggestions/source.json"


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
    assert {"label": "素材来源", "value": "源素材账户"} in payload["summary"]["items"]
    assert {"label": "账户数", "value": 2} in payload["summary"]["items"]
    assert payload["table"]["columns"] == [
        "账户 ID",
        "账户名",
        "创建模式",
        "产品",
        "素材来源",
        "负责人",
        "目标日期",
        "出价",
        "ROI 系数",
    ]
    assert payload["table"]["rows"][0]["账户 ID"] == "1001"
    assert payload["table"]["rows"][0]["账户名"] == "未配置账户名"
    assert payload["table"]["rows"][0]["素材来源"] == "源素材账户"
    assert payload["raw"]["command"][1] == "scripts/run_create_mode.py"
    assert "--execute" not in payload["raw"]["command"]


def test_create_plan_preview_blocks_gravity_source_without_local_materials(tmp_path):
    client = TestClient(create_app(project_root=tmp_path))

    response = client.post(
        "/api/create-plans/preview",
        json={**_create_plan_request(), "material_source": "gravity_engine"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["status"] == "blocked"
    assert {"label": "素材来源", "value": "引力素材库"} in payload["summary"]["items"]
    assert {"label": "候选引力素材", "value": 0} in payload["summary"]["items"]
    assert payload["summary"]["blocking_reasons"] == [
        "没有命中可用于创建计划的本地引力素材；请先更新引力素材并确认固定模式里的素材规则。"
    ]
    assert payload["table"]["columns"] == [
        "账户 ID",
        "账户名",
        "创建模式",
        "产品",
        "素材来源",
        "负责人",
        "目标日期",
        "出价",
        "ROI 系数",
    ]
    assert payload["table"]["rows"][0]["素材来源"] == "引力素材库"
    command = payload["raw"]["command"]
    assert "--material-source" in command
    assert command[command.index("--material-source") + 1] == "gravity_engine"
    assert "--execute" not in command


def test_create_plan_preview_shows_gravity_auto_material_selection(tmp_path):
    mode_dir = tmp_path / "configs" / "create-modes" / "diandian-hero"
    mode_dir.mkdir(parents=True)
    (mode_dir / "wx_pay_male_random_materials.local.json").write_text(
        json.dumps(
            {
                "mode_key": "wx_pay_male_random_materials",
                "display_name": "每付男包随机素材",
                "product": "点点英雄",
                "product_key": "diandian-hero",
                "template_key": "wx_pay_general",
                "material_requirements": {"material_type": "video", "materials_per_unit": 1},
                "material_selection": {
                    "lookback_days": 7,
                    "selection_type": "high_spend",
                    "min_stat_cost": 100,
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    db_path = tmp_path / "data" / "roibang_v2.sqlite3"
    bootstrap_database(db_path)
    with sqlite3.connect(db_path) as conn:
        for material_id, name, stat_cost, convert_cnt in [
            ("gravity-m-1", "引力素材A", 300.0, 8),
            ("gravity-m-2", "引力素材B", 180.0, 3),
        ]:
            conn.execute(
                """
                INSERT INTO materials (
                  material_id, name, material_type, video_id, review_status,
                  cost_lookback, score, source, synced_at
                ) VALUES (?, ?, 'video', '', '可用', ?, ?, 'gravity_engine', 'now')
                """,
                (material_id, name, stat_cost, stat_cost),
            )
            conn.execute(
                """
                INSERT INTO product_source_materials (
                  product, source_advertiser_id, organization_id, material_id,
                  video_id, name, material_type, review_status, signature, create_time,
                  is_active, cost_lookback, score, payload_json, source, synced_at
                ) VALUES (
                  '点点英雄', 'gravity_engine_182', '182', ?, '', ?, 'video', '可用', ?,
                  '2026-06-08T10:00:00+08:00', 1, ?, ?, ?, 'gravity_engine', 'now'
                )
                """,
                (
                    material_id,
                    name,
                    f"md5-{material_id}",
                    stat_cost,
                    stat_cost,
                    json.dumps({"album_name": "黑旗-6480咸鱼-微小合集", "folder_name": "测试素材"}, ensure_ascii=False),
                ),
            )
            conn.execute(
                """
                INSERT INTO product_source_material_metric_rollups (
                  product, source_advertiser_id, organization_id, window_key, window_days,
                  period_start, period_end, material_id, material_type, source_video_id,
                  name, review_status, signature, stat_cost, convert_cnt,
                  roi_1day_cost_weighted, source, synced_at
                ) VALUES (
                  '点点英雄', 'gravity_engine_182', '182', 'last_7d', 7,
                  '2026-06-02', '2026-06-08', ?, 'video', '', ?, '可用', ?,
                  ?, ?, 0.42, 'gravity_engine', 'now'
                )
                """,
                (material_id, name, f"md5-{material_id}", stat_cost, convert_cnt),
            )
        conn.execute(
            """
            INSERT INTO gravity_upload_tasks (
              product, gravity_material_id, signature, target_advertiser_id,
              target_account_name, status, video_id, material_id_in_account,
              created_at, updated_at
            ) VALUES (
              '点点英雄', 'gravity-m-1', 'md5-gravity-m-1', '1001',
              '点点英雄-账户一', 'completed', 'v-uploaded-1', 'account-material-1',
              'now', 'now'
            )
            """
        )

    response = TestClient(create_app(project_root=tmp_path)).post(
        "/api/create-plans/preview",
        json={**_create_plan_request(), "material_source": "gravity_engine"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["status"] == "warning"
    assert {"label": "候选引力素材", "value": 2} in payload["summary"]["items"]
    assert {"label": "已可直接用", "value": "1 个素材 / 1 个账户覆盖"} in payload["summary"]["items"]
    assert {"label": "需要实时推送", "value": "3 个素材账户组合"} in payload["summary"]["items"]
    assert "本步骤只做自动选材预览，不上传素材、不创建广告。" in payload["summary"]["warnings"]
    section = next(section for section in payload["sections"] if section["title"] == "引力素材自动选材")
    assert section["table"]["columns"] == [
        "素材名",
        "引力素材 ID",
        "7天消耗",
        "7天转化",
        "ROI",
        "推送覆盖",
        "下一步",
    ]
    assert section["table"]["rows"][0]["素材名"] == "引力素材A"
    assert section["table"]["rows"][0]["推送覆盖"] == "已可用 1/2 个账户"
    assert section["table"]["rows"][0]["下一步"] == "缺失账户需实时推送"
    assert payload["raw"]["gravity_material_selection"]["pending_push_pairs"] == 3


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


def test_create_plan_modes_lists_product_specific_ai_promoted_modes(tmp_path):
    mode_path = tmp_path / "configs" / "create-modes" / "demo-game" / "ai_wx_pay_general_recent_scale_cost500_v1.local.json"
    mode_path.parent.mkdir(parents=True)
    mode_path.write_text(
        json.dumps(
            {
                "mode_key": "ai_wx_pay_general_recent_scale_cost500_v1",
                "display_name": "AI 每付通投近期放量 消耗500草稿",
                "product_key": "demo-game",
                "product": "演示游戏",
                "template_key": "wx_pay_general",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    client = TestClient(create_app(project_root=tmp_path))

    response = client.get("/api/create-plans/modes", params={"product_key": "demo-game"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "创建模式列表"
    assert payload["summary"]["execution_enabled"] is False
    assert {"label": "产品专属模式", "value": 1} in payload["summary"]["items"]
    rows = payload["table"]["rows"]
    ai_row = next(row for row in rows if row["模式 Key"] == "ai_wx_pay_general_recent_scale_cost500_v1")
    assert ai_row["创建模式"] == "AI 每付通投近期放量 消耗500草稿"
    assert ai_row["产品"] == "演示游戏"
    assert ai_row["产品 Key"] == "demo-game"
    assert ai_row["来源"] == "产品专属"
    assert ai_row["路径"] == "configs/create-modes/demo-game/ai_wx_pay_general_recent_scale_cost500_v1.local.json"
    assert ai_row["模板 Key"] == "wx_pay_general"
    assert any(row["模式 Key"] == "wx_pay_general_recent_scale" for row in rows)
    assert payload["raw"]["modes"][0]["label"]


def test_create_plan_preview_shows_ai_promoted_mode_source_and_path(tmp_path):
    mode_path = tmp_path / "configs" / "create-modes" / "demo-game" / "ai_wx_pay_general_recent_scale_cost500_v1.local.json"
    mode_path.parent.mkdir(parents=True)
    mode_path.write_text(
        json.dumps(
            {
                "mode_key": "ai_wx_pay_general_recent_scale_cost500_v1",
                "display_name": "AI 每付通投近期放量 消耗500草稿",
                "product_key": "demo-game",
                "product": "演示游戏",
                "template_key": "wx_pay_general",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    client = TestClient(create_app(project_root=tmp_path))

    response = client.post(
        "/api/create-plans/preview",
        json={
            **_create_plan_request(),
            "mode": "ai_wx_pay_general_recent_scale_cost500_v1",
            "product_key": "demo-game",
            "product_name": "演示游戏",
            "template_catalog": "configs/create-templates/wx-mini-game.json",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["status"] == "planned"
    assert {"label": "创建模式", "value": "ai_wx_pay_general_recent_scale_cost500_v1"} in payload["summary"]["items"]
    assert {"label": "模式名称", "value": "AI 每付通投近期放量 消耗500草稿"} in payload["summary"]["items"]
    assert {"label": "模式来源", "value": "产品专属"} in payload["summary"]["items"]
    assert {
        "label": "模式文件",
        "value": "configs/create-modes/demo-game/ai_wx_pay_general_recent_scale_cost500_v1.local.json",
    } in payload["summary"]["items"]
    assert payload["raw"]["mode_metadata"]["source"] == "产品专属"
    assert payload["raw"]["mode_metadata"]["path"] == "configs/create-modes/demo-game/ai_wx_pay_general_recent_scale_cost500_v1.local.json"
    command = payload["raw"]["command"]
    assert command[command.index("--mode") + 1] == "ai_wx_pay_general_recent_scale_cost500_v1"
    assert command[command.index("--product-key") + 1] == "demo-game"


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


def test_create_plan_execution_review_preview_returns_sections_and_artifact(tmp_path):
    plan_path = _write_create_plan(tmp_path)
    source_path = _write_create_suggestion_preview(tmp_path)
    client = TestClient(create_app(project_root=tmp_path))

    response = client.post(
        "/api/create-plans/execution-review/preview",
        json={
            "plan_path": plan_path,
            "source_suggestion_preview_path": source_path,
            "operator": "郭靖",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "创建计划执行前复核"
    assert payload["summary"]["status"] == "warning_only"
    assert payload["summary"]["execution_enabled"] is False
    assert {"label": "来源策略", "value": "stage4-capacity-v1"} in payload["summary"]["items"]
    assert payload["table"]["columns"] == ["检查项", "结果", "等级", "说明", "证据"]
    assert {section["title"] for section in payload["sections"]} == {"运营记录", "确认执行清单", "来源建议证据"}
    assert Path(payload["artifact_path"]).exists()


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


def test_create_plan_execute_blocks_when_execution_review_finds_duplicate_ledger(tmp_path):
    plan_path = _write_create_plan(tmp_path)
    source_path = _write_create_suggestion_preview(tmp_path)
    db_path = tmp_path / "data" / "roibang_v2.sqlite3"
    bootstrap_database(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO create_provider_id_ledger (
              entity_type, local_key, provider_id, plan_id, request_id, advertiser_id,
              parent_local_key, status, source_workflow, execution_enabled,
              response_payload_json, first_seen_at, last_seen_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "project",
                "acc-1-p001",
                "project-real-1",
                "plan-1",
                "",
                "acc-1",
                "",
                "active",
                "create_live_execute_once",
                0,
                "{}",
                "2026-05-31T00:00:00Z",
                "2026-05-31T00:00:00Z",
            ),
        )
    client = TestClient(create_app(project_root=tmp_path))

    response = client.post(
        "/api/create-plans/plan-1/execute",
        json={
            "confirmation": "确认执行",
            "plan_path": plan_path,
            "source_suggestion_preview_path": source_path,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "创建计划执行被复核阻断"
    assert payload["summary"]["status"] == "blocked"
    assert payload["summary"]["execution_enabled"] is False
    assert "本地账本已存在计划 plan-1" in payload["summary"]["blocking_reasons"][0]
    assert "task" not in payload


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
