import importlib.util
import json
import os
from pathlib import Path

from roibang_v2.scheduler.runner import run_scheduler_job


def _load_runner_script():
    script_path = Path("scripts/run_scheduler_job.py")
    spec = importlib.util.spec_from_file_location("run_scheduler_job", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _write_json(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _dummy_registry() -> dict:
    return {
        "jobs": [
            {
                "id": "dummy-success",
                "name": "Dummy success",
                "enabled": True,
                "schedule": {"type": "cron", "expr": "0 9 * * *", "tz": "Asia/Shanghai"},
                "script": {"path": "scripts/dummy_success.py", "mode": "foreground", "args": ["--message", "hello"]},
                "policy": {},
                "result_contract": {
                    "workflow": "dummy",
                    "artifact_dir": "data/runs/dummy",
                    "must_include": ["ok", "workflow", "message"],
                },
            }
        ]
    }


def test_run_scheduler_job_executes_fixed_script_and_validates_artifact(tmp_path):
    script = tmp_path / "scripts" / "dummy_success.py"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(
        """#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--message")
args = parser.parse_args()
target = Path("data/runs/dummy/20260101T000000Z.json")
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(json.dumps({"ok": True, "workflow": "dummy", "message": args.message}), encoding="utf-8")
print("dummy script complete")
""",
        encoding="utf-8",
    )
    os.chmod(script, 0o755)

    result = run_scheduler_job(_dummy_registry(), job_id="dummy-success", repo_root=tmp_path)

    assert result["ok"] is True
    assert result["job_id"] == "dummy-success"
    assert result["script"]["exit_code"] == 0
    assert result["script"]["stdout"].strip() == "dummy script complete"
    assert result["artifact_contract"]["ok"] is True
    assert result["execution_result_path"].endswith(".json")
    written = json.loads(Path(result["execution_result_path"]).read_text(encoding="utf-8"))
    assert written["workflow"] == "scheduler_job"
    assert written["job_id"] == "dummy-success"


def test_run_scheduler_job_executes_python_script_without_execute_bit(tmp_path):
    script = tmp_path / "scripts" / "dummy_success.py"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(
        """from pathlib import Path
import json

target = Path("data/runs/dummy/20260101T000000Z.json")
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(json.dumps({"ok": True, "workflow": "dummy", "message": "ok"}), encoding="utf-8")
print("python script complete")
""",
        encoding="utf-8",
    )
    os.chmod(script, 0o644)

    result = run_scheduler_job(_dummy_registry(), job_id="dummy-success", repo_root=tmp_path)

    assert result["ok"] is True
    assert result["script"]["path"] == "scripts/dummy_success.py"
    assert result["script"]["argv"][:2] == ["python3", "scripts/dummy_success.py"]
    assert result["script"]["stdout"].strip() == "python script complete"


def test_run_scheduler_job_prefers_explicit_command_over_path_args(tmp_path):
    command_script = tmp_path / "scripts" / "command_success.py"
    fallback_script = tmp_path / "scripts" / "fallback_should_not_run.py"
    command_script.parent.mkdir(parents=True, exist_ok=True)
    command_script.write_text(
        """import argparse
import json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--message")
args = parser.parse_args()
target = Path("data/runs/dummy/20260101T000000Z.json")
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(json.dumps({"ok": True, "workflow": "dummy", "message": args.message}), encoding="utf-8")
print("command script complete")
""",
        encoding="utf-8",
    )
    fallback_script.write_text("raise SystemExit('fallback should not run')\n", encoding="utf-8")
    registry = _dummy_registry()
    registry["jobs"][0]["script"] = {
        "command": ["python3", "scripts/command_success.py", "--message", "from-command"],
        "path": "scripts/fallback_should_not_run.py",
        "mode": "foreground",
        "args": ["--message", "from-path-args"],
    }

    result = run_scheduler_job(registry, job_id="dummy-success", repo_root=tmp_path)

    assert result["ok"] is True
    assert result["script"]["argv"] == ["python3", "scripts/command_success.py", "--message", "from-command"]
    assert result["script"]["stdout"].strip() == "command script complete"


def test_run_scheduler_job_writes_failed_execution_result_when_script_fails(tmp_path):
    registry = _dummy_registry()
    script = tmp_path / "scripts" / "dummy_success.py"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(
        """#!/usr/bin/env python3
import sys
print("bad news", file=sys.stderr)
raise SystemExit(7)
""",
        encoding="utf-8",
    )
    os.chmod(script, 0o755)

    result = run_scheduler_job(registry, job_id="dummy-success", repo_root=tmp_path)

    assert result["ok"] is False
    assert result["script"]["exit_code"] == 7
    assert "bad news" in result["script"]["stderr"]
    assert result["artifact_contract"]["ok"] is False
    assert "script exited with non-zero status" in result["violations"]
    assert Path(result["execution_result_path"]).exists()


def test_run_scheduler_job_writes_failed_result_when_success_script_missing_artifact(tmp_path):
    script = tmp_path / "scripts" / "dummy_success.py"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text("#!/usr/bin/env python3\nprint('forgot artifact')\n", encoding="utf-8")
    os.chmod(script, 0o755)

    result = run_scheduler_job(_dummy_registry(), job_id="dummy-success", repo_root=tmp_path)

    assert result["ok"] is False
    assert result["script"]["exit_code"] == 0
    assert result["artifact_contract"]["ok"] is False
    assert "no artifact json files found" in result["violations"][0]
    assert Path(result["execution_result_path"]).exists()


def test_run_scheduler_job_cli_returns_nonzero_for_failed_script(tmp_path, capsys):
    registry = _dummy_registry()
    registry_path = tmp_path / "registry.json"
    _write_json(registry_path, registry)
    script = tmp_path / "scripts" / "dummy_success.py"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text("#!/usr/bin/env python3\nraise SystemExit(3)\n", encoding="utf-8")
    os.chmod(script, 0o755)
    module = _load_runner_script()

    exit_code = module.run_from_args(
        [
            "--registry",
            str(registry_path),
            "--job-id",
            "dummy-success",
            "--repo-root",
            str(tmp_path),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert '"exit_code": 3' in captured.out
