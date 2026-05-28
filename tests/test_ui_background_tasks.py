import json
import subprocess
import time
from pathlib import Path

from roibang_v2.ui.background_tasks import build_runner_command
from roibang_v2.ui.background_tasks import build_task_record
from roibang_v2.ui.background_tasks import load_task_record
from roibang_v2.ui.background_tasks import task_paths
from roibang_v2.ui.background_tasks import write_task_record


def test_build_task_record_contains_stable_paths(tmp_path: Path):
    runs_dir = tmp_path / "runs"
    record = build_task_record(
        runs_dir=runs_dir,
        operation_type="create_live_execute",
        command=["python3", "scripts/run_create_live_execute_terminal.py"],
        cwd="/repo",
        request={"plan_path": "data/runs/create_mode/plan.json"},
    )

    assert record["task_id"].startswith("frontend-")
    assert record["status"] == "queued"
    assert record["operation_type"] == "create_live_execute"
    assert record["command"] == ["python3", "scripts/run_create_live_execute_terminal.py"]
    assert record["stdout_path"].startswith("frontend_tasks/")
    assert record["stderr_path"].startswith("frontend_tasks/")
    assert record["artifact_path"].startswith("frontend_tasks/")


def test_write_and_load_task_record_roundtrip(tmp_path: Path):
    runs_dir = tmp_path / "runs"
    record = build_task_record(
        runs_dir=runs_dir,
        operation_type="project_update_execute",
        command=["python3", "scripts/run_project_update.py"],
        cwd="/repo",
        request={"config_path": "data/runs/project_update/config.json"},
    )

    path = write_task_record(runs_dir, record)
    loaded = load_task_record(path)

    assert loaded["task_id"] == record["task_id"]
    assert loaded["status"] == "queued"
    assert task_paths(runs_dir, record["task_id"])["task"].name.endswith(".json")


def test_build_runner_command_uses_fixed_entrypoint(tmp_path: Path):
    task_path = tmp_path / "runs" / "frontend_tasks" / "frontend-x.json"

    command = build_runner_command(task_path)

    assert command[:2] == ["python3", "scripts/run_frontend_task.py"]
    assert command[-2:] == ["--task", str(task_path)]


def test_run_frontend_task_records_completed_result(tmp_path: Path):
    runs_dir = tmp_path / "runs"
    script = tmp_path / "ok.py"
    script.write_text("import json; print(json.dumps({'ok': True, 'artifact_path': 'x.json'}))", encoding="utf-8")
    record = build_task_record(
        runs_dir=runs_dir,
        operation_type="test_ok",
        command=["python3", str(script)],
        cwd=str(tmp_path),
        request={},
    )
    task_path = write_task_record(runs_dir, record)

    completed = subprocess.run(
        ["python3", "scripts/run_frontend_task.py", "--task", str(task_path)],
        cwd=Path.cwd(),
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0
    loaded = load_task_record(task_path)
    assert loaded["status"] == "completed"
    assert loaded["return_code"] == 0
    assert loaded["result"]["ok"] is True


def test_run_frontend_task_records_failed_result(tmp_path: Path):
    runs_dir = tmp_path / "runs"
    script = tmp_path / "fail.py"
    script.write_text("import sys; print('bad', file=sys.stderr); sys.exit(7)", encoding="utf-8")
    record = build_task_record(
        runs_dir=runs_dir,
        operation_type="test_fail",
        command=["python3", str(script)],
        cwd=str(tmp_path),
        request={},
    )
    task_path = write_task_record(runs_dir, record)

    completed = subprocess.run(
        ["python3", "scripts/run_frontend_task.py", "--task", str(task_path)],
        cwd=Path.cwd(),
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 7
    loaded = load_task_record(task_path)
    assert loaded["status"] == "failed"
    assert loaded["return_code"] == 7
    assert "bad" in (runs_dir / loaded["stderr_path"]).read_text(encoding="utf-8")


def test_run_frontend_task_runs_report_command_after_success(tmp_path: Path):
    runs_dir = tmp_path / "runs"
    main_script = tmp_path / "main.py"
    report_script = tmp_path / "report.py"
    main_script.write_text("import json; print(json.dumps({'ok': True, 'artifact_path': 'execute.json'}))", encoding="utf-8")
    report_script.write_text("import json; print(json.dumps({'ok': True, 'artifact_path': 'report.json'}))", encoding="utf-8")
    record = build_task_record(
        runs_dir=runs_dir,
        operation_type="create_live_execute",
        command=["python3", str(main_script)],
        cwd=str(tmp_path),
        request={},
        post_commands=[["python3", str(report_script)]],
    )
    task_path = write_task_record(runs_dir, record)

    completed = subprocess.run(
        ["python3", "scripts/run_frontend_task.py", "--task", str(task_path)],
        cwd=Path.cwd(),
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0
    loaded = load_task_record(task_path)
    assert loaded["status"] == "completed"
    assert loaded["result"]["artifact_path"] == "execute.json"
    assert loaded["post_results"][0]["artifact_path"] == "report.json"


def test_run_frontend_task_expands_result_artifact_placeholder(tmp_path: Path):
    runs_dir = tmp_path / "runs"
    main_script = tmp_path / "main.py"
    report_script = tmp_path / "report.py"
    seen_path = tmp_path / "seen.txt"
    main_script.write_text("import json; print(json.dumps({'ok': True, 'artifact_path': 'execute.json'}))", encoding="utf-8")
    report_script.write_text(
        "import json, sys; open(sys.argv[1], 'w').write(sys.argv[2]); print(json.dumps({'ok': True}))",
        encoding="utf-8",
    )
    record = build_task_record(
        runs_dir=runs_dir,
        operation_type="create_live_execute",
        command=["python3", str(main_script)],
        cwd=str(tmp_path),
        request={},
        post_commands=[["python3", str(report_script), str(seen_path), "{result.artifact_path}"]],
    )
    task_path = write_task_record(runs_dir, record)

    completed = subprocess.run(
        ["python3", "scripts/run_frontend_task.py", "--task", str(task_path)],
        cwd=Path.cwd(),
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0
    assert seen_path.read_text(encoding="utf-8") == "execute.json"


def test_run_frontend_task_treats_ok_false_as_failed_and_skips_report(tmp_path: Path):
    runs_dir = tmp_path / "runs"
    main_script = tmp_path / "main.py"
    report_script = tmp_path / "report.py"
    report_marker = tmp_path / "report-ran.txt"
    main_script.write_text("import json; print(json.dumps({'ok': False, 'status': 'blocked'}))", encoding="utf-8")
    report_script.write_text(f"open({str(report_marker)!r}, 'w').write('ran')", encoding="utf-8")
    record = build_task_record(
        runs_dir=runs_dir,
        operation_type="create_live_execute",
        command=["python3", str(main_script)],
        cwd=str(tmp_path),
        request={},
        post_commands=[["python3", str(report_script), "{result.artifact_path}"]],
    )
    task_path = write_task_record(runs_dir, record)

    completed = subprocess.run(
        ["python3", "scripts/run_frontend_task.py", "--task", str(task_path)],
        cwd=Path.cwd(),
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 1
    loaded = load_task_record(task_path)
    assert loaded["status"] == "failed"
    assert loaded["post_results"] == []
    assert not report_marker.exists()


def test_run_frontend_task_streams_stdout_while_running(tmp_path: Path):
    runs_dir = tmp_path / "runs"
    script = tmp_path / "slow.py"
    script.write_text(
        "\n".join(
            [
                "import json, time",
                "print('[create_live_execute_once] operation=create_project done=1/5 status=running calls=1', flush=True)",
                "time.sleep(1)",
                "print(json.dumps({'ok': True, 'artifact_path': 'execute.json'}), flush=True)",
            ]
        ),
        encoding="utf-8",
    )
    record = build_task_record(
        runs_dir=runs_dir,
        operation_type="create_live_execute",
        command=["python3", str(script)],
        cwd=str(tmp_path),
        request={},
    )
    task_path = write_task_record(runs_dir, record)
    stdout_path = runs_dir / record["stdout_path"]

    process = subprocess.Popen(
        ["python3", "scripts/run_frontend_task.py", "--task", str(task_path)],
        cwd=Path.cwd(),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        deadline = time.monotonic() + 0.8
        streamed = ""
        while time.monotonic() < deadline:
            if stdout_path.exists():
                streamed = stdout_path.read_text(encoding="utf-8")
                if "done=1/5" in streamed:
                    break
            time.sleep(0.05)

        assert "done=1/5" in streamed
        assert load_task_record(task_path)["status"] == "running"
    finally:
        stdout, stderr = process.communicate(timeout=5)

    assert process.returncode == 0, stdout + stderr
