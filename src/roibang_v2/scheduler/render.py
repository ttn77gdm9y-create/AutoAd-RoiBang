from __future__ import annotations

import plistlib
import shlex
from pathlib import Path
from typing import Any

from roibang_v2.scheduler.jobs import validate_job_registry


CRON_OUTPUT = Path("cron") / "roibang-v2.cron.example"
LAUNCHD_OUTPUT_DIR = Path("launchd")


def _enabled_jobs(registry: dict[str, Any]) -> list[dict[str, Any]]:
    validate_job_registry(registry)
    return [job for job in registry["jobs"] if bool(job.get("enabled", False))]


def _job_command(job: dict[str, Any], repo_root: Path, *, redirect_logs: bool = True) -> str:
    args = [
        "scripts/run_scheduler_job.py",
        "--registry",
        "configs/scheduler/roibang-v2.jobs.example.json",
        "--job-id",
        str(job["id"]),
        "--repo-root",
        str(repo_root),
    ]
    command = f"cd {shlex.quote(str(repo_root))} && mkdir -p logs/scheduler && PYTHONPATH=src {shlex.join(args)}"
    if redirect_logs:
        job_id = str(job["id"])
        command = (
            f"{command} >> {shlex.quote(f'logs/scheduler/{job_id}.out.log')} "
            f"2>> {shlex.quote(f'logs/scheduler/{job_id}.err.log')}"
        )
    return command


def render_cron(registry: dict[str, Any], *, repo_root: str | Path) -> str:
    root = Path(repo_root)
    lines = [
        "# RoiBang-v2 Phase 1 scheduler example.",
        "# Review before installing. This file is not installed by the renderer.",
        "# Create logs/scheduler before enabling these entries.",
        "",
    ]
    for job in _enabled_jobs(registry):
        schedule = job["schedule"]
        lines.append(f"# {job['id']} - {job['name']} [{schedule['tz']}]")
        lines.append(f"{schedule['expr']} {_job_command(job, root)}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _cron_calendar_interval(expr: str) -> dict[str, int]:
    parts = expr.split()
    if len(parts) != 5:
        raise ValueError(f"unsupported cron expression: {expr}")
    minute, hour, day, month, weekday = parts
    if day != "*" or month != "*" or weekday != "*":
        raise ValueError(f"launchd renderer only supports daily cron expressions: {expr}")
    if not minute.isdigit() or not hour.isdigit():
        raise ValueError(f"launchd renderer only supports fixed minute/hour cron expressions: {expr}")
    return {"Hour": int(hour), "Minute": int(minute)}


def render_launchd_plist(job: dict[str, Any], *, repo_root: str | Path) -> str:
    label = f"com.roibang.v2.{job['id']}"
    command = _job_command(job, Path(repo_root))
    plist = {
        "Label": label,
        "ProgramArguments": ["/bin/zsh", "-lc", command],
        "RunAtLoad": False,
        "StartCalendarInterval": _cron_calendar_interval(str(job["schedule"]["expr"])),
        "StandardOutPath": str(Path(repo_root) / "logs" / "scheduler" / f"{job['id']}.launchd.out.log"),
        "StandardErrorPath": str(Path(repo_root) / "logs" / "scheduler" / f"{job['id']}.launchd.err.log"),
        "WorkingDirectory": str(repo_root),
    }
    return plistlib.dumps(plist, sort_keys=False).decode("utf-8")


def render_scheduler_templates(
    registry: dict[str, Any],
    *,
    output_dir: str | Path,
    repo_root: str | Path,
) -> dict[str, int]:
    enabled_jobs = _enabled_jobs(registry)
    output_root = Path(output_dir)
    cron_dir = output_root / CRON_OUTPUT.parent
    launchd_dir = output_root / LAUNCHD_OUTPUT_DIR
    cron_dir.mkdir(parents=True, exist_ok=True)
    launchd_dir.mkdir(parents=True, exist_ok=True)

    (output_root / CRON_OUTPUT).write_text(render_cron(registry, repo_root=repo_root), encoding="utf-8")
    for stale in launchd_dir.glob("com.roibang.v2.*.plist.example"):
        stale.unlink()
    for job in enabled_jobs:
        path = launchd_dir / f"com.roibang.v2.{job['id']}.plist.example"
        path.write_text(render_launchd_plist(job, repo_root=repo_root), encoding="utf-8")

    return {"cron_files": 1, "launchd_files": len(enabled_jobs), "enabled_jobs": len(enabled_jobs)}
