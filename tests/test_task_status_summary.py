from roibang_v2.ui.task_status_summary import build_task_status_summary


def test_task_status_summary_marks_running_progress_and_auto_refresh():
    summary = build_task_status_summary(
        task={"task_id": "task-1", "operation_type": "create_live_execute", "status": "running"},
        progress={
            "percent": 37,
            "current": {
                "status": "running",
                "operation": "create_unit",
                "done": 3,
                "total": 8,
                "advertiser_id": "acc-1",
                "external_api_calls": 12,
            },
            "events": [{"status": "running", "operation": "create_unit"}],
        },
    )

    assert summary["status_level"] == "running"
    assert summary["should_auto_refresh"] is True
    assert summary["progress_percent"] == 37
    assert summary["progress_operation"] == "create_unit"
    assert summary["progress_done"] == 3
    assert summary["progress_total"] == 8
    assert summary["progress_account"] == "acc-1"
    assert summary["external_api_calls"] == 12


def test_task_status_summary_exposes_partial_failure_and_feishu_status():
    report = {
        "status": "reported_partial_completed",
        "summary": {
            "created_project_count": 20,
            "created_unit_count": 10,
            "material_bind_count": 98,
            "affected_account_count": 2,
            "skipped_unit_count": 10,
            "material_bind_failure_count": 2,
        },
        "delivery": {"feishu": {"attempted": True, "ok": False, "reason": "webhook error"}},
        "readable_reference": {
            "execution_issues": {
                "manual_review_required": True,
                "accounts": [{"advertiser_id": "acc-1", "codes": ["400170"]}],
                "rebuild_reference": [{"advertiser_id": "acc-1", "reason": "补建"}],
            }
        },
    }

    summary = build_task_status_summary(task={"status": "completed"}, report_payload=report)

    assert summary["status"] == "reported_partial_completed"
    assert summary["status_level"] == "warning"
    assert summary["manual_review_required"] is True
    assert summary["affected_account_count"] == 2
    assert summary["skipped_unit_count"] == 10
    assert summary["material_bind_failure_count"] == 2
    assert summary["feishu_status"] == "failed"
    assert summary["feishu_reason"] == "webhook error"
    assert summary["issue_accounts"][0]["advertiser_id"] == "acc-1"
    assert summary["rebuild_reference"][0]["reason"] == "补建"


def test_task_status_summary_marks_execute_failure():
    summary = build_task_status_summary(
        task={"status": "failed", "return_code": 1},
        execute_payload={
            "status": "create_http_failed",
            "failure": {"operation": "create_project", "code": 40000, "message": "系统错误"},
        },
    )

    assert summary["status_level"] == "error"
    assert summary["return_code"] == 1
    assert summary["failure"]["message"] == "系统错误"


def test_task_status_summary_does_not_treat_stale_progress_as_running_when_task_completed():
    summary = build_task_status_summary(
        task={"status": "completed"},
        progress={"percent": 50, "current": {"status": "running", "operation": "create_unit", "done": 1, "total": 2}},
    )

    assert summary["status"] == "completed"
    assert summary["status_level"] == "success"
    assert summary["should_auto_refresh"] is False
