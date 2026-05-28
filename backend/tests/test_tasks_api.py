import json
from pathlib import Path

from backend.app.services.tasks import list_tasks
from backend.app.services.tasks import load_task_detail


def test_task_detail_localizes_existing_create_plan_block(tmp_path: Path):
    runs_dir = tmp_path / "data" / "runs"
    task_dir = runs_dir / "frontend_tasks"
    task_dir.mkdir(parents=True)
    accounts_path = tmp_path / "configs" / "accounts" / "product-accounts.local.json"
    accounts_path.parent.mkdir(parents=True)
    accounts_path.write_text(
        json.dumps(
            {
                "accounts": [
                    {
                        "advertiser_id": "1001",
                        "advertiser_name": "点点英雄-微小-郭靖",
                        "product_key": "diandian-hero",
                        "product_name": "点点英雄",
                        "status": "active",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    result = {
        "ok": False,
        "workflow": "create_live_execute_once",
        "phase": "phase2_preparation",
        "status": "blocked",
        "execution_enabled": False,
        "external_api_calls": 0,
        "blocking_reasons": [
            "existing active project/unit provider IDs found for this plan_id/request_id; generate a new create_mode plan or pass --resume-existing-plan to continue the old plan"
        ],
        "existing_plan_ledger": {
            "count": 4,
            "by_entity_type": {"project": 2, "promotion": 2},
            "samples": [
                {
                    "entity_type": "project",
                    "local_key": "1001-p001",
                    "provider_id": "project-1",
                    "advertiser_id": "",
                }
            ],
        },
        "artifact_path": "data/runs/create_live_execute_once/result.json",
    }
    (task_dir / "frontend-existing-plan.json").write_text(
        json.dumps(
            {
                "task_id": "frontend-existing-plan",
                "operation_type": "create_live_execute",
                "status": "failed",
                "created_at": "2026-05-28T14:47:12+08:00",
                "updated_at": "2026-05-28T14:47:12+08:00",
                "return_code": 1,
                "result": result,
                "stdout_path": "frontend_tasks/frontend-existing-plan.stdout.log",
                "stderr_path": "frontend_tasks/frontend-existing-plan.stderr.log",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    rows = list_tasks(runs_dir, tmp_path / "configs")
    detail = load_task_detail(runs_dir, "frontend-existing-plan", tmp_path / "configs")

    assert "已阻止重复执行" in rows[0]["result_summary"]
    assert "项目 2 个、单元 2 个" in rows[0]["result_summary"]
    assert detail["summary"]["blocking_reasons"] == [
        "这个创建计划已有创建记录（项目 2 个、单元 2 个），系统未发起外部创建，已阻止重复执行。要新建一批，请重新生成计划。"
    ]
    assert "续跑已有计划" not in detail["summary"]["blocking_reasons"][0]
    assert {"label": "已存在创建记录", "value": "项目 2 个、单元 2 个"} in detail["summary"]["items"]
    assert {"label": "真实外部创建", "value": "未发起"} in detail["summary"]["items"]
    assert detail["sections"][0]["title"] == "已存在创建记录"
    assert detail["sections"][0]["table"]["rows"][0]["账户名"] == "点点英雄-微小-郭靖"


def test_running_task_progress_is_parsed_from_stdout(tmp_path: Path):
    runs_dir = tmp_path / "data" / "runs"
    task_dir = runs_dir / "frontend_tasks"
    task_dir.mkdir(parents=True)
    (task_dir / "frontend-running.json").write_text(
        json.dumps(
            {
                "task_id": "frontend-running",
                "operation_type": "create_live_execute",
                "status": "running",
                "created_at": "2026-05-28T15:52:24+08:00",
                "updated_at": "2026-05-28T15:52:30+08:00",
                "return_code": None,
                "stdout_path": "frontend_tasks/frontend-running.stdout.log",
                "stderr_path": "frontend_tasks/frontend-running.stderr.log",
                "result": {},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (task_dir / "frontend-running.stderr.log").write_text(
        "\n".join(
            [
                "[create_live_execute_once] operation=create_project done=0/20 status=running calls=0 message=pending=20 skipped=0",
                "[create_live_execute_once] operation=create_project done=5/20 status=running calls=5 account=1866125091469320",
            ]
        ),
        encoding="utf-8",
    )

    rows = list_tasks(runs_dir, tmp_path / "configs")
    detail = load_task_detail(runs_dir, "frontend-running", tmp_path / "configs")

    assert rows[0]["progress"] == {
        "percent": 25,
        "current": 5,
        "total": 20,
        "label": "创建项目 5/20",
        "status": "active",
    }
    assert detail["summary"]["progress"] == rows[0]["progress"]
    assert {"label": "当前进度", "value": "创建项目 5/20"} in detail["summary"]["items"]


def test_failed_create_task_summary_includes_api_failure_reason(tmp_path: Path):
    runs_dir = tmp_path / "data" / "runs"
    task_dir = runs_dir / "frontend_tasks"
    task_dir.mkdir(parents=True)
    (task_dir / "frontend-failed.json").write_text(
        json.dumps(
            {
                "task_id": "frontend-failed",
                "operation_type": "create_live_execute",
                "status": "failed",
                "created_at": "2026-05-28T15:52:24+08:00",
                "updated_at": "2026-05-28T15:52:44+08:00",
                "return_code": 1,
                "stdout_path": "frontend_tasks/frontend-failed.stdout.log",
                "stderr_path": "frontend_tasks/frontend-failed.stderr.log",
                "result": {
                    "ok": False,
                    "status": "create_http_failed",
                    "failure": {
                        "operation": "create_project",
                        "code": 51010,
                        "message": "服务错误，请稍后重试",
                    },
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    detail = load_task_detail(runs_dir, "frontend-failed", tmp_path / "configs")

    assert {"label": "失败步骤", "value": "创建项目"} in detail["summary"]["items"]
    assert {"label": "失败原因", "value": "服务错误，请稍后重试（51010）"} in detail["summary"]["items"]


def test_tasks_show_create_template_and_project_action_context(tmp_path: Path):
    runs_dir = tmp_path / "data" / "runs"
    task_dir = runs_dir / "frontend_tasks"
    create_plan_dir = runs_dir / "create_mode"
    project_update_dir = tmp_path / "configs" / "project-updates"
    task_dir.mkdir(parents=True)
    create_plan_dir.mkdir(parents=True)
    project_update_dir.mkdir(parents=True)
    (create_plan_dir / "plan-1.json").write_text(
        json.dumps(
            {
                "mode_key": "wx_pay_male_random_materials",
                "summary": {
                    "display_name": "点点英雄每付男素材不限",
                    "template_catalog_path": "configs/create-templates/diandian-hero.local.json",
                },
                "create_request": {
                    "template_key": "wx_pay_male",
                    "project_template_name": "微小每付男素材不限",
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (project_update_dir / "delete.local.json").write_text(
        json.dumps(
            {
                "project_update_id": "delete-1",
                "actions": [
                    {
                        "action_type": "delete_project",
                        "advertiser_id": "1001",
                        "project_id": "p-1",
                        "project_name": "项目1",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (task_dir / "frontend-create.json").write_text(
        json.dumps(
            {
                "task_id": "frontend-create",
                "operation_type": "create_live_execute",
                "status": "queued",
                "created_at": "2026-05-28T14:47:12+08:00",
                "updated_at": "2026-05-28T14:47:12+08:00",
                "return_code": None,
                "request": {"plan_path": "data/runs/create_mode/plan-1.json"},
                "result": {"status": "queued"},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (task_dir / "frontend-project.json").write_text(
        json.dumps(
            {
                "task_id": "frontend-project",
                "operation_type": "project_update_execute",
                "status": "queued",
                "created_at": "2026-05-28T14:48:12+08:00",
                "updated_at": "2026-05-28T14:48:12+08:00",
                "return_code": None,
                "request": {"project_update_path": "configs/project-updates/delete.local.json"},
                "result": {"status": "queued"},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    rows = list_tasks(runs_dir, tmp_path / "configs")
    create_detail = load_task_detail(runs_dir, "frontend-create", tmp_path / "configs")
    project_detail = load_task_detail(runs_dir, "frontend-project", tmp_path / "configs")

    rows_by_id = {row["task_id"]: row for row in rows}
    assert rows_by_id["frontend-create"]["business_context"] == "固定模式：点点英雄每付男素材不限；基础模板：微小每付男素材不限"
    assert "固定模式 点点英雄每付男素材不限" in rows_by_id["frontend-create"]["result_summary"]
    assert rows_by_id["frontend-project"]["business_context"] == "项目管理动作：删除项目"
    assert "项目管理动作 删除项目" in rows_by_id["frontend-project"]["result_summary"]
    assert {"label": "固定模式", "value": "点点英雄每付男素材不限"} in create_detail["summary"]["items"]
    assert {"label": "基础模板", "value": "微小每付男素材不限"} in create_detail["summary"]["items"]
    assert {"label": "模板文件", "value": "configs/create-templates/diandian-hero.local.json"} in create_detail["summary"]["items"]
    assert {"label": "项目管理动作", "value": "删除项目"} in project_detail["summary"]["items"]
