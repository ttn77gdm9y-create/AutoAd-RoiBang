from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi import Request
from pydantic import BaseModel
from pydantic import Field

from backend.app.safety.confirmation import require_execute_confirmation
from backend.app.services.project_management import build_project_management_execute_preview
from backend.app.services.project_management import build_project_management_config_preview
from backend.app.services.project_management import start_project_management_execute_task
from backend.app.services.project_management import start_project_management_config_task

router = APIRouter()


class ProjectManagementConfigPreviewRequest(BaseModel):
    project_update_id: str = ""
    advertiser_ids: str | list[str] = ""
    action_type: str = ""
    name_contains: str = ""
    spend_window: str = ""
    metric_field: str = ""
    metric_op: str = ""
    metric_value: str = ""
    metric_filters: list[dict[str, Any]] = Field(default_factory=list)
    output_path: str = ""
    opt_status: str = ""
    budget: str = ""
    cpa_bid: str = ""
    roi_goal: str = ""
    extra: dict[str, Any] = Field(default_factory=dict)


class ProjectManagementExecutePreviewRequest(BaseModel):
    project_update_path: str = ""
    config_source: str = ""


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
    require_execute_confirmation(body.confirmation)
    return start_project_management_execute_task(
        body.model_dump(),
        project_root=request.app.state.settings.project_root,
    )
