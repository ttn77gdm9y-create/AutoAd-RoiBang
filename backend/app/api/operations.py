from __future__ import annotations

from fastapi import APIRouter
from fastapi import Request

from backend.app.services.operation_logs import build_operation_log_detail_result
from backend.app.services.operation_logs import build_operation_logs_result

router = APIRouter()


@router.get("/operations")
def operations(
    request: Request,
    product: str = "",
    operation_type: str = "",
    status: str = "",
    limit: int = 200,
) -> dict:
    settings = request.app.state.settings
    return build_operation_logs_result(
        settings.runs_dir,
        configs_dir=settings.configs_dir,
        product=product,
        operation_type=operation_type,
        status=status,
        limit=limit,
    )


@router.get("/operations/{task_id}")
def operation_detail(request: Request, task_id: str) -> dict:
    settings = request.app.state.settings
    return build_operation_log_detail_result(
        settings.runs_dir,
        task_id,
        configs_dir=settings.configs_dir,
    )
