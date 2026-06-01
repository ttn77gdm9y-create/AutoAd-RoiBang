from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api import account_remarks
from backend.app.api import accounts
from backend.app.api import actions
from backend.app.api import create_plans
from backend.app.api import dashboard
from backend.app.api import health
from backend.app.api import operations
from backend.app.api import product_automation
from backend.app.api import project_management
from backend.app.api import sites
from backend.app.api import suggestions
from backend.app.api import tasks
from backend.app.api import workflows
from backend.app.services.settings import build_settings


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
    app.include_router(health.router, prefix="/api")
    app.include_router(workflows.router, prefix="/api")
    app.include_router(tasks.router, prefix="/api")
    app.include_router(actions.router, prefix="/api")
    app.include_router(accounts.router, prefix="/api")
    app.include_router(dashboard.router, prefix="/api")
    app.include_router(operations.router, prefix="/api")
    app.include_router(product_automation.router, prefix="/api")
    app.include_router(suggestions.router, prefix="/api")
    app.include_router(create_plans.router, prefix="/api")
    app.include_router(project_management.router, prefix="/api")
    app.include_router(account_remarks.router, prefix="/api")
    app.include_router(sites.router, prefix="/api")
    return app


app = create_app()
