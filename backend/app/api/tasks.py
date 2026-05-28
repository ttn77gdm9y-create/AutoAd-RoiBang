from __future__ import annotations

from fastapi import APIRouter
from fastapi import HTTPException
from fastapi import Request
from fastapi.responses import PlainTextResponse

from backend.app.services.tasks import list_tasks
from backend.app.services.tasks import load_task_detail
from backend.app.services.tasks import load_task_log

router = APIRouter()


@router.get("/tasks")
def tasks(request: Request) -> dict:
    settings = request.app.state.settings
    return {"items": list_tasks(settings.runs_dir, settings.configs_dir)}


@router.get("/tasks/{task_id}")
def task_detail(request: Request, task_id: str) -> dict:
    settings = request.app.state.settings
    detail = load_task_detail(settings.runs_dir, task_id, settings.configs_dir)
    if not detail:
        raise HTTPException(status_code=404, detail=f"未找到任务: {task_id}")
    return detail


@router.get("/tasks/{task_id}/stdout", response_class=PlainTextResponse)
def task_stdout(request: Request, task_id: str) -> str:
    text = load_task_log(request.app.state.settings.runs_dir, task_id, "stdout")
    if text is None:
        raise HTTPException(status_code=404, detail=f"未找到任务: {task_id}")
    return text


@router.get("/tasks/{task_id}/stderr", response_class=PlainTextResponse)
def task_stderr(request: Request, task_id: str) -> str:
    text = load_task_log(request.app.state.settings.runs_dir, task_id, "stderr")
    if text is None:
        raise HTTPException(status_code=404, detail=f"未找到任务: {task_id}")
    return text
