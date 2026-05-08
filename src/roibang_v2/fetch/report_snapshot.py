from __future__ import annotations

import json
import shutil
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from roibang_v2.accounts.pool import import_accounts_csv, select_accounts
from roibang_v2.fetch.openapi_executor import build_snapshots_from_execution, execute_openapi_readonly_plan
from roibang_v2.fetch.openapi_http import build_http_transport
from roibang_v2.fetch.openapi_readonly import build_openapi_readonly_plan
from roibang_v2.runs import write_run_artifact


def _report_fetch_config(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("report_fetch")
    return dict(value) if isinstance(value, dict) else dict(request)


def _date_range(start_date: str, end_date: str) -> list[str]:
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    if end < start:
        raise ValueError("end date must be greater than or equal to start date")
    days: list[str] = []
    current = start
    while current <= end:
        days.append(current.isoformat())
        current += timedelta(days=1)
    return days


def _compact_date(value: str) -> str:
    return value[5:7] + value[8:10]


def _safe_suffix(value: str) -> str:
    return value[-6:] if len(value) >= 6 else value


def _mock_account_snapshot(account: dict[str, Any], *, target_date: str) -> dict[str, Any]:
    advertiser_id = str(account["advertiser_id"])
    suffix = _safe_suffix(advertiser_id)
    date_tag = _compact_date(target_date)
    cost = round(max(float(account.get("historical_spend") or 0) / 1000, 80), 2)
    conversions = max(int(cost // 80), 1)
    project_id = f"mock_project_{suffix}_{target_date.replace('-', '')}"
    promotion_id = f"mock_promotion_{suffix}_{target_date.replace('-', '')}"
    material_id = f"mock_material_{suffix}"
    return {
        "advertiser_id": advertiser_id,
        "projects": [
            {
                "advertiser_id": advertiser_id,
                "project_id": project_id,
                "project_name": f"{date_tag}_{account['product']}_{account['platform']}_{suffix}",
                "project_status": "PROJECT_STATUS_ENABLE",
            }
        ],
        "promotions": [
            {
                "advertiser_id": advertiser_id,
                "project_id": project_id,
                "project_name": f"{date_tag}_{account['product']}_{account['platform']}_{suffix}",
                "promotion_id": promotion_id,
                "promotion_name": f"{date_tag}_{account['product']}_mock_unit_{suffix}",
                "promotion_status_name": "投放中",
                "promotion_materials": {
                    "video_material_list": [
                        {
                            "material_id": material_id,
                            "video_id": f"mock_video_{suffix}",
                            "title": f"{account['product']} mock video {suffix}",
                        }
                    ]
                },
            }
        ],
        "promotion_metrics": [
            {
                "promotion_id": promotion_id,
                "stat_cost": cost,
                "active_register": conversions * 2,
                "attribution_convert_cnt": conversions,
                "attribution_billing_game_in_app_roi_1day": 0.32,
                "attribution_billing_game_in_app_roi_7days": 0.58,
            }
        ],
        "operation_logs": [
            {
                "operation_id": f"mock_op_{suffix}_{target_date.replace('-', '')}",
                "occurred_at": f"{target_date}T09:00:00+08:00",
                "operator": "mock_fetcher",
                "entity_type": "account",
                "entity_id": advertiser_id,
                "action": "mock_report_fetch",
                "detail": "本地模拟报表快照生成",
            }
        ],
    }


def _write_snapshot(snapshot_dir: Path, *, target_date: str, accounts: list[dict[str, Any]]) -> Path:
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    path = snapshot_dir / f"{target_date}.json"
    payload = {
        "period": {"start": target_date, "end": target_date},
        "accounts": [_mock_account_snapshot(account, target_date=target_date) for account in accounts],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _run_local_fixture(cfg: dict[str, Any], snapshot_dir: Path) -> list[dict[str, Any]]:
    source = Path(cfg["fixture_file"])
    target_date = str(cfg.get("target_date") or source.stem)
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    target = snapshot_dir / f"{target_date}.json"
    shutil.copyfile(source, target)
    return [{"date": target_date, "path": str(target), "account_count": 0}]


def _write_payload_snapshot(snapshot_dir: Path, payload: dict[str, Any]) -> dict[str, Any]:
    period = payload.get("period") if isinstance(payload.get("period"), dict) else {}
    target_date = str(period.get("start") or "")
    if not target_date:
        raise ValueError("snapshot payload requires period.start")
    accounts = payload.get("accounts") if isinstance(payload.get("accounts"), list) else []
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    path = snapshot_dir / f"{target_date}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"date": target_date, "path": str(path), "account_count": len(accounts)}


def _fixture_transport_from_file(path: str | Path):
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    responses = payload.get("responses")
    if not isinstance(responses, list):
        raise ValueError("fixture responses file requires responses list")
    index: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    fallback_index: dict[tuple[str, str, str], dict[str, Any]] = {}
    for item in responses:
        if not isinstance(item, dict):
            continue
        endpoint_key = str(item.get("endpoint_key") or "")
        report_preset = str(item.get("report_preset") or "")
        page = str(item.get("page") or 1)
        advertiser_id = str(item.get("advertiser_id") or "")
        response = item.get("response")
        if endpoint_key and isinstance(response, dict):
            if advertiser_id:
                index[(endpoint_key, report_preset, page, advertiser_id)] = response
            else:
                fallback_index[(endpoint_key, report_preset, page)] = response

    def transport(request: dict[str, Any]) -> dict[str, Any]:
        query_params = request.get("query_params") if isinstance(request.get("query_params"), dict) else {}
        account = request.get("account") if isinstance(request.get("account"), dict) else {}
        key = (
            str(request.get("endpoint_key") or ""),
            str(request.get("report_preset") or ""),
            str(query_params.get("page") or 1),
            str(account.get("advertiser_id") or query_params.get("advertiser_id") or ""),
        )
        if key not in index:
            fallback_key = key[:3]
            if fallback_key not in fallback_index:
                raise KeyError(f"missing fixture response for {key}")
            return fallback_index[fallback_key]
        return index[key]

    return transport


def _load_configured_accounts(cfg: dict[str, Any], *, db_path: str | Path) -> list[dict[str, Any]]:
    account_pool_csv = cfg.get("account_pool_csv")
    if account_pool_csv:
        import_accounts_csv(account_pool_csv, db_path=db_path)
    platforms = [str(item) for item in cfg.get("platforms", [])]
    accounts = select_accounts(db_path=db_path, product=str(cfg["product"]), platforms=platforms)
    limits = cfg.get("limits") if isinstance(cfg.get("limits"), dict) else {}
    if limits.get("max_accounts"):
        accounts = accounts[: int(limits["max_accounts"])]
    account_ids = [str(item) for item in cfg.get("account_ids", [])] if isinstance(cfg.get("account_ids"), list) else []
    if account_ids:
        by_id = {account["advertiser_id"]: account for account in accounts}
        accounts = [by_id[item] for item in account_ids if item in by_id]
    return accounts


def _configured_days(cfg: dict[str, Any]) -> list[str]:
    date_range = cfg.get("date_range") if isinstance(cfg.get("date_range"), dict) else {}
    days = _date_range(str(date_range["start"]), str(date_range["end"]))
    limits = cfg.get("limits") if isinstance(cfg.get("limits"), dict) else {}
    if limits.get("max_dates"):
        days = days[: int(limits["max_dates"])]
    return days


def run_report_fetch_request(
    request: dict[str, Any],
    *,
    db_path: str | Path,
    runs_dir: str | Path,
    http_opener=None,
    http_sleeper=None,
) -> dict[str, Any]:
    cfg = _report_fetch_config(request)
    source = str(cfg.get("source") or "mock_openapi")
    execution = cfg.get("execution") if isinstance(cfg.get("execution"), dict) else {}
    if source == "openapi_http_execute":
        if str(execution.get("status") or "") != "execute":
            raise RuntimeError("openapi_http_execute requires execution.status=execute")
        if not bool(execution.get("external_api_enabled", False)):
            raise RuntimeError("openapi_http_execute requires external_api_enabled=true")
    elif execution.get("external_api_enabled"):
        raise RuntimeError("Phase 1 report fetch requires external_api_enabled=false")

    output = cfg.get("output") if isinstance(cfg.get("output"), dict) else {}
    snapshot_dir = Path(output.get("snapshot_dir") or "data/snapshots/report")
    snapshots: list[dict[str, Any]]
    accounts: list[dict[str, Any]] = []
    days: list[str] = []
    request_plan: dict[str, Any] | None = None
    execution_result: dict[str, Any] | None = None
    if source == "local_fixture":
        snapshots = _run_local_fixture(cfg, snapshot_dir)
    elif source == "mock_openapi":
        accounts = _load_configured_accounts(cfg, db_path=db_path)
        days = _configured_days(cfg)
        snapshots = []
        for day in days:
            path = _write_snapshot(snapshot_dir, target_date=day, accounts=accounts)
            snapshots.append({"date": day, "path": str(path), "account_count": len(accounts)})
    elif source == "openapi_readonly":
        if str(execution.get("status") or "") != "planned_only":
            raise RuntimeError("openapi_readonly requires execution.status=planned_only")
        accounts = _load_configured_accounts(cfg, db_path=db_path)
        days = _configured_days(cfg)
        openapi = cfg.get("openapi") if isinstance(cfg.get("openapi"), dict) else {}
        request_plan = build_openapi_readonly_plan(
            accounts=accounts,
            dates=days,
            endpoints=[str(item) for item in openapi.get("endpoints", [])],
            report_presets=[str(item) for item in openapi.get("report_presets", [])],
            platforms=[str(item) for item in cfg.get("platforms", [])],
            page_size=int(openapi.get("page_size") or 100),
        )
        snapshots = []
    elif source == "openapi_mock_execute":
        accounts = _load_configured_accounts(cfg, db_path=db_path)
        days = _configured_days(cfg)
        openapi = cfg.get("openapi") if isinstance(cfg.get("openapi"), dict) else {}
        fixture_responses = openapi.get("fixture_responses")
        if not fixture_responses:
            raise ValueError("openapi_mock_execute requires openapi.fixture_responses")
        request_plan = build_openapi_readonly_plan(
            accounts=accounts,
            dates=days,
            endpoints=[str(item) for item in openapi.get("endpoints", [])],
            report_presets=[str(item) for item in openapi.get("report_presets", [])],
            platforms=[str(item) for item in cfg.get("platforms", [])],
            page_size=int(openapi.get("page_size") or 100),
        )
        execution_result = execute_openapi_readonly_plan(
            request_plan,
            transport=_fixture_transport_from_file(str(fixture_responses)),
        )
        snapshots = [
            _write_payload_snapshot(snapshot_dir, snapshot_payload)
            for snapshot_payload in build_snapshots_from_execution(execution_result)
        ]
    elif source == "openapi_http_execute":
        accounts = _load_configured_accounts(cfg, db_path=db_path)
        days = _configured_days(cfg)
        openapi = cfg.get("openapi") if isinstance(cfg.get("openapi"), dict) else {}
        openapi_http = cfg.get("openapi_http") if isinstance(cfg.get("openapi_http"), dict) else {}
        request_plan = build_openapi_readonly_plan(
            accounts=accounts,
            dates=days,
            endpoints=[str(item) for item in openapi.get("endpoints", [])],
            report_presets=[str(item) for item in openapi.get("report_presets", [])],
            platforms=[str(item) for item in cfg.get("platforms", [])],
            page_size=int(openapi.get("page_size") or 100),
        )
        response_dir = Path(openapi_http.get("response_audit_dir") or Path(runs_dir) / "openapi_http")
        transport = build_http_transport(
            openapi_http,
            response_dir=response_dir,
            opener=http_opener,
            sleeper=http_sleeper,
        )
        execution_result = execute_openapi_readonly_plan(request_plan, transport=transport)
        snapshots = [
            _write_payload_snapshot(snapshot_dir, snapshot_payload)
            for snapshot_payload in build_snapshots_from_execution(execution_result)
        ]
    else:
        raise ValueError(f"unsupported report fetch source: {source}")

    summary = {
        "mode": str(cfg.get("mode") or "backfill"),
        "source": source,
        "product": str(cfg.get("product") or ""),
        "platforms": [str(item) for item in cfg.get("platforms", [])],
        "account_count": len(accounts) if accounts else sum(item.get("account_count", 0) for item in snapshots),
        "date_count": len(days) if days else len(snapshots),
        "snapshots_written": len(snapshots),
    }
    if request_plan is not None:
        summary["planned_request_count"] = request_plan["summary"]["planned_request_count"]
    if source in {"openapi_mock_execute", "openapi_http_execute"} and execution_result is not None:
        summary["transport_calls"] = execution_result["summary"]["transport_calls"]
        summary["rows_received"] = execution_result["summary"]["rows_received"]
    external_api_calls = 0
    if source == "openapi_http_execute" and execution_result is not None:
        external_api_calls = int(execution_result["summary"]["transport_calls"])

    payload = {
        "ok": True,
        "workflow": "report_fetch",
        "phase": "phase1",
        "mode": str(cfg.get("mode") or "backfill"),
        "source": source,
        "execution_enabled": False,
        "external_api_calls": external_api_calls,
        "summary": summary,
        "snapshots": snapshots,
    }
    if request_plan is not None:
        payload["request_plan"] = request_plan
    if source in {"openapi_mock_execute", "openapi_http_execute"}:
        payload["execution_result"] = execution_result
    artifact = write_run_artifact(runs_dir, "report_fetch", payload)
    return {**payload, "artifact_path": str(artifact)}
