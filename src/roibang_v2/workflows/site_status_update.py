from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable

from roibang_v2.runs import write_run_artifact
from roibang_v2.workflows.create_http_transport import build_create_http_transport


Transport = Callable[[dict[str, Any]], dict[str, Any]]

SITE_STATUS_ENDPOINT = "/open_api/2/tools/site/update_status/"
DEFAULT_SITE_BASE_URL = "https://ad.oceanengine.com"
MAX_SITE_IDS_PER_REQUEST = 20
ALLOWED_STATUSES = {"published", "unpublished", "delete", "undeleted"}


def _cfg(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("site_status_update")
    return dict(value) if isinstance(value, dict) else dict(request)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _to_api_id(value: Any) -> int | str:
    text = _text(value)
    return int(text) if text.isdigit() else text


def _chunks(items: list[str], size: int) -> list[list[str]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def _split_ids(value: Any) -> list[str]:
    if isinstance(value, list):
        raw_items = value
    else:
        raw_items = str(value or "").replace("\n", ",").split(",")
    ids: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        identifier = _text(item)
        if not identifier or identifier in seen:
            continue
        seen.add(identifier)
        ids.append(identifier)
    return ids


def _pairs_from_handsel_artifact(path: str | Path) -> list[dict[str, str]]:
    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(f"handsel artifact not found: {source}")
    payload = json.loads(source.read_text(encoding="utf-8"))
    success_list = payload.get("success_list") if isinstance(payload.get("success_list"), list) else []
    pairs: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for row in success_list:
        if not isinstance(row, dict):
            continue
        advertiser_id = _text(row.get("target_advertiser_id") or row.get("advertiser_id"))
        site_id = _text(row.get("site_id"))
        if not advertiser_id or not site_id or (advertiser_id, site_id) in seen:
            continue
        seen.add((advertiser_id, site_id))
        pairs.append({"advertiser_id": advertiser_id, "site_id": site_id})
    return pairs


def _pairs_from_cfg(cfg: dict[str, Any]) -> list[dict[str, str]]:
    handsel_artifact = _text(cfg.get("handsel_artifact") or cfg.get("handsel_artifact_path"))
    if handsel_artifact:
        return _pairs_from_handsel_artifact(handsel_artifact)
    pairs = cfg.get("site_pairs") if isinstance(cfg.get("site_pairs"), list) else []
    result: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for row in pairs:
        if not isinstance(row, dict):
            continue
        advertiser_id = _text(row.get("advertiser_id") or row.get("target_advertiser_id"))
        site_id = _text(row.get("site_id"))
        if not advertiser_id or not site_id or (advertiser_id, site_id) in seen:
            continue
        seen.add((advertiser_id, site_id))
        result.append({"advertiser_id": advertiser_id, "site_id": site_id})
    advertiser_id = _text(cfg.get("advertiser_id"))
    site_ids = _split_ids(cfg.get("site_ids"))
    for site_id in site_ids:
        if advertiser_id and (advertiser_id, site_id) not in seen:
            seen.add((advertiser_id, site_id))
            result.append({"advertiser_id": advertiser_id, "site_id": site_id})
    return result


def build_site_status_update_plan(request: dict[str, Any]) -> dict[str, Any]:
    cfg = _cfg(request)
    execute = bool(cfg.get("execute", False))
    status = _text(cfg.get("status") or "delete").lower()
    pairs = _pairs_from_cfg(cfg)

    blocking_reasons: list[str] = []
    if status not in ALLOWED_STATUSES:
        blocking_reasons.append(f"unsupported status: {status}")
    if not pairs:
        blocking_reasons.append("missing site pairs")

    grouped: dict[str, list[str]] = defaultdict(list)
    for pair in pairs:
        grouped[pair["advertiser_id"]].append(pair["site_id"])

    requests: list[dict[str, Any]] = []
    for advertiser_id in sorted(grouped):
        for site_ids in _chunks(grouped[advertiser_id], MAX_SITE_IDS_PER_REQUEST):
            requests.append(
                {
                    "operation": "update_site_status",
                    "endpoint": SITE_STATUS_ENDPOINT,
                    "payload": {
                        "advertiser_id": _to_api_id(advertiser_id),
                        "site_ids": [_to_api_id(site_id) for site_id in site_ids],
                        "status": status,
                    },
                }
            )

    return {
        "ok": not blocking_reasons,
        "workflow": "site_status_update",
        "phase": "plan" if not execute else "execute",
        "status": "blocked" if blocking_reasons else ("ready_to_execute" if execute else "planned"),
        "execution_enabled": execute,
        "external_api_calls": 0,
        "blocking_reasons": blocking_reasons,
        "summary": {
            "status": status,
            "advertiser_count": len(grouped),
            "site_count": len(pairs),
            "request_count": len(requests),
            "max_site_ids_per_request": MAX_SITE_IDS_PER_REQUEST,
        },
        "site_pairs": pairs,
        "requests": requests,
        "readable_reference": {
            "用途": "批量更改橙子建站站点状态。",
            "目标状态": status,
            "账户数": len(grouped),
            "站点数": len(pairs),
            "执行方式": "真实执行" if execute else "dry-run（预演）",
        },
    }


def _transport_config(config: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:
    source = config.get("create_http_transport") if isinstance(config.get("create_http_transport"), dict) else {}
    result = dict(source)
    result["base_url"] = (
        _text(cfg.get("base_url"))
        or _text(config.get("site_status_update_base_url"))
        or DEFAULT_SITE_BASE_URL
    )
    return result


def _response_rows(response: dict[str, Any]) -> tuple[list[str], list[dict[str, Any]]]:
    data = response.get("data") if isinstance(response.get("data"), dict) else {}
    success = data.get("success") if isinstance(data.get("success"), list) else []
    fail = data.get("fail") if isinstance(data.get("fail"), list) else []
    return [_text(item) for item in success if _text(item)], [row for row in fail if isinstance(row, dict)]


def run_site_status_update_request(
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
    plan = build_site_status_update_plan(request)
    if plan["blocking_reasons"] or not plan["execution_enabled"]:
        artifact = write_run_artifact(runs_dir, "site_status_update", plan)
        plan["artifact_path"] = str(artifact)
        artifact.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return plan

    response_dir = Path(runs_dir) / "openapi_http" / "site-status-update"
    real_transport = transport or build_create_http_transport(
        _transport_config(config, cfg),
        response_dir=response_dir,
        opener=http_opener,
        oauth_opener=oauth_opener,
        sleeper=http_sleeper,
    )

    responses: list[dict[str, Any]] = []
    success_rows: list[dict[str, str]] = []
    error_rows: list[dict[str, str]] = []
    for item in plan["requests"]:
        response = real_transport(item)
        responses.append({"request": item, "response": response})
        success, fail = _response_rows(response)
        advertiser_id = _text(item["payload"].get("advertiser_id"))
        for site_id in success:
            success_rows.append({"advertiser_id": advertiser_id, "site_id": site_id, "status": plan["summary"]["status"]})
        for row in fail:
            error_rows.append(
                {
                    "advertiser_id": advertiser_id,
                    "site_id": _text(row.get("site_id")),
                    "message": _text(row.get("message")) or _text(response.get("message")),
                }
            )
        try:
            code = int(response.get("code", 0))
        except (TypeError, ValueError):
            code = -1
        if code != 0 and not fail:
            error_rows.append(
                {
                    "advertiser_id": advertiser_id,
                    "site_id": "",
                    "message": _text(response.get("message")) or f"OpenAPI response code={code}",
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
            "失败原因": error_rows,
        },
    }
    artifact = write_run_artifact(runs_dir, "site_status_update", result)
    result["artifact_path"] = str(artifact)
    artifact.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result
