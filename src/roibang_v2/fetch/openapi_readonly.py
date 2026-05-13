from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


API_HOST = "https://api.oceanengine.com"


@dataclass(frozen=True)
class ReadOnlyEndpoint:
    key: str
    name: str
    method: str
    path: str
    host: str = API_HOST


READONLY_ENDPOINTS: dict[str, ReadOnlyEndpoint] = {
    "report_custom_config": ReadOnlyEndpoint(
        key="report_custom_config",
        name="获取自定义报表可用指标和维度",
        method="GET",
        path="/open_api/v3.0/report/custom/config/get/",
    ),
    "report_custom": ReadOnlyEndpoint(
        key="report_custom",
        name="自定义报表",
        method="GET",
        path="/open_api/v3.0/report/custom/get/",
    ),
    "project_list": ReadOnlyEndpoint(
        key="project_list",
        name="获取项目列表",
        method="GET",
        path="/open_api/v3.0/project/list/",
    ),
    "promotion_list": ReadOnlyEndpoint(
        key="promotion_list",
        name="获取单元列表",
        method="GET",
        path="/open_api/v3.0/promotion/list/",
    ),
    "account_video_material_get": ReadOnlyEndpoint(
        key="account_video_material_get",
        name="获取同主体下客户视频素材",
        method="GET",
        path="/open_api/2/file/video/ad/get/",
    ),
    "video_material_get": ReadOnlyEndpoint(
        key="video_material_get",
        name="获取视频素材",
        method="GET",
        path="/open_api/2/file/video/get/",
    ),
    "ebp_video_material_get": ReadOnlyEndpoint(
        key="ebp_video_material_get",
        name="获取账户可用的组织视频列表",
        method="GET",
        path="/open_api/v3.0/file/ebp_video/get/",
    ),
    "material_attributes_list": ReadOnlyEndpoint(
        key="material_attributes_list",
        name="获取视频素材评估标签",
        method="GET",
        path="/open_api/2/file/material_attributes/list/",
    ),
    "operation_log_search": ReadOnlyEndpoint(
        key="operation_log_search",
        name="操作日志查询",
        method="GET",
        host="https://ad.oceanengine.com",
        path="/open_api/2/tools/log_search/",
    ),
}


ENDPOINT_MAX_PAGE_SIZE: dict[str, int] = {
    "promotion_list": 20,
}


MUTATION_MARKERS = {
    "add",
    "adjust",
    "apply",
    "bind",
    "budget",
    "create",
    "delete",
    "disable",
    "enable",
    "execute",
    "pause",
    "push",
    "resume",
    "schedule",
    "status",
    "stop",
    "update",
    "upload",
}


REPORT_PRESETS: dict[str, dict[str, Any]] = {
    "account_daily": {
        "data_topic": "BASIC_DATA",
        "dimensions": ["stat_time_day"],
        "metrics": [
            "stat_cost",
            "show_cnt",
            "click_cnt",
            "convert_cnt",
            "attribution_convert_cnt",
            "attribution_convert_cost",
            "attribution_billing_game_in_app_ltv_1day",
            "attribution_billing_game_in_app_roi_1day",
        ],
    },
    "project_daily": {
        "data_topic": "BASIC_DATA",
        "dimensions": ["stat_time_day", "cdp_project_id", "cdp_project_name"],
        "metrics": [
            "stat_cost",
            "show_cnt",
            "click_cnt",
            "convert_cnt",
            "attribution_convert_cnt",
            "attribution_convert_cost",
            "attribution_billing_game_in_app_ltv_1day",
            "attribution_billing_game_in_app_roi_1day",
        ],
    },
    "project_hourly": {
        "data_topic": "BASIC_DATA",
        "dimensions": ["stat_time_hour", "cdp_project_id", "cdp_project_name"],
        "metrics": [
            "stat_cost",
            "show_cnt",
            "click_cnt",
            "convert_cnt",
            "attribution_billing_game_in_app_roi_1day",
        ],
    },
    "promotion_daily": {
        "data_topic": "BASIC_DATA",
        "dimensions": ["stat_time_day", "cdp_project_id", "cdp_project_name", "cdp_promotion_id", "cdp_promotion_name"],
        "metrics": [
            "stat_cost",
            "show_cnt",
            "click_cnt",
            "convert_cnt",
            "attribution_convert_cnt",
            "attribution_convert_cost",
            "attribution_billing_game_in_app_ltv_1day",
            "attribution_billing_game_in_app_roi_1day",
        ],
    },
    "material_daily": {
        "data_topic": "MATERIAL_DATA",
        "max_page_size": 20,
        "dimensions": [
            "stat_time_day",
            "cdp_project_id",
            "cdp_project_name",
            "cdp_promotion_id",
            "cdp_promotion_name",
            "material_id",
        ],
        "metrics": [
            "stat_cost",
            "show_cnt",
            "click_cnt",
            "convert_cnt",
            "attribution_convert_cnt",
            "attribution_convert_cost",
            "attribution_billing_game_in_app_ltv_1day",
            "attribution_billing_game_in_app_roi_1day",
            "attribution_billing_game_in_app_roi_7days",
        ],
    },
}


def _compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _encode_query_params(params: dict[str, Any]) -> dict[str, str]:
    encoded: dict[str, str] = {}
    for key, value in params.items():
        if value is None:
            continue
        if isinstance(value, bool):
            encoded[key] = "true" if value else "false"
        elif isinstance(value, int | float | str):
            encoded[key] = str(value)
        else:
            encoded[key] = _compact_json(value)
    return encoded


def validate_readonly_endpoint(endpoint_key: str) -> ReadOnlyEndpoint:
    key = endpoint_key.strip()
    marker_source = key.lower().replace("-", "_").replace("/", "_")
    markers = {part for part in marker_source.split("_") if part}
    if markers & MUTATION_MARKERS:
        raise ValueError(f"endpoint is not read-only: {endpoint_key}")
    endpoint = READONLY_ENDPOINTS.get(key)
    if endpoint is None:
        raise ValueError(f"endpoint is not in readonly allowlist: {endpoint_key}")
    if endpoint.method != "GET":
        raise ValueError(f"readonly endpoint must use GET: {endpoint_key}")
    return endpoint


def build_readonly_request(endpoint_key: str, params: dict[str, Any]) -> dict[str, Any]:
    endpoint = validate_readonly_endpoint(endpoint_key)
    return {
        "endpoint_key": endpoint.key,
        "name": endpoint.name,
        "method": endpoint.method,
        "host": endpoint.host,
        "path": endpoint.path,
        "url": endpoint.host + endpoint.path,
        "headers": {"Access-Token": "<redacted>"},
        "query_params": _encode_query_params(params),
    }


def _configured_endpoints(endpoints: list[str] | None) -> list[str]:
    configured = endpoints or ["report_custom_config", "report_custom", "project_list", "promotion_list"]
    return [validate_readonly_endpoint(item).key for item in configured]


def _configured_presets(report_presets: list[str] | None) -> list[str]:
    configured = report_presets or ["promotion_daily"]
    unknown = [item for item in configured if item not in REPORT_PRESETS]
    if unknown:
        raise ValueError(f"unknown report preset: {', '.join(unknown)}")
    return configured


def _report_filters(_platforms: list[str]) -> list[dict[str, Any]]:
    return []


def _report_topics(report_presets: list[str]) -> list[str]:
    topics = {str(REPORT_PRESETS[preset]["data_topic"]) for preset in report_presets}
    return sorted(topics)


def _daily_log_window(target_date: str) -> dict[str, str]:
    return {
        "start_time": f"{target_date} 00:00:00",
        "end_time": f"{target_date} 23:59:59",
    }


def build_openapi_readonly_plan(
    *,
    accounts: list[dict[str, Any]],
    dates: list[str],
    endpoints: list[str] | None = None,
    report_presets: list[str] | None = None,
    platforms: list[str] | None = None,
    page_size: int = 100,
) -> dict[str, Any]:
    endpoint_keys = _configured_endpoints(endpoints)
    preset_keys = _configured_presets(report_presets)
    target_platforms = [str(item) for item in platforms or []]
    requests: list[dict[str, Any]] = []

    for target_date in dates:
        for account in accounts:
            advertiser_id = str(account["advertiser_id"])
            account_ref = {
                "advertiser_id": advertiser_id,
                "account_name": str(account.get("account_name") or ""),
                "product": str(account.get("product") or ""),
                "platform": str(account.get("platform") or ""),
            }
            for endpoint_key in endpoint_keys:
                if endpoint_key == "report_custom_config":
                    requests.append(
                        {
                            "date": target_date,
                            "account": account_ref,
                            **build_readonly_request(
                                endpoint_key,
                                {
                                    "advertiser_id": advertiser_id,
                                    "data_topics": _report_topics(preset_keys),
                                },
                            ),
                        }
                    )
                elif endpoint_key == "report_custom":
                    for preset_key in preset_keys:
                        preset = REPORT_PRESETS[preset_key]
                        preset_page_size = min(page_size, int(preset.get("max_page_size") or page_size))
                        requests.append(
                            {
                                "date": target_date,
                                "account": account_ref,
                                "report_preset": preset_key,
                                **build_readonly_request(
                                    endpoint_key,
                                    {
                                        "advertiser_id": advertiser_id,
                                        "data_topic": preset["data_topic"],
                                        "dimensions": preset["dimensions"],
                                        "metrics": preset["metrics"],
                                        "filters": _report_filters(target_platforms),
                                        "start_time": target_date,
                                        "end_time": target_date,
                                        "order_by": [{"field": "stat_cost", "type": "DESC"}],
                                        "page": 1,
                                        "page_size": preset_page_size,
                                    },
                                ),
                            }
                        )
                elif endpoint_key == "operation_log_search":
                    requests.append(
                        {
                            "date": target_date,
                            "account": account_ref,
                            **build_readonly_request(
                                endpoint_key,
                                {
                                    "advertiser_id": advertiser_id,
                                    **_daily_log_window(target_date),
                                    "page": 1,
                                    "page_size": min(page_size, 20),
                                },
                            ),
                        }
                    )
                else:
                    endpoint_page_size = min(page_size, ENDPOINT_MAX_PAGE_SIZE.get(endpoint_key, page_size))
                    requests.append(
                        {
                            "date": target_date,
                            "account": account_ref,
                            **build_readonly_request(
                                endpoint_key,
                                {
                                    "advertiser_id": advertiser_id,
                                    "page": 1,
                                    "page_size": endpoint_page_size,
                                },
                            ),
                        }
                    )

    return {
        "ok": True,
        "workflow": "openapi_readonly_plan",
        "phase": "phase1",
        "execution_enabled": False,
        "external_api_calls": 0,
        "summary": {
            "account_count": len(accounts),
            "date_count": len(dates),
            "endpoint_count": len(endpoint_keys),
            "report_preset_count": len(preset_keys),
            "planned_request_count": len(requests),
        },
        "endpoints": endpoint_keys,
        "report_presets": preset_keys,
        "requests": requests,
    }
