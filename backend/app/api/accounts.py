from __future__ import annotations

from email import policy
from email.parser import BytesParser

from fastapi import APIRouter
from fastapi import HTTPException
from fastapi import Request
from fastapi import Response
from pydantic import BaseModel
from pydantic import Field

from backend.app.services.accounts_store import account_store_path
from backend.app.services.accounts_store import accounts_result
from backend.app.services.accounts_store import accounts_template_csv
from backend.app.services.accounts_store import accounts_to_csv
from backend.app.services.accounts_store import backfill_accounts_from_history
from backend.app.services.accounts_store import bulk_update_accounts
from backend.app.services.accounts_store import commit_import
from backend.app.services.accounts_store import filter_accounts
from backend.app.services.accounts_store import load_accounts
from backend.app.services.accounts_store import parse_csv_bytes
from backend.app.services.accounts_store import parse_paste_text
from backend.app.services.accounts_store import parse_xlsx_bytes
from backend.app.services.accounts_store import preview_import
from backend.app.services.accounts_store import preview_bulk_update_accounts

router = APIRouter()


class PasteImportRequest(BaseModel):
    text: str


class BulkUpdateAccountsRequest(BaseModel):
    product_key: str = ""
    channel: str = ""
    owner: str = ""
    status: str = ""
    advertiser_ids: list[str] = Field(default_factory=list)
    advertiser_ids_text: str = ""
    updates: dict[str, str] = Field(default_factory=dict)


@router.get("/accounts")
def accounts(
    request: Request,
    product_key: str = "",
    channel: str = "",
    owner: str = "",
    status: str = "",
) -> dict:
    settings = request.app.state.settings
    rows = filter_accounts(
        load_accounts(settings.configs_dir),
        product_key=product_key,
        channel=channel,
        owner=owner,
        status=status,
    )
    return accounts_result(rows, artifact_path=str(account_store_path(settings.configs_dir)))


@router.post("/accounts/paste/preview")
def paste_preview(request: Request, body: PasteImportRequest) -> dict:
    settings = request.app.state.settings
    incoming = parse_paste_text(body.text)
    return preview_import(load_accounts(settings.configs_dir), incoming)


@router.post("/accounts/paste/commit")
def paste_commit(request: Request, body: PasteImportRequest) -> dict:
    incoming = parse_paste_text(body.text)
    return commit_import(request.app.state.settings.configs_dir, incoming)


@router.post("/accounts/import/preview")
async def import_preview(request: Request) -> dict:
    filename, content = await _read_upload_request(request)
    incoming = _parse_upload(filename, content)
    return preview_import(load_accounts(request.app.state.settings.configs_dir), incoming)


@router.post("/accounts/import/commit")
async def import_commit(request: Request) -> dict:
    filename, content = await _read_upload_request(request)
    incoming = _parse_upload(filename, content)
    return commit_import(request.app.state.settings.configs_dir, incoming)


@router.get("/accounts/export")
def export_accounts(request: Request) -> Response:
    csv_text = accounts_to_csv(load_accounts(request.app.state.settings.configs_dir))
    return Response(
        content=csv_text,
        media_type="text/csv; charset=utf-8",
        headers={"content-disposition": "attachment; filename=product-accounts.csv"},
    )


@router.get("/accounts/template")
def download_accounts_template() -> Response:
    return Response(
        content=accounts_template_csv(),
        media_type="text/csv; charset=utf-8",
        headers={"content-disposition": "attachment; filename=product-accounts-template.csv"},
    )


@router.post("/accounts/bulk-update")
def bulk_update(request: Request, body: BulkUpdateAccountsRequest) -> dict:
    settings = request.app.state.settings
    return bulk_update_accounts(
        settings.configs_dir,
        filters={
            "product_key": body.product_key,
            "channel": body.channel,
            "owner": body.owner,
            "status": body.status,
        },
        updates=body.updates,
        advertiser_ids=body.advertiser_ids,
        advertiser_ids_text=body.advertiser_ids_text,
    )


@router.post("/accounts/bulk-update/preview")
def bulk_update_preview(request: Request, body: BulkUpdateAccountsRequest) -> dict:
    settings = request.app.state.settings
    return preview_bulk_update_accounts(
        settings.configs_dir,
        filters={
            "product_key": body.product_key,
            "channel": body.channel,
            "owner": body.owner,
            "status": body.status,
        },
        updates=body.updates,
        advertiser_ids=body.advertiser_ids,
        advertiser_ids_text=body.advertiser_ids_text,
    )


@router.post("/accounts/backfill/history")
def backfill_history(request: Request) -> dict:
    settings = request.app.state.settings
    return backfill_accounts_from_history(settings.configs_dir, settings.runs_dir)


async def _read_upload_request(request: Request) -> tuple[str, bytes]:
    content_type = request.headers.get("content-type", "")
    body = await request.body()
    if "multipart/form-data" not in content_type:
        return "accounts.csv", body

    message = BytesParser(policy=policy.default).parsebytes(
        f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("utf-8") + body
    )
    for part in message.iter_parts():
        disposition = part.get_content_disposition()
        params = dict(part.get_params(header="content-disposition") or [])
        if disposition == "form-data" and params.get("name") == "file":
            filename = str(params.get("filename") or "accounts.csv")
            payload = part.get_payload(decode=True)
            return filename, payload or b""
    raise HTTPException(status_code=400, detail="上传请求中没有找到 file 文件")


def _parse_upload(filename: str, content: bytes) -> list[dict[str, str]]:
    filename = filename.lower()
    if filename.endswith(".csv") or filename.endswith(".txt"):
        return parse_csv_bytes(content)
    if filename.endswith(".xlsx"):
        try:
            return parse_xlsx_bytes(content)
        except RuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise HTTPException(status_code=400, detail="只支持 CSV、TXT 或 XLSX 文件")
