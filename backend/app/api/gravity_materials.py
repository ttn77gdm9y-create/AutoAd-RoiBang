from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi import Request
from pydantic import BaseModel
from pydantic import Field

from backend.app.safety.confirmation import require_execute_confirmation
from backend.app.services.gravity_materials import build_gravity_upload_preview_result
from backend.app.services.gravity_materials import delete_gravity_binding
from backend.app.services.gravity_materials import gravity_album_tree
from backend.app.services.gravity_materials import gravity_sync_readiness
from backend.app.services.gravity_materials import gravity_upload_status_result
from backend.app.services.gravity_materials import list_gravity_bindings
from backend.app.services.gravity_materials import list_gravity_materials
from backend.app.services.gravity_materials import save_gravity_binding
from backend.app.services.gravity_materials import start_gravity_upload_status_refresh_task
from backend.app.services.gravity_materials import start_gravity_upload_task

router = APIRouter()


class GravityBindingRequest(BaseModel):
    product: str
    album_id: str
    album_name: str
    folder_id: str = ""
    folder_name: str = ""


class GravityUploadTargetAccount(BaseModel):
    advertiser_id: str
    account_name: str = ""


class GravityUploadPreviewRequest(BaseModel):
    product: str = ""
    target_accounts: list[GravityUploadTargetAccount] = Field(default_factory=list)
    material_ids: list[str] = Field(default_factory=list)


class GravityUploadExecuteRequest(BaseModel):
    preview_path: str
    auth_file: str = "data/gravity_token.json"
    confirmation: str


class GravityUploadStatusRefreshRequest(BaseModel):
    task_id: str
    auth_file: str = "data/gravity_token.json"


@router.get("/gravity-materials/bindings")
def gravity_material_bindings(request: Request, product: str = "") -> dict[str, Any]:
    return list_gravity_bindings(project_root=request.app.state.settings.project_root, product=product)


@router.post("/gravity-materials/bindings")
def gravity_material_binding_save(request: Request, body: GravityBindingRequest) -> dict[str, Any]:
    return save_gravity_binding(project_root=request.app.state.settings.project_root, body=body.model_dump())


@router.delete("/gravity-materials/bindings/{binding_id}")
def gravity_material_binding_delete(request: Request, binding_id: int) -> dict[str, Any]:
    return delete_gravity_binding(project_root=request.app.state.settings.project_root, binding_id=binding_id)


@router.get("/gravity-materials/materials")
def gravity_material_rows(
    request: Request,
    product: str = "",
    status: str = "",
    keyword: str = "",
    limit: int = 100,
    page: int = 1,
    page_size: int = 100,
    sort_by: str = "",
    sort_order: str = "",
) -> dict[str, Any]:
    return list_gravity_materials(
        project_root=request.app.state.settings.project_root,
        product=product,
        status=status,
        keyword=keyword,
        limit=limit,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
    )


@router.get("/gravity-materials/sync-readiness")
def gravity_material_sync_readiness(request: Request, product: str = "", auth_file: str = "data/gravity_token.json") -> dict[str, Any]:
    return gravity_sync_readiness(
        project_root=request.app.state.settings.project_root,
        product=product,
        auth_file=auth_file,
    )


@router.get("/gravity-materials/albums")
def gravity_material_albums(request: Request) -> dict[str, Any]:
    return gravity_album_tree(project_root=request.app.state.settings.project_root)


@router.post("/gravity-materials/upload-preview")
def gravity_material_upload_preview(request: Request, body: GravityUploadPreviewRequest) -> dict[str, Any]:
    return build_gravity_upload_preview_result(
        project_root=request.app.state.settings.project_root,
        body=body.model_dump(),
    )


@router.post("/gravity-materials/upload-execute")
def gravity_material_upload_execute(request: Request, body: GravityUploadExecuteRequest) -> dict[str, Any]:
    require_execute_confirmation(body.confirmation)
    return start_gravity_upload_task(
        project_root=request.app.state.settings.project_root,
        body=body.model_dump(),
    )


@router.post("/gravity-materials/upload-status-refresh")
def gravity_material_upload_status_refresh(request: Request, body: GravityUploadStatusRefreshRequest) -> dict[str, Any]:
    return start_gravity_upload_status_refresh_task(
        project_root=request.app.state.settings.project_root,
        body=body.model_dump(),
    )


@router.get("/gravity-materials/upload-status/{task_id}")
def gravity_material_upload_status(request: Request, task_id: str) -> dict[str, Any]:
    return gravity_upload_status_result(
        project_root=request.app.state.settings.project_root,
        task_id=task_id,
        title="引力素材上传状态",
    )


@router.get("/gravity-materials/upload-result/{task_id}")
def gravity_material_upload_result(request: Request, task_id: str) -> dict[str, Any]:
    return gravity_upload_status_result(
        project_root=request.app.state.settings.project_root,
        task_id=task_id,
        title="引力素材上传结果",
    )
