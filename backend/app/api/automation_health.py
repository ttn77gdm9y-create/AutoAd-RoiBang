from __future__ import annotations

from fastapi import APIRouter
from fastapi import Request

from backend.app.services.automation_health import build_automation_health_overview

router = APIRouter()


@router.get("/automation-health/overview")
def automation_health_overview(request: Request) -> dict:
    settings = request.app.state.settings
    return build_automation_health_overview(
        project_root=settings.project_root,
        configs_dir=settings.configs_dir,
        runs_dir=settings.runs_dir,
    )
