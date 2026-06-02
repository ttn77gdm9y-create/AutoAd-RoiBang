from __future__ import annotations

import json
import sqlite3
from datetime import date
from datetime import timedelta
from pathlib import Path
from typing import Any

from roibang_v2.config import load_json
from roibang_v2.runs import write_run_artifact
from roibang_v2.workflows.product_automation_job import load_product_configs

WORKFLOW = "create_project_suggestions"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _number(value: Any, default: float = 0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    text = _text(value).lower()
    if not text:
        return default
    return text in {"1", "true", "yes", "y", "enabled", "enable", "是", "启用"}


def _rows(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [dict(item) for item in value if isinstance(item, dict)]
    return []


def _json_rows(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [dict(row) for row in value if isinstance(row, dict)]
    if isinstance(value, dict):
        for key in ["allowed_target_accounts", "accounts", "rows", "strategies"]:
            rows = value.get(key)
            if isinstance(rows, list):
                return [dict(row) for row in rows if isinstance(row, dict)]
    return []


def _connect(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ? LIMIT 1",
        (table,),
    ).fetchone()
    return row is not None


def _strategy_files(strategy_dir: Path) -> list[Path]:
    if not strategy_dir.exists():
        return []
    # Backend auto-load intentionally ignores example files. Example strategies are
    # templates and should be passed explicitly to the CLI or copied to .local.json.
    return sorted(strategy_dir.glob("*.local.json"))


def _load_strategies(strategy_paths: list[str | Path], strategy_dir: str | Path | None) -> list[dict[str, Any]]:
    paths: list[Path] = [Path(path) for path in strategy_paths if _text(path)]
    if not paths and strategy_dir is not None:
        paths.extend(_strategy_files(Path(strategy_dir)))
    strategies: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for path in paths:
        try:
            payload = load_json(path)
        except (FileNotFoundError, json.JSONDecodeError, ValueError):
            continue
        rows = _json_rows(payload)
        if not rows:
            rows = [payload]
        for row in rows:
            strategy = dict(row)
            strategy.setdefault("_config_path", str(path))
            strategy_id = _text(strategy.get("strategy_id")) or path.stem.replace(".local", "").replace(".example", "")
            strategy["strategy_id"] = strategy_id
            key = (strategy_id, _text(strategy.get("strategy_version")), _text(strategy.get("product_key")))
            if key in seen:
                continue
            seen.add(key)
            strategies.append(strategy)
    return strategies


def _mode_config_path(mode_dir: str | Path, *, product_key: str, mode_key: str) -> str:
    root = Path(mode_dir)
    candidates: list[Path] = []
    if product_key:
        candidates.extend(
            [
                root / product_key / f"{mode_key}.local.json",
                root / product_key / f"{mode_key}.json",
                root / product_key / f"{mode_key}.example.json",
            ]
        )
    candidates.extend([root / f"{mode_key}.local.json", root / f"{mode_key}.json", root / f"{mode_key}.example.json"])
    for path in candidates:
        if path.exists():
            return str(path)
    return ""


def _resolve_path(project_root: str | Path, path_text: str) -> Path:
    path = Path(path_text)
    if path.is_absolute():
        return path
    return Path(project_root) / path


def _allowed_accounts(project_root: str | Path, product: dict[str, Any]) -> dict[str, str]:
    path_text = _text(product.get("allowed_target_accounts_path"))
    if not path_text:
        return {}
    path = _resolve_path(project_root, path_text)
    try:
        payload = load_json(path)
    except (FileNotFoundError, json.JSONDecodeError, ValueError):
        return {}
    accounts: dict[str, str] = {}
    for row in _json_rows(payload):
        if not _bool(row.get("enable", row.get("enabled", True)), True):
            continue
        advertiser_id = _text(row.get("advertiser_id") or row.get("account_id"))
        account_name = _text(row.get("account_name") or row.get("name") or row.get("账户名"))
        if advertiser_id:
            accounts[advertiser_id] = account_name or advertiser_id
    return accounts


def _account_pool_rows(conn: sqlite3.Connection, *, product_name: str) -> list[dict[str, Any]]:
    if not _table_exists(conn, "account_pool"):
        return []
    rows = conn.execute(
        """
        SELECT advertiser_id, account_name, product, platform
        FROM account_pool
        WHERE advertiser_id <> ''
          AND (
            product = :product_name
            OR product LIKE :product_like
            OR account_name LIKE :product_like
          )
        ORDER BY advertiser_id
        """,
        {"product_name": product_name, "product_like": f"%{product_name}%"},
    ).fetchall()
    return [dict(row) for row in rows]


def _disabled_statuses(strategy: dict[str, Any]) -> set[str]:
    account = strategy.get("account") if isinstance(strategy.get("account"), dict) else {}
    raw = account.get("disabled_statuses")
    values = raw if isinstance(raw, list) else []
    defaults = [
        "PROJECT_STATUS_DISABLE",
        "PROJECT_STATUS_DISABLED",
        "PROJECT_STATUS_DELETE",
        "DISABLE",
        "DISABLED",
        "DELETED",
        "DELETE",
    ]
    return {_text(item).upper() for item in [*defaults, *values] if _text(item)}


def _active_project_count(conn: sqlite3.Connection, *, advertiser_id: str, strategy: dict[str, Any]) -> int:
    if not _table_exists(conn, "projects"):
        return 0
    disabled = _disabled_statuses(strategy)
    rows = conn.execute(
        """
        SELECT status
        FROM projects
        WHERE advertiser_id = ?
          AND project_id <> ''
        """,
        (advertiser_id,),
    ).fetchall()
    count = 0
    for row in rows:
        status = _text(row["status"]).upper()
        if status and status in disabled:
            continue
        count += 1
    return count


def _latest_create_operation_date(conn: sqlite3.Connection, *, advertiser_id: str) -> str:
    if not _table_exists(conn, "operation_logs"):
        return ""
    row = conn.execute(
        """
        SELECT MAX(substr(occurred_at, 1, 10)) AS latest_date
        FROM operation_logs
        WHERE advertiser_id = ?
          AND entity_type IN ('project', '项目')
          AND (
            action LIKE '%创建%'
            OR action LIKE '%create%'
            OR detail LIKE '%创建%'
            OR detail LIKE '%create%'
          )
        """,
        (advertiser_id,),
    ).fetchone()
    return _text(row["latest_date"] if row else "")


def _target_date(conn: sqlite3.Connection, configured: str) -> str:
    value = _text(configured)
    if value and value != "latest":
        return value
    for table, column in [("material_daily_metrics", "metric_date"), ("product_source_material_metric_rollups", "period_end")]:
        if not _table_exists(conn, table):
            continue
        row = conn.execute(f"SELECT MAX({column}) AS value FROM {table}").fetchone()
        text = _text(row["value"] if row else "")
        if text:
            return text[:10]
    return date.today().isoformat()


def _date_window_end(target_date: str) -> date | None:
    try:
        return date.fromisoformat(target_date[:10])
    except ValueError:
        return None


def _recent_account_metrics(
    conn: sqlite3.Connection,
    *,
    advertiser_id: str,
    target_date: str,
    window_days: int,
) -> dict[str, Any]:
    if not _table_exists(conn, "material_daily_metrics"):
        return {"stat_cost": 0.0, "convert_cnt": 0.0, "active_days": 0, "project_count": 0}
    end_date = _date_window_end(target_date)
    if end_date is None:
        return {"stat_cost": 0.0, "convert_cnt": 0.0, "active_days": 0, "project_count": 0}
    start_date = end_date - timedelta(days=max(window_days, 1) - 1)
    row = conn.execute(
        """
        SELECT
          COUNT(DISTINCT metric_date) AS active_days,
          COUNT(DISTINCT project_id) AS project_count,
          COALESCE(SUM(stat_cost), 0) AS stat_cost,
          COALESCE(SUM(convert_cnt), 0) AS convert_cnt
        FROM material_daily_metrics
        WHERE advertiser_id = ?
          AND metric_date >= ?
          AND metric_date <= ?
        """,
        (advertiser_id, start_date.isoformat(), end_date.isoformat()),
    ).fetchone()
    if row is None:
        return {"stat_cost": 0.0, "convert_cnt": 0.0, "active_days": 0, "project_count": 0}
    return {
        "stat_cost": round(float(row["stat_cost"] or 0), 4),
        "convert_cnt": round(float(row["convert_cnt"] or 0), 4),
        "active_days": int(row["active_days"] or 0),
        "project_count": int(row["project_count"] or 0),
    }


def _account_candidate_scope(strategy: dict[str, Any]) -> str:
    account = strategy.get("account") if isinstance(strategy.get("account"), dict) else {}
    return _text(account.get("candidate_scope")) or "allowed_and_account_pool"


def _strategy_max_suggestions(strategy: dict[str, Any]) -> int:
    limits = strategy.get("limits") if isinstance(strategy.get("limits"), dict) else {}
    return _int(limits.get("max_suggestions_per_run"), 0)


def _qualified_materials(
    conn: sqlite3.Connection,
    *,
    product: dict[str, Any],
    strategy: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[str]]:
    if not _table_exists(conn, "product_source_material_metric_rollups"):
        return [], ["missing product_source_material_metric_rollups table"]
    materials_cfg = strategy.get("materials") if isinstance(strategy.get("materials"), dict) else {}
    product_name = _text(product.get("product") or product.get("product_name"))
    source_advertiser_id = _text(product.get("source_advertiser_id"))
    window_key = _text(materials_cfg.get("window_key")) or "last_7d"
    material_type = _text(materials_cfg.get("material_type")) or "video"
    min_stat_cost = _number(materials_cfg.get("min_stat_cost"), 0)
    min_convert_cnt = _number(materials_cfg.get("min_convert_cnt"), 0)
    min_roi_1day = _number(materials_cfg.get("min_roi_1day"), 0)
    params = {
        "product": product_name,
        "source_advertiser_id": source_advertiser_id,
        "window_key": window_key,
        "material_type": material_type,
        "min_stat_cost": min_stat_cost,
        "min_convert_cnt": min_convert_cnt,
        "min_roi_1day": min_roi_1day,
    }
    rows = conn.execute(
        """
        SELECT
          material_id,
          source_video_id,
          name,
          stat_cost,
          convert_cnt,
          roi_1day_cost_weighted,
          roi_7days_cost_weighted,
          period_start,
          period_end,
          window_key
        FROM product_source_material_metric_rollups
        WHERE product = :product
          AND source_advertiser_id = :source_advertiser_id
          AND window_key = :window_key
          AND material_type = :material_type
          AND stat_cost >= :min_stat_cost
          AND convert_cnt >= :min_convert_cnt
          AND roi_1day_cost_weighted >= :min_roi_1day
          AND COALESCE(source_video_id, '') <> ''
        ORDER BY stat_cost DESC, convert_cnt DESC, material_id
        LIMIT 200
        """,
        params,
    ).fetchall()
    return [dict(row) for row in rows], []


def _strategy_matches_product(strategy: dict[str, Any], product: dict[str, Any]) -> bool:
    product_key = _text(product.get("product_key"))
    strategy_product_key = _text(strategy.get("product_key"))
    return not strategy_product_key or strategy_product_key == product_key


def _candidate_accounts(
    conn: sqlite3.Connection,
    *,
    project_root: str | Path,
    product: dict[str, Any],
    strategy: dict[str, Any],
    target_date: str = "",
    target_account_ids: list[str] | None = None,
    target_account_names: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    product_name = _text(product.get("product") or product.get("product_name"))
    account_cfg = strategy.get("account") if isinstance(strategy.get("account"), dict) else {}
    candidate_scope = _account_candidate_scope(strategy)
    allowed = _allowed_accounts(project_root, product)
    candidates: dict[str, dict[str, Any]] = {}
    for account_id, account_name in allowed.items():
        candidates[account_id] = {
            "advertiser_id": account_id,
            "account_name": account_name,
            "in_allowed_accounts": True,
            "source": "allowed_target_accounts",
        }
    for row in _account_pool_rows(conn, product_name=product_name):
        advertiser_id = _text(row.get("advertiser_id"))
        if not advertiser_id:
            continue
        item = candidates.setdefault(
            advertiser_id,
            {
                "advertiser_id": advertiser_id,
                "account_name": _text(row.get("account_name")) or advertiser_id,
                "in_allowed_accounts": False,
                "source": "account_pool",
            },
        )
        if _text(row.get("account_name")):
            item["account_name"] = _text(row.get("account_name"))
        item["product"] = _text(row.get("product"))
        item["platform"] = _text(row.get("platform"))
    if target_account_names:
        for advertiser_id, account_name in target_account_names.items():
            account_id = _text(advertiser_id)
            if account_id and _text(account_name) and account_id in candidates:
                candidates[account_id]["account_name"] = _text(account_name)
    rows = list(candidates.values())
    if target_account_ids is not None:
        target_ids = {_text(item) for item in target_account_ids if _text(item)}
        rows = [row for row in rows if _text(row.get("advertiser_id")) in target_ids]
    if candidate_scope == "allowed_accounts_with_recent_spend":
        window_days = _int(account_cfg.get("recent_window_days"), 1)
        min_recent_stat_cost = _number(account_cfg.get("min_recent_stat_cost"), 0)
        min_recent_convert_cnt = _number(account_cfg.get("min_recent_convert_cnt"), 0)
        filtered: list[dict[str, Any]] = []
        for row in rows:
            if not bool(row.get("in_allowed_accounts")):
                continue
            metrics = _recent_account_metrics(
                conn,
                advertiser_id=_text(row.get("advertiser_id")),
                target_date=target_date,
                window_days=window_days,
            )
            row["recent_metrics"] = metrics
            row["candidate_scope"] = candidate_scope
            if metrics["stat_cost"] < min_recent_stat_cost:
                continue
            if metrics["convert_cnt"] < min_recent_convert_cnt:
                continue
            filtered.append(row)
        return sorted(
            filtered,
            key=lambda item: (
                -_number(item.get("recent_metrics", {}).get("stat_cost") if isinstance(item.get("recent_metrics"), dict) else 0),
                _text(item.get("advertiser_id")),
            ),
        )
    return sorted(rows, key=lambda item: _text(item.get("advertiser_id")))


def _blocked_suggestion(
    *,
    target_date: str,
    product: dict[str, Any],
    strategy: dict[str, Any],
    account: dict[str, Any],
    reasons: list[str],
    evidence: dict[str, Any],
) -> dict[str, Any]:
    suggestion = _suggestion(
        target_date=target_date,
        product=product,
        strategy=strategy,
        account=account,
        evidence=evidence,
        reason="创建项目建议被阻断，需要先处理阻断原因。",
    )
    suggestion["blocking_reasons"] = reasons
    suggestion["status"] = "blocked"
    return suggestion


def _suggestion(
    *,
    target_date: str,
    product: dict[str, Any],
    strategy: dict[str, Any],
    account: dict[str, Any],
    evidence: dict[str, Any],
    reason: str,
) -> dict[str, Any]:
    product_key = _text(product.get("product_key"))
    product_name = _text(product.get("product") or product.get("product_name"))
    advertiser_id = _text(account.get("advertiser_id"))
    mode_key = _text(strategy.get("mode_key"))
    strategy_id = _text(strategy.get("strategy_id"))
    strategy_version = _text(strategy.get("strategy_version"))
    return {
        "suggestion_id": f"{target_date}:account:{advertiser_id}:suggest_create_project:{mode_key}",
        "suggested_action": "suggest_create_project",
        "suggestion_type": "suggest_create_project",
        "entity_type": "account",
        "target_date": target_date,
        "product_key": product_key,
        "product_name": product_name,
        "product": product_name,
        "advertiser_id": advertiser_id,
        "account_name": _text(account.get("account_name")) or advertiser_id,
        "mode_key": mode_key,
        "recommended_mode_key": mode_key,
        "strategy_id": strategy_id,
        "strategy_version": strategy_version,
        "rule_id": strategy_id,
        "reason": reason,
        "metrics": {
            "project_count": evidence.get("current_project_count", 0),
            "project_capacity": evidence.get("project_capacity", 0),
            "qualified_material_count": evidence.get("qualified_material_count", 0),
        },
        "thresholds": evidence.get("thresholds", {}),
        "evidence": evidence,
        "risk_warnings": [],
        "blocking_reasons": [],
        "human_review_required": True,
        "execution_enabled": False,
        "execution": {"enabled": False, "status": "suggestion_only"},
    }


def _evaluate_account(
    conn: sqlite3.Connection,
    *,
    project_root: str | Path,
    mode_dir: str | Path,
    product: dict[str, Any],
    strategy: dict[str, Any],
    account: dict[str, Any],
    target_date: str,
    qualified_materials: list[dict[str, Any]],
    material_reasons: list[str],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    account_cfg = strategy.get("account") if isinstance(strategy.get("account"), dict) else {}
    materials_cfg = strategy.get("materials") if isinstance(strategy.get("materials"), dict) else {}
    recommendation = strategy.get("recommendation") if isinstance(strategy.get("recommendation"), dict) else {}
    mode_key = _text(strategy.get("mode_key"))
    mode_path = _mode_config_path(mode_dir, product_key=_text(product.get("product_key")), mode_key=mode_key)
    active_project_count = _active_project_count(conn, advertiser_id=_text(account.get("advertiser_id")), strategy=strategy)
    max_active_projects = _int(account_cfg.get("max_active_projects"), 20)
    project_capacity = max(max_active_projects - active_project_count, 0)
    cooldown_days = _int(account_cfg.get("cooldown_days_after_create"), 0)
    latest_create_date = _latest_create_operation_date(conn, advertiser_id=_text(account.get("advertiser_id")))
    min_material_count = _int(materials_cfg.get("min_qualified_material_count"), 1)
    evidence = {
        "product_key": _text(product.get("product_key")),
        "product": _text(product.get("product") or product.get("product_name")),
        "account_id": _text(account.get("advertiser_id")),
        "account_name": _text(account.get("account_name")),
        "in_allowed_accounts": bool(account.get("in_allowed_accounts")),
        "candidate_scope": _account_candidate_scope(strategy),
        "recent_metrics": account.get("recent_metrics") if isinstance(account.get("recent_metrics"), dict) else {},
        "current_project_count": active_project_count,
        "max_active_projects": max_active_projects,
        "project_capacity": project_capacity,
        "latest_create_operation_date": latest_create_date,
        "mode_key": mode_key,
        "mode_config_path": mode_path,
        "qualified_material_count": len(qualified_materials),
        "top_materials": [
            {
                "material_id": _text(row.get("material_id")),
                "source_video_id": _text(row.get("source_video_id")),
                "name": _text(row.get("name")),
                "stat_cost": _number(row.get("stat_cost")),
                "convert_cnt": _number(row.get("convert_cnt")),
                "roi_1day": _number(row.get("roi_1day_cost_weighted")),
            }
            for row in qualified_materials[:10]
        ],
        "recommended_request": {
            "mode_key": mode_key,
            "project_count": _int(recommendation.get("project_count"), 1),
            "units_per_project": _int(recommendation.get("units_per_project"), 1),
            "daily_budget": _int(recommendation.get("daily_budget"), 0),
        },
        "thresholds": {
            "candidate_scope": _account_candidate_scope(strategy),
            "recent_window_days": _int(account_cfg.get("recent_window_days"), 1),
            "min_recent_stat_cost": _number(account_cfg.get("min_recent_stat_cost"), 0),
            "min_recent_convert_cnt": _number(account_cfg.get("min_recent_convert_cnt"), 0),
            "max_active_projects": max_active_projects,
            "cooldown_days_after_create": cooldown_days,
            "min_qualified_material_count": min_material_count,
            "window_key": _text(materials_cfg.get("window_key")) or "last_7d",
            "min_stat_cost": _number(materials_cfg.get("min_stat_cost"), 0),
            "min_convert_cnt": _number(materials_cfg.get("min_convert_cnt"), 0),
            "min_roi_1day": _number(materials_cfg.get("min_roi_1day"), 0),
        },
    }
    reasons = list(material_reasons)
    if _bool(account_cfg.get("require_allowed_account"), True) and not bool(account.get("in_allowed_accounts")):
        reasons.append("账户不在允许创建名单中")
    if not mode_key:
        reasons.append("策略缺少 mode_key")
    elif not mode_path:
        reasons.append(f"创建模式不存在：{mode_key}")
    if project_capacity <= 0:
        reasons.append(f"账户当前项目数 {active_project_count} 已达到策略上限 {max_active_projects}")
    if len(qualified_materials) < min_material_count:
        reasons.append(f"合格素材 {len(qualified_materials)} 个，低于策略要求 {min_material_count} 个")
    if cooldown_days > 0 and latest_create_date:
        try:
            latest_date = date.fromisoformat(latest_create_date[:10])
            current_date = date.fromisoformat(target_date[:10])
        except ValueError:
            latest_date = None
            current_date = None
        if latest_date and current_date and latest_date + timedelta(days=cooldown_days) > current_date:
            reasons.append(f"最近创建操作日期 {latest_create_date} 未超过 {cooldown_days} 天冷却期")

    if reasons:
        return None, _blocked_suggestion(
            target_date=target_date,
            product=product,
            strategy=strategy,
            account=account,
            reasons=reasons,
            evidence=evidence,
        )

    reason = (
        f"账户在允许创建名单内，当前项目数 {active_project_count}/{max_active_projects} 未满，"
        f"合格素材 {len(qualified_materials)} 个达到策略要求，建议进入创建计划人工预览。"
    )
    return _suggestion(
        target_date=target_date,
        product=product,
        strategy=strategy,
        account=account,
        evidence=evidence,
        reason=reason,
    ), None


def build_create_project_suggestions(
    *,
    db_path: str | Path,
    project_root: str | Path = ".",
    products_dir: str | Path = "configs/products",
    mode_dir: str | Path = "configs/create-modes",
    strategy_paths: list[str | Path] | None = None,
    strategy_dir: str | Path | None = "configs/create-suggestion-strategies",
    product_key: str = "",
    target_date: str = "",
    target_account_ids: list[str] | None = None,
    target_account_names: dict[str, str] | None = None,
) -> dict[str, Any]:
    strategies = _load_strategies(strategy_paths or [], strategy_dir)
    enabled_strategies = [strategy for strategy in strategies if _bool(strategy.get("enabled"), False)]
    products = load_product_configs(products_dir, product_key=product_key)
    suggestions: list[dict[str, Any]] = []
    blocked_suggestions: list[dict[str, Any]] = []
    product_summaries: list[dict[str, Any]] = []
    if not Path(db_path).exists():
        return {
            "ok": False,
            "workflow": WORKFLOW,
            "phase": "readonly_rule_suggestions",
            "execution_enabled": False,
            "external_api_calls": 0,
            "summary": {"product_count": len(products), "strategy_count": len(enabled_strategies), "suggestion_count": 0},
            "blocking_reasons": [f"database not found: {db_path}"],
            "suggestions": [],
            "blocked_suggestions": [],
        }
    resolved_target_date = target_date
    with _connect(db_path) as conn:
        resolved_target_date = _target_date(conn, target_date)
        for product in products:
            product_key_text = _text(product.get("product_key"))
            product_name = _text(product.get("product") or product.get("product_name"))
            product_strategy_count = 0
            for strategy in enabled_strategies:
                if not _strategy_matches_product(strategy, product):
                    continue
                product_strategy_count += 1
                qualified, material_reasons = _qualified_materials(conn, product=product, strategy=strategy)
                accounts = _candidate_accounts(
                    conn,
                    project_root=project_root,
                    product=product,
                    strategy=strategy,
                    target_date=resolved_target_date,
                    target_account_ids=target_account_ids,
                    target_account_names=target_account_names,
                )
                max_suggestions = _strategy_max_suggestions(strategy)
                strategy_suggestion_count = 0
                for account in accounts:
                    suggestion, blocked = _evaluate_account(
                        conn,
                        project_root=project_root,
                        mode_dir=mode_dir,
                        product=product,
                        strategy=strategy,
                        account=account,
                        target_date=resolved_target_date,
                        qualified_materials=qualified,
                        material_reasons=material_reasons,
                    )
                    if suggestion:
                        if max_suggestions > 0 and strategy_suggestion_count >= max_suggestions:
                            continue
                        suggestions.append(suggestion)
                        strategy_suggestion_count += 1
                    if blocked:
                        blocked_suggestions.append(blocked)
            product_summaries.append(
                {
                    "product_key": product_key_text,
                    "product": product_name,
                    "strategy_count": product_strategy_count,
                    "suggestion_count": len([item for item in suggestions if _text(item.get("product_key")) == product_key_text]),
                    "blocked_suggestion_count": len(
                        [item for item in blocked_suggestions if _text(item.get("product_key")) == product_key_text]
                    ),
                }
            )
    action_counts: dict[str, int] = {}
    for suggestion in suggestions:
        action = _text(suggestion.get("suggested_action"))
        action_counts[action] = action_counts.get(action, 0) + 1
    return {
        "ok": True,
        "workflow": WORKFLOW,
        "phase": "readonly_rule_suggestions",
        "execution_enabled": False,
        "external_api_calls": 0,
        "summary": {
            "target_date": target_date or "latest",
            "resolved_target_date": resolved_target_date,
            "product_count": len(products),
            "strategy_count": len(enabled_strategies),
            "suggestion_count": len(suggestions),
            "blocked_suggestion_count": len(blocked_suggestions),
            "action_counts": action_counts,
            "realtime_target_account_count": len(target_account_ids) if target_account_ids is not None else None,
        },
        "source": {
            "workflow": WORKFLOW,
            "db_path": str(db_path),
            "strategy_dir": str(strategy_dir or ""),
            "strategy_paths": [str(path) for path in strategy_paths or []],
        },
        "product_summaries": product_summaries,
        "suggestions": suggestions,
        "blocked_suggestions": blocked_suggestions,
        "guardrails": [
            "只读取本地 SQLite 数据和本地 JSON 策略配置。",
            "只生成创建项目建议，不生成创建计划，不执行真实创建。",
            "创建建议后续必须进入创建计划页预览和人工确认。",
        ],
        "blocking_reasons": [],
    }


def run_create_project_suggestions_request(request: dict[str, Any], *, runs_dir: str | Path) -> dict[str, Any]:
    raw_target_account_ids = request.get("target_account_ids")
    result = build_create_project_suggestions(
        db_path=request.get("db_path") or request.get("database_path") or "data/roibang_v2.sqlite3",
        project_root=request.get("project_root") or ".",
        products_dir=request.get("products_dir") or "configs/products",
        mode_dir=request.get("mode_dir") or "configs/create-modes",
        strategy_paths=[_text(item) for item in request.get("strategy_paths", []) if _text(item)]
        if isinstance(request.get("strategy_paths"), list)
        else [_text(request.get("strategy_path") or request.get("strategy"))],
        strategy_dir=request.get("strategy_dir") or "configs/create-suggestion-strategies",
        product_key=_text(request.get("product_key")),
        target_date=_text(request.get("target_date")),
        target_account_ids=[_text(item) for item in raw_target_account_ids if _text(item)]
        if isinstance(raw_target_account_ids, list)
        else None,
        target_account_names={
            _text(key): _text(value)
            for key, value in (request.get("target_account_names") or {}).items()
            if _text(key) and _text(value)
        }
        if isinstance(request.get("target_account_names"), dict)
        else None,
    )
    result["artifact_path"] = str(write_run_artifact(runs_dir, WORKFLOW, result))
    return result
