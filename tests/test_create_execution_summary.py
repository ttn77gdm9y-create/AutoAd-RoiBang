from roibang_v2.ui.create_execution_summary import build_create_execution_summary


def test_summary_prefers_report_counts_and_feishu_status():
    report = {
        "status": "reported_completed",
        "summary": {
            "created_project_count": 20,
            "created_unit_count": 10,
            "material_bind_count": 98,
            "source_external_api_calls": 132,
        },
        "delivery": {"feishu": {"attempted": True, "ok": True}},
        "message": "真实创建结果：完成项目20个、单元10个、素材推送98组。",
    }

    summary = build_create_execution_summary(report_payload=report)

    assert summary["status"] == "reported_completed"
    assert summary["created_project_count"] == 20
    assert summary["created_unit_count"] == 10
    assert summary["material_bind_count"] == 98
    assert summary["external_api_calls"] == 132
    assert summary["feishu_status"] == "sent"
    assert summary["message"] == "真实创建结果：完成项目20个、单元10个、素材推送98组。"
    assert summary["manual_review_required"] is False


def test_summary_exposes_partial_failure_accounts_and_rebuild_reference():
    report = {
        "status": "reported_partial_completed",
        "summary": {
            "created_project_count": 20,
            "created_unit_count": 10,
            "material_bind_count": 98,
            "material_bind_failure_count": 2,
            "skipped_unit_count": 10,
            "affected_account_count": 2,
        },
        "delivery": {"feishu": {"attempted": True, "ok": False, "reason": "webhook error"}},
        "readable_reference": {
            "execution_issues": {
                "manual_review_required": True,
                "affected_account_count": 2,
                "skipped_unit_count": 10,
                "material_bind_failure_count": 2,
                "accounts": [
                    {
                        "advertiser_id": "1866125088740552",
                        "skipped_unit_count": 5,
                        "codes": ["400170"],
                        "messages": ["部分视频无权限或不存在"],
                    }
                ],
                "rebuild_reference": [
                    {
                        "advertiser_id": "1866125088740552",
                        "skipped_unit_count": 5,
                        "reason": "部分视频无权限或不存在",
                    }
                ],
            }
        },
    }

    summary = build_create_execution_summary(report_payload=report)

    assert summary["status"] == "reported_partial_completed"
    assert summary["manual_review_required"] is True
    assert summary["affected_account_count"] == 2
    assert summary["skipped_unit_count"] == 10
    assert summary["material_bind_failure_count"] == 2
    assert summary["feishu_status"] == "failed"
    assert summary["feishu_reason"] == "webhook error"
    assert summary["issue_accounts"][0]["advertiser_id"] == "1866125088740552"
    assert summary["rebuild_reference"][0]["reason"] == "部分视频无权限或不存在"


def test_summary_falls_back_to_task_and_execute_payload():
    task = {"status": "failed", "return_code": 1}
    execute = {
        "ok": False,
        "status": "create_http_failed",
        "external_api_calls": 6,
        "failure": {"operation": "create_project", "code": 40000, "message": "系统错误"},
    }

    summary = build_create_execution_summary(task=task, execute_payload=execute)

    assert summary["status"] == "create_http_failed"
    assert summary["task_status"] == "failed"
    assert summary["return_code"] == 1
    assert summary["external_api_calls"] == 6
    assert summary["failure"]["message"] == "系统错误"
