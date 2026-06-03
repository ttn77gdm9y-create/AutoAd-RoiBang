import importlib.util
from pathlib import Path

from roibang_v2.scheduler.jobs import load_job_registry
from roibang_v2.scheduler.render import render_cron, render_launchd_plist, render_scheduler_templates


def _load_render_script():
    script_path = Path("scripts/render_scheduler_templates.py")
    spec = importlib.util.spec_from_file_location("render_scheduler_templates", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_render_cron_uses_fixed_script_paths_without_ai_execution_prompts():
    registry = load_job_registry(Path("configs/scheduler/roibang-v2.jobs.example.json"))

    cron_text = render_cron(registry, repo_root=Path("/tmp/RoiBang v2"))

    assert "prompt" not in cron_text
    assert "agentId" not in cron_text
    assert "operator_task" not in cron_text
    assert "/bin/zsh" not in cron_text
    assert "mkdir -p logs/scheduler" in cron_text
    assert "PYTHONPATH=src" in cron_text
    assert "scripts/run_scheduler_job.py --registry configs/scheduler/roibang-v2.jobs.example.json --job-id roibang-daily-report-pipeline" in cron_text
    assert "scripts/run_scheduler_job.py --registry configs/scheduler/roibang-v2.jobs.example.json --job-id roibang-source-material-account-auto-push" in cron_text
    assert "scripts/run_scheduler_job.py --registry configs/scheduler/roibang-v2.jobs.example.json --job-id roibang-source-material-preload-to-guojing-spent" in cron_text
    assert "scripts/run_scheduler_job.py --registry configs/scheduler/roibang-v2.jobs.example.json --job-id roibang-scheduler-status" in cron_text
    assert "scripts/run_scheduler_job.py --registry configs/scheduler/roibang-v2.jobs.example.json --job-id roibang-project-schedule-restore-due" in cron_text
    assert "scripts/run_scheduler_job.py --registry configs/scheduler/roibang-v2.jobs.example.json --job-id roibang-operation-log-yesterday-sync" in cron_text
    assert "scripts/run_scheduler_job.py --registry configs/scheduler/roibang-v2.jobs.example.json --job-id roibang-material-kind-reconcile" in cron_text
    assert "scripts/run_scheduler_job.py --registry configs/scheduler/roibang-v2.jobs.example.json --job-id roibang-source-material-rollup-rebuild" in cron_text
    assert "scripts/run_scheduler_job.py --registry configs/scheduler/roibang-v2.jobs.example.json --job-id roibang-strategy-learning" in cron_text
    assert "--job-id roibang-report-field-catalog" not in cron_text
    assert "scripts/run_data_sync.py" not in cron_text
    assert "--job-id roibang-data-sync" not in cron_text
    assert "--job-id roibang-daily-learning" not in cron_text
    assert "logs/scheduler/roibang-daily-report-pipeline.out.log" in cron_text
    assert "--job-id roibang-strategy-preflight" not in cron_text
    assert "--job-id roibang-strategy-dry-run" not in cron_text
    assert "--job-id roibang-material-history-yesterday" in cron_text
    assert "--job-id roibang-strategy-approval" not in cron_text
    assert "--job-id roibang-strategy-execute" not in cron_text
    job_lines = [line for line in cron_text.splitlines() if line and not line.startswith("#")]
    assert len(job_lines) == 12
    assert any(line.startswith("0 2 * * * cd '/tmp/RoiBang v2'") and "--job-id roibang-material-history-yesterday" in line for line in job_lines)
    assert any(line.startswith("30 2 * * * cd '/tmp/RoiBang v2'") and "--job-id roibang-operation-log-yesterday-sync" in line for line in job_lines)
    assert any(line.startswith("0 4 * * * cd '/tmp/RoiBang v2'") and "--job-id roibang-daily-report-pipeline" in line for line in job_lines)
    assert any(line.startswith("30 4 * * * cd '/tmp/RoiBang v2'") and "--job-id roibang-material-kind-reconcile" in line for line in job_lines)
    assert any(line.startswith("0 5 * * * cd '/tmp/RoiBang v2'") and "--job-id roibang-source-material-account-auto-push" in line for line in job_lines)
    assert any(line.startswith("20 5 * * * cd '/tmp/RoiBang v2'") and "--job-id roibang-source-material-preload-to-guojing-spent" in line for line in job_lines)
    assert any(line.startswith("30 5 * * * cd '/tmp/RoiBang v2'") and "--job-id roibang-source-material-rollup-rebuild" in line for line in job_lines)
    assert any(line.startswith("50 5 * * * cd '/tmp/RoiBang v2'") and "--job-id roibang-strategy-learning" in line for line in job_lines)
    assert any(line.startswith("0 6 * * * cd '/tmp/RoiBang v2'") and "--job-id roibang-scheduler-status" in line for line in job_lines)
    assert any(line.startswith("30 8-23 * * * cd '/tmp/RoiBang v2'") and "--job-id roibang-delivery-patrol" in line for line in job_lines)
    assert any(line.startswith("10 0 * * * cd '/tmp/RoiBang v2'") and "--job-id roibang-project-schedule-restore-due" in line for line in job_lines)
    assert any(line.startswith("50 23 * * * cd '/tmp/RoiBang v2'") and "--job-id roibang-delivery-readonly-report-chain" in line for line in job_lines)


def test_render_launchd_plist_uses_calendar_interval_and_shell_command():
    registry = load_job_registry(Path("configs/scheduler/roibang-v2.jobs.example.json"))
    job = next(item for item in registry["jobs"] if item["id"] == "roibang-data-sync")

    plist = render_launchd_plist(job, repo_root=Path("/tmp/RoiBang v2"))

    assert "<string>com.roibang.v2.roibang-data-sync</string>" in plist
    assert "<key>StartCalendarInterval</key>" in plist
    assert "<key>Hour</key>" in plist
    assert "<integer>9</integer>" in plist
    assert "<key>Minute</key>" in plist
    assert "<integer>0</integer>" in plist
    assert "cd /tmp" in plist
    assert "PYTHONPATH='/tmp/RoiBang v2/src' /Library/Frameworks/Python.framework/Versions/3.11/bin/python3 '/tmp/RoiBang v2/scripts/run_scheduler_job.py'" in plist
    assert "--job-id roibang-data-sync" in plist
    assert "<key>WorkingDirectory</key>" not in plist
    assert "--repo-root '/tmp/RoiBang v2'" in plist
    assert "scripts/run_data_sync.py" not in plist
    assert "prompt" not in plist
    assert "operator_task" not in plist


def test_render_launchd_plist_uses_calendar_interval_for_restore_due():
    registry = load_job_registry(Path("configs/scheduler/roibang-v2.jobs.example.json"))
    job = next(item for item in registry["jobs"] if item["id"] == "roibang-project-schedule-restore-due")

    plist = render_launchd_plist(job, repo_root=Path("/tmp/RoiBang v2"))

    assert "<string>com.roibang.v2.roibang-project-schedule-restore-due</string>" in plist
    assert "<key>StartCalendarInterval</key>" in plist
    assert "<key>Hour</key>" in plist
    assert "<integer>0</integer>" in plist
    assert "<key>Minute</key>" in plist
    assert "<integer>10</integer>" in plist
    assert "<key>StartInterval</key>" not in plist


def test_render_launchd_plist_supports_hour_ranges():
    registry = load_job_registry(Path("configs/scheduler/roibang-v2.jobs.example.json"))
    job = next(item for item in registry["jobs"] if item["id"] == "roibang-delivery-patrol")
    job = {**job, "enabled": True, "schedule": {"type": "cron", "expr": "30 8-23 * * *", "tz": "Asia/Shanghai"}}

    plist = render_launchd_plist(job, repo_root=Path("/tmp/RoiBang v2"))

    assert "<key>StartCalendarInterval</key>" in plist
    assert plist.count("<key>Hour</key>") == 16
    assert "<integer>8</integer>" in plist
    assert "<integer>23</integer>" in plist
    assert plist.count("<key>Minute</key>") == 16
    assert "<integer>30</integer>" in plist


def test_render_scheduler_templates_writes_cron_and_launchd_examples(tmp_path):
    registry = load_job_registry(Path("configs/scheduler/roibang-v2.jobs.example.json"))
    stale_file = tmp_path / "launchd" / "com.roibang.v2.roibang-data-sync.plist.example"
    stale_file.parent.mkdir(parents=True)
    stale_file.write_text("stale", encoding="utf-8")

    summary = render_scheduler_templates(registry, output_dir=tmp_path, repo_root=Path("/tmp/RoiBang v2"))

    cron_file = tmp_path / "cron" / "roibang-v2.cron.example"
    launchd_file = tmp_path / "launchd" / "com.roibang.v2.roibang-source-material-account-auto-push.plist.example"
    assert summary == {"cron_files": 1, "launchd_files": 12, "enabled_jobs": 12}
    assert cron_file.exists()
    assert launchd_file.exists()
    assert not stale_file.exists()
    assert "roibang-material-history-yesterday" in cron_file.read_text()
    assert "roibang-operation-log-yesterday-sync" in cron_file.read_text()
    assert "roibang-daily-report-pipeline" in cron_file.read_text()
    assert "roibang-material-kind-reconcile" in cron_file.read_text()
    assert "roibang-strategy-learning" in cron_file.read_text()
    assert "roibang-source-material-account-auto-push" in cron_file.read_text()
    assert "roibang-source-material-preload-to-guojing-spent" in cron_file.read_text()
    assert "roibang-source-material-rollup-rebuild" in cron_file.read_text()
    assert "roibang-scheduler-status" in cron_file.read_text()
    assert "roibang-project-schedule-restore-due" in cron_file.read_text()
    assert "roibang-delivery-patrol" in cron_file.read_text()
    assert "roibang-delivery-readonly-report-chain" in cron_file.read_text()
    assert "roibang-strategy-plan" not in cron_file.read_text()
    assert "roibang-report-field-catalog" not in cron_file.read_text()
    assert "roibang-strategy-preflight" not in cron_file.read_text()
    assert "roibang-strategy-dry-run" not in cron_file.read_text()
    assert "roibang-strategy-approval" not in cron_file.read_text()
    assert "roibang-strategy-execute" not in cron_file.read_text()
    assert "<string>com.roibang.v2.roibang-source-material-account-auto-push</string>" in launchd_file.read_text()
    assert (tmp_path / "launchd" / "com.roibang.v2.roibang-project-schedule-restore-due.plist.example").exists()
    assert (tmp_path / "launchd" / "com.roibang.v2.roibang-operation-log-yesterday-sync.plist.example").exists()
    assert (tmp_path / "launchd" / "com.roibang.v2.roibang-material-kind-reconcile.plist.example").exists()
    assert (tmp_path / "launchd" / "com.roibang.v2.roibang-source-material-rollup-rebuild.plist.example").exists()
    assert (tmp_path / "launchd" / "com.roibang.v2.roibang-delivery-patrol.plist.example").exists()
    assert (tmp_path / "launchd" / "com.roibang.v2.roibang-delivery-readonly-report-chain.plist.example").exists()


def test_render_scheduler_cli_entrypoint_writes_summary(tmp_path, capsys):
    module = _load_render_script()

    exit_code = module.render_from_args(
        [
            "--registry",
            "configs/scheduler/roibang-v2.jobs.example.json",
            "--output-dir",
            str(tmp_path),
            "--repo-root",
            "/tmp/RoiBang v2",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert '"launchd_files": 12' in captured.out
    assert '"enabled_jobs": 12' in captured.out
    assert (tmp_path / "cron" / "roibang-v2.cron.example").exists()
