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
    assert "scripts/run_scheduler_job.py --registry configs/scheduler/roibang-v2.jobs.example.json --job-id roibang-report-field-catalog" in cron_text
    assert "scripts/run_scheduler_job.py --registry configs/scheduler/roibang-v2.jobs.example.json --job-id roibang-daily-report-pipeline" in cron_text
    assert "scripts/run_data_sync.py" not in cron_text
    assert "--job-id roibang-data-sync" not in cron_text
    assert "--job-id roibang-daily-learning" not in cron_text
    assert "logs/scheduler/roibang-daily-report-pipeline.out.log" in cron_text
    assert "--job-id roibang-strategy-preflight" in cron_text
    assert "--job-id roibang-strategy-dry-run" in cron_text
    assert "--job-id roibang-strategy-approval" in cron_text
    assert "--job-id roibang-strategy-execute" in cron_text
    job_lines = [line for line in cron_text.splitlines() if line and not line.startswith("#")]
    assert len(job_lines) == 9
    assert job_lines[0].startswith("10 8 * * * cd '/tmp/RoiBang v2'")
    assert "--job-id roibang-report-field-catalog" in job_lines[0]
    assert "--job-id roibang-daily-report-pipeline" in job_lines[1]


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
    assert "PYTHONPATH=src scripts/run_scheduler_job.py" in plist
    assert "--job-id roibang-data-sync" in plist
    assert "scripts/run_data_sync.py" not in plist
    assert "prompt" not in plist
    assert "operator_task" not in plist


def test_render_scheduler_templates_writes_cron_and_launchd_examples(tmp_path):
    registry = load_job_registry(Path("configs/scheduler/roibang-v2.jobs.example.json"))
    stale_file = tmp_path / "launchd" / "com.roibang.v2.roibang-data-sync.plist.example"
    stale_file.parent.mkdir(parents=True)
    stale_file.write_text("stale", encoding="utf-8")

    summary = render_scheduler_templates(registry, output_dir=tmp_path, repo_root=Path("/tmp/RoiBang v2"))

    cron_file = tmp_path / "cron" / "roibang-v2.cron.example"
    launchd_file = tmp_path / "launchd" / "com.roibang.v2.roibang-material-sync.plist.example"
    assert summary == {"cron_files": 1, "launchd_files": 9, "enabled_jobs": 9}
    assert cron_file.exists()
    assert launchd_file.exists()
    assert not stale_file.exists()
    assert "roibang-strategy-plan" in cron_file.read_text()
    assert "roibang-report-field-catalog" in cron_file.read_text()
    assert "roibang-strategy-preflight" in cron_file.read_text()
    assert "roibang-strategy-dry-run" in cron_file.read_text()
    assert "roibang-strategy-approval" in cron_file.read_text()
    assert "roibang-strategy-execute" in cron_file.read_text()
    assert "<string>com.roibang.v2.roibang-material-sync</string>" in launchd_file.read_text()


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
    assert '"launchd_files": 9' in captured.out
    assert (tmp_path / "cron" / "roibang-v2.cron.example").exists()
