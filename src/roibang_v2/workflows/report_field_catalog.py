from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from roibang_v2.accounts.pool import import_accounts_csv, select_accounts
from roibang_v2.fetch.openapi_http import build_http_transport
from roibang_v2.fetch.openapi_readonly import REPORT_PRESETS
from roibang_v2.fetch.openapi_readonly import build_readonly_request
from roibang_v2.runs import write_run_artifact


def _workflow_config(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("report_field_catalog")
    return dict(value) if isinstance(value, dict) else dict(request)


def _configured_accounts(cfg: dict[str, Any], *, db_path: str | Path) -> list[dict[str, Any]]:
    account_pool_csv = cfg.get("account_pool_csv")
    if account_pool_csv:
        import_accounts_csv(account_pool_csv, db_path=db_path)
    platforms = [str(item) for item in cfg.get("platforms", [])]
    accounts = select_accounts(db_path=db_path, product=str(cfg["product"]), platforms=platforms)
    account_ids = [str(item) for item in cfg.get("account_ids", [])] if isinstance(cfg.get("account_ids"), list) else []
    if account_ids:
        by_id = {account["advertiser_id"]: account for account in accounts}
        accounts = [by_id[item] for item in account_ids if item in by_id]
    return accounts


def _data_topics(cfg: dict[str, Any]) -> list[str]:
    topics = [str(item) for item in cfg.get("data_topics", [])] if isinstance(cfg.get("data_topics"), list) else []
    return topics or sorted({str(preset["data_topic"]) for preset in REPORT_PRESETS.values()})


def _sample_advertiser_id(cfg: dict[str, Any], accounts: list[dict[str, Any]]) -> str:
    configured = str(cfg.get("sample_advertiser_id") or "").strip()
    if configured:
        return configured
    if not accounts:
        raise ValueError("report_field_catalog requires at least one configured account or sample_advertiser_id")
    return str(accounts[0]["advertiser_id"])


def _request(cfg: dict[str, Any], *, db_path: str | Path) -> tuple[dict[str, Any], list[dict[str, Any]], list[str], str]:
    accounts = _configured_accounts(cfg, db_path=db_path)
    topics = _data_topics(cfg)
    advertiser_id = _sample_advertiser_id(cfg, accounts)
    return (
        build_readonly_request(
            "report_custom_config",
            {
                "advertiser_id": advertiser_id,
                "data_topics": topics,
            },
        ),
        accounts,
        topics,
        advertiser_id,
    )


def build_report_field_catalog_preflight(
    request: dict[str, Any],
    *,
    db_path: str | Path,
    runs_dir: str | Path,
) -> dict[str, Any]:
    cfg = _workflow_config(request)
    _readonly_request, accounts, topics, advertiser_id = _request(cfg, db_path=db_path)
    payload = {
        "ok": True,
        "workflow": "report_field_catalog_preflight",
        "phase": "phase1",
        "execution_enabled": False,
        "external_api_calls": 0,
        "summary": {
            "account_count": len(accounts),
            "sample_advertiser_id": advertiser_id,
            "data_topics": topics,
            "planned_request_count": 1,
        },
    }
    artifact = write_run_artifact(runs_dir, "report_field_catalog_preflight", payload)
    return {**payload, "artifact_path": str(artifact)}


def _field_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "field": str(item.get("field") or ""),
        "name": str(item.get("name") or ""),
        "description": str(item.get("description") or ""),
        "filter_able": bool(item.get("filter_able", False)),
        "sort_able": bool(item.get("sort_able", False)),
    }


def _extract_catalog(response: dict[str, Any]) -> dict[str, Any]:
    data = response.get("data") if isinstance(response.get("data"), dict) else {}
    items = data.get("list") if isinstance(data.get("list"), list) else []
    topics: dict[str, Any] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        topic = str(item.get("data_topic") or "")
        if not topic:
            continue
        dimensions = [_field_item(value) for value in item.get("dimensions", []) if isinstance(value, dict)]
        metrics = [_field_item(value) for value in item.get("metrics", []) if isinstance(value, dict)]
        topics[topic] = {
            "dimensions": dimensions,
            "metrics": metrics,
            "dimension_fields": [value["field"] for value in dimensions if value["field"]],
            "metric_fields": [value["field"] for value in metrics if value["field"]],
        }
    return {"topics": topics}


def _raise_for_api_error(response: dict[str, Any]) -> None:
    code = response.get("code")
    if code in (None, "", 0, "0"):
        return
    raise RuntimeError(f"OpenAPI response code={code}: {response.get('message') or response.get('msg') or ''}")


def _validate_presets(catalog: dict[str, Any]) -> dict[str, Any]:
    topics = catalog.get("topics") if isinstance(catalog.get("topics"), dict) else {}
    results: dict[str, Any] = {}
    for preset_name, preset in REPORT_PRESETS.items():
        topic = str(preset.get("data_topic") or "")
        topic_catalog = topics.get(topic) if isinstance(topics.get(topic), dict) else {}
        dimensions = set(topic_catalog.get("dimension_fields") or [])
        metrics = set(topic_catalog.get("metric_fields") or [])
        missing_dimensions = [str(item) for item in preset.get("dimensions", []) if str(item) not in dimensions]
        missing_metrics = [str(item) for item in preset.get("metrics", []) if str(item) not in metrics]
        results[preset_name] = {
            "data_topic": topic,
            "ok": not missing_dimensions and not missing_metrics,
            "missing_dimensions": missing_dimensions,
            "missing_metrics": missing_metrics,
        }
    return results


def _validation_ok(validation: dict[str, Any]) -> bool:
    return all(bool(item.get("ok")) for item in validation.values() if isinstance(item, dict))


def run_report_field_catalog_request(
    request: dict[str, Any],
    *,
    db_path: str | Path,
    runs_dir: str | Path,
    transport=None,
    http_opener=None,
    http_sleeper=None,
) -> dict[str, Any]:
    cfg = _workflow_config(request)
    readonly_request, accounts, topics, advertiser_id = _request(cfg, db_path=db_path)
    if transport is None:
        openapi_http = cfg.get("openapi_http") if isinstance(cfg.get("openapi_http"), dict) else {}
        response_dir = Path(openapi_http.get("response_audit_dir") or Path(runs_dir) / "openapi_http" / "report-field-catalog")
        transport = build_http_transport(
            openapi_http,
            response_dir=response_dir,
            opener=http_opener,
            sleeper=http_sleeper,
        )
    response = transport(readonly_request)
    _raise_for_api_error(response)
    catalog = _extract_catalog(response)
    validation = _validate_presets(catalog) if bool(cfg.get("validate_presets", True)) else {}
    preset_ok = _validation_ok(validation) if validation else True
    payload = {
        "ok": preset_ok,
        "workflow": "report_field_catalog",
        "phase": "phase1",
        "execution_enabled": False,
        "external_api_calls": 1,
        "summary": {
            "account_count": len(accounts),
            "sample_advertiser_id": advertiser_id,
            "data_topics": topics,
            "topic_count": len(catalog["topics"]),
            "preset_validation_ok": preset_ok,
        },
        "request": {
            **deepcopy(readonly_request),
            "headers": {"Access-Token": "<redacted>"},
        },
        "catalog": catalog,
        "preset_validation": validation,
    }
    artifact = write_run_artifact(runs_dir, "report_field_catalog", payload)
    return {**payload, "artifact_path": str(artifact)}
