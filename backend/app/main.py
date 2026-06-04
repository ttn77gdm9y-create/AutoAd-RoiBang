from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi import Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.app.api import account_remarks
from backend.app.api import accounts
from backend.app.api import actions
from backend.app.api import automation_health
from backend.app.api import create_plans
from backend.app.api import dashboard
from backend.app.api import gravity_materials
from backend.app.api import health
from backend.app.api import operations
from backend.app.api import product_automation
from backend.app.api import project_management
from backend.app.api import sites
from backend.app.api import suggestions
from backend.app.api import tasks
from backend.app.api import workflow_runs
from backend.app.api import workflows
from backend.app.services.settings import build_settings

logger = logging.getLogger(__name__)


def _detail_message(detail: object) -> str:
    return detail if isinstance(detail, str) else "请求失败"


def create_app(project_root: str | Path | None = None) -> FastAPI:
    settings = build_settings(project_root)
    app = FastAPI(title="RoiBang Local API", version="0.1.0")
    app.state.settings = settings
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1:5173",
            "http://127.0.0.1:5174",
            "http://127.0.0.1:5175",
            "http://127.0.0.1:5176",
            "http://localhost:5173",
            "http://localhost:5174",
            "http://localhost:5175",
            "http://localhost:5176",
        ],
        allow_origin_regex=r"http://(127\.0\.0\.1|localhost):51[0-9]{2}",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "detail": exc.detail,
                "error_code": "http_error",
                "message": _detail_message(exc.detail),
            },
            headers=exc.headers,
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, _exc: Exception) -> JSONResponse:
        logger.exception("Unhandled API exception: %s %s", request.method, request.url.path)
        message = "本地服务异常，请查看后端日志"
        return JSONResponse(
            status_code=500,
            content={
                "detail": message,
                "error_code": "internal_server_error",
                "message": message,
            },
        )

    app.include_router(health.router, prefix="/api")
    app.include_router(workflows.router, prefix="/api")
    app.include_router(workflow_runs.router, prefix="/api")
    app.include_router(tasks.router, prefix="/api")
    app.include_router(automation_health.router, prefix="/api")
    app.include_router(actions.router, prefix="/api")
    app.include_router(accounts.router, prefix="/api")
    app.include_router(dashboard.router, prefix="/api")
    app.include_router(gravity_materials.router, prefix="/api")
    app.include_router(operations.router, prefix="/api")
    app.include_router(product_automation.router, prefix="/api")
    app.include_router(suggestions.router, prefix="/api")
    app.include_router(create_plans.router, prefix="/api")
    app.include_router(project_management.router, prefix="/api")
    app.include_router(account_remarks.router, prefix="/api")
    app.include_router(sites.router, prefix="/api")
    return app


app = create_app()
