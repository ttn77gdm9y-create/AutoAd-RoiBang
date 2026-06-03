from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi import HTTPException
from fastapi import Request
from pydantic import BaseModel
from pydantic import Field

from backend.app.services.workflow_registry import workflow_catalog_result
from backend.app.services.workflow_runner import build_workflow_preview
from backend.app.services.workflow_runner import start_workflow_task

router = APIRouter()


class WorkflowRunRequest(BaseModel):
    request: dict[str, Any] = Field(default_factory=dict)


@router.get("/workflow-runs/catalog")
def workflow_run_catalog() -> dict:
    return workflow_catalog_result()


@router.post("/workflow-runs/{workflow_id}/preview")
def workflow_run_preview(request: Request, workflow_id: str, body: WorkflowRunRequest) -> dict:
    return build_workflow_preview(workflow_id, body.request, project_root=request.app.state.settings.project_root)


@router.post("/workflow-runs/{workflow_id}/run")
def workflow_run_start(request: Request, workflow_id: str, body: WorkflowRunRequest) -> dict:
    result = start_workflow_task(workflow_id, body.request, project_root=request.app.state.settings.project_root)
    if not bool(result.get("task")):
        reasons = result.get("summary", {}).get("blocking_reasons") or ["该任务暂不能启动"]
        raise HTTPException(status_code=400, detail=str(reasons[0]))
    return result
