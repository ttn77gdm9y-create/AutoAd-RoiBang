from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi import HTTPException
from fastapi import Request
from pydantic import BaseModel
from pydantic import Field

from backend.app.services.script_registry import build_action_task
from backend.app.services.script_registry import list_action_catalog
from backend.app.services.script_registry import start_action_task

router = APIRouter()


class ActionPreviewRequest(BaseModel):
    request: dict[str, Any] = Field(default_factory=dict)


class ActionExecuteRequest(BaseModel):
    confirmation: str
    request: dict[str, Any] = Field(default_factory=dict)


@router.get("/actions/catalog")
def action_catalog() -> dict:
    return list_action_catalog()


@router.post("/actions/{action}/preview")
def action_preview(request: Request, action: str, body: ActionPreviewRequest) -> dict:
    return build_action_task(action, body.request, project_root=request.app.state.settings.project_root)


@router.post("/actions/{action}/execute")
def action_execute(request: Request, action: str, body: ActionExecuteRequest) -> dict:
    if body.confirmation != "确认执行":
        raise HTTPException(status_code=400, detail="真实执行前必须输入：确认执行")
    preview = build_action_task(action, body.request, project_root=request.app.state.settings.project_root)
    if not preview.get("ok"):
        raise HTTPException(status_code=400, detail=preview["summary"]["blocking_reasons"][0])
    started = start_action_task(request.app.state.settings.project_root, preview["task"])
    return {
        "summary": preview["summary"],
        "table": preview["table"],
        "task": started,
        "raw": {"preview": preview, "started": started},
    }
