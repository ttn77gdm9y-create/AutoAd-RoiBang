from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi import HTTPException
from fastapi import Query
from fastapi import Request
from pydantic import BaseModel
from pydantic import Field

from backend.app.services.create_plans import build_create_plan_detail
from backend.app.services.create_plans import build_create_plan_execute_preview
from backend.app.services.create_plans import build_create_plan_generate_preview
from backend.app.services.create_plans import build_create_plan_template_detail
from backend.app.services.create_plans import build_latest_create_plan_detail
from backend.app.services.create_plans import list_create_plan_templates
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
    extra: dict[str, Any] = Field(default_factory=dict)


class CreatePlanDetailRequest(BaseModel):
    plan_path: str = ""
    plan_source: str = ""


class CreatePlanExecutePreviewRequest(CreatePlanDetailRequest):
    resume_existing_plan: bool = False


class CreatePlanExecuteRequest(CreatePlanExecutePreviewRequest):
    confirmation: str


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


@router.get("/create-plans/templates")
def create_plan_templates(request: Request) -> dict:
    return list_create_plan_templates(project_root=request.app.state.settings.project_root)


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
    if body.confirmation != "确认执行":
        raise HTTPException(status_code=400, detail="真实执行前必须输入：确认执行")
    return start_create_plan_execute_task(
        plan_id,
        body.model_dump(),
        project_root=request.app.state.settings.project_root,
    )
