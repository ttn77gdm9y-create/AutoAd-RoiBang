from __future__ import annotations

import sqlite3
from copy import deepcopy
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from roibang_v2.accounts.pool import import_accounts_csv, select_accounts
from roibang_v2.fetch.workbench_account_discovery import WorkbenchAccountDiscoveryError
from roibang_v2.fetch.workbench_account_discovery import discover_spending_accounts
from roibang_v2.fetch.openapi_readonly import build_openapi_readonly_plan
from roibang_v2.fetch.report_snapshot import run_report_fetch_request
from roibang_v2.runs import write_run_artifact
from roibang_v2.workflows.daily_learning import build_daily_learning_artifact
from roibang_v2.workflows.data_sync import run_data_sync_request
from roibang_v2.workflows.material_source import build_material_source_preflight
from roibang_v2.workflows.material_source import run_material_source_request


def _pipeline_config(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("daily_report_pipeline")
    return dict(value) if isinstance(value, dict) else dict(request)


def _target_date(cfg: dict[str, Any], *, today: date | None = None) -> str:
    value = cfg.get("target_date")
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, dict) and str(value.get("mode") or "") == "yesterday":
        base = today or date.today()
        return (base - timedelta(days=1)).isoformat()
    if isinstance(value, dict) and value.get("date"):
        return str(value["date"])
    raise ValueError("daily_report_pipeline requires target_date or target_date.mode=yesterday")


def _date_span(start_date: str, end_date: str) -> list[str]:
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    if end < start:
        return []
    result: list[str] = []
    current = start
    while current <= end:
        result.append(current.isoformat())
        current += timedelta(days=1)
    return result


def _latest_metric_snapshot_date(db_path: str | Path, *, before_or_on: str) -> str:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT MAX(metric_date) FROM metric_snapshots WHERE metric_date <= ?",
            (before_or_on,),
        ).fetchone()
    return str(row[0] or "") if row else ""


def _catch_up_config(cfg: dict[str, Any]) -> dict[str, Any]:
    value = cfg.get("catch_up")
    return dict(value) if isinstance(value, dict) else {}


def _target_dates(cfg: dict[str, Any], *, db_path: str | Path, today: date | None = None) -> list[str]:
    target = _target_date(cfg, today=today)
    catch_up = _catch_up_config(cfg)
    if not bool(catch_up.get("enabled", False)):
        return [target]
    source_table = str(catch_up.get("source_table") or "metric_snapshots")
    if source_table != "metric_snapshots":
        raise ValueError("daily_report_pipeline.catch_up.source_table only supports metric_snapshots")
    latest = _latest_metric_snapshot_date(db_path, before_or_on=target)
    if not latest:
        return [target]
    start = date.fromisoformat(latest) + timedelta(days=1)
    end = date.fromisoformat(target)
    if start > end:
        return [target]
    max_days = max(int(catch_up.get("max_days") or 7), 1)
    floor = end - timedelta(days=max_days - 1)
    if start < floor:
        start = floor
    return _date_span(start.isoformat(), target)


def _fetch_request(cfg: dict[str, Any], target_date: str) -> dict[str, Any]:
    report_fetch = deepcopy(cfg.get("report_fetch") if isinstance(cfg.get("report_fetch"), dict) else {})
    report_fetch["mode"] = "daily"
    report_fetch["date_range"] = {"start": target_date, "end": target_date}
    return {"report_fetch": report_fetch}


def _active_discovery_config(cfg: dict[str, Any]) -> dict[str, Any]:
    value = cfg.get("active_account_discovery")
    return dict(value) if isinstance(value, dict) else {}


def _configured_accounts(report_fetch: dict[str, Any], *, db_path: str | Path) -> list[dict[str, Any]]:
    account_pool_csv = report_fetch.get("account_pool_csv")
    if account_pool_csv:
        import_accounts_csv(account_pool_csv, db_path=db_path)
    platforms = [str(item) for item in report_fetch.get("platforms", [])]
    accounts = select_accounts(db_path=db_path, product=str(report_fetch["product"]), platforms=platforms)
    limits = report_fetch.get("limits") if isinstance(report_fetch.get("limits"), dict) else {}
    if limits.get("max_accounts"):
        accounts = accounts[: int(limits["max_accounts"])]
    account_ids = (
        [str(item) for item in report_fetch.get("account_ids", [])]
        if isinstance(report_fetch.get("account_ids"), list)
        else []
    )
    if account_ids:
        by_id = {account["advertiser_id"]: account for account in accounts}
        accounts = [by_id[item] for item in account_ids if item in by_id]
    return accounts


def _discovery_fetch_request(
    cfg: dict[str, Any],
    discovery: dict[str, Any],
    target_date: str,
) -> dict[str, Any]:
    report_fetch = deepcopy(cfg.get("report_fetch") if isinstance(cfg.get("report_fetch"), dict) else {})
    report_fetch["mode"] = "daily_active_account_discovery"
    report_fetch["date_range"] = {"start": target_date, "end": target_date}
    if isinstance(discovery.get("limits"), dict):
        report_fetch["limits"] = deepcopy(discovery["limits"])
    else:
        report_fetch.pop("limits", None)
    openapi = deepcopy(report_fetch.get("openapi") if isinstance(report_fetch.get("openapi"), dict) else {})
    openapi.update(deepcopy(discovery.get("openapi") if isinstance(discovery.get("openapi"), dict) else {}))
    openapi["endpoints"] = ["report_custom"]
    openapi["report_presets"] = ["account_daily"]
    report_fetch["openapi"] = openapi
    output = deepcopy(report_fetch.get("output") if isinstance(report_fetch.get("output"), dict) else {})
    if discovery.get("snapshot_dir"):
        output["snapshot_dir"] = str(discovery["snapshot_dir"])
    elif output.get("snapshot_dir"):
        output["snapshot_dir"] = str(Path(str(output["snapshot_dir"])) / "active-account-discovery")
    report_fetch["output"] = output
    return {"report_fetch": report_fetch}


def _number(value: Any) -> float:
    try:
        return float(str(value or "0").replace(",", "").replace("%", ""))
    except ValueError:
        return 0.0


def _discover_spending_account_ids(
    discovery_result: dict[str, Any],
    *,
    min_spend: float,
) -> list[str]:
    spend_by_account: dict[str, float] = {}
    execution = discovery_result.get("execution_result") if isinstance(discovery_result.get("execution_result"), dict) else {}
    for item in execution.get("responses") or []:
        if not isinstance(item, dict):
            continue
        request = item.get("request") if isinstance(item.get("request"), dict) else {}
        account = request.get("account") if isinstance(request.get("account"), dict) else {}
        request_advertiser_id = str(account.get("advertiser_id") or "")
        if request.get("endpoint_key") != "report_custom" or request.get("report_preset") != "account_daily":
            continue
        for row in item.get("rows") or []:
            if not isinstance(row, dict):
                continue
            dimensions = row.get("dimensions") if isinstance(row.get("dimensions"), dict) else {}
            metrics = row.get("metrics") if isinstance(row.get("metrics"), dict) else {}
            advertiser_id = str(dimensions.get("advertiser_id") or request_advertiser_id)
            if not advertiser_id:
                continue
            spend_by_account[advertiser_id] = spend_by_account.get(advertiser_id, 0.0) + _number(metrics.get("stat_cost"))
    return sorted(advertiser_id for advertiser_id, spend in spend_by_account.items() if spend > min_spend)


def _detail_fetch_request(cfg: dict[str, Any], target_date: str, account_ids: list[str]) -> dict[str, Any]:
    request = _fetch_request(cfg, target_date)
    if account_ids:
        request["report_fetch"]["account_ids"] = account_ids
        request["report_fetch"].pop("limits", None)
    return request


def _run_openapi_active_account_discovery(
    cfg: dict[str, Any],
    discovery: dict[str, Any],
    *,
    target_date: str,
    db_path: str | Path,
    runs_dir: str | Path,
    http_opener,
    http_sleeper,
) -> dict[str, Any]:
    discovery_request = _discovery_fetch_request(cfg, discovery, target_date)
    report_fetch = discovery_request["report_fetch"]
    candidate_accounts = _configured_accounts(report_fetch, db_path=db_path)
    discovery_result = run_report_fetch_request(
        discovery_request,
        db_path=db_path,
        runs_dir=runs_dir,
        http_opener=http_opener,
        http_sleeper=http_sleeper,
    )
    min_spend = _number(discovery.get("min_spend"))
    active_account_ids = _discover_spending_account_ids(discovery_result, min_spend=min_spend)
    request_plan = discovery_result.get("request_plan") if isinstance(discovery_result.get("request_plan"), dict) else {}
    execution_result = (
        discovery_result.get("execution_result") if isinstance(discovery_result.get("execution_result"), dict) else {}
    )
    return {
        "enabled": True,
        "source": "openapi_account_daily",
        "artifact_path": discovery_result["artifact_path"],
        "external_api_calls": int(discovery_result.get("external_api_calls") or 0),
        "active_account_ids": active_account_ids,
        "summary": {
            "enabled": True,
            "source": "openapi_account_daily",
            "target_date": target_date,
            "candidate_account_count": len(candidate_accounts),
            "active_account_count": len(active_account_ids),
            "min_spend": min_spend,
            "planned_request_count": int(
                (request_plan.get("summary") if isinstance(request_plan.get("summary"), dict) else {}).get(
                    "planned_request_count", 0
                )
            ),
            "transport_calls": int(
                (execution_result.get("summary") if isinstance(execution_result.get("summary"), dict) else {}).get(
                    "transport_calls", 0
                )
            ),
            "rows_received": int(
                (execution_result.get("summary") if isinstance(execution_result.get("summary"), dict) else {}).get(
                    "rows_received", 0
                )
            ),
        },
    }


def _run_workbench_active_account_discovery(
    cfg: dict[str, Any],
    discovery: dict[str, Any],
    *,
    target_date: str,
    db_path: str | Path,
    workbench_opener,
) -> dict[str, Any]:
    workbench = deepcopy(discovery.get("workbench") if isinstance(discovery.get("workbench"), dict) else {})
    report_fetch = cfg.get("report_fetch") if isinstance(cfg.get("report_fetch"), dict) else {}
    candidate_accounts = _configured_accounts(report_fetch, db_path=db_path)
    workbench["allowed_account_ids"] = [str(account["advertiser_id"]) for account in candidate_accounts]
    min_spend = _number(discovery.get("min_spend"))
    result = discover_spending_accounts(
        workbench,
        target_date=target_date,
        min_spend=min_spend,
        opener=workbench_opener,
    )
    return {
        **result,
        "artifact_path": "",
        "external_api_calls": int(result.get("external_api_calls") or 0),
    }


def _run_active_account_discovery(
    cfg: dict[str, Any],
    *,
    target_date: str,
    db_path: str | Path,
    runs_dir: str | Path,
    http_opener,
    http_sleeper,
    workbench_opener,
) -> dict[str, Any] | None:
    discovery = _active_discovery_config(cfg)
    if not bool(discovery.get("enabled", False)):
        return None

    source = str(discovery.get("source") or "openapi_account_daily")
    if source == "workbench_account_list":
        try:
            return _run_workbench_active_account_discovery(
                cfg,
                discovery,
                target_date=target_date,
                db_path=db_path,
                workbench_opener=workbench_opener,
            )
        except WorkbenchAccountDiscoveryError as exc:
            if not bool(discovery.get("fallback_to_openapi", True)):
                raise
            fallback = _run_openapi_active_account_discovery(
                cfg,
                discovery,
                target_date=target_date,
                db_path=db_path,
                runs_dir=runs_dir,
                http_opener=http_opener,
                http_sleeper=http_sleeper,
            )
            fallback["summary"]["fallback_used"] = True
            fallback["summary"]["fallback_reason"] = str(exc)
            return fallback

    if source not in {"openapi_account_daily", "openapi"}:
        raise ValueError(f"unsupported active_account_discovery.source: {source}")
    return _run_openapi_active_account_discovery(
        cfg,
        discovery,
        target_date=target_date,
        db_path=db_path,
        runs_dir=runs_dir,
        http_opener=http_opener,
        http_sleeper=http_sleeper,
    )


def _learning_policy(cfg: dict[str, Any], target_date: str) -> dict[str, Any]:
    policy = deepcopy(cfg.get("daily_learning") if isinstance(cfg.get("daily_learning"), dict) else {})
    policy["target_date"] = target_date
    return policy


def _material_source_request(cfg: dict[str, Any]) -> dict[str, Any] | None:
    value = cfg.get("material_source")
    if not isinstance(value, dict):
        return None
    return {"material_source": deepcopy(value)}


def _openapi_cfg(report_fetch: dict[str, Any]) -> dict[str, Any]:
    return dict(report_fetch.get("openapi") if isinstance(report_fetch.get("openapi"), dict) else {})


def _plan_from_fetch_cfg(
    report_fetch: dict[str, Any],
    *,
    accounts: list[dict[str, Any]],
    target_date: str,
) -> dict[str, Any]:
    openapi = _openapi_cfg(report_fetch)
    return build_openapi_readonly_plan(
        accounts=accounts,
        dates=[target_date],
        endpoints=[str(item) for item in openapi.get("endpoints", [])],
        report_presets=[str(item) for item in openapi.get("report_presets", [])],
        platforms=[str(item) for item in report_fetch.get("platforms", [])],
        page_size=int(openapi.get("page_size") or 100),
    )


def build_daily_report_pipeline_preflight(
    request: dict[str, Any],
    *,
    db_path: str | Path,
    runs_dir: str | Path,
    today: date | None = None,
) -> dict[str, Any]:
    cfg = _pipeline_config(request)
    target_date = _target_date(cfg, today=today)
    discovery = _active_discovery_config(cfg)
    discovery_enabled = bool(discovery.get("enabled", False))
    if discovery_enabled:
        source = str(discovery.get("source") or "openapi_account_daily")
        if source == "workbench_account_list":
            report_fetch = cfg.get("report_fetch") if isinstance(cfg.get("report_fetch"), dict) else {}
            candidate_accounts = _configured_accounts(report_fetch, db_path=db_path)
            limit = int(
                (
                    discovery.get("workbench")
                    if isinstance(discovery.get("workbench"), dict)
                    else {}
                ).get("limit")
                or 100
            )
            request_count = (len(candidate_accounts) + limit - 1) // limit if candidate_accounts else 0
            discovery_plan = {
                "summary": {
                    "source": "workbench_account_list",
                    "planned_request_count": request_count,
                    "candidate_account_count": len(candidate_accounts),
                    "external_api_calls": 0,
                },
                "endpoints": ["workbench_account_list"],
                "report_presets": ["account_spend_sorted"],
            }
        else:
            discovery_request = _discovery_fetch_request(cfg, discovery, target_date)
            discovery_fetch = discovery_request["report_fetch"]
            candidate_accounts = _configured_accounts(discovery_fetch, db_path=db_path)
            discovery_plan = _plan_from_fetch_cfg(discovery_fetch, accounts=candidate_accounts, target_date=target_date)
    else:
        report_fetch = cfg.get("report_fetch") if isinstance(cfg.get("report_fetch"), dict) else {}
        candidate_accounts = _configured_accounts(report_fetch, db_path=db_path)
        discovery_plan = None

    detail_request = _fetch_request(cfg, target_date)
    detail_fetch = detail_request["report_fetch"]
    detail_accounts = candidate_accounts if discovery_enabled else _configured_accounts(detail_fetch, db_path=db_path)
    detail_plan = _plan_from_fetch_cfg(detail_fetch, accounts=detail_accounts, target_date=target_date)
    discovery_request_count = (
        int(discovery_plan["summary"]["planned_request_count"]) if isinstance(discovery_plan, dict) else 0
    )
    detail_request_count = int(detail_plan["summary"]["planned_request_count"])
    material_source_request = _material_source_request(cfg)
    material_source_plan = None
    material_source_request_count = 0
    if material_source_request is not None:
        material_source_plan = build_material_source_preflight(material_source_request)
        material_source_request_count = int(material_source_plan["summary"]["planned_request_count"])
    payload = {
        "ok": True,
        "workflow": "daily_report_pipeline_preflight",
        "phase": "phase1",
        "execution_enabled": False,
        "external_api_calls": 0,
        "summary": {
            "target_date": target_date,
            "source": str(detail_fetch.get("source") or ""),
            "candidate_account_count": len(candidate_accounts),
            "discovery_enabled": discovery_enabled,
            "discovery_planned_request_count": discovery_request_count,
            "detail_worst_case_account_count": len(detail_accounts),
            "detail_worst_case_initial_request_count": detail_request_count,
            "material_source_planned_request_count": material_source_request_count,
            "estimated_total_initial_request_count": discovery_request_count
            + detail_request_count
            + material_source_request_count,
        },
        "discovery_plan": {
            "summary": discovery_plan["summary"],
            "endpoints": discovery_plan["endpoints"],
            "report_presets": discovery_plan["report_presets"],
        }
        if isinstance(discovery_plan, dict)
        else None,
        "detail_plan": {
            "summary": detail_plan["summary"],
            "endpoints": detail_plan["endpoints"],
            "report_presets": detail_plan["report_presets"],
        },
        "material_source_plan": {
            "summary": material_source_plan["summary"],
            "plan_summary": material_source_plan["plan"].get("summary", {}),
        }
        if isinstance(material_source_plan, dict)
        else None,
    }
    artifact = write_run_artifact(runs_dir, "daily_report_pipeline_preflight", payload)
    return {**payload, "artifact_path": str(artifact)}


def run_daily_report_pipeline_request(
    request: dict[str, Any],
    *,
    db_path: str | Path,
    runs_dir: str | Path,
    today: date | None = None,
    http_opener=None,
    http_sleeper=None,
    workbench_opener=None,
) -> dict[str, Any]:
    cfg = _pipeline_config(request)
    target_dates = _target_dates(cfg, db_path=db_path, today=today)
    if len(target_dates) > 1:
        return _run_daily_report_pipeline_batch(
            cfg,
            target_dates=target_dates,
            db_path=db_path,
            runs_dir=runs_dir,
            http_opener=http_opener,
            http_sleeper=http_sleeper,
            workbench_opener=workbench_opener,
        )
    target_date = target_dates[0]
    active_discovery = _run_active_account_discovery(
        cfg,
        target_date=target_date,
        db_path=db_path,
        runs_dir=runs_dir,
        http_opener=http_opener,
        http_sleeper=http_sleeper,
        workbench_opener=workbench_opener,
    )
    active_account_ids = active_discovery["active_account_ids"] if active_discovery is not None else []
    if active_discovery is not None and not active_account_ids:
        fetch_result = {
            "ok": True,
            "workflow": "report_fetch",
            "phase": "phase1",
            "mode": "daily",
            "source": str((cfg.get("report_fetch") if isinstance(cfg.get("report_fetch"), dict) else {}).get("source") or ""),
            "execution_enabled": False,
            "external_api_calls": 0,
            "summary": {
                "mode": "daily",
                "source": str(
                    (cfg.get("report_fetch") if isinstance(cfg.get("report_fetch"), dict) else {}).get("source") or ""
                ),
                "product": str(
                    (cfg.get("report_fetch") if isinstance(cfg.get("report_fetch"), dict) else {}).get("product") or ""
                ),
                "platforms": [
                    str(item)
                    for item in (
                        (cfg.get("report_fetch") if isinstance(cfg.get("report_fetch"), dict) else {}).get(
                            "platforms", []
                        )
                    )
                ],
                "account_count": 0,
                "date_count": 1,
                "snapshots_written": 0,
            },
            "snapshots": [],
            "skipped": True,
            "skip_reason": "no active spending accounts discovered",
        }
    else:
        fetch_result = run_report_fetch_request(
            _detail_fetch_request(cfg, target_date, active_account_ids),
            db_path=db_path,
            runs_dir=runs_dir,
            http_opener=http_opener,
            http_sleeper=http_sleeper,
        )

    data_sync_results: list[dict[str, Any]] = []
    for snapshot in fetch_result.get("snapshots") or []:
        snapshot_file = snapshot.get("path")
        if snapshot_file:
            data_sync_results.append(
                run_data_sync_request(
                    {"data_sync": {"kind": "local_report_snapshot", "snapshot_file": snapshot_file}},
                    db_path=db_path,
                    runs_dir=runs_dir,
                )
            )

    material_source = None
    material_source_request = _material_source_request(cfg)
    if material_source_request is not None:
        material_source = run_material_source_request(
            material_source_request,
            db_path=db_path,
            runs_dir=runs_dir,
        )

    daily_learning = None
    if data_sync_results:
        daily_learning = build_daily_learning_artifact(db_path=db_path, policy=_learning_policy(cfg, target_date))

    discovery_external_api_calls = int(active_discovery.get("external_api_calls") or 0) if active_discovery else 0
    material_source_external_api_calls = int(material_source.get("external_api_calls") or 0) if material_source else 0
    external_api_calls = (
        discovery_external_api_calls + int(fetch_result.get("external_api_calls") or 0) + material_source_external_api_calls
    )
    summary = {
        "target_date": target_date,
        "snapshots_written": len(fetch_result.get("snapshots") or []),
        "snapshots_imported": len(data_sync_results),
        "daily_learning_built": daily_learning is not None,
        "external_api_calls": external_api_calls,
    }
    if material_source_request is not None:
        summary["material_source_built"] = material_source is not None
    if active_discovery is not None:
        summary["active_accounts_discovered"] = len(active_account_ids)
        summary["detail_fetch_account_count"] = len(active_account_ids)
    payload = {
        "ok": bool(fetch_result.get("ok")) and all(bool(item.get("ok")) for item in data_sync_results),
        "workflow": "daily_report_pipeline",
        "phase": "phase1",
        "execution_enabled": False,
        "external_api_calls": external_api_calls,
        "summary": summary,
        "steps": {
            "active_account_discovery": active_discovery,
            "report_fetch": {
                "artifact_path": fetch_result.get("artifact_path", ""),
                "summary": fetch_result["summary"],
                "skipped": bool(fetch_result.get("skipped", False)),
            },
            "data_sync": [
                {
                    "artifact_path": item["artifact_path"],
                    "import": item["import"],
                }
                for item in data_sync_results
            ],
            "material_source": material_source,
            "daily_learning": daily_learning,
        },
    }
    artifact = write_run_artifact(runs_dir, "daily_report_pipeline", payload)
    return {**payload, "artifact_path": str(artifact)}


def _run_daily_report_pipeline_batch(
    cfg: dict[str, Any],
    *,
    target_dates: list[str],
    db_path: str | Path,
    runs_dir: str | Path,
    http_opener=None,
    http_sleeper=None,
    workbench_opener=None,
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for target_date in target_dates:
        single_cfg = deepcopy(cfg)
        single_cfg["target_date"] = {"date": target_date}
        single_cfg.pop("catch_up", None)
        results.append(
            run_daily_report_pipeline_request(
                {"daily_report_pipeline": single_cfg},
                db_path=db_path,
                runs_dir=runs_dir,
                http_opener=http_opener,
                http_sleeper=http_sleeper,
                workbench_opener=workbench_opener,
            )
        )

    external_api_calls = sum(int(item.get("external_api_calls") or 0) for item in results)
    summary = {
        "target_date": target_dates[-1],
        "target_dates": target_dates,
        "snapshots_written": sum(int(item["summary"].get("snapshots_written") or 0) for item in results),
        "snapshots_imported": sum(int(item["summary"].get("snapshots_imported") or 0) for item in results),
        "daily_learning_built": any(bool(item["summary"].get("daily_learning_built")) for item in results),
        "external_api_calls": external_api_calls,
        "catch_up_runs": len(results),
    }
    if any("active_accounts_discovered" in item["summary"] for item in results):
        summary["active_accounts_discovered"] = sum(
            int(item["summary"].get("active_accounts_discovered") or 0) for item in results
        )
        summary["detail_fetch_account_count"] = sum(
            int(item["summary"].get("detail_fetch_account_count") or 0) for item in results
        )
    payload = {
        "ok": all(bool(item.get("ok")) for item in results),
        "workflow": "daily_report_pipeline",
        "phase": "phase1",
        "execution_enabled": False,
        "external_api_calls": external_api_calls,
        "summary": summary,
        "steps": {
            "catch_up": [
                {
                    "target_date": target_date,
                    "artifact_path": item["artifact_path"],
                    "summary": item["summary"],
                }
                for target_date, item in zip(target_dates, results)
            ]
        },
    }
    artifact = write_run_artifact(runs_dir, "daily_report_pipeline", payload)
    return {**payload, "artifact_path": str(artifact)}
