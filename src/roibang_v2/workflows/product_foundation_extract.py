from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from roibang_v2.fetch.openapi_executor import execute_openapi_readonly_plan
from roibang_v2.fetch.openapi_http import build_http_transport
from roibang_v2.fetch.openapi_readonly import build_readonly_request
from roibang_v2.runs import write_run_artifact


Transport = Callable[[dict[str, Any]], dict[str, Any]]


FOUNDATION_FIELDS = [
    "effective_touch_url",
    "anchor_id",
    "anchor_type",
    "anchor_related_type",
    "landing_url",
    "product_image_id",
    "fixed_video_cover_id",
    "micro_app_instance_id",
    "micro_promotion_type",
]


def _cfg(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("product_foundation_extract")
    return dict(value) if isinstance(value, dict) else dict(request)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _path_text(path: tuple[str, ...]) -> str:
    return ".".join(path)


def _walk(value: Any, path: tuple[str, ...] = ()):
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _walk(child, (*path, str(key)))
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk(child, (*path, str(index)))
        return
    yield path, value


def _records(rows: list[dict[str, Any]], source: str) -> list[tuple[tuple[str, ...], Any]]:
    records: list[tuple[tuple[str, ...], Any]] = []
    for index, row in enumerate(rows):
        for path, value in _walk(row, (source, str(index))):
            records.append((path, value))
    return records


def _path_has(path: tuple[str, ...], token: str) -> bool:
    return any(part == token for part in path)


def _last_key(path: tuple[str, ...]) -> str:
    return path[-1] if path else ""


def _candidate(
    records: list[tuple[tuple[str, ...], Any]],
    *,
    field: str,
    matcher: Callable[[tuple[str, ...], Any], bool],
) -> dict[str, Any]:
    candidates: list[dict[str, str]] = []
    for path, value in records:
        text = _text(value)
        if not text or not matcher(path, value):
            continue
        candidates.append({"value": text, "source_path": _path_text(path)})
    selected = candidates[0]["value"] if candidates else ""
    return {
        "field": field,
        "value": selected,
        "source_path": candidates[0]["source_path"] if candidates else "",
        "candidate_count": len(candidates),
        "candidates": candidates[:20],
    }


def extract_product_foundation(
    *,
    project_rows: list[dict[str, Any]],
    promotion_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    records = _records(project_rows, "project_rows") + _records(promotion_rows, "promotion_rows")
    candidate_specs = {
        "effective_touch_url": lambda path, _value: (
            (_last_key(path) in {"url", "effective_touch_url"} and _path_has(path, "mini_program_info"))
            or _last_key(path) in {"effective_touch_url", "action_track_url"}
        ),
        "anchor_id": lambda path, _value: _last_key(path) == "anchor_id",
        "anchor_type": lambda path, _value: _last_key(path) == "anchor_type",
        "anchor_related_type": lambda path, _value: _last_key(path) == "anchor_related_type",
        "landing_url": lambda path, _value: (
            _path_has(path, "external_url_material_list")
            or _last_key(path) in {"landing_url", "open_url", "ulink_url"}
        ),
        "product_image_id": lambda path, _value: (
            _path_has(path, "image_ids")
            or _last_key(path) in {"product_image_id", "image_id"}
            or (_last_key(path) == "uri" and _path_has(path, "product_info"))
        ),
        "fixed_video_cover_id": lambda path, _value: _last_key(path) in {"fixed_video_cover_id", "video_cover_id"},
        "micro_app_instance_id": lambda path, _value: (
            _last_key(path) == "micro_app_instance_id"
            or (_last_key(path) == "app_id" and _path_has(path, "mini_program_info"))
        ),
        "micro_promotion_type": lambda path, _value: _last_key(path) in {"micro_promotion_type", "app_type", "mini_program_type"},
    }
    evidence = {
        field: _candidate(records, field=field, matcher=matcher)
        for field, matcher in candidate_specs.items()
    }
    foundation = {field: evidence[field]["value"] for field in FOUNDATION_FIELDS}
    missing = [field for field in FOUNDATION_FIELDS if not foundation.get(field)]
    return {
        "foundation": foundation,
        "field_evidence": evidence,
        "missing_fields": missing,
    }


def _build_plan(*, advertiser_id: str, project_id: str) -> dict[str, Any]:
    account_ref = {"advertiser_id": advertiser_id}
    requests = [
        {
            "account": account_ref,
            **build_readonly_request(
                "project_list",
                {
                    "advertiser_id": advertiser_id,
                    "filtering": {"ids": [project_id]},
                    "page": 1,
                    "page_size": 20,
                },
            ),
        },
        {
            "account": account_ref,
            **build_readonly_request(
                "promotion_list",
                {
                    "advertiser_id": advertiser_id,
                    "filtering": {"project_id": project_id},
                    "page": 1,
                    "page_size": 20,
                },
            ),
        },
    ]
    return {
        "ok": True,
        "workflow": "product_foundation_extract_plan",
        "phase": "readonly_extract",
        "execution_enabled": False,
        "external_api_calls": 0,
        "requests": requests,
        "summary": {
            "advertiser_id": advertiser_id,
            "project_id": project_id,
            "planned_request_count": len(requests),
        },
    }


def _rows_by_endpoint(execution: dict[str, Any], endpoint_key: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in execution.get("responses") or []:
        if not isinstance(item, dict):
            continue
        request = item.get("request") if isinstance(item.get("request"), dict) else {}
        if str(request.get("endpoint_key") or "") != endpoint_key:
            continue
        rows.extend([row for row in item.get("rows") or [] if isinstance(row, dict)])
    return rows


def build_product_foundation_draft(
    *,
    cfg: dict[str, Any],
    execution: dict[str, Any],
) -> dict[str, Any]:
    project_rows = _rows_by_endpoint(execution, "project_list")
    promotion_rows = _rows_by_endpoint(execution, "promotion_list")
    extracted = extract_product_foundation(project_rows=project_rows, promotion_rows=promotion_rows)
    product_key = _text(cfg.get("product_key")) or "diandian-hero"
    product = _text(cfg.get("product")) or "点点英雄"
    source_advertiser_id = _text(cfg.get("source_advertiser_id")) or _text(cfg.get("advertiser_id"))
    draft = {
        "product_key": product_key,
        "product": product,
        "platform": _text(cfg.get("platform")) or "WECHAT_GAME",
        "source_advertiser_id": source_advertiser_id,
        "organization_id": _text(cfg.get("organization_id")),
        "allowed_target_accounts_path": _text(cfg.get("allowed_target_accounts_path")),
        "account_remark_pattern": _text(cfg.get("account_remark_pattern")),
        "foundation": extracted["foundation"],
    }
    return {
        "draft": draft,
        "project_rows": project_rows,
        "promotion_rows": promotion_rows,
        **extracted,
    }


def run_product_foundation_extract_request(
    request: dict[str, Any],
    *,
    config: dict[str, Any],
    runs_dir: str | Path = "data/runs",
    transport: Transport | None = None,
    http_opener=None,
    http_sleeper=None,
) -> dict[str, Any]:
    cfg = _cfg(request)
    advertiser_id = _text(cfg.get("advertiser_id") or cfg.get("source_advertiser_id"))
    project_id = _text(cfg.get("project_id"))
    blocking_reasons: list[str] = []
    if not advertiser_id:
        blocking_reasons.append("missing advertiser_id/source_advertiser_id")
    if not project_id:
        blocking_reasons.append("missing project_id")
    if blocking_reasons:
        result = {
            "ok": False,
            "workflow": "product_foundation_extract",
            "phase": "readonly_extract",
            "status": "blocked",
            "execution_enabled": False,
            "external_api_calls": 0,
            "blocking_reasons": blocking_reasons,
            "summary": {"advertiser_id": advertiser_id, "project_id": project_id},
        }
        artifact = write_run_artifact(runs_dir, "product_foundation_extract", result)
        result["artifact_path"] = str(artifact)
        artifact.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return result

    openapi_http = config.get("openapi_http") if isinstance(config.get("openapi_http"), dict) else {}
    if not openapi_http:
        openapi_http = config.get("create_http_transport") if isinstance(config.get("create_http_transport"), dict) else {}
    response_dir = Path(runs_dir) / "openapi_http" / "product-foundation-extract"
    real_transport = transport or build_http_transport(
        openapi_http,
        response_dir=openapi_http.get("response_audit_dir") or response_dir,
        opener=http_opener,
        sleeper=http_sleeper,
    )
    plan = _build_plan(advertiser_id=advertiser_id, project_id=project_id)
    execution = execute_openapi_readonly_plan(
        {"requests": plan["requests"]},
        transport=real_transport,
        retry_api_codes=list(openapi_http.get("retry_api_codes") or [40100]),
        max_api_retries=int(openapi_http.get("max_api_retries") or 2),
        retry_sleep_seconds=float(openapi_http.get("retry_sleep_seconds") or 2),
        sleeper=http_sleeper,
    )
    draft_payload = build_product_foundation_draft(cfg=cfg, execution=execution)
    missing_fields = list(draft_payload["missing_fields"])
    status = "extracted" if not missing_fields else "partial"
    summary = {
        "product": _text(cfg.get("product")) or "点点英雄",
        "product_key": _text(cfg.get("product_key")) or "diandian-hero",
        "advertiser_id": advertiser_id,
        "project_id": project_id,
        "project_count": len(draft_payload["project_rows"]),
        "promotion_count": len(draft_payload["promotion_rows"]),
        "missing_field_count": len(missing_fields),
        "missing_fields": missing_fields,
    }
    readable_reference = {
        "用途": "从已有项目和单元只读抽取新产品基础字段，供人工确认后写入产品配置。",
        "产品": summary["product"],
        "源素材账户": advertiser_id,
        "参考项目": project_id,
        "已抽取字段": draft_payload["draft"]["foundation"],
        "缺失字段": missing_fields,
        "下一步": "确认字段正确后，再用 product_config_publish（产品配置发布）生成本地产品配置。",
    }
    result = {
        "ok": True,
        "workflow": "product_foundation_extract",
        "phase": "readonly_extract",
        "status": status,
        "execution_enabled": False,
        "external_api_calls": int(execution["summary"]["transport_calls"]),
        "blocking_reasons": [],
        "summary": summary,
        "draft": draft_payload["draft"],
        "field_evidence": draft_payload["field_evidence"],
        "readable_reference": readable_reference,
        "raw_counts": {
            "project_rows": len(draft_payload["project_rows"]),
            "promotion_rows": len(draft_payload["promotion_rows"]),
        },
    }
    artifact = write_run_artifact(runs_dir, "product_foundation_extract", result)
    result["artifact_path"] = str(artifact)
    artifact.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result
