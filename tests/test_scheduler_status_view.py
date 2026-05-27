from roibang_v2.ui.scheduler_status_view import build_scheduler_status_view


def test_scheduler_status_view_builds_product_and_job_rows():
    payload = {
        "ok": False,
        "summary": {
            "report_date": "2026-05-27",
            "expected_data_date": "2026-05-26",
            "job_count": 1,
            "ok_count": 0,
            "attention_count": 1,
            "product_count": 1,
        },
        "jobs": [
            {
                "job_id": "roibang-source-material-account-auto-push",
                "display_name": "05:00 源素材账户自动补材",
                "status": "attention",
                "issues": ["launchd 上次退出码 1"],
                "launchd": {"last_exit_code": "1"},
                "data_check": {"type": "source_material_account", "status": "ok"},
                "artifact_contract": {"ok": True, "artifact_path": "data/runs/product_automation_job_source_material_auto_push/a.json"},
                "scheduler_result": {"ok": False, "path": "data/runs/scheduler/job/a.json"},
                "product_results": [
                    {
                        "product": "点点英雄",
                        "product_key": "diandian-hero",
                        "job": "source_material_auto_push",
                        "ok": True,
                        "status": "completed",
                        "summary": {"new_material_count": 3},
                    }
                ],
            }
        ],
        "message": "日报",
    }

    view = build_scheduler_status_view(payload)

    assert view["summary"]["attention_count"] == 1
    assert view["job_rows"][0]["last_exit_code"] == "1"
    assert view["product_rows"][0]["product"] == "点点英雄"
    assert view["product_rows"][0]["status"] == "attention"
    assert view["product_rows"][0]["summary"]["new_material_count"] == 3
    assert view["issue_rows"][0]["issue"] == "launchd 上次退出码 1"
    assert len(view["artifact_rows"]) == 2


def test_scheduler_status_view_uses_top_level_product_summary_when_job_details_missing():
    payload = {
        "ok": True,
        "summary": {"product_count": 1},
        "product_summary": [
            {
                "product": "点点英雄",
                "product_key": "diandian-hero",
                "jobs": [
                    {
                        "job_id": "job-1",
                        "display_name": "任务",
                        "job": "daily_report_sync",
                        "status": "ok",
                        "artifact_path": "data/runs/x.json",
                        "summary": {"snapshots_written": 12},
                    }
                ],
            }
        ],
    }

    view = build_scheduler_status_view(payload)

    assert view["summary"]["product_count"] == 1
    assert view["product_rows"][0]["job"] == "daily_report_sync"
    assert view["product_rows"][0]["summary"]["snapshots_written"] == 12
