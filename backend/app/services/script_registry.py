from __future__ import annotations

from pathlib import Path
from typing import Any

from roibang_v2.ui.background_tasks import build_runner_command
from roibang_v2.ui.background_tasks import build_task_record
from roibang_v2.ui.background_tasks import start_runner
from roibang_v2.ui.background_tasks import write_task_record

ACTION_CATALOG = {
    "dry_run_probe": {
        "name": "链路探针",
        "risk_level": "low",
        "description": "只验证本地白名单任务、确认、任务记录和中文结果展示链路，不触发真实业务动作。",
    }
}


def list_action_catalog() -> dict[str, Any]:
    rows = [
        {
            "动作": action,
            "名称": meta["name"],
            "风险": meta["risk_level"],
            "说明": meta["description"],
        }
        for action, meta in ACTION_CATALOG.items()
    ]
    return {
        "summary": {
            "title": "链路探针动作目录",
            "status": "loaded",
            "risk_level": "low",
            "execution_enabled": False,
            "items": [{"label": "可用动作数", "value": len(rows)}],
            "warnings": [],
            "blocking_reasons": [],
        },
        "table": {"columns": ["动作", "名称", "风险", "说明"], "rows": rows},
        "artifact_path": "",
        "raw": {"actions": list(ACTION_CATALOG)},
    }


def build_action_task(action: str, request: dict[str, Any], *, project_root: str | Path) -> dict[str, Any]:
    root = Path(project_root)
    runs_dir = root / "data" / "runs"
    if action not in ACTION_CATALOG:
        return {
            "ok": False,
            "summary": {
                "title": "链路探针预览",
                "status": "blocked",
                "risk_level": "high",
                "execution_enabled": False,
                "items": [{"label": "动作", "value": action}],
                "warnings": [],
                "blocking_reasons": [f"动作 {action} 不在固定脚本白名单中"],
            },
            "table": {"columns": [], "rows": []},
            "raw": {"action": action, "request": request},
        }

    message = str(request.get("message") or "dry-run-ok")
    code = (
        "import json,sys; "
        "print(json.dumps({'ok': True, 'status': 'completed', 'message': sys.argv[1]}, ensure_ascii=False))"
    )
    task = build_task_record(
        runs_dir=runs_dir,
        operation_type="dry_run_probe",
        command=["python3", "-c", code, message],
        cwd=str(root),
        request=request,
    )
    return {
        "ok": True,
        "summary": {
            "title": "链路探针预览",
            "status": "planned",
            "risk_level": "low",
            "execution_enabled": True,
            "items": [{"label": "动作", "value": "dry_run_probe"}, {"label": "消息", "value": message}],
            "warnings": [],
            "blocking_reasons": [],
        },
        "table": {"columns": ["动作", "消息"], "rows": [{"动作": "dry_run_probe", "消息": message}]},
        "task": task,
        "raw": {"action": action, "request": request},
    }


def start_action_task(project_root: str | Path, task: dict[str, Any]) -> dict[str, Any]:
    runs_dir = Path(project_root) / "data" / "runs"
    task_path = write_task_record(runs_dir, task)
    pid = start_runner(build_runner_command(task_path), cwd=project_root)
    task["pid"] = pid
    write_task_record(runs_dir, task)
    return {"task_id": task["task_id"], "pid": pid, "artifact_path": str(task_path)}
