from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi import HTTPException
from fastapi import Request
from pydantic import BaseModel
from pydantic import Field

from backend.app.services.account_remarks import build_account_remark_config_preview
from backend.app.services.account_remarks import build_account_remark_execute_preview
from backend.app.services.account_remarks import start_account_remark_config_task
from backend.app.services.account_remarks import start_account_remark_execute_task

router = APIRouter()


class AccountRemarkConfigPreviewRequest(BaseModel):
    update_id: str = "ui-account-remark"
    remark: str = ""
    advertiser_ids: str | list[str] = ""
    output_path: str = ""
    extra: dict[str, Any] = Field(default_factory=dict)


class AccountRemarkExecutePreviewRequest(BaseModel):
    account_remark_update_path: str = "configs/account-updates/ui-account-remark.local.json"


class AccountRemarkExecuteRequest(AccountRemarkExecutePreviewRequest):
    confirmation: str


@router.post("/account-remarks/config/preview")
def account_remark_config_preview(request: Request, body: AccountRemarkConfigPreviewRequest) -> dict:
    return build_account_remark_config_preview(
        body.model_dump(),
        project_root=request.app.state.settings.project_root,
    )


@router.post("/account-remarks/config/generate")
def account_remark_config_generate(request: Request, body: AccountRemarkConfigPreviewRequest) -> dict:
    return start_account_remark_config_task(
        body.model_dump(),
        project_root=request.app.state.settings.project_root,
    )


@router.post("/account-remarks/execute/preview")
def account_remark_execute_preview(request: Request, body: AccountRemarkExecutePreviewRequest) -> dict:
    return build_account_remark_execute_preview(
        body.model_dump(),
        project_root=request.app.state.settings.project_root,
    )


@router.post("/account-remarks/execute")
def account_remark_execute(request: Request, body: AccountRemarkExecuteRequest) -> dict:
    if body.confirmation != "确认执行":
        raise HTTPException(status_code=400, detail="真实执行前必须输入：确认执行")
    return start_account_remark_execute_task(
        body.model_dump(),
        project_root=request.app.state.settings.project_root,
    )
