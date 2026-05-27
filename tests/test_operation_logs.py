import json
from pathlib import Path

from roibang_v2.ui.operation_logs import filter_operation_logs
from roibang_v2.ui.operation_logs import load_operation_log_detail
from roibang_v2.ui.operation_logs import load_operation_logs


def _write_log(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_load_operation_logs_supports_filters_and_old_artifacts(tmp_path: Path):
    runs_dir = tmp_path / "runs"
    log_dir = runs_dir / "frontend_operation_log"
    first = log_dir / "20260526T120000Z.json"
    second = log_dir / "20260526T130000Z.json"
    _write_log(
        first,
        {
            "task_id": "task-1",
            "operation_type": "create_plan_generate",
            "status": "completed",
            "actor": "郭靖",
            "summary": {
                "product": "点点英雄",
                "product_key": "diandian-hero",
                "account_count": 2,
                "material_assignment_count": 20,
                "unique_material_count": 10,
                "review_status": "passed",
            },
            "created_at": "2026-05-26T12:00:00+00:00",
        },
    )
    _write_log(
        second,
        {
            "workflow": "frontend_operation_log",
            "operation_type": "delivery_patrol_run",
            "status": "failed",
            "summary": {"product": "勇者突进"},
            "created_at": "2026-05-26T13:00:00+00:00",
        },
    )

    rows = load_operation_logs(runs_dir)

    assert [row["operation_type"] for row in rows] == ["delivery_patrol_run", "create_plan_generate"]
    assert rows[1]["task_id"] == "task-1"
    assert rows[1]["product_key"] == "diandian-hero"
    assert rows[0]["task_id"].startswith("legacy-")
    assert filter_operation_logs(rows, product="点点英雄") == [rows[1]]
    assert filter_operation_logs(rows, operation_type="delivery_patrol_run") == [rows[0]]
    assert filter_operation_logs(rows, status="completed") == [rows[1]]


def test_load_operation_log_detail_extracts_create_review_and_feishu_status(tmp_path: Path):
    runs_dir = tmp_path / "runs"
    execute_path = runs_dir / "create_live_execute_once" / "result.json"
    report_path = runs_dir / "create_live_execute_report" / "report.json"
    log_path = runs_dir / "frontend_operation_log" / "20260526T120000Z.json"
    _write_log(
        execute_path,
        {
            "ok": False,
            "status": "create_http_failed",
            "failure": {
                "operation": "create_project",
                "index": 5,
                "code": 40000,
                "message": "当前优化目标不可用，请重新选择",
            },
        },
    )
    _write_log(
        report_path,
        {
            "delivery": {
                "feishu": {
                    "attempted": True,
                    "ok": False,
                    "reason": "webhook error",
                }
            },
            "message": "真实创建结果：部分失败",
        },
    )
    _write_log(
        log_path,
        {
            "task_id": "task-create",
            "operation_type": "create_live_execute",
            "status": "failed",
            "actor": "郭靖",
            "summary": {
                "product": "点点英雄",
                "product_key": "diandian-hero",
                "account_count": 1,
                "material_assignment_count": 1,
                "unique_material_count": 1,
                "review_status": "passed",
            },
            "result": {
                "execute_artifact_path": str(execute_path),
                "report_artifact_path": str(report_path),
                "status": "create_http_failed",
            },
            "details": {
                "review": {
                    "can_execute": True,
                    "summary": {"warning_count": 0},
                    "blocking_reasons": [],
                },
                "accounts": [{"advertiser_id": "acc-1", "project_count": 1}],
                "materials": [
                    {
                        "material_id": "m-1",
                        "video_id": "video-1",
                        "product_stat_cost": 123.45,
                        "product_convert_cnt": 6,
                        "usage_count": 1,
                    }
                ],
                "creative_usage": {
                    "titles": [{"title": "标题1", "usage_count": 1}],
                    "ctas": [{"cta": "立即下载", "usage_count": 1}],
                    "selling_points": [{"selling_point": "爆率高", "usage_count": 1}],
                },
                "unit_assignments": [{"unit_key": "u1", "materials": [{"material_id": "m-1"}]}],
            },
            "created_at": "2026-05-26T12:00:00+00:00",
        },
    )

    detail = load_operation_log_detail(runs_dir, "task-create")

    assert detail["row"]["task_id"] == "task-create"
    assert detail["artifact"]["operation_type"] == "create_live_execute"
    assert detail["create_review"]["materials"][0]["product_stat_cost"] == 123.45
    assert detail["create_review"]["creative_usage"]["titles"][0]["title"] == "标题1"
    assert detail["failure"] == {
        "operation": "create_project",
        "index": 5,
        "code": 40000,
        "message": "当前优化目标不可用，请重新选择",
    }
    assert detail["feishu"] == {"status": "failed", "reason": "webhook error", "message": "真实创建结果：部分失败"}


def test_load_operation_logs_merges_frontend_task_final_status(tmp_path: Path):
    runs_dir = tmp_path / "runs"
    log_path = runs_dir / "frontend_operation_log" / "20260526T120000Z.json"
    task_path = runs_dir / "frontend_tasks" / "frontend-create-1.json"
    execute_path = runs_dir / "create_live_execute_once" / "result.json"
    report_path = runs_dir / "create_live_execute_report" / "report.json"
    _write_log(
        log_path,
        {
            "task_id": "frontend-create-1",
            "operation_type": "create_live_execute",
            "status": "running",
            "summary": {"product": "点点英雄", "product_key": "diandian-hero"},
            "result": {"task_id": "frontend-create-1", "status": "running"},
            "created_at": "2026-05-26T12:00:00+00:00",
        },
    )
    _write_log(
        task_path,
        {
            "task_id": "frontend-create-1",
            "operation_type": "create_live_execute",
            "status": "completed",
            "return_code": 0,
            "stdout_path": "frontend_tasks/frontend-create-1.stdout.log",
            "stderr_path": "frontend_tasks/frontend-create-1.stderr.log",
            "result": {
                "ok": True,
                "status": "create_http_completed",
                "artifact_path": str(execute_path),
            },
            "post_results": [
                {
                    "ok": True,
                    "artifact_path": str(report_path),
                    "delivery": {"feishu": {"attempted": True, "ok": True}},
                }
            ],
            "updated_at": "2026-05-26T12:10:00+00:00",
        },
    )

    rows = load_operation_logs(runs_dir)
    detail = load_operation_log_detail(runs_dir, "frontend-create-1")

    assert rows[0]["status"] == "completed"
    assert rows[0]["task_status"] == "completed"
    assert rows[0]["return_code"] == 0
    assert rows[0]["result_status"] == "create_http_completed"
    assert rows[0]["execute_artifact_path"] == str(execute_path)
    assert rows[0]["report_artifact_path"] == str(report_path)
    assert rows[0]["feishu_status"] == "sent"
    assert rows[0]["stdout_path"] == "frontend_tasks/frontend-create-1.stdout.log"
    assert detail["row"]["status"] == "completed"
    assert detail["task"]["task_id"] == "frontend-create-1"


def test_load_operation_log_detail_derives_review_from_real_operation_details(tmp_path: Path):
    runs_dir = tmp_path / "runs"
    log_path = runs_dir / "frontend_operation_log" / "20260526T120000Z.json"
    _write_log(
        log_path,
        {
            "task_id": "task-create",
            "operation_type": "create_plan_generate",
            "status": "completed",
            "summary": {"product": "点点英雄", "product_key": "diandian-hero"},
            "details": {
                "product": "点点英雄",
                "product_key": "diandian-hero",
                "source_advertiser_id": "source-dd",
                "accounts": [{"advertiser_id": "acc-1", "project_count": 1}],
                "material_assignments": [
                    {
                        "advertiser_id": "acc-1",
                        "unit_key": "u1",
                        "material_id": "m-1",
                        "source_video_id": "video-1",
                        "name": "素材1",
                        "stat_cost": 123.45,
                        "convert_cnt": 6,
                    }
                ],
                "unit_copywriting": [
                    {
                        "advertiser_id": "acc-1",
                        "unit_key": "u1",
                        "promotion_name": "单元1",
                        "title_material_list": [{"title": "标题1"}],
                        "call_to_action_buttons": ["立即下载"],
                        "product_info": {"selling_points": ["爆率高"]},
                    }
                ],
            },
            "created_at": "2026-05-26T12:00:00+00:00",
        },
    )

    detail = load_operation_log_detail(runs_dir, "task-create")

    assert detail["create_review"]["materials"][0]["material_id"] == "m-1"
    assert detail["create_review"]["materials"][0]["product_stat_cost"] == 123.45
    assert detail["create_review"]["creative_usage"]["titles"][0]["title"] == "标题1"
    assert detail["create_review"]["creative_usage"]["ctas"][0]["cta"] == "立即下载"
    assert detail["create_review"]["creative_usage"]["selling_points"][0]["selling_point"] == "爆率高"
    assert detail["create_review"]["unit_assignments"][0]["materials"][0]["video_id"] == "video-1"
