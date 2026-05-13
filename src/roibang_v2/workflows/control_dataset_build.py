from __future__ import annotations

import json
import sqlite3
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from roibang_v2.fetch.openapi_executor import Transport
from roibang_v2.fetch.openapi_executor import build_snapshots_from_execution
from roibang_v2.fetch.openapi_executor import execute_openapi_readonly_plan
from roibang_v2.fetch.openapi_http import build_http_transport
from roibang_v2.fetch.openapi_readonly import build_readonly_request
from roibang_v2.reports.snapshot import import_report_snapshot_file
from roibang_v2.runs import utc_timestamp
from roibang_v2.runs import write_run_artifact


def _connect(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _date_from_text(value: str) -> date:
    text = str(value or "").strip()
    if len(text) < 10:
        raise ValueError(f"invalid date value: {value!r}")
    return date.fromisoformat(text[:10])


def _date_list(start: str, end: str) -> list[str]:
    start_date = _date_from_text(start)
    end_date = _date_from_text(end)
    if start_date > end_date:
        raise ValueError(f"start date {start} is after end date {end}")
    days = (end_date - start_date).days + 1
    return [(start_date + timedelta(days=offset)).isoformat() for offset in range(days)]


def _configured_operation_log_date_bounds(date_range: Any) -> tuple[str, str, str] | None:
    if not isinstance(date_range, dict):
        return None
    mode = str(date_range.get("mode") or "").strip()
    if mode == "yesterday":
        today = _date_from_text(str(date_range.get("today") or date.today().isoformat()))
        target = today - timedelta(days=1)
        return target.isoformat(), target.isoformat(), "yesterday"
    target_date = str(date_range.get("target_date") or date_range.get("date") or "").strip()
    if mode in {"target_date", "single_date"} or target_date:
        target = _date_from_text(target_date)
        return target.isoformat(), target.isoformat(), "target_date"
    start = str(date_range.get("start") or "").strip()
    end = str(date_range.get("end") or "").strip()
    if mode in {"range", "fixed"} or start or end:
        if not start or not end:
            raise ValueError("date_range.start and date_range.end are required for range mode")
        start_date = _date_from_text(start)
        end_date = _date_from_text(end)
        if start_date > end_date:
            raise ValueError(f"date_range.start {start} is after date_range.end {end}")
        return start_date.isoformat(), end_date.isoformat(), "range"
    if mode:
        raise ValueError(f"unsupported operation log date_range.mode: {mode}")
    return None


def _metric_scope_filter(product_keyword: str = "", *, alias: str = "") -> tuple[str, dict[str, Any]]:
    prefix = f"{alias}." if alias else ""
    advertiser_expr = f"{prefix}advertiser_id"
    clauses = [f"{advertiser_expr} <> ''"]
    params: dict[str, Any] = {}
    keyword = str(product_keyword or "").strip()
    if keyword:
        clauses.append(
            """
            EXISTS (
              SELECT 1
              FROM account_pool ap
              WHERE ap.advertiser_id = {advertiser_expr}
                AND (
                  ap.account_name LIKE :product_keyword_like
                  OR ap.product = :product_keyword_exact
                  OR ap.product LIKE :product_keyword_like
                )
            )
            """.format(advertiser_expr=advertiser_expr)
        )
        params["product_keyword_like"] = f"%{keyword}%"
        params["product_keyword_exact"] = keyword
    return " AND ".join(clauses), params


def _metric_summary(conn: sqlite3.Connection, *, product_keyword: str = "") -> dict[str, Any]:
    where_sql, params = _metric_scope_filter(product_keyword, alias="mdm")
    row = conn.execute(
        f"""
        SELECT
          MIN(mdm.metric_date) AS start_date,
          MAX(mdm.metric_date) AS end_date,
          COUNT(*) AS metric_row_count
        FROM material_daily_metrics mdm
        WHERE {where_sql}
        """,
        params,
    ).fetchone()
    if not row or not row["start_date"] or not row["end_date"]:
        raise ValueError("material_daily_metrics has no account/date data for control dataset")
    start = str(row["start_date"])
    end = str(row["end_date"])
    return {
        "date_range": {
            "start": start,
            "end": end,
            "days": len(_date_list(start, end)),
        },
        "metric_row_count": int(row["metric_row_count"] or 0),
    }


def discover_control_metric_scope(db_path: str | Path, *, product_keyword: str = "") -> dict[str, Any]:
    keyword = str(product_keyword or "").strip()
    with _connect(db_path) as conn:
        metric_summary = _metric_summary(conn, product_keyword=keyword)
        date_range = metric_summary["date_range"]
        where_sql, params = _metric_scope_filter(keyword, alias="mdm")
        accounts = [
            {
                "advertiser_id": str(row["advertiser_id"]),
                "account_name": str(row["account_name"] or ""),
                "product": str(row["product"] or ""),
                "platform": str(row["platform"] or "WECHAT_GAME"),
            }
            for row in conn.execute(
                f"""
                SELECT DISTINCT
                  mdm.advertiser_id,
                  ap.account_name,
                  ap.product,
                  ap.platform
                FROM material_daily_metrics mdm
                LEFT JOIN account_pool ap
                  ON ap.advertiser_id = mdm.advertiser_id
                WHERE {where_sql}
                ORDER BY mdm.advertiser_id
                """,
                params,
            )
        ]

    return {
        "account_source": "material_daily_metrics",
        "date_range_source": "material_daily_metrics",
        "filter": {"product_keyword": keyword} if keyword else {},
        "date_range": date_range,
        "account_count": len(accounts),
        "metric_row_count": metric_summary["metric_row_count"],
        "accounts": accounts,
    }


def _spent_account_dates(
    db_path: str | Path,
    *,
    product_keyword: str = "",
    date_range: dict[str, Any] | None = None,
    window_days: int | None = None,
) -> list[dict[str, Any]]:
    keyword = str(product_keyword or "").strip()
    with _connect(db_path) as conn:
        where_sql, params = _metric_scope_filter(keyword, alias="mdm")
        configured_bounds = _configured_operation_log_date_bounds(date_range)
        if configured_bounds is not None:
            start_date, end_date, _mode = configured_bounds
            where_sql = f"{where_sql} AND mdm.metric_date BETWEEN :sync_start_date AND :sync_end_date"
            params = {
                **params,
                "sync_start_date": start_date,
                "sync_end_date": end_date,
            }
        elif window_days is not None:
            if window_days < 1:
                raise ValueError("window_days must be >= 1")
            latest_row = conn.execute(
                f"""
                SELECT MAX(mdm.metric_date) AS latest_date
                FROM material_daily_metrics mdm
                WHERE {where_sql}
                """,
                params,
            ).fetchone()
            latest = str(latest_row["latest_date"] or "") if latest_row else ""
            if latest:
                end_date = _date_from_text(latest)
                start_date = end_date - timedelta(days=window_days - 1)
                where_sql = f"{where_sql} AND mdm.metric_date BETWEEN :window_start_date AND :window_end_date"
                params = {
                    **params,
                    "window_start_date": start_date.isoformat(),
                    "window_end_date": end_date.isoformat(),
                }
        rows = conn.execute(
            f"""
            SELECT
              mdm.metric_date,
              mdm.advertiser_id,
              ap.account_name,
              ap.product,
              ap.platform,
              SUM(mdm.stat_cost) AS stat_cost
            FROM material_daily_metrics mdm
            LEFT JOIN account_pool ap
              ON ap.advertiser_id = mdm.advertiser_id
            WHERE {where_sql}
            GROUP BY mdm.metric_date, mdm.advertiser_id, ap.account_name, ap.product, ap.platform
            HAVING SUM(mdm.stat_cost) > 0
            ORDER BY mdm.metric_date, mdm.advertiser_id
            """,
            params,
        ).fetchall()
    return [
        {
            "metric_date": str(row["metric_date"]),
            "account": {
                "advertiser_id": str(row["advertiser_id"]),
                "account_name": str(row["account_name"] or ""),
                "product": str(row["product"] or keyword),
                "platform": str(row["platform"] or "WECHAT_GAME"),
            },
            "stat_cost": float(row["stat_cost"] or 0),
        }
        for row in rows
    ]


def _operation_log_plan_from_spent_account_dates(
    *,
    account_dates: list[dict[str, Any]],
    page_size: int,
) -> dict[str, Any]:
    requests: list[dict[str, Any]] = []
    for item in account_dates:
        target_date = str(item["metric_date"])
        account = dict(item["account"])
        advertiser_id = str(account["advertiser_id"])
        requests.append(
            {
                "date": target_date,
                "account": account,
                **build_readonly_request(
                    "operation_log_search",
                    {
                        "advertiser_id": advertiser_id,
                        "start_time": f"{target_date} 00:00:00",
                        "end_time": f"{target_date} 23:59:59",
                        "page": 1,
                        "page_size": min(page_size, 20),
                    },
                ),
            }
        )
    dates = sorted({str(item["metric_date"]) for item in account_dates})
    accounts = sorted({str(item["account"]["advertiser_id"]) for item in account_dates})
    return {
        "ok": True,
        "workflow": "openapi_readonly_plan",
        "phase": "phase1",
        "execution_enabled": False,
        "external_api_calls": 0,
        "summary": {
            "account_count": len(accounts),
            "date_count": len(dates),
            "account_date_count": len(account_dates),
            "endpoint_count": 1,
            "report_preset_count": 0,
            "planned_request_count": len(requests),
        },
        "endpoints": ["operation_log_search"],
        "report_presets": [],
        "requests": requests,
    }


def build_operation_log_sync_plan_from_metrics(
    db_path: str | Path,
    *,
    page_size: int = 20,
    product_keyword: str = "",
    date_range: dict[str, Any] | None = None,
    window_days: int | None = None,
) -> dict[str, Any]:
    scope = discover_control_metric_scope(db_path, product_keyword=product_keyword)
    account_dates = _spent_account_dates(
        db_path,
        product_keyword=product_keyword,
        date_range=date_range,
        window_days=window_days,
    )
    plan = _operation_log_plan_from_spent_account_dates(account_dates=account_dates, page_size=page_size)
    dates = sorted({str(item["metric_date"]) for item in account_dates})
    configured_bounds = _configured_operation_log_date_bounds(date_range)
    if configured_bounds is not None:
        start_date, end_date, range_mode = configured_bounds
        selected_date_range = {
            "start": start_date,
            "end": end_date,
            "days": len(_date_list(start_date, end_date)),
        }
    else:
        range_mode = "latest_metric_window" if window_days is not None else "all_metric_dates"
        selected_date_range = {
            "start": dates[0],
            "end": dates[-1],
            "days": len(_date_list(dates[0], dates[-1])),
        } if dates else {"start": "", "end": "", "days": 0}
    return {
        "ok": True,
        "workflow": "control_dataset_build",
        "phase": "control_analysis",
        "execution_enabled": False,
        "external_api_calls": 0,
        "summary": {
            "account_source": scope["account_source"],
            "account_date_source": "material_daily_metrics_spent_account_dates",
            "date_range_source": scope["date_range_source"],
            "account_count": plan["summary"]["account_count"],
            "active_date_count": plan["summary"]["date_count"],
            "account_date_count": plan["summary"]["account_date_count"],
            "filter": scope["filter"],
            "date_range": selected_date_range,
            "metric_scope_date_range": {
                "start": scope["date_range"]["start"],
                "end": scope["date_range"]["end"],
                "days": scope["date_range"]["days"],
            },
            "date_range_mode": range_mode,
            "sync_window_days": int(window_days or 0),
            "metric_row_count": scope["metric_row_count"],
            "planned_request_count": plan["summary"]["planned_request_count"],
            "note": "readonly_plan_only; requests are built only for spent account-date pairs",
        },
        "plan": plan,
    }


def _operation_log_execution_config(request: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    openapi_http = request.get("openapi_http") if isinstance(request.get("openapi_http"), dict) else {}
    execution = request.get("execution") if isinstance(request.get("execution"), dict) else {}
    return dict(openapi_http), dict(execution)


def _require_operation_log_readonly_enabled(
    *,
    openapi_http: dict[str, Any],
    execution: dict[str, Any],
    transport: Transport | None,
) -> None:
    if transport is not None:
        return
    if str(execution.get("status") or "") != "execute":
        raise RuntimeError("operation log history sync requires execution.status=execute")
    if not bool(execution.get("external_api_enabled", False)):
        raise RuntimeError("operation log history sync requires execution.external_api_enabled=true")
    if not bool(openapi_http.get("enabled", False)):
        raise RuntimeError("operation log history sync requires openapi_http.enabled=true")


def _retry_options(openapi_http: dict[str, Any]) -> dict[str, Any]:
    return {
        "retry_api_codes": list(openapi_http.get("retry_api_codes") or []),
        "max_api_retries": int(openapi_http.get("max_api_retries", openapi_http.get("max_retries") or 0) or 0),
        "retry_sleep_seconds": float(openapi_http.get("retry_sleep_seconds") or 1),
    }


def _write_snapshot_files(
    snapshots: list[dict[str, Any]],
    *,
    runs_dir: str | Path,
) -> list[str]:
    target_dir = Path(runs_dir) / "control_operation_log_history_snapshots"
    target_dir.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []
    for snapshot in snapshots:
        period = snapshot.get("period") if isinstance(snapshot.get("period"), dict) else {}
        date_key = str(period.get("start") or "unknown")
        path = target_dir / f"{date_key}.json"
        path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        paths.append(str(path))
    return paths


def _import_snapshot_files(paths: list[str], *, db_path: str | Path) -> dict[str, int]:
    result = {
        "snapshot_count": 0,
        "operation_logs_imported": 0,
        "projects_imported": 0,
        "promotions_imported": 0,
    }
    for path in paths:
        imported = import_report_snapshot_file(path, db_path=db_path)
        result["snapshot_count"] += 1
        result["operation_logs_imported"] += int(imported.get("operation_logs_imported") or 0)
        result["projects_imported"] += int(imported.get("projects_imported") or 0)
        result["promotions_imported"] += int(imported.get("promotions_imported") or 0)
    return result


def _write_dataset_rows_jsonl(
    rows: list[dict[str, Any]],
    *,
    runs_dir: str | Path,
    workflow: str,
) -> str:
    target_dir = Path(runs_dir) / f"{workflow}_rows"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{utc_timestamp()}.jsonl"
    target.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    return str(target)


def _write_plan_requests_jsonl(
    operation_log_plan: dict[str, Any],
    *,
    runs_dir: str | Path,
    workflow: str,
) -> str:
    plan = operation_log_plan.get("plan") if isinstance(operation_log_plan.get("plan"), dict) else {}
    requests = plan.get("requests") if isinstance(plan.get("requests"), list) else []
    target_dir = Path(runs_dir) / f"{workflow}_requests"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{utc_timestamp()}.jsonl"
    target.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in requests),
        encoding="utf-8",
    )
    return str(target)


def _compact_dataset(dataset: dict[str, Any], *, row_sample_limit: int) -> dict[str, Any]:
    rows = dataset.get("rows") if isinstance(dataset.get("rows"), list) else []
    limit = max(int(row_sample_limit), 0)
    return {
        **dataset,
        "rows": rows[:limit],
        "row_sample_count": min(len(rows), limit),
        "rows_truncated": len(rows) > limit,
    }


def _compact_operation_log_plan(operation_log_plan: dict[str, Any], *, request_sample_limit: int) -> dict[str, Any]:
    plan = operation_log_plan.get("plan") if isinstance(operation_log_plan.get("plan"), dict) else {}
    requests = plan.get("requests") if isinstance(plan.get("requests"), list) else []
    limit = max(int(request_sample_limit), 0)
    return {
        **operation_log_plan,
        "plan": {
            "ok": bool(plan.get("ok", True)),
            "workflow": str(plan.get("workflow") or "openapi_readonly_plan"),
            "phase": str(plan.get("phase") or "phase1"),
            "execution_enabled": False,
            "external_api_calls": 0,
            "summary": plan.get("summary") if isinstance(plan.get("summary"), dict) else {},
            "endpoints": list(plan.get("endpoints") or []),
            "report_presets": list(plan.get("report_presets") or []),
        },
        "request_sample": requests[:limit],
        "request_sample_count": min(len(requests), limit),
        "requests_truncated": len(requests) > limit,
    }


def run_control_operation_log_history_sync_request(
    request: dict[str, Any] | None,
    *,
    db_path: str | Path,
    runs_dir: str | Path,
    transport: Transport | None = None,
    http_opener=None,
    http_sleeper=None,
) -> dict[str, Any]:
    cfg = dict(request or {})
    page_size = int(cfg.get("operation_log_page_size") or 20)
    window_days = int(cfg.get("window_days") or 3)
    product_keyword = str(cfg.get("product_keyword") or "").strip()
    plan_payload = build_operation_log_sync_plan_from_metrics(
        db_path,
        page_size=page_size,
        product_keyword=product_keyword,
        date_range=cfg.get("date_range") if isinstance(cfg.get("date_range"), dict) else None,
        window_days=window_days,
    )
    openapi_http, execution_cfg = _operation_log_execution_config(cfg)
    _require_operation_log_readonly_enabled(
        openapi_http=openapi_http,
        execution=execution_cfg,
        transport=transport,
    )
    real_transport = transport or build_http_transport(
        openapi_http,
        response_dir=openapi_http.get("response_audit_dir") or Path(runs_dir) / "openapi_http" / "operation-log-history",
        opener=http_opener,
        sleeper=http_sleeper,
    )
    execution = execute_openapi_readonly_plan(
        plan_payload["plan"],
        transport=real_transport,
        **_retry_options(openapi_http),
    )
    snapshots = build_snapshots_from_execution(execution)
    snapshot_paths = _write_snapshot_files(snapshots, runs_dir=runs_dir)
    import_result = _import_snapshot_files(snapshot_paths, db_path=db_path)
    dataset = build_control_operation_dataset(
        db_path,
        window_days=window_days,
        product_keyword=product_keyword,
    )
    row_sample_limit = int(cfg.get("row_sample_limit") or 20)
    dataset_rows = dataset.get("rows") if isinstance(dataset.get("rows"), list) else []
    dataset_rows_path = _write_dataset_rows_jsonl(
        dataset_rows,
        runs_dir=runs_dir,
        workflow="control_operation_log_history_sync",
    )
    transport_calls = int(execution["summary"]["transport_calls"])
    payload = {
        "ok": True,
        "workflow": "control_operation_log_history_sync",
        "phase": "control_analysis",
        "execution_enabled": False,
        "external_api_calls": transport_calls,
        "summary": {
            "account_source": plan_payload["summary"]["account_source"],
            "filter": plan_payload["summary"]["filter"],
            "date_range": plan_payload["summary"]["date_range"],
            "planned_request_count": int(plan_payload["summary"]["planned_request_count"]),
            "transport_calls": transport_calls,
            "rows_received": int(execution["summary"]["rows_received"]),
            "snapshot_count": int(import_result["snapshot_count"]),
            "operation_logs_imported": int(import_result["operation_logs_imported"]),
            "control_dataset_operation_count": int(dataset["summary"]["operation_count"]),
        },
        "operation_log_sync_plan_summary": plan_payload["summary"],
        "execution_summary": execution["summary"],
        "snapshot_paths": snapshot_paths,
        "import_result": import_result,
        "control_dataset": _compact_dataset(dataset, row_sample_limit=row_sample_limit),
        "control_dataset_rows_path": dataset_rows_path,
        "guardrails": [
            "Readonly only: this workflow uses operation_log_search and writes local SQLite data.",
            "No create/update/delete/pause/budget/schedule API is called.",
        ],
    }
    payload["artifact_path"] = str(write_run_artifact(runs_dir, "control_operation_log_history_sync", payload))
    return payload


def _metric_where(entity_type: str, *, alias: str = "") -> tuple[str, str]:
    prefix = f"{alias}." if alias else ""
    normalized = str(entity_type or "").strip().lower()
    if normalized in {"project", "campaign", "项目"}:
        return "project", f"{prefix}project_id = :entity_id"
    if normalized in {"promotion", "ad", "unit", "广告计划", "单元"}:
        return "promotion", f"{prefix}promotion_id = :entity_id"
    if normalized in {"material", "video", "素材", "视频"}:
        return "material", f"{prefix}material_id = :entity_id"
    return "account", "1 = 1"


def _aggregate_window(
    conn: sqlite3.Connection,
    *,
    advertiser_id: str,
    entity_type: str,
    entity_id: str,
    start_date: date,
    end_date: date,
    product_keyword: str = "",
) -> dict[str, Any]:
    if start_date > end_date:
        return _empty_metric_window(start_date=start_date.isoformat(), end_date=end_date.isoformat())
    match_level, entity_filter = _metric_where(entity_type, alias="mdm")
    scope_filter_sql, scope_params = _metric_scope_filter(product_keyword, alias="mdm")
    scope_params.update(
        {
            "advertiser_id": advertiser_id,
            "entity_id": entity_id,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        }
    )
    row = conn.execute(
        f"""
        SELECT
          COUNT(*) AS row_count,
          COUNT(DISTINCT project_id) AS project_count,
          COUNT(DISTINCT promotion_id) AS promotion_count,
          COUNT(DISTINCT material_id) AS material_count,
          COALESCE(SUM(stat_cost), 0) AS stat_cost,
          COALESCE(SUM(show_cnt), 0) AS show_cnt,
          COALESCE(SUM(click_cnt), 0) AS click_cnt,
          COALESCE(SUM(convert_cnt), 0) AS convert_cnt,
          COALESCE(SUM(CASE WHEN stat_cost > 0 THEN stat_cost * roi_1day ELSE 0 END), 0) AS roi_1day_weighted_sum
        FROM material_daily_metrics mdm
        WHERE {scope_filter_sql}
          AND mdm.advertiser_id = :advertiser_id
          AND mdm.metric_date BETWEEN :start_date AND :end_date
          AND {entity_filter}
        """,
        scope_params,
    ).fetchone()
    stat_cost = float(row["stat_cost"] or 0)
    convert_cnt = float(row["convert_cnt"] or 0)
    return {
        "start": start_date.isoformat(),
        "end": end_date.isoformat(),
        "match_level": match_level,
        "row_count": int(row["row_count"] or 0),
        "project_count": int(row["project_count"] or 0),
        "promotion_count": int(row["promotion_count"] or 0),
        "material_count": int(row["material_count"] or 0),
        "stat_cost": _rounded(stat_cost),
        "show_cnt": _rounded(float(row["show_cnt"] or 0)),
        "click_cnt": _rounded(float(row["click_cnt"] or 0)),
        "convert_cnt": _rounded(convert_cnt),
        "cpa": _rounded(stat_cost / convert_cnt) if convert_cnt > 0 else None,
        "roi_1day_cost_weighted": _rounded(float(row["roi_1day_weighted_sum"] or 0) / stat_cost)
        if stat_cost > 0
        else None,
    }


def _empty_metric_window(*, start_date: str, end_date: str) -> dict[str, Any]:
    return {
        "start": start_date,
        "end": end_date,
        "match_level": "",
        "row_count": 0,
        "project_count": 0,
        "promotion_count": 0,
        "material_count": 0,
        "stat_cost": 0,
        "show_cnt": 0,
        "click_cnt": 0,
        "convert_cnt": 0,
        "cpa": None,
        "roi_1day_cost_weighted": None,
    }


def _rounded(value: float) -> float:
    rounded = round(float(value), 6)
    if rounded == int(rounded):
        return int(rounded)
    return rounded


def build_control_operation_dataset(
    db_path: str | Path,
    *,
    window_days: int = 3,
    product_keyword: str = "",
) -> dict[str, Any]:
    if window_days < 1:
        raise ValueError("window_days must be >= 1")
    rows: list[dict[str, Any]] = []
    keyword = str(product_keyword or "").strip()
    with _connect(db_path) as conn:
        scope = discover_control_metric_scope(db_path, product_keyword=keyword)
        account_ids = [account["advertiser_id"] for account in scope["accounts"]]
        placeholders = ", ".join(f":account_{idx}" for idx in range(len(account_ids)))
        params = {f"account_{idx}": advertiser_id for idx, advertiser_id in enumerate(account_ids)}
        operations = conn.execute(
            f"""
            SELECT
              operation_id, occurred_at, advertiser_id, entity_type, entity_id,
              action, operator, detail
            FROM operation_logs
            WHERE occurred_at <> ''
              AND advertiser_id <> ''
              {"AND advertiser_id IN (" + placeholders + ")" if account_ids else "AND 1 = 0"}
            ORDER BY occurred_at, operation_id
            """,
            params,
        ).fetchall()
        for operation in operations:
            occurred_date = _date_from_text(str(operation["occurred_at"]))
            advertiser_id = str(operation["advertiser_id"])
            entity_type = str(operation["entity_type"])
            entity_id = str(operation["entity_id"])
            before_start = occurred_date - timedelta(days=window_days)
            before_end = occurred_date - timedelta(days=1)
            after_start = occurred_date + timedelta(days=1)
            after_end = occurred_date + timedelta(days=window_days)
            rows.append(
                {
                    "operation_id": str(operation["operation_id"]),
                    "occurred_at": str(operation["occurred_at"]),
                    "operation_date": occurred_date.isoformat(),
                    "advertiser_id": advertiser_id,
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "action": str(operation["action"]),
                    "operator": str(operation["operator"]),
                    "detail": str(operation["detail"]),
                    f"before_{window_days}d": _aggregate_window(
                        conn,
                        advertiser_id=advertiser_id,
                        entity_type=entity_type,
                        entity_id=entity_id,
                        start_date=before_start,
                        end_date=before_end,
                        product_keyword=keyword,
                    ),
                    "event_day": _aggregate_window(
                        conn,
                        advertiser_id=advertiser_id,
                        entity_type=entity_type,
                        entity_id=entity_id,
                        start_date=occurred_date,
                        end_date=occurred_date,
                        product_keyword=keyword,
                    ),
                    f"after_{window_days}d": _aggregate_window(
                        conn,
                        advertiser_id=advertiser_id,
                        entity_type=entity_type,
                        entity_id=entity_id,
                        start_date=after_start,
                        end_date=after_end,
                        product_keyword=keyword,
                    ),
                }
            )

    return {
        "ok": True,
        "workflow": "control_dataset_build",
        "phase": "control_analysis",
        "execution_enabled": False,
        "external_api_calls": 0,
        "summary": {
            "operation_count": len(rows),
            "window_days": window_days,
            "metric_source": "material_daily_metrics",
            "operation_source": "operation_logs",
            "roi_field": "roi_1day",
            "filter": {"product_keyword": keyword} if keyword else {},
        },
        "rows": rows,
    }


def run_control_dataset_build_request(
    request: dict[str, Any] | None,
    *,
    db_path: str | Path,
    runs_dir: str | Path,
) -> dict[str, Any]:
    cfg = dict(request or {})
    page_size = int(cfg.get("operation_log_page_size") or 20)
    window_days = int(cfg.get("window_days") or 3)
    row_sample_limit = int(cfg.get("row_sample_limit") or 20)
    product_keyword = str(cfg.get("product_keyword") or "").strip()
    operation_log_plan = build_operation_log_sync_plan_from_metrics(
        db_path,
        page_size=page_size,
        product_keyword=product_keyword,
        date_range=cfg.get("date_range") if isinstance(cfg.get("date_range"), dict) else None,
        window_days=window_days,
    )
    plan_requests_path = _write_plan_requests_jsonl(
        operation_log_plan,
        runs_dir=runs_dir,
        workflow="control_dataset_build",
    )
    dataset = build_control_operation_dataset(
        db_path,
        window_days=window_days,
        product_keyword=product_keyword,
    )
    dataset_rows = dataset.get("rows") if isinstance(dataset.get("rows"), list) else []
    dataset_rows_path = _write_dataset_rows_jsonl(
        dataset_rows,
        runs_dir=runs_dir,
        workflow="control_dataset_build",
    )
    payload = {
        "ok": True,
        "workflow": "control_dataset_build",
        "phase": "control_analysis",
        "execution_enabled": False,
        "external_api_calls": 0,
        "summary": {
            "account_source": operation_log_plan["summary"]["account_source"],
            "filter": operation_log_plan["summary"]["filter"],
            "date_range": operation_log_plan["summary"]["date_range"],
            "planned_operation_log_request_count": operation_log_plan["summary"]["planned_request_count"],
            "operation_count": dataset["summary"]["operation_count"],
            "window_days": window_days,
        },
        "operation_log_sync_plan": _compact_operation_log_plan(
            operation_log_plan,
            request_sample_limit=row_sample_limit,
        ),
        "operation_log_sync_plan_requests_path": plan_requests_path,
        "operation_metric_dataset": _compact_dataset(dataset, row_sample_limit=row_sample_limit),
        "operation_metric_dataset_rows_path": dataset_rows_path,
    }
    payload["artifact_path"] = str(write_run_artifact(runs_dir, "control_dataset_build", payload))
    return payload
