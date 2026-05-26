from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _run_help_from_tmp(script: str, tmp_path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / script), "--help"],
        cwd=tmp_path,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def test_fixed_create_entrypoints_bootstrap_from_other_cwd(tmp_path: Path) -> None:
    for script in (
        "run_create_mode.py",
        "run_create_live_execute_terminal.py",
        "run_create_live_execute_once.py",
    ):
        result = _run_help_from_tmp(script, tmp_path)

        assert result.returncode == 0, result.stderr
        assert "usage:" in result.stdout


def test_fixed_project_and_scheduler_entrypoints_bootstrap_from_other_cwd(tmp_path: Path) -> None:
    for script in (
        "run_project_management_update_config.py",
        "run_project_update_execute.py",
        "run_account_remark_update_config.py",
        "run_account_remark_update.py",
        "restart_streamlit_ui.py",
        "run_scheduler_job.py",
    ):
        result = _run_help_from_tmp(script, tmp_path)

        assert result.returncode == 0, result.stderr
        assert "usage:" in result.stdout
