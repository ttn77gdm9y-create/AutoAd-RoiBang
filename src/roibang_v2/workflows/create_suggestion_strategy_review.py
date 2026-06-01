from __future__ import annotations

from pathlib import Path
from typing import Any

from roibang_v2.runs import write_run_artifact
from roibang_v2.workflows.create_plan_from_suggestions import _find_template_catalog
from roibang_v2.workflows.create_project_suggestions import _account_pool_rows
from roibang_v2.workflows.create_project_suggestions import _account_candidate_scope
from roibang_v2.workflows.create_project_suggestions import _allowed_accounts
from roibang_v2.workflows.create_project_suggestions import _bool
from roibang_v2.workflows.create_project_suggestions import _candidate_accounts
from roibang_v2.workflows.create_project_suggestions import _connect
from roibang_v2.workflows.create_project_suggestions import _evaluate_account
from roibang_v2.workflows.create_project_suggestions import _int
from roibang_v2.workflows.create_project_suggestions import _load_strategies
from roibang_v2.workflows.create_project_suggestions import _mode_config_path
from roibang_v2.workflows.create_project_suggestions import _number
from roibang_v2.workflows.create_project_suggestions import _qualified_materials
from roibang_v2.workflows.create_project_suggestions import _strategy_max_suggestions
from roibang_v2.workflows.create_project_suggestions import _target_date
from roibang_v2.workflows.create_project_suggestions import _text
from roibang_v2.workflows.product_automation_job import load_product_configs


WORKFLOW = "create_suggestion_strategy_review"


def _strategy_review_files(strategy_dir: str | Path, *, include_examples: bool) -> list[Path]:
    directory = Path(strategy_dir)
    if not directory.exists():
        return []
    local_paths = sorted(directory.glob("*.local.json"))
    if local_paths and not include_examples:
        return local_paths
    example_paths = sorted(
        path
        for path in directory.glob("*.json")
        if "example" in path.name and path not in local_paths
    )
    if local_paths:
        return [*local_paths, *example_paths]
    return example_paths


def _source_kind(path_text: str) -> str:
    path = Path(path_text)
    if path.name.endswith(".local.json"):
        return "local"
    if "example" in path.name:
        return "example"
    return "json"


def _material_thresholds(strategy: dict[str, Any]) -> dict[str, Any]:
    materials = strategy.get("materials") if isinstance(strategy.get("materials"), dict) else {}
    return {
        "window_key": _text(materials.get("window_key")) or "last_7d",
        "material_type": _text(materials.get("material_type")) or "video",
        "min_qualified_material_count": _int(materials.get("min_qualified_material_count"), 1),
        "min_stat_cost": _number(materials.get("min_stat_cost"), 0),
        "min_convert_cnt": _number(materials.get("min_convert_cnt"), 0),
        "min_roi_1day": _number(materials.get("min_roi_1day"), 0),
    }


def _account_thresholds(strategy: dict[str, Any]) -> dict[str, Any]:
    account = strategy.get("account") if isinstance(strategy.get("account"), dict) else {}
    return {
        "candidate_scope": _account_candidate_scope(strategy),
        "recent_window_days": _int(account.get("recent_window_days"), 1),
        "min_recent_stat_cost": _number(account.get("min_recent_stat_cost"), 0),
        "min_recent_convert_cnt": _number(account.get("min_recent_convert_cnt"), 0),
        "require_allowed_account": _bool(account.get("require_allowed_account"), True),
        "max_active_projects": _int(account.get("max_active_projects"), 20),
        "cooldown_days_after_create": _int(account.get("cooldown_days_after_create"), 0),
    }


def _recommendation(strategy: dict[str, Any]) -> dict[str, Any]:
    recommendation = strategy.get("recommendation") if isinstance(strategy.get("recommendation"), dict) else {}
    return {
        "project_count": _int(recommendation.get("project_count"), 1),
        "units_per_project": _int(recommendation.get("units_per_project"), 1),
        "daily_budget": _int(recommendation.get("daily_budget"), 0),
    }


def _matching_products(
    strategy: dict[str, Any],
    products: list[dict[str, Any]],
    *,
    requested_product_key: str,
) -> list[dict[str, Any]]:
    strategy_product_key = _text(strategy.get("product_key"))
    if requested_product_key and strategy_product_key and strategy_product_key != requested_product_key:
        return []
    if strategy_product_key:
        matched = [product for product in products if _text(product.get("product_key")) == strategy_product_key]
        if matched:
            return matched
        return [{"product_key": strategy_product_key, "_missing_product_config": True}]
    if products:
        return products
    return [{"product_key": requested_product_key, "_missing_product_config": True}]


def _status_from_review(
    *,
    enabled: bool,
    blocking_reasons: list[str],
    warnings: list[str],
    suggestion_count: int,
    blocked_candidate_count: int,
) -> str:
    if not enabled:
        return "disabled"
    if blocking_reasons:
        return "blocked"
    if warnings or suggestion_count == 0 or blocked_candidate_count > 0:
        return "warning"
    return "healthy"


def _repair_suggestions(
    *,
    enabled: bool,
    source_kind: str,
    product_key: str,
    mode_key: str,
    mode_exists: bool,
    db_exists: bool,
    product_exists: bool,
    candidate_account_count: int,
    qualified_material_count: int,
    material_thresholds: dict[str, Any],
    blocked_candidate_count: int,
) -> list[str]:
    repairs: list[str] = []
    if source_kind == "example":
        repairs.append("这是示例策略模板；复制为 .local.json，补齐产品和阈值后再启用。")
    if not enabled:
        repairs.append("策略未启用；确认阈值后将 enabled 设为 true。")
    if not product_exists:
        repairs.append(f"补充产品配置或修正 strategy.product_key：{product_key or '未填写'}。")
    if not db_exists:
        repairs.append("先完成本地 SQLite 初始化和只读数据同步。")
    if mode_key and not mode_exists:
        repairs.append(f"补充创建模式配置：configs/create-modes/{product_key}/{mode_key}.local.json。")
    if enabled and db_exists and product_exists and candidate_account_count == 0:
        repairs.append("检查允许创建账户名单和账户池同步结果。")
    if enabled and db_exists and product_exists and qualified_material_count < int(material_thresholds["min_qualified_material_count"]):
        repairs.append("检查源素材汇总，或在策略配置里调整素材门槛。")
    if enabled and blocked_candidate_count > 0:
        repairs.append("查看阻断候选账户，确认是否达到项目上限、冷却期或名单限制。")
    return _unique_texts(repairs)


def _unique_texts(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _text(value)
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _review_strategy_product(
    *,
    conn: Any,
    db_exists: bool,
    project_root: str | Path,
    mode_dir: str | Path,
    template_dir: str | Path,
    strategy: dict[str, Any],
    product: dict[str, Any],
    resolved_target_date: str,
) -> dict[str, Any]:
    enabled = _bool(strategy.get("enabled"), False)
    config_path = _text(strategy.get("_config_path"))
    source_kind = _source_kind(config_path)
    product_key = _text(product.get("product_key"))
    product_name = _text(product.get("product") or product.get("product_name"))
    product_exists = not bool(product.get("_missing_product_config"))
    mode_key = _text(strategy.get("mode_key"))
    mode_path = _mode_config_path(mode_dir, product_key=product_key, mode_key=mode_key) if mode_key else ""
    template_catalog = (
        _find_template_catalog(project_root, template_dir, product_key=product_key, product_name=product_name)
        if product_exists
        else ""
    )
    account_thresholds = _account_thresholds(strategy)
    material_thresholds = _material_thresholds(strategy)
    recommendation = _recommendation(strategy)
    warnings: list[str] = []
    blocking_reasons: list[str] = []
    qualified_material_count = 0
    allowed_account_count = 0
    account_pool_count = 0
    candidate_account_count = 0
    estimated_suggestion_count = 0
    raw_suggestion_count = 0
    blocked_candidate_count = 0
    top_blocking_reasons: dict[str, int] = {}

    if source_kind == "example":
        warnings.append("示例策略不会被自动建议生成器加载。")
    if not enabled:
        warnings.append("策略未启用，当前不会产出创建建议。")
    if not product_exists:
        blocking_reasons.append(f"产品配置不存在：{product_key or '未填写'}")
    if not mode_key:
        blocking_reasons.append("策略缺少 mode_key。")
    elif product_exists and not mode_path:
        blocking_reasons.append(f"创建模式配置不存在：{mode_key}")
    if not db_exists:
        blocking_reasons.append(f"本地数据库不存在。")
    if product_exists and not template_catalog:
        warnings.append("未找到匹配创建模板；后续创建计划预览需要手动指定模板。")

    if enabled and db_exists and product_exists and conn is not None:
        allowed_account_count = len(_allowed_accounts(project_root, product))
        account_pool_count = len(_account_pool_rows(conn, product_name=product_name))
        candidates = _candidate_accounts(
            conn,
            project_root=project_root,
            product=product,
            strategy=strategy,
            target_date=resolved_target_date,
        )
        candidate_account_count = len(candidates)
        qualified_materials, material_reasons = _qualified_materials(conn, product=product, strategy=strategy)
        qualified_material_count = len(qualified_materials)
        blocking_reasons.extend(reason for reason in material_reasons if _text(reason))
        for account in candidates:
            suggestion, blocked = _evaluate_account(
                conn,
                project_root=project_root,
                mode_dir=mode_dir,
                product=product,
                strategy=strategy,
                account=account,
                target_date=resolved_target_date,
                qualified_materials=qualified_materials,
                material_reasons=material_reasons,
            )
            if suggestion:
                raw_suggestion_count += 1
            if blocked:
                blocked_candidate_count += 1
                for reason in blocked.get("blocking_reasons") or []:
                    text = _text(reason)
                    if text:
                        top_blocking_reasons[text] = top_blocking_reasons.get(text, 0) + 1
        if candidate_account_count == 0:
            warnings.append("当前没有候选账户，策略暂时不会产出创建建议。")
        if qualified_material_count < int(material_thresholds["min_qualified_material_count"]):
            warnings.append("当前合格素材低于策略门槛，策略暂时不会产出创建建议。")
        if raw_suggestion_count == 0 and blocked_candidate_count > 0:
            warnings.append("当前候选账户均被策略门槛阻断。")
        max_suggestions = _strategy_max_suggestions(strategy)
        estimated_suggestion_count = min(raw_suggestion_count, max_suggestions) if max_suggestions > 0 else raw_suggestion_count
        if max_suggestions > 0 and raw_suggestion_count > max_suggestions:
            warnings.append(f"当前命中 {raw_suggestion_count} 个账户，已按策略上限收敛为 {max_suggestions} 条建议。")

    status = _status_from_review(
        enabled=enabled,
        blocking_reasons=blocking_reasons,
        warnings=warnings,
        suggestion_count=estimated_suggestion_count,
        blocked_candidate_count=blocked_candidate_count,
    )
    repairs = _repair_suggestions(
        enabled=enabled,
        source_kind=source_kind,
        product_key=product_key,
        mode_key=mode_key,
        mode_exists=bool(mode_path),
        db_exists=db_exists,
        product_exists=product_exists,
        candidate_account_count=candidate_account_count,
        qualified_material_count=qualified_material_count,
        material_thresholds=material_thresholds,
        blocked_candidate_count=blocked_candidate_count,
    )
    return {
        "strategy_id": _text(strategy.get("strategy_id")),
        "strategy_version": _text(strategy.get("strategy_version")),
        "enabled": enabled,
        "status": status,
        "source_kind": source_kind,
        "config_path": config_path,
        "product_key": product_key,
        "product_name": product_name,
        "product_exists": product_exists,
        "mode_key": mode_key,
        "mode_config_path": mode_path,
        "mode_exists": bool(mode_path),
        "template_catalog": template_catalog,
        "template_exists": bool(template_catalog),
        "account_thresholds": account_thresholds,
        "material_thresholds": material_thresholds,
        "recommendation": recommendation,
        "allowed_account_count": allowed_account_count,
        "account_pool_count": account_pool_count,
        "candidate_account_count": candidate_account_count,
        "qualified_material_count": qualified_material_count,
        "estimated_suggestion_count": estimated_suggestion_count,
        "raw_suggestion_count": raw_suggestion_count,
        "max_suggestions_per_run": _strategy_max_suggestions(strategy),
        "blocked_candidate_count": blocked_candidate_count,
        "top_blocking_reasons": top_blocking_reasons,
        "warnings": _unique_texts(warnings),
        "blocking_reasons": _unique_texts(blocking_reasons),
        "repair_suggestions": repairs,
    }


def build_create_suggestion_strategy_review(
    *,
    db_path: str | Path,
    project_root: str | Path = ".",
    products_dir: str | Path = "configs/products",
    mode_dir: str | Path = "configs/create-modes",
    template_dir: str | Path = "configs/create-templates",
    strategy_paths: list[str | Path] | None = None,
    strategy_dir: str | Path | None = "configs/create-suggestion-strategies",
    product_key: str = "",
    target_date: str = "",
    include_examples: bool = True,
) -> dict[str, Any]:
    requested_product_key = _text(product_key)
    paths = [Path(path) for path in strategy_paths or [] if _text(path)]
    if not paths and strategy_dir is not None:
        paths = _strategy_review_files(strategy_dir, include_examples=include_examples)
    strategies = _load_strategies(paths, None)
    products = load_product_configs(products_dir, product_key=requested_product_key)
    db_exists = Path(db_path).exists()
    resolved_target_date = target_date or "latest"
    reviews: list[dict[str, Any]] = []
    if db_exists:
        with _connect(db_path) as conn:
            resolved_target_date = _target_date(conn, target_date)
            for strategy in strategies:
                for product in _matching_products(strategy, products, requested_product_key=requested_product_key):
                    reviews.append(
                        _review_strategy_product(
                            conn=conn,
                            db_exists=True,
                            project_root=project_root,
                            mode_dir=mode_dir,
                            template_dir=template_dir,
                            strategy=strategy,
                            product=product,
                            resolved_target_date=resolved_target_date,
                        )
                    )
    else:
        for strategy in strategies:
            for product in _matching_products(strategy, products, requested_product_key=requested_product_key):
                reviews.append(
                    _review_strategy_product(
                        conn=None,
                        db_exists=False,
                        project_root=project_root,
                        mode_dir=mode_dir,
                        template_dir=template_dir,
                        strategy=strategy,
                        product=product,
                        resolved_target_date=resolved_target_date,
                    )
                )

    status_counts: dict[str, int] = {}
    for review in reviews:
        status = _text(review.get("status"))
        status_counts[status] = status_counts.get(status, 0) + 1
    blocking_reasons: list[str] = []
    if strategy_dir is not None and not paths:
        blocking_reasons.append(f"没有找到创建建议策略配置：{strategy_dir}")
    return {
        "ok": not blocking_reasons,
        "workflow": WORKFLOW,
        "phase": "readonly_strategy_review",
        "execution_enabled": False,
        "external_api_calls": 0,
        "summary": {
            "target_date": target_date or "latest",
            "resolved_target_date": resolved_target_date,
            "product_count": len(products),
            "strategy_count": len(strategies),
            "review_count": len(reviews),
            "enabled_strategy_count": sum(1 for review in reviews if bool(review.get("enabled"))),
            "healthy_strategy_count": status_counts.get("healthy", 0),
            "warning_strategy_count": status_counts.get("warning", 0),
            "blocked_strategy_count": status_counts.get("blocked", 0),
            "disabled_strategy_count": status_counts.get("disabled", 0),
            "estimated_candidate_account_count": sum(int(review.get("candidate_account_count") or 0) for review in reviews),
            "estimated_suggestion_count": sum(int(review.get("estimated_suggestion_count") or 0) for review in reviews),
            "blocked_candidate_count": sum(int(review.get("blocked_candidate_count") or 0) for review in reviews),
        },
        "source": {
            "db_path": str(db_path),
            "products_dir": str(products_dir),
            "mode_dir": str(mode_dir),
            "template_dir": str(template_dir),
            "strategy_dir": str(strategy_dir or ""),
            "strategy_paths": [str(path) for path in paths],
            "include_examples": include_examples,
        },
        "strategy_reviews": reviews,
        "guardrails": [
            "只读取本地 SQLite 数据和本地 JSON 策略配置。",
            "只评估策略健康和命中预估，不修改策略配置。",
            "不生成创建建议、不生成创建计划、不执行真实创建。",
        ],
        "blocking_reasons": blocking_reasons,
    }


def run_create_suggestion_strategy_review_request(request: dict[str, Any], *, runs_dir: str | Path) -> dict[str, Any]:
    result = build_create_suggestion_strategy_review(
        db_path=request.get("db_path") or request.get("database_path") or "data/roibang_v2.sqlite3",
        project_root=request.get("project_root") or ".",
        products_dir=request.get("products_dir") or "configs/products",
        mode_dir=request.get("mode_dir") or "configs/create-modes",
        template_dir=request.get("template_dir") or "configs/create-templates",
        strategy_paths=[_text(item) for item in request.get("strategy_paths", []) if _text(item)]
        if isinstance(request.get("strategy_paths"), list)
        else [_text(request.get("strategy_path") or request.get("strategy"))],
        strategy_dir=request.get("strategy_dir") or "configs/create-suggestion-strategies",
        product_key=_text(request.get("product_key")),
        target_date=_text(request.get("target_date")),
        include_examples=_bool(request.get("include_examples"), True),
    )
    result["artifact_path"] = str(write_run_artifact(runs_dir, WORKFLOW, result))
    return result
