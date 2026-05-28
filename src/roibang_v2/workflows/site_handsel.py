from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from roibang_v2.runs import write_run_artifact
from roibang_v2.workflows.create_http_transport import build_create_http_transport


Transport = Callable[[dict[str, Any]], dict[str, Any]]

SITE_HANDSEL_ENDPOINT = "/open_api/2/tools/site/handsel/"
DEFAULT_SITE_BASE_URL = "https://ad.oceanengine.com"
MAX_TARGETS_PER_REQUEST = 20


def _cfg(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("site_handsel")
    return dict(value) if isinstance(value, dict) else dict(request)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _split_targets(value: Any) -> list[str]:
    if isinstance(value, list):
        raw_items = value
    else:
        raw_items = str(value or "").replace("\n", ",").split(",")
    targets: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        target = _text(item)
        if not target or target in seen:
            continue
        seen.add(target)
        targets.append(target)
    return targets


def _targets_from_file(path: str | Path) -> list[str]:
    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(f"target accounts file not found: {source}")
    return _split_targets(source.read_text(encoding="utf-8"))


def _chunks(items: list[str], size: int) -> list[list[str]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def build_site_handsel_plan(request: dict[str, Any]) -> dict[str, Any]:
    cfg = _cfg(request)
    source_advertiser_id = _text(cfg.get("source_advertiser_id") or cfg.get("advertiser_id"))
    site_id = _text(cfg.get("site_id") or cfg.get("landing_site_id"))
    target_accounts_path = _text(cfg.get("target_accounts_path") or cfg.get("target_advertiser_ids_path"))
    target_advertiser_ids = _split_targets(
        cfg.get("target_advertiser_ids") or cfg.get("target_accounts") or cfg.get("targets")
    )
    if target_accounts_path:
        target_advertiser_ids.extend(
            item for item in _targets_from_file(target_accounts_path) if item not in set(target_advertiser_ids)
        )
    execute = bool(cfg.get("execute", False))

    blocking_reasons: list[str] = []
    if not source_advertiser_id:
        blocking_reasons.append("missing source_advertiser_id")
    if not site_id:
        blocking_reasons.append("missing site_id")
    if not target_advertiser_ids:
        blocking_reasons.append("missing target_advertiser_ids")
    if source_advertiser_id and source_advertiser_id in target_advertiser_ids:
        blocking_reasons.append("target_advertiser_ids cannot contain source_advertiser_id")

    batches = _chunks(target_advertiser_ids, MAX_TARGETS_PER_REQUEST)
    requests = [
        {
            "operation": "handsel_site",
            "endpoint": SITE_HANDSEL_ENDPOINT,
            "payload": {
                "advertiser_id": source_advertiser_id,
                "site_ids": [site_id],
                "target_advertiser_ids": batch,
            },
        }
        for batch in batches
    ]
    return {
        "ok": not blocking_reasons,
        "workflow": "site_handsel",
        "phase": "plan" if not execute else "execute",
        "status": "blocked" if blocking_reasons else ("ready_to_execute" if execute else "planned"),
        "execution_enabled": execute,
        "external_api_calls": 0,
        "blocking_reasons": blocking_reasons,
        "summary": {
            "source_advertiser_id": source_advertiser_id,
            "site_id": site_id,
            "target_count": len(target_advertiser_ids),
            "batch_count": len(batches),
            "max_targets_per_request": MAX_TARGETS_PER_REQUEST,
        },
        "target_advertiser_ids": target_advertiser_ids,
        "requests": requests,
        "readable_reference": {
            "用途": "把一个橙子建站站点转赠到一批目标账户。",
            "源账户": source_advertiser_id,
            "源站点": site_id,
            "目标账户数": len(target_advertiser_ids),
            "执行方式": "真实执行" if execute else "dry-run（预演）",
        },
    }


def _transport_config(config: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:
    source = config.get("create_http_transport") if isinstance(config.get("create_http_transport"), dict) else {}
    result = dict(source)
    result["base_url"] = _text(cfg.get("base_url")) or _text(config.get("site_handsel_base_url")) or DEFAULT_SITE_BASE_URL
    return result


def _response_rows(response: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    data = response.get("data") if isinstance(response.get("data"), dict) else {}
    success = data.get("success_list") if isinstance(data.get("success_list"), list) else []
    errors = data.get("error_list") if isinstance(data.get("error_list"), list) else []
    return [row for row in success if isinstance(row, dict)], [row for row in errors if isinstance(row, dict)]


def run_site_handsel_request(
    request: dict[str, Any],
    *,
    config: dict[str, Any],
    runs_dir: str | Path = "data/runs",
    transport: Transport | None = None,
    http_opener=None,
    oauth_opener=None,
    http_sleeper=None,
) -> dict[str, Any]:
    cfg = _cfg(request)
    plan = build_site_handsel_plan(request)
    if plan["blocking_reasons"] or not plan["execution_enabled"]:
        artifact = write_run_artifact(runs_dir, "site_handsel", plan)
        plan["artifact_path"] = str(artifact)
        artifact.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return plan

    response_dir = Path(runs_dir) / "openapi_http" / "site-handsel"
    real_transport = transport or build_create_http_transport(
        _transport_config(config, cfg),
        response_dir=response_dir,
        opener=http_opener,
        oauth_opener=oauth_opener,
        sleeper=http_sleeper,
    )

    responses: list[dict[str, Any]] = []
    success_rows: list[dict[str, Any]] = []
    error_rows: list[dict[str, Any]] = []
    for item in plan["requests"]:
        response = real_transport(item)
        responses.append({"request": item, "response": response})
        success, errors = _response_rows(response)
        success_rows.extend(success)
        error_rows.extend(errors)
        try:
            code = int(response.get("code", 0))
        except (TypeError, ValueError):
            code = -1
        if code != 0 and not errors:
            error_rows.append(
                {
                    "origin_site_id": plan["summary"]["site_id"],
                    "target_advertiser_id": "",
                    "error_reason": _text(response.get("message")) or f"OpenAPI response code={code}",
                }
            )

    success_count = len(success_rows)
    error_count = len(error_rows)
    status = "completed" if error_count == 0 else ("partial" if success_count else "failed")
    result = {
        **plan,
        "ok": error_count == 0,
        "phase": "execute",
        "status": status,
        "external_api_calls": len(responses),
        "summary": {
            **plan["summary"],
            "success_count": success_count,
            "error_count": error_count,
        },
        "success_list": success_rows,
        "error_list": error_rows,
        "responses": responses,
        "readable_reference": {
            **plan["readable_reference"],
            "成功数": success_count,
            "失败数": error_count,
            "新站点": [
                {
                    "target_advertiser_id": _text(row.get("target_advertiser_id")),
                    "site_id": _text(row.get("site_id")),
                }
                for row in success_rows
            ],
            "失败原因": [
                {
                    "target_advertiser_id": _text(row.get("target_advertiser_id")),
                    "reason": _text(row.get("error_reason")),
                }
                for row in error_rows
            ],
        },
    }
    artifact = write_run_artifact(runs_dir, "site_handsel", result)
    result["artifact_path"] = str(artifact)
    artifact.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result
