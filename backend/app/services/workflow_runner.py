from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.app.services.workflow_registry import blocked_unknown_workflow_result
from backend.app.services.workflow_registry import build_workflow_command
from backend.app.services.workflow_registry import get_workflow_definition
from backend.app.services.workflow_registry import normalize_workflow_request
from backend.app.services.workflow_registry import workflow_preview_result
from roibang_v2.ui.background_tasks import build_runner_command
from roibang_v2.ui.background_tasks import build_task_record
from roibang_v2.ui.background_tasks import start_runner
from roibang_v2.ui.background_tasks import write_task_record


def build_workflow_preview(workflow_id: str, request: dict[str, Any], *, project_root: str | Path) -> dict[str, Any]:
    definition = get_workflow_definition(workflow_id)
    if definition is None:
        return blocked_unknown_workflow_result(workflow_id)
    normalized_request, blocking_reasons = normalize_workflow_request(definition, request)
    command = None if blocking_reasons else build_workflow_command(definition, normalized_request)
    return workflow_preview_result(
        definition,
        normalized_request,
        command=command,
        blocking_reasons=blocking_reasons,
    )


def start_workflow_task(workflow_id: str, request: dict[str, Any], *, project_root: str | Path) -> dict[str, Any]:
    definition = get_workflow_definition(workflow_id)
    if definition is None:
        return blocked_unknown_workflow_result(workflow_id)
    preview = build_workflow_preview(workflow_id, request, project_root=project_root)
    if not bool(preview.get("raw", {}).get("can_run")):
        return preview

    root = Path(project_root)
    runs_dir = root / "data" / "runs"
    command = [str(part) for part in preview["raw"]["command"]]
    normalized_request = dict(preview["raw"]["request"])
    task = build_task_record(
        runs_dir=runs_dir,
        operation_type=definition.operation_type,
        command=command,
        cwd=str(root),
        request=normalized_request,
    )
    task_path = write_task_record(runs_dir, task)
    pid = start_runner(build_runner_command(task_path), cwd=root)
    task["pid"] = pid
    write_task_record(runs_dir, task)

    return {
        "summary": {
            "title": f"{definition.name}任务已提交",
            "status": "queued",
            "risk_level": definition.risk_level,
            "execution_enabled": False,
            "items": [
                {"label": "任务", "value": definition.name},
                {"label": "任务 ID", "value": task["task_id"]},
                {"label": "真实投放动作", "value": "否"},
            ],
            "warnings": [],
            "blocking_reasons": [],
        },
        "table": {
            "columns": ["任务 ID", "任务名称", "当前状态", "真实投放动作"],
            "rows": [
                {
                    "任务 ID": task["task_id"],
                    "任务名称": definition.name,
                    "当前状态": "排队中",
                    "真实投放动作": "否",
                }
            ],
        },
        "artifact_path": str(task_path),
        "task": {"task_id": task["task_id"], "pid": pid, "artifact_path": str(task_path)},
        "raw": {"preview": preview, "task": task},
    }
