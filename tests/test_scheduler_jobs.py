from pathlib import Path

import pytest

from roibang_v2.scheduler.jobs import load_job_registry, validate_job_registry


def test_scheduler_registry_has_no_ai_execution_prompts():
    registry = load_job_registry(Path("configs/scheduler/roibang-v2.jobs.example.json"))

    result = validate_job_registry(registry)

    assert result == {
        "ok": True,
        "jobs": 24,
        "enabled_jobs": 12,
        "disabled_jobs": 12,
        "violations": [],
    }


def test_scheduler_registry_includes_disabled_fixed_create_chain_jobs():
    registry = load_job_registry(Path("configs/scheduler/roibang-v2.jobs.example.json"))
    jobs = {job["id"]: job for job in registry["jobs"]}

    expected = {
        "roibang-create-plan-validate": (
            "create_plan_validate",
            "scripts/run_create_plan_validate.py",
        ),
        "roibang-create-live-execute-once": (
            "create_live_execute_once",
            "scripts/run_create_live_execute_once.py",
        ),
        "roibang-create-live-execute-report": (
            "create_live_execute_report",
            "scripts/run_create_live_execute_report.py",
        ),
    }
    for job_id, (workflow, script_path) in expected.items():
        job = jobs[job_id]
        assert job["enabled"] is False
        assert job["script"]["command"][1] == script_path
        assert "path" not in job["script"]
        assert "args" not in job["script"]
        assert "prompt" not in job
        assert job["result_contract"]["workflow"] == workflow
        assert job["result_contract"]["artifact_dir"] == f"data/runs/{workflow}"
    removed_non_main_jobs = {
        "roibang-create-approval",
        "roibang-create-plan-snapshot",
        "roibang-create-chain-replay",
        "roibang-create-chain-manifest",
        "roibang-create-readiness-matrix",
        "roibang-create-live-execute-phase-gate",
        "roibang-create-live-payload-adapter-scaffold",
        "roibang-create-mock-execute",
        "roibang-create-adapter-review-pack",
        "roibang-create-chain-index",
        "roibang-create-chain-final-report",
        "roibang-create-phase1-acceptance-checklist",
        "roibang-create-phase1-baseline-freeze",
        "roibang-create-first-live-local-chain",
    }
    assert removed_non_main_jobs.isdisjoint(jobs)
    assert jobs["roibang-create-live-execute-once"]["script"]["command"] == [
        "python3",
        "scripts/run_create_live_execute_once.py",
        "--config",
        "configs/runtime.example.json",
        "--plan",
        "configs/create-plans/first-live.local.json",
        "--policy",
        "policies/create-policy.example.json",
        "--create-execute-artifact",
        "data/runs/create_execute/first-live.local.json",
    ]
    assert jobs["roibang-create-live-execute-report"]["script"]["command"] == [
        "python3",
        "scripts/run_create_live_execute_report.py",
        "--config",
        "configs/runtime.example.json",
        "--plan",
        "configs/create-plans/first-live.local.json",
    ]
    assert jobs["roibang-create-plan-validate"]["script"]["command"] == [
        "python3",
        "scripts/run_create_plan_validate.py",
        "--config",
        "configs/runtime.example.json",
        "--plan",
        "configs/create-plans/first-live.local.json",
        "--policy",
        "policies/create-policy.example.json",
    ]


def test_scheduler_registry_phase1_contracts_pin_safe_execution_values():
    registry = load_job_registry(Path("configs/scheduler/roibang-v2.jobs.example.json"))

    for job in registry["jobs"]:
        contract = job["result_contract"]
        if job["id"] == "roibang-project-schedule-restore-due":
            assert contract["must_equal"]["execution_enabled"] is True
            continue
        if job["id"] == "roibang-source-material-account-auto-push":
            assert contract["must_equal"] == {}
            continue
        if job["id"] == "roibang-source-material-preload-to-guojing-spent":
            assert contract["must_equal"] == {"execution_enabled": True}
            continue
        assert contract["must_equal"]["execution_enabled"] is False
        if job["id"] in {
            "roibang-daily-report-pipeline",
            "roibang-material-history-yesterday",
            "roibang-operation-log-yesterday-sync",
            "roibang-delivery-patrol",
        }:
            assert "external_api_calls" not in contract["must_equal"]
        elif job["id"] == "roibang-project-schedule-restore-due":
            assert contract["must_equal"] == {"execution_enabled": True}
        else:
            assert contract["must_equal"]["external_api_calls"] == 0

    jobs = {job["id"]: job for job in registry["jobs"]}
    for job_id in [
        "roibang-strategy-preflight",
        "roibang-strategy-dry-run",
        "roibang-create-live-execute-report",
        "roibang-create-plan-validate",
    ]:
        assert "actions" in jobs[job_id]["result_contract"]["must_be_empty"]

    live_execute_contract = jobs["roibang-create-live-execute-once"]["result_contract"]
    assert "blocking_reasons" in live_execute_contract["must_include"]
    assert "transport_call_count" in live_execute_contract["must_include"]
    assert live_execute_contract["must_equal"]["live_execute_enabled"] is False
    assert jobs["roibang-create-live-execute-once"]["policy"]["plan"] == "configs/create-plans/first-live.local.json"
    assert jobs["roibang-create-live-execute-once"]["policy"]["create_execute_artifact"] == "data/runs/create_execute/first-live.local.json"

    report_contract = jobs["roibang-create-live-execute-report"]["result_contract"]
    assert "create_plan_summary" in report_contract["must_include"]
    assert "create_plan_contract" in report_contract["must_include"]
    assert jobs["roibang-create-live-execute-report"]["policy"]["plan"] == "configs/create-plans/first-live.local.json"


def test_scheduler_registry_includes_readonly_material_history_yesterday_job():
    registry = load_job_registry(Path("configs/scheduler/roibang-v2.jobs.example.json"))
    jobs = {job["id"]: job for job in registry["jobs"]}
    job = jobs["roibang-material-history-yesterday"]

    assert job["enabled"] is True
    assert job["category"] == "readonly_sync"
    assert job["schedule"] == {"type": "cron", "expr": "0 2 * * *", "tz": "Asia/Shanghai"}
    assert job["script"]["command"] == [
        "python3",
        "scripts/run_product_automation_job.py",
        "--job",
        "material_daily_sync",
        "--target-date",
        "yesterday",
        "--enable-readonly",
    ]
    assert job["result_contract"]["workflow"] == "product_automation_job_material_daily_sync"
    assert job["result_contract"]["must_equal"] == {"execution_enabled": False}


def test_scheduler_registry_includes_enabled_operation_log_yesterday_job():
    registry = load_job_registry(Path("configs/scheduler/roibang-v2.jobs.example.json"))
    jobs = {job["id"]: job for job in registry["jobs"]}
    job = jobs["roibang-operation-log-yesterday-sync"]

    assert job["enabled"] is True
    assert job["category"] == "readonly_sync"
    assert job["schedule"] == {"type": "cron", "expr": "30 2 * * *", "tz": "Asia/Shanghai"}
    assert job["script"]["command"] == [
        "python3",
        "scripts/run_product_automation_job.py",
        "--job",
        "operation_log_sync",
        "--target-date",
        "yesterday",
        "--enable-readonly",
    ]
    assert job["policy"]["account_date_source"] == "material_daily_metrics_yesterday_spent_accounts"
    assert job["result_contract"]["workflow"] == "product_automation_job_operation_log_sync"
    assert "artifact_path" not in job["result_contract"]["must_include"]
    assert job["result_contract"]["must_equal"] == {"execution_enabled": False}


def test_scheduler_registry_keeps_daily_jobs_and_restore_due_job():
    registry = load_job_registry(Path("configs/scheduler/roibang-v2.jobs.example.json"))
    enabled_jobs = [job for job in registry["jobs"] if job["enabled"] is True]

    assert [(job["id"], job["schedule"]["expr"]) for job in enabled_jobs] == [
        ("roibang-daily-report-pipeline", "0 4 * * *"),
        ("roibang-material-history-yesterday", "0 2 * * *"),
        ("roibang-operation-log-yesterday-sync", "30 2 * * *"),
        ("roibang-material-kind-reconcile", "30 4 * * *"),
        ("roibang-source-material-account-auto-push", "0 5 * * *"),
        ("roibang-source-material-preload-to-guojing-spent", "20 5 * * *"),
        ("roibang-source-material-rollup-rebuild", "30 5 * * *"),
        ("roibang-strategy-learning", "50 5 * * *"),
        ("roibang-scheduler-status", "0 6 * * *"),
        ("roibang-project-schedule-restore-due", "10 0 * * *"),
        ("roibang-delivery-patrol", "30 8-23 * * *"),
        ("roibang-delivery-readonly-report-chain", "50 23 * * *"),
    ]

    source_account_push = {job["id"]: job for job in registry["jobs"]}["roibang-source-material-account-auto-push"]
    source_material_preload = {job["id"]: job for job in registry["jobs"]}[
        "roibang-source-material-preload-to-guojing-spent"
    ]
    material_kind_reconcile = {job["id"]: job for job in registry["jobs"]}["roibang-material-kind-reconcile"]
    source_material_rollup = {job["id"]: job for job in registry["jobs"]}["roibang-source-material-rollup-rebuild"]
    daily_job = {job["id"]: job for job in registry["jobs"]}["roibang-daily-report-pipeline"]
    status_job = {job["id"]: job for job in registry["jobs"]}["roibang-scheduler-status"]
    restore_due_job = {job["id"]: job for job in registry["jobs"]}["roibang-project-schedule-restore-due"]
    assert daily_job["script"]["command"] == [
        "python3",
        "scripts/run_product_automation_job.py",
        "--job",
        "daily_report_sync",
        "--target-date",
        "yesterday",
        "--enable-readonly",
    ]
    assert daily_job["policy"] == {
        "job": "daily_report_sync",
        "products_dir": "configs/products",
        "target_date": "yesterday",
        "readonly": True,
    }
    assert daily_job["result_contract"]["workflow"] == "product_automation_job_daily_report_sync"
    assert daily_job["result_contract"]["must_equal"] == {"execution_enabled": False}

    assert source_account_push["script"]["command"] == [
        "python3",
        "scripts/run_product_automation_job.py",
        "--job",
        "source_material_auto_push",
        "--target-date",
        "yesterday",
        "--enable-readonly",
        "--execute",
        "--yes",
    ]
    assert source_account_push["result_contract"]["workflow"] == "product_automation_job_source_material_auto_push"
    assert source_account_push["result_contract"]["must_equal"] == {}
    assert source_material_preload["script"]["command"] == [
        "python3",
        "scripts/run_product_automation_job.py",
        "--job",
        "source_material_preload",
        "--target-date",
        "today",
        "--execute",
        "--yes",
    ]
    assert source_material_preload["policy"]["approval_policy"] == "fixed_daily_product_source_material_preload"
    assert source_material_preload["result_contract"]["workflow"] == "product_automation_job_source_material_preload"
    assert source_material_preload["result_contract"]["must_equal"] == {"execution_enabled": True}
    assert material_kind_reconcile["script"]["command"] == [
        "python3",
        "scripts/run_material_kind_reconcile.py",
        "--config",
        "configs/runtime.example.json",
        "--request",
        "configs/material-kind-reconcile.example.json",
    ]
    assert material_kind_reconcile["result_contract"]["workflow"] == "material_kind_reconcile"
    assert material_kind_reconcile["result_contract"]["must_equal"] == {
        "execution_enabled": False,
        "external_api_calls": 0,
    }
    assert source_material_rollup["script"]["command"] == [
        "python3",
        "scripts/run_product_automation_job.py",
        "--job",
        "source_material_rollup",
        "--target-date",
        "yesterday",
    ]
    assert source_material_rollup["result_contract"]["workflow"] == "product_automation_job_source_material_rollup"
    assert source_material_rollup["result_contract"]["must_equal"] == {
        "execution_enabled": False,
        "external_api_calls": 0,
    }
    assert status_job["script"]["command"] == [
        "python3",
        "scripts/run_scheduler_status.py",
        "--config",
        "configs/runtime.example.json",
        "--request",
        "configs/scheduler-status.local.json",
        "--registry",
        "configs/scheduler/roibang-v2.jobs.example.json",
    ]
    assert status_job["delivery"] == {"channel": "feishu"}
    assert restore_due_job["script"]["command"] == [
        "python3",
        "scripts/run_project_schedule_restore_due.py",
        "--restore-queue",
        "data/runs/project_schedule_restore_queue.json",
        "--config",
        "configs/project-update-execute.local.json",
        "--execute",
        "--yes",
    ]
    assert restore_due_job["policy"] == {
        "restore_queue": "data/runs/project_schedule_restore_queue.json",
        "config": "configs/project-update-execute.local.json",
        "approval_policy": "restore_from_execute_ledger_only",
    }


def test_scheduler_registry_includes_delivery_patrol_jobs():
    registry = load_job_registry(Path("configs/scheduler/roibang-v2.jobs.example.json"))
    jobs = {job["id"]: job for job in registry["jobs"]}
    patrol = jobs["roibang-delivery-patrol"]
    suggestions = jobs["roibang-delivery-patrol-suggestions"]
    readonly_report_chain = jobs["roibang-delivery-readonly-report-chain"]

    assert patrol["enabled"] is True
    assert patrol["schedule"] == {"type": "cron", "expr": "30 8-23 * * *", "tz": "Asia/Shanghai"}
    assert patrol["script"]["command"] == [
        "python3",
        "scripts/run_product_automation_job.py",
        "--job",
        "delivery_patrol",
        "--target-date",
        "today",
        "--enable-readonly",
    ]
    assert patrol["result_contract"]["workflow"] == "product_automation_job_delivery_patrol"
    assert "results" in patrol["result_contract"]["must_include"]
    assert patrol["result_contract"]["must_equal"] == {"execution_enabled": False}

    assert suggestions["enabled"] is False
    assert suggestions["script"]["command"] == [
        "python3",
        "scripts/run_delivery_patrol_suggestions.py",
        "--patrol-artifact",
        "data/runs/delivery_patrol/latest.json",
        "--request",
        "configs/delivery-patrol-suggestions.example.json",
        "--db",
        "data/roibang_v2.sqlite3",
    ]
    assert suggestions["result_contract"]["workflow"] == "delivery_patrol_suggestions"
    assert suggestions["result_contract"]["must_equal"] == {
        "execution_enabled": False,
        "external_api_calls": 0,
    }

    assert readonly_report_chain["enabled"] is True
    assert readonly_report_chain["schedule"] == {"type": "cron", "expr": "50 23 * * *", "tz": "Asia/Shanghai"}
    assert readonly_report_chain["script"]["command"] == [
        "python3",
        "scripts/run_delivery_readonly_report_chain.py",
        "--request",
        "configs/delivery-readonly-report-chain.example.json",
    ]
    assert readonly_report_chain["result_contract"]["workflow"] == "delivery_readonly_report_chain"
    assert "delivery" in readonly_report_chain["result_contract"]["must_include"]
    assert readonly_report_chain["result_contract"]["must_equal"] == {
        "execution_enabled": False,
        "external_api_calls": 0,
    }


def test_scheduler_registry_rejects_prompt_driven_jobs():
    registry = {
        "jobs": [
            {
                "id": "bad-ai-command",
                "name": "Bad AI command",
                "schedule": {"type": "cron", "expr": "0 1 * * *", "tz": "Asia/Shanghai"},
                "prompt": "调用 bash 工具运行创建脚本",
                "delivery": {"channel": "feishu-roi"},
            }
        ]
    }

    with pytest.raises(ValueError, match="prompt"):
        validate_job_registry(registry)


def test_scheduler_registry_accepts_direct_command_without_path_args():
    registry = {
        "jobs": [
            {
                "id": "direct-command",
                "name": "Direct command",
                "schedule": {"type": "cron", "expr": "0 1 * * *", "tz": "Asia/Shanghai"},
                "script": {"command": ["python3", "scripts/run_create_plan_validate.py"], "mode": "foreground"},
                "policy": {},
                "result_contract": {
                    "workflow": "create_plan_validate",
                    "artifact_dir": "data/runs/create_plan_validate",
                },
            }
        ]
    }

    assert validate_job_registry(registry)["ok"] is True


def test_live_mutation_jobs_must_have_policy_and_result_contract():
    registry = {
        "jobs": [
            {
                "id": "bad-live-job",
                "name": "Bad live job",
                "category": "live_mutation",
                "enabled": True,
                "schedule": {"type": "cron", "expr": "0 1 * * *", "tz": "Asia/Shanghai"},
                "script": {"path": "scripts/jobs/bad.py", "mode": "foreground"},
                "delivery": {"channel": "feishu-roi"},
            }
        ]
    }

    with pytest.raises(ValueError, match="policy"):
        validate_job_registry(registry)
