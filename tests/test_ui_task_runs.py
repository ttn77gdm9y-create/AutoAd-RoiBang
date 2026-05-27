import json
from pathlib import Path

from roibang_v2.ui.task_runs import load_recent_task_runs
from roibang_v2.ui.task_runs import load_frontend_task_rows
from roibang_v2.ui.task_runs import load_task_detail
from roibang_v2.ui.task_runs import progress_percent
from roibang_v2.ui.task_runs import read_create_live_progress


def test_load_recent_task_runs_summarizes_frontend_operation_artifacts(tmp_path: Path):
    runs_dir = tmp_path / "runs"
    log_dir = runs_dir / "frontend_operation_log"
    log_dir.mkdir(parents=True)
    artifact = log_dir / "20260526T120000Z.json"
    artifact.write_text(
        json.dumps(
            {
                "task_id": "task-create-1",
                "workflow": "frontend_operation_log",
                "operation_type": "create_live_execute",
                "status": "failed",
                "actor": "郭靖",
                "summary": {
                    "product": "点点英雄",
                    "account_count": 2,
                    "material_assignment_count": 25,
                    "unique_material_count": 10,
                    "review_status": "blocked",
                    "review_blocking_reason_count": 1,
                    "review_warning_count": 2,
                },
                "result": {
                    "execute_artifact_path": "data/runs/create_live_execute_once/result.json",
                    "report_artifact_path": "data/runs/create_live_execute_report/report.json",
                    "status": "create_http_failed",
                    "ok": False,
                },
                "created_at": "2026-05-26T12:00:00+00:00",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    rows = load_recent_task_runs(runs_dir)

    assert rows == [
        {
            "task_id": "task-create-1",
            "operation_type": "create_live_execute",
            "status": "failed",
            "product": "点点英雄",
            "actor": "郭靖",
            "created_at": "2026-05-26T12:00:00+00:00",
            "account_count": 2,
            "material_assignment_count": 25,
            "unique_material_count": 10,
            "result_status": "create_http_failed",
            "review_status": "blocked",
            "review_blocking_reason_count": 1,
            "review_warning_count": 2,
            "artifact_path": str(artifact),
            "execute_artifact_path": "data/runs/create_live_execute_once/result.json",
            "report_artifact_path": "data/runs/create_live_execute_report/report.json",
        }
    ]


def test_read_create_live_progress_loads_current_and_recent_events(tmp_path: Path):
    runs_dir = tmp_path / "runs"
    progress_dir = runs_dir / "create_live_execute_once" / "progress"
    progress_dir.mkdir(parents=True)
    (progress_dir / "current.json").write_text(
        json.dumps({"operation": "create_unit", "status": "running", "done": 3, "total": 8}, ensure_ascii=False),
        encoding="utf-8",
    )
    (progress_dir / "events.jsonl").write_text(
        "\n".join(
            [
                json.dumps({"operation": "create_project", "status": "completed", "done": 1, "total": 8}, ensure_ascii=False),
                json.dumps({"operation": "create_unit", "status": "running", "done": 3, "total": 8}, ensure_ascii=False),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    progress = read_create_live_progress(runs_dir, recent_events=1)

    assert progress["current"]["operation"] == "create_unit"
    assert progress["percent"] == 37
    assert progress["events"] == [{"operation": "create_unit", "status": "running", "done": 3, "total": 8}]


def test_load_task_detail_includes_artifact_payload_and_progress(tmp_path: Path):
    runs_dir = tmp_path / "runs"
    log_dir = runs_dir / "frontend_operation_log"
    progress_dir = runs_dir / "create_live_execute_once" / "progress"
    log_dir.mkdir(parents=True)
    progress_dir.mkdir(parents=True)
    artifact = log_dir / "20260526T120000Z.json"
    artifact.write_text(
        json.dumps(
            {
                "task_id": "task-create-1",
                "workflow": "frontend_operation_log",
                "operation_type": "create_live_execute",
                "status": "completed",
                "summary": {"product": "点点英雄"},
                "result": {"ok": True},
                "created_at": "2026-05-26T12:00:00+00:00",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (progress_dir / "current.json").write_text(
        json.dumps({"operation": "create_unit", "status": "completed", "done": 8, "total": 8}, ensure_ascii=False),
        encoding="utf-8",
    )

    detail = load_task_detail(runs_dir, "task-create-1")

    assert detail["task"]["task_id"] == "task-create-1"
    assert detail["artifact"]["operation_type"] == "create_live_execute"
    assert detail["progress"]["percent"] == 100


def test_progress_percent_handles_missing_or_invalid_totals():
    assert progress_percent({"done": 1, "total": 0}) == 0
    assert progress_percent({"done": "bad", "total": 10}) == 0
    assert progress_percent({"done": 11, "total": 10}) == 100


def test_load_frontend_task_rows_sorts_recent_first(tmp_path: Path):
    runs_dir = tmp_path / "runs"
    task_dir = runs_dir / "frontend_tasks"
    task_dir.mkdir(parents=True)
    (task_dir / "a.json").write_text(
        json.dumps(
            {
                "task_id": "a",
                "operation_type": "create_live_execute",
                "status": "completed",
                "created_at": "2026-05-26T01:00:00+08:00",
                "updated_at": "2026-05-26T01:02:00+08:00",
                "return_code": 0,
                "stdout_path": "frontend_tasks/a.stdout.log",
                "stderr_path": "frontend_tasks/a.stderr.log",
                "result": {"artifact_path": "data/runs/x/a.json"},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (task_dir / "b.json").write_text(
        json.dumps(
            {
                "task_id": "b",
                "operation_type": "create_live_execute",
                "status": "running",
                "created_at": "2026-05-26T02:00:00+08:00",
                "updated_at": "2026-05-26T02:01:00+08:00",
                "return_code": None,
                "stdout_path": "frontend_tasks/b.stdout.log",
                "stderr_path": "frontend_tasks/b.stderr.log",
                "result": {},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    rows = load_frontend_task_rows(runs_dir, limit=10)

    assert [row["task_id"] for row in rows] == ["b", "a"]
    assert rows[0]["status"] == "running"
    assert rows[1]["execute_artifact_path"] == "data/runs/x/a.json"
