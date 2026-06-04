from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi import Query
from fastapi import Request
from pydantic import BaseModel
from pydantic import Field

from backend.app.safety.confirmation import require_execute_confirmation
from backend.app.services.create_plans import build_create_plan_detail
from backend.app.services.create_plans import build_create_plan_execute_preview
from backend.app.services.create_plans import build_create_plan_execution_review_preview
from backend.app.services.create_plans import build_create_plan_generate_preview
from backend.app.services.create_plans import build_create_plan_suggestion_preview_detail
from backend.app.services.create_plans import build_create_plan_template_detail
from backend.app.services.create_plans import build_latest_create_plan_detail
from backend.app.services.create_plans import list_create_plan_templates
from backend.app.services.create_plans import list_create_plan_modes
from backend.app.services.create_plans import start_create_plan_execute_task
from backend.app.services.create_plans import start_create_plan_generate_task

router = APIRouter()


class CreatePlanPreviewRequest(BaseModel):
    mode: str = ""
    advertiser_ids: str | list[str] = ""
    owner: str = ""
    target_date: str = ""
    product_key: str = ""
    product_name: str = ""
    template_catalog: str = ""
    cpa_bid: str = ""
    roi_coefficient: str = ""
    material_source: str = ""
    extra: dict[str, Any] = Field(default_factory=dict)


class CreatePlanDetailRequest(BaseModel):
    plan_path: str = ""
    plan_source: str = ""
    source_suggestion_preview_path: str = ""
    execution_review_artifact_path: str = ""
    review_config_path: str = ""
    operator: str = ""


class CreatePlanExecutePreviewRequest(CreatePlanDetailRequest):
    resume_existing_plan: bool = False


class CreatePlanExecuteRequest(CreatePlanExecutePreviewRequest):
    confirmation: str


class CreatePlanExecutionReviewRequest(CreatePlanDetailRequest):
    create_plan_preview_path: str = ""
    batch_name: str = ""
    batch_sequence: str = ""
    resume_existing_plan: bool = False


@router.post("/create-plans/preview")
def create_plan_preview(request: Request, body: CreatePlanPreviewRequest) -> dict:
    return build_create_plan_generate_preview(
        body.model_dump(),
        project_root=request.app.state.settings.project_root,
    )


@router.post("/create-plans/generate")
def create_plan_generate(request: Request, body: CreatePlanPreviewRequest) -> dict:
    return start_create_plan_generate_task(
        body.model_dump(),
        project_root=request.app.state.settings.project_root,
    )


@router.get("/create-plans/latest")
def latest_create_plan(request: Request) -> dict:
    return build_latest_create_plan_detail(
        project_root=request.app.state.settings.project_root,
    )


@router.get("/create-plans/suggestion-preview")
def create_plan_suggestion_preview(request: Request, path: str = Query(default="")) -> dict:
    return build_create_plan_suggestion_preview_detail(
        path,
        project_root=request.app.state.settings.project_root,
    )


@router.post("/create-plans/execution-review/preview")
def create_plan_execution_review_preview(request: Request, body: CreatePlanExecutionReviewRequest) -> dict:
    return build_create_plan_execution_review_preview(
        body.model_dump(),
        project_root=request.app.state.settings.project_root,
    )


@router.get("/create-plans/templates")
def create_plan_templates(request: Request) -> dict:
    return list_create_plan_templates(project_root=request.app.state.settings.project_root)


@router.get("/create-plans/modes")
def create_plan_modes(request: Request, product_key: str = Query(default="")) -> dict:
    return list_create_plan_modes(project_root=request.app.state.settings.project_root, product_key=product_key)


@router.get("/create-plans/template-detail")
def create_plan_template_detail(request: Request, path: str = Query(default="")) -> dict:
    return build_create_plan_template_detail(path, project_root=request.app.state.settings.project_root)


@router.get("/create-plans/{plan_id}")
def create_plan_detail(request: Request, plan_id: str, plan_path: str = Query(default="")) -> dict:
    return build_create_plan_detail(
        plan_id,
        {"plan_path": plan_path},
        project_root=request.app.state.settings.project_root,
    )


@router.post("/create-plans/{plan_id}/execute/preview")
def create_plan_execute_preview(request: Request, plan_id: str, body: CreatePlanExecutePreviewRequest) -> dict:
    return build_create_plan_execute_preview(
        plan_id,
        body.model_dump(),
        project_root=request.app.state.settings.project_root,
    )


@router.post("/create-plans/{plan_id}/execute")
def create_plan_execute(request: Request, plan_id: str, body: CreatePlanExecuteRequest) -> dict:
    require_execute_confirmation(body.confirmation)
    return start_create_plan_execute_task(
        plan_id,
        body.model_dump(),
        project_root=request.app.state.settings.project_root,
    )
