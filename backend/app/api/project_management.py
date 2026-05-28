from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi import HTTPException
from fastapi import Request
from pydantic import BaseModel
from pydantic import Field

from backend.app.services.project_management import build_project_management_execute_preview
from backend.app.services.project_management import build_project_management_config_preview
from backend.app.services.project_management import start_project_management_execute_task
from backend.app.services.project_management import start_project_management_config_task

router = APIRouter()


class ProjectManagementConfigPreviewRequest(BaseModel):
    project_update_id: str = "ui-project-filter"
    advertiser_ids: str | list[str] = ""
    action_type: str = "delete_project"
    name_contains: str = ""
    spend_window: str = "today"
    metric_field: str = "stat_cost"
    metric_op: str = "lte"
    metric_value: str = "100"
    output_path: str = ""
    opt_status: str = ""
    budget: str = ""
    cpa_bid: str = ""
    roi_goal: str = ""
    extra: dict[str, Any] = Field(default_factory=dict)


class ProjectManagementExecutePreviewRequest(BaseModel):
    project_update_path: str = "configs/project-updates/ui-project-filter.local.json"


class ProjectManagementExecuteRequest(ProjectManagementExecutePreviewRequest):
    confirmation: str


@router.post("/project-management/config/preview")
def project_management_config_preview(request: Request, body: ProjectManagementConfigPreviewRequest) -> dict:
    return build_project_management_config_preview(
        body.model_dump(),
        project_root=request.app.state.settings.project_root,
    )


@router.post("/project-management/config/generate")
def project_management_config_generate(request: Request, body: ProjectManagementConfigPreviewRequest) -> dict:
    return start_project_management_config_task(
        body.model_dump(),
        project_root=request.app.state.settings.project_root,
    )


@router.post("/project-management/execute/preview")
def project_management_execute_preview(request: Request, body: ProjectManagementExecutePreviewRequest) -> dict:
    return build_project_management_execute_preview(
        body.model_dump(),
        project_root=request.app.state.settings.project_root,
    )


@router.post("/project-management/execute")
def project_management_execute(request: Request, body: ProjectManagementExecuteRequest) -> dict:
    if body.confirmation != "确认执行":
        raise HTTPException(status_code=400, detail="真实执行前必须输入：确认执行")
    return start_project_management_execute_task(
        body.model_dump(),
        project_root=request.app.state.settings.project_root,
    )
