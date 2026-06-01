from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi import Request
from pydantic import BaseModel
from pydantic import Field

from backend.app.services.suggestions import build_suggestions_list
from backend.app.services.suggestions import build_suggestions_lifecycle
from backend.app.services.suggestions import build_suggestions_overview
from backend.app.services.suggestions import build_suggestions_backtest
from backend.app.services.suggestions import build_suggestions_create_strategy_review
from backend.app.services.suggestions import build_suggestions_create_plan_preview
from backend.app.services.suggestions import build_suggestions_daily_operations
from backend.app.services.suggestions import build_suggestions_effect_review
from backend.app.services.suggestions import build_suggestions_ai_draft
from backend.app.services.suggestions import build_suggestions_project_update_preview
from backend.app.services.suggestions import start_suggestions_refresh_task
from backend.app.services.suggestions import start_suggestions_project_update_task

router = APIRouter()


class SuggestionsProjectUpdateRequest(BaseModel):
    suggestions_artifact_path: str = ""
    project_update_id: str = ""
    operator: str = ""
    product_key: str = ""
    product_name: str = ""
    allowed_target_accounts_path: str = ""
    selected_suggestion_ids: list[str] = Field(default_factory=list)
    suggested_actions: list[str] = Field(default_factory=list)
    output_path: str = ""
    extra: dict[str, Any] = Field(default_factory=dict)


class SuggestionsBacktestRequest(BaseModel):
    suggestions_artifact_path: str = ""
    product_key: str = ""
    lookahead_days: int = 1
    max_after_stat_cost: float = 100
    max_after_convert_cnt: float = 0


class SuggestionsCreatePlanPreviewRequest(BaseModel):
    suggestions_artifact_path: str = ""
    selected_suggestion_ids: list[str] = Field(default_factory=list)
    product_key: str = ""
    product_name: str = ""
    owner: str = ""
    target_date: str = ""
    template_catalog: str = ""
    cpa_bid: str = ""
    roi_coefficient: str = ""
    extra: dict[str, Any] = Field(default_factory=dict)


class SuggestionsAiDraftRequest(BaseModel):
    suggestions_artifact_path: str = ""
    project_update_id: str = ""
    operator: str = ""
    product_key: str = ""
    product_name: str = ""
    selected_suggestion_ids: list[str] = Field(default_factory=list)
    suggested_actions: list[str] = Field(default_factory=list)


class SuggestionsRefreshRequest(BaseModel):
    product_key: str = ""
    target_date: str = "today"


@router.get("/suggestions/overview")
def suggestions_overview(request: Request, product_key: str = "") -> dict:
    settings = request.app.state.settings
    return build_suggestions_overview(
        project_root=settings.project_root,
        configs_dir=settings.configs_dir,
        runs_dir=settings.runs_dir,
        product_key=product_key,
    )


@router.get("/suggestions")
def suggestions_list(request: Request, product_key: str = "") -> dict:
    settings = request.app.state.settings
    return build_suggestions_list(
        project_root=settings.project_root,
        configs_dir=settings.configs_dir,
        runs_dir=settings.runs_dir,
        product_key=product_key,
    )


@router.get("/suggestions/lifecycle")
def suggestions_lifecycle(request: Request, product_key: str = "") -> dict:
    settings = request.app.state.settings
    return build_suggestions_lifecycle(
        project_root=settings.project_root,
        configs_dir=settings.configs_dir,
        runs_dir=settings.runs_dir,
        product_key=product_key,
    )


@router.get("/suggestions/create-strategies")
def suggestions_create_strategies(request: Request, product_key: str = "") -> dict:
    settings = request.app.state.settings
    return build_suggestions_create_strategy_review(
        project_root=settings.project_root,
        configs_dir=settings.configs_dir,
        runs_dir=settings.runs_dir,
        product_key=product_key,
    )


@router.get("/suggestions/daily-operations")
def suggestions_daily_operations(request: Request, product_key: str = "") -> dict:
    settings = request.app.state.settings
    return build_suggestions_daily_operations(
        project_root=settings.project_root,
        configs_dir=settings.configs_dir,
        runs_dir=settings.runs_dir,
        product_key=product_key,
    )


@router.get("/suggestions/effect-review")
def suggestions_effect_review(request: Request, product_key: str = "") -> dict:
    settings = request.app.state.settings
    return build_suggestions_effect_review(
        project_root=settings.project_root,
        configs_dir=settings.configs_dir,
        runs_dir=settings.runs_dir,
        product_key=product_key,
    )


@router.post("/suggestions/refresh")
def suggestions_refresh(request: Request, body: SuggestionsRefreshRequest) -> dict:
    return start_suggestions_refresh_task(
        body.model_dump(),
        project_root=request.app.state.settings.project_root,
    )


@router.post("/suggestions/project-update/preview")
def suggestions_project_update_preview(request: Request, body: SuggestionsProjectUpdateRequest) -> dict:
    return build_suggestions_project_update_preview(
        body.model_dump(),
        project_root=request.app.state.settings.project_root,
    )


@router.post("/suggestions/project-update/generate")
def suggestions_project_update_generate(request: Request, body: SuggestionsProjectUpdateRequest) -> dict:
    return start_suggestions_project_update_task(
        body.model_dump(),
        project_root=request.app.state.settings.project_root,
    )


@router.post("/suggestions/create-plan/preview")
def suggestions_create_plan_preview(request: Request, body: SuggestionsCreatePlanPreviewRequest) -> dict:
    settings = request.app.state.settings
    return build_suggestions_create_plan_preview(
        body.model_dump(),
        project_root=settings.project_root,
        configs_dir=settings.configs_dir,
        runs_dir=settings.runs_dir,
    )


@router.post("/suggestions/ai-draft")
def suggestions_ai_draft(request: Request, body: SuggestionsAiDraftRequest) -> dict:
    settings = request.app.state.settings
    return build_suggestions_ai_draft(
        body.model_dump(),
        project_root=settings.project_root,
        configs_dir=settings.configs_dir,
        runs_dir=settings.runs_dir,
    )


@router.post("/suggestions/backtest")
def suggestions_backtest(request: Request, body: SuggestionsBacktestRequest) -> dict:
    settings = request.app.state.settings
    return build_suggestions_backtest(
        body.model_dump(),
        project_root=settings.project_root,
        configs_dir=settings.configs_dir,
        runs_dir=settings.runs_dir,
    )
