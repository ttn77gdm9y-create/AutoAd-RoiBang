from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi import HTTPException
from fastapi import Request
from pydantic import BaseModel
from pydantic import Field

from backend.app.services.sites import build_site_handsel_results
from backend.app.services.sites import build_site_status_preview
from backend.app.services.sites import build_site_template_foundation_preview
from backend.app.services.sites import start_site_status_task
from backend.app.services.sites import start_site_template_foundation_task

router = APIRouter()


class SiteStatusPreviewRequest(BaseModel):
    advertiser_id: str = ""
    site_ids: str | list[str] = ""
    handsel_artifact: str = ""
    status: str = ""
    extra: dict[str, Any] = Field(default_factory=dict)


class SiteStatusExecuteRequest(SiteStatusPreviewRequest):
    confirmation: str


class SiteTemplateFoundationPreviewRequest(BaseModel):
    source_advertiser_id: str = ""
    source_site_id: str = ""
    template_id: str = ""
    template_name: str = ""
    wechat_game_index: str = ""
    game_instance_id: str = ""
    game_path: str = ""
    target_advertiser_ids: str | list[str] = ""
    target_accounts_path: str = ""
    site_mapping_artifact: str = ""
    site_name_prefix: str = ""
    edit_existing: bool | None = None
    publish: bool | None = None
    product: str = ""
    product_key: str = ""
    owner: str = ""
    operator: str = ""
    extra: dict[str, Any] = Field(default_factory=dict)


class SiteTemplateFoundationExecuteRequest(SiteTemplateFoundationPreviewRequest):
    confirmation: str


@router.get("/sites/handsel-results")
def site_handsel_results(request: Request, artifact_path: str = "") -> dict:
    return build_site_handsel_results(
        project_root=request.app.state.settings.project_root,
        artifact_path=artifact_path,
    )


@router.post("/sites/status/preview")
def site_status_preview(request: Request, body: SiteStatusPreviewRequest) -> dict:
    return build_site_status_preview(
        body.model_dump(),
        project_root=request.app.state.settings.project_root,
    )


@router.post("/sites/status/execute")
def site_status_execute(request: Request, body: SiteStatusExecuteRequest) -> dict:
    if body.confirmation != "确认执行":
        raise HTTPException(status_code=400, detail="真实执行前必须输入：确认执行")
    return start_site_status_task(
        body.model_dump(),
        project_root=request.app.state.settings.project_root,
    )


@router.post("/sites/template-foundation/preview")
def site_template_foundation_preview(request: Request, body: SiteTemplateFoundationPreviewRequest) -> dict:
    return build_site_template_foundation_preview(
        body.model_dump(),
        project_root=request.app.state.settings.project_root,
    )


@router.post("/sites/template-foundation/execute")
def site_template_foundation_execute(request: Request, body: SiteTemplateFoundationExecuteRequest) -> dict:
    if body.confirmation != "确认执行":
        raise HTTPException(status_code=400, detail="真实执行前必须输入：确认执行")
    return start_site_template_foundation_task(
        body.model_dump(),
        project_root=request.app.state.settings.project_root,
    )
