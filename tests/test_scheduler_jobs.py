from pathlib import Path

import pytest

from roibang_v2.scheduler.jobs import load_job_registry, validate_job_registry


def test_scheduler_registry_has_no_ai_execution_prompts():
    registry = load_job_registry(Path("configs/scheduler/roibang-v2.jobs.example.json"))

    result = validate_job_registry(registry)

    assert result == {
        "ok": True,
        "jobs": 11,
        "enabled_jobs": 9,
        "disabled_jobs": 2,
        "violations": [],
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
