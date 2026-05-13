from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from roibang_v2.fetch.openapi_executor import Transport
from roibang_v2.fetch.openapi_executor import execute_openapi_readonly_plan
from roibang_v2.fetch.openapi_http import build_http_transport
from roibang_v2.fetch.openapi_readonly import build_openapi_readonly_plan
from roibang_v2.runs import write_run_artifact


def _connect(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _json_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [dict(item) for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ["allowed_target_accounts", "accounts", "rows"]:
            value = payload.get(key)
            if isinstance(value, list):
                return [dict(item) for item in value if isinstance(item, dict)]
    return []


def _enabled(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "enabled"}


def _load_allowed_accounts(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    path_text = str(cfg.get("allowed_target_accounts_path") or "").strip()
    if not path_text:
        raise ValueError("project hourly realtime sync requires allowed_target_accounts_path")
    path = Path(path_text)
    if not path.exists():
        raise ValueError(f"allowed_target_accounts_path not found: {path}")
    product_keyword = str(cfg.get("product_keyword") or "").strip()
    accounts: list[dict[str, Any]] = []
    for row in _json_rows(json.loads(path.read_text(encoding="utf-8"))):
        advertiser_id = str(row.get("advertiser_id") or row.get("account_id") or "").strip()
        product = str(row.get("product") or "").strip()
        account_name = str(row.get("account_name") or "").strip()
        if not advertiser_id or not _enabled(row.get("enable", row.get("enabled", True))):
            continue
        if product_keyword and product_keyword not in product and product_keyword not in account_name:
            continue
        accounts.append(
            {
                "advertiser_id": advertiser_id,
                "account_name": account_name,
                "product": product,
                "platform": "WECHAT_GAME",
            }
        )
    return accounts


def _target_date(cfg: dict[str, Any]) -> str:
    value = str(cfg.get("target_date") or "").strip()
    if not value:
        raise ValueError("project hourly realtime sync requires target_date")
    return value


def build_project_hourly_realtime_plan(db_path: str | Path, request: dict[str, Any] | None) -> dict[str, Any]:
    cfg = dict(request or {})
    accounts = _load_allowed_accounts(cfg)
    target_date = _target_date(cfg)
    page_size = int(cfg.get("page_size") or 100)
    plan = build_openapi_readonly_plan(
        accounts=accounts,
        dates=[target_date],
        endpoints=["report_custom"],
        report_presets=["project_hourly"],
        platforms=["WECHAT_GAME"],
        page_size=page_size,
    )
    return {
        "ok": True,
        "workflow": "project_hourly_realtime_sync_plan",
        "phase": "control_analysis",
        "execution_enabled": False,
        "external_api_calls": 0,
        "summary": {
            "target_date": target_date,
            "allowed_account_count": len(accounts),
            "planned_request_count": int(plan["summary"]["planned_request_count"]),
        },
        "plan": plan,
    }


def _number(value: Any) -> float:
    try:
        return float(str(value or "0").replace(",", "").replace("%", ""))
    except ValueError:
        return 0.0


def _metric_hour(value: Any) -> int:
    text = str(value or "").strip()
    if not text:
        return 0
    if text.isdigit():
        return int(text)
    try:
        return datetime.fromisoformat(text.replace(" ", "T")).hour
    except ValueError:
        return int(text[11:13]) if len(text) >= 13 and text[11:13].isdigit() else 0


def _import_project_hourly_execution(
    execution: dict[str, Any],
    *,
    db_path: str | Path,
) -> int:
    imported = 0
    with _connect(db_path) as conn:
        for item in execution.get("responses") or []:
            if not isinstance(item, dict):
                continue
            request = item.get("request") if isinstance(item.get("request"), dict) else {}
            if request.get("endpoint_key") != "report_custom" or request.get("report_preset") != "project_hourly":
                continue
            account = request.get("account") if isinstance(request.get("account"), dict) else {}
            advertiser_id = str(account.get("advertiser_id") or "")
            target_date = str(request.get("date") or "")
            for row in item.get("rows") or []:
                if not isinstance(row, dict):
                    continue
                dimensions = row.get("dimensions") if isinstance(row.get("dimensions"), dict) else {}
                metrics = row.get("metrics") if isinstance(row.get("metrics"), dict) else {}
                project_id = str(dimensions.get("project_id") or dimensions.get("cdp_project_id") or "")
                if not advertiser_id or not target_date or not project_id:
                    continue
                conn.execute(
                    """
                    INSERT INTO project_hourly_metrics (
                      metric_date, metric_hour, advertiser_id, project_id, project_name,
                      stat_cost, show_cnt, click_cnt, convert_cnt, roi_1day,
                      metric_payload_json, source, synced_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(metric_date, metric_hour, advertiser_id, project_id) DO UPDATE SET
                      project_name = excluded.project_name,
                      stat_cost = excluded.stat_cost,
                      show_cnt = excluded.show_cnt,
                      click_cnt = excluded.click_cnt,
                      convert_cnt = excluded.convert_cnt,
                      roi_1day = excluded.roi_1day,
                      metric_payload_json = excluded.metric_payload_json,
                      source = excluded.source,
                      synced_at = excluded.synced_at
                    """,
                    (
                        target_date,
                        _metric_hour(dimensions.get("stat_time_hour") or dimensions.get("stat_time")),
                        advertiser_id,
                        project_id,
                        str(dimensions.get("project_name") or dimensions.get("cdp_project_name") or ""),
                        _number(metrics.get("stat_cost")),
                        _number(metrics.get("show_cnt")),
                        _number(metrics.get("click_cnt")),
                        _number(metrics.get("convert_cnt")),
                        _number(
                            metrics.get("attribution_billing_game_in_app_roi_1day")
                            or metrics.get("roi_1day")
                            or metrics.get("pay_amount_roi")
                        ),
                        json.dumps(row, ensure_ascii=False, sort_keys=True),
                        "project_hourly_realtime_sync",
                        datetime.now().astimezone().isoformat(timespec="seconds"),
                    ),
                )
                imported += 1
    return imported


def _require_readonly_enabled(openapi_http: dict[str, Any], execution: dict[str, Any], transport: Transport | None) -> None:
    if transport is not None:
        return
    if str(execution.get("status") or "") != "execute":
        raise RuntimeError("project hourly realtime sync requires execution.status=execute")
    if not bool(execution.get("external_api_enabled", False)):
        raise RuntimeError("project hourly realtime sync requires execution.external_api_enabled=true")
    if not bool(openapi_http.get("enabled", False)):
        raise RuntimeError("project hourly realtime sync requires openapi_http.enabled=true")


def run_project_hourly_realtime_sync_request(
    request: dict[str, Any] | None,
    *,
    db_path: str | Path,
    runs_dir: str | Path,
    transport: Transport | None = None,
    http_opener=None,
    http_sleeper=None,
) -> dict[str, Any]:
    cfg = dict(request or {})
    openapi_http = cfg.get("openapi_http") if isinstance(cfg.get("openapi_http"), dict) else {}
    execution_cfg = cfg.get("execution") if isinstance(cfg.get("execution"), dict) else {}
    _require_readonly_enabled(openapi_http, execution_cfg, transport)
    plan_payload = build_project_hourly_realtime_plan(db_path, cfg)
    real_transport = transport or build_http_transport(
        openapi_http,
        response_dir=openapi_http.get("response_audit_dir") or Path(runs_dir) / "openapi_http" / "project-hourly-realtime",
        opener=http_opener,
        sleeper=http_sleeper,
    )
    execution = execute_openapi_readonly_plan(plan_payload["plan"], transport=real_transport)
    rows_imported = _import_project_hourly_execution(execution, db_path=db_path)
    transport_calls = int(execution["summary"]["transport_calls"])
    payload = {
        "ok": True,
        "workflow": "project_hourly_realtime_sync",
        "phase": "control_analysis",
        "execution_enabled": False,
        "external_api_calls": transport_calls,
        "summary": {
            **plan_payload["summary"],
            "transport_calls": transport_calls,
            "rows_received": int(execution["summary"]["rows_received"]),
            "rows_imported": rows_imported,
        },
        "plan_summary": plan_payload["summary"],
        "execution_summary": execution["summary"],
        "guardrails": [
            "Readonly only: this workflow reads project hourly report data and writes local SQLite data.",
            "No create/update/delete/pause/budget/schedule API is called.",
        ],
    }
    payload["artifact_path"] = str(write_run_artifact(runs_dir, "project_hourly_realtime_sync", payload))
    return payload
