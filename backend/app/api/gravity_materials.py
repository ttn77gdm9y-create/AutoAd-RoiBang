from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi import Request
from pydantic import BaseModel

from backend.app.services.gravity_materials import delete_gravity_binding
from backend.app.services.gravity_materials import gravity_album_tree
from backend.app.services.gravity_materials import list_gravity_bindings
from backend.app.services.gravity_materials import list_gravity_materials
from backend.app.services.gravity_materials import save_gravity_binding

router = APIRouter()


class GravityBindingRequest(BaseModel):
    product: str
    album_id: str
    album_name: str
    folder_id: str = ""
    folder_name: str = ""


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
) -> dict[str, Any]:
    return list_gravity_materials(
        project_root=request.app.state.settings.project_root,
        product=product,
        status=status,
        keyword=keyword,
        limit=limit,
    )


@router.get("/gravity-materials/albums")
def gravity_material_albums(request: Request) -> dict[str, Any]:
    return gravity_album_tree(project_root=request.app.state.settings.project_root)
