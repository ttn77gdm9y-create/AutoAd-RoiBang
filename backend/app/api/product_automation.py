from __future__ import annotations

from email import policy
from email.parser import BytesParser

from fastapi import APIRouter
from fastapi import HTTPException
from fastapi import Request
from fastapi import Response
from pydantic import BaseModel
from pydantic import Field

from backend.app.services.product_automation import build_allowed_accounts_template
from backend.app.services.product_automation import build_product_automation_dry_run
from backend.app.services.product_automation import build_product_automation_overview
from backend.app.services.product_automation import import_allowed_accounts_upload
from backend.app.services.product_automation import save_product_automation_config

router = APIRouter()


class ProductAutomationConfigRequest(BaseModel):
    product_key: str
    product: str
    platform: str = "WECHAT_GAME"
    source_advertiser_name: str
    source_advertiser_id: str
    organization_id: str
    allowed_target_accounts_path: str
    account_name_keyword: str
    account_remark_equals: str = ""
    enabled_jobs: list[str] = Field(default_factory=list)


class ProductAutomationDryRunRequest(BaseModel):
    product_key: str
    job: str
    target_date: str = "yesterday"


@router.get("/product-automation/overview")
def product_automation_overview(request: Request) -> dict:
    settings = request.app.state.settings
    return build_product_automation_overview(
        project_root=settings.project_root,
        configs_dir=settings.configs_dir,
        runs_dir=settings.runs_dir,
    )


@router.post("/product-automation/config/save")
def product_automation_config_save(request: Request, body: ProductAutomationConfigRequest) -> dict:
    settings = request.app.state.settings
    return save_product_automation_config(configs_dir=settings.configs_dir, body=body.model_dump())


@router.get("/product-automation/allowed-accounts/template")
def product_automation_allowed_accounts_template(
    product_key: str = "",
    product: str = "",
    platform: str = "WECHAT_GAME",
) -> Response:
    try:
        content, filename = build_allowed_accounts_template(
            product_key=product_key,
            product=product,
            platform=platform,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"content-disposition": f"attachment; filename={filename}"},
    )


@router.post("/product-automation/allowed-accounts/import")
async def product_automation_allowed_accounts_import(
    request: Request,
    product_key: str = "",
    product: str = "",
    platform: str = "WECHAT_GAME",
) -> dict:
    filename, content = await _read_upload_request(request)
    settings = request.app.state.settings
    return import_allowed_accounts_upload(
        configs_dir=settings.configs_dir,
        filename=filename,
        content=content,
        product_key=product_key,
        product=product,
        platform=platform,
    )


@router.post("/product-automation/dry-run")
def product_automation_dry_run(request: Request, body: ProductAutomationDryRunRequest) -> dict:
    settings = request.app.state.settings
    return build_product_automation_dry_run(
        project_root=settings.project_root,
        configs_dir=settings.configs_dir,
        runs_dir=settings.runs_dir,
        product_key=body.product_key,
        job=body.job,
        target_date=body.target_date,
    )


async def _read_upload_request(request: Request) -> tuple[str, bytes]:
    content_type = request.headers.get("content-type", "")
    body = await request.body()
    if "multipart/form-data" not in content_type:
        return "allowed-accounts.xlsx", body

    message = BytesParser(policy=policy.default).parsebytes(
        f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("utf-8") + body
    )
    for part in message.iter_parts():
        disposition = part.get_content_disposition()
        params = dict(part.get_params(header="content-disposition") or [])
        if disposition == "form-data" and params.get("name") == "file":
            filename = str(params.get("filename") or "allowed-accounts.xlsx")
            payload = part.get_payload(decode=True)
            return filename, payload or b""
    raise HTTPException(status_code=400, detail="上传请求中没有找到 file 文件")
