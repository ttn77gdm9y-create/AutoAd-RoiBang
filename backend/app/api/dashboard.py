from __future__ import annotations

from fastapi import APIRouter
from fastapi import HTTPException
from fastapi import Request

from backend.app.services.dashboard import build_dashboard_accounts
from backend.app.services.dashboard import build_dashboard_account_detail
from backend.app.services.dashboard import build_dashboard_filters
from backend.app.services.dashboard import build_dashboard_material_detail
from backend.app.services.dashboard import build_dashboard_materials
from backend.app.services.dashboard import build_dashboard_overview
from backend.app.services.dashboard import build_dashboard_project_detail
from backend.app.services.dashboard import build_dashboard_product_detail
from backend.app.services.dashboard import build_dashboard_products
from backend.app.services.dashboard import build_dashboard_projects
from backend.app.services.dashboard import build_dashboard_suggestions

router = APIRouter()


@router.get("/dashboard/filters")
def dashboard_filters(request: Request) -> dict:
    return build_dashboard_filters(request.app.state.settings.configs_dir)


@router.get("/dashboard/overview")
def dashboard_overview(
    request: Request,
    product_key: str = "",
    channel: str = "",
    owner: str = "",
    status: str = "",
    start_date: str = "",
    end_date: str = "",
    date_range: str = "",
) -> dict:
    settings = request.app.state.settings
    return build_dashboard_overview(
        settings.runs_dir,
        settings.configs_dir,
        product_key=product_key,
        channel=channel,
        owner=owner,
        status=status,
        start_date=start_date,
        end_date=end_date,
        date_range=date_range,
    )


@router.get("/dashboard/products")
def dashboard_products(
    request: Request,
    product_key: str = "",
    channel: str = "",
    owner: str = "",
    status: str = "",
    start_date: str = "",
    end_date: str = "",
    date_range: str = "",
) -> dict:
    settings = request.app.state.settings
    return build_dashboard_products(
        settings.runs_dir,
        settings.configs_dir,
        product_key=product_key,
        channel=channel,
        owner=owner,
        status=status,
        start_date=start_date,
        end_date=end_date,
        date_range=date_range,
    )


@router.get("/dashboard/products/{product_key}")
def dashboard_product_detail(
    request: Request,
    product_key: str,
    start_date: str = "",
    end_date: str = "",
    date_range: str = "",
) -> dict:
    settings = request.app.state.settings
    result = build_dashboard_product_detail(
        settings.runs_dir,
        settings.configs_dir,
        product_key,
        start_date=start_date,
        end_date=end_date,
        date_range=date_range,
    )
    if result is None:
        raise HTTPException(status_code=404, detail=f"未找到产品：{product_key}")
    return result


@router.get("/dashboard/projects")
def dashboard_projects(
    request: Request,
    product_key: str = "",
    channel: str = "",
    owner: str = "",
    status: str = "",
    start_date: str = "",
    end_date: str = "",
    date_range: str = "",
) -> dict:
    settings = request.app.state.settings
    return build_dashboard_projects(
        settings.runs_dir,
        settings.configs_dir,
        product_key=product_key,
        channel=channel,
        owner=owner,
        status=status,
        start_date=start_date,
        end_date=end_date,
        date_range=date_range,
    )


@router.get("/dashboard/projects/{project_id}")
def dashboard_project_detail(
    request: Request,
    project_id: str,
    start_date: str = "",
    end_date: str = "",
    date_range: str = "",
) -> dict:
    settings = request.app.state.settings
    result = build_dashboard_project_detail(
        settings.runs_dir,
        settings.configs_dir,
        project_id,
        start_date=start_date,
        end_date=end_date,
        date_range=date_range,
    )
    if result is None:
        raise HTTPException(status_code=404, detail=f"未找到项目：{project_id}")
    return result


@router.get("/dashboard/accounts")
def dashboard_accounts(
    request: Request,
    product_key: str = "",
    channel: str = "",
    owner: str = "",
    status: str = "",
    start_date: str = "",
    end_date: str = "",
    date_range: str = "",
) -> dict:
    settings = request.app.state.settings
    return build_dashboard_accounts(
        settings.runs_dir,
        settings.configs_dir,
        product_key=product_key,
        channel=channel,
        owner=owner,
        status=status,
        start_date=start_date,
        end_date=end_date,
        date_range=date_range,
    )


@router.get("/dashboard/accounts/{advertiser_id}")
def dashboard_account_detail(
    request: Request,
    advertiser_id: str,
    start_date: str = "",
    end_date: str = "",
    date_range: str = "",
) -> dict:
    settings = request.app.state.settings
    result = build_dashboard_account_detail(
        settings.runs_dir,
        settings.configs_dir,
        advertiser_id,
        start_date=start_date,
        end_date=end_date,
        date_range=date_range,
    )
    if result is None:
        raise HTTPException(status_code=404, detail=f"未找到账户：{advertiser_id}")
    return result


@router.get("/dashboard/suggestions")
def dashboard_suggestions(
    request: Request,
    product_key: str = "",
    channel: str = "",
    owner: str = "",
    status: str = "",
    start_date: str = "",
    end_date: str = "",
    date_range: str = "",
) -> dict:
    settings = request.app.state.settings
    return build_dashboard_suggestions(
        settings.runs_dir,
        settings.configs_dir,
        product_key=product_key,
        channel=channel,
        owner=owner,
        status=status,
        start_date=start_date,
        end_date=end_date,
        date_range=date_range,
    )


@router.get("/dashboard/materials")
def dashboard_materials(
    request: Request,
    product_key: str = "",
    channel: str = "",
    owner: str = "",
    status: str = "",
    start_date: str = "",
    end_date: str = "",
    date_range: str = "",
) -> dict:
    settings = request.app.state.settings
    return build_dashboard_materials(
        settings.runs_dir,
        settings.configs_dir,
        product_key=product_key,
        channel=channel,
        owner=owner,
        status=status,
        start_date=start_date,
        end_date=end_date,
        date_range=date_range,
    )


@router.get("/dashboard/materials/{promotion_id}")
def dashboard_material_detail(
    request: Request,
    promotion_id: str,
    start_date: str = "",
    end_date: str = "",
    date_range: str = "",
) -> dict:
    settings = request.app.state.settings
    result = build_dashboard_material_detail(
        settings.runs_dir,
        settings.configs_dir,
        promotion_id,
        start_date=start_date,
        end_date=end_date,
        date_range=date_range,
    )
    if result is None:
        raise HTTPException(status_code=404, detail=f"未找到单元素材：{promotion_id}")
    return result
