from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Callable

from roibang_v2.runs import write_run_artifact
from roibang_v2.workflows.create_http_transport import build_create_http_transport


Transport = Callable[[dict[str, Any]], dict[str, Any]]

SITE_READ_ENDPOINT = "/open_api/2/tools/site/read/"
SITE_UPDATE_ENDPOINT = "/open_api/2/tools/site/update/"
SITE_PUBLISH_ENDPOINT = "/open_api/2/tools/site/update_status/"
WECHAT_GAME_LIST_ENDPOINT = "/open_api/v3.0/tools/wechat_game/list/"
SITE_BASE_URL = "https://ad.oceanengine.com"
API_BASE_URL = "https://api.oceanengine.com"


def _cfg(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("site_game_path_update")
    return dict(value) if isinstance(value, dict) else dict(request)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _mappings_from_artifact(path: str | Path) -> list[dict[str, str]]:
    data = _load_json(path)
    rows = data.get("success_list") if isinstance(data.get("success_list"), list) else []
    mappings: list[dict[str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        advertiser_id = _text(row.get("target_advertiser_id") or row.get("advertiser_id"))
        site_id = _text(row.get("site_id"))
        if advertiser_id and site_id:
            mappings.append({"advertiser_id": advertiser_id, "site_id": site_id})
    return mappings


def _mappings_from_cfg(cfg: dict[str, Any]) -> list[dict[str, str]]:
    mappings: list[dict[str, str]] = []
    for row in cfg.get("sites") or cfg.get("mappings") or []:
        if not isinstance(row, dict):
            continue
        advertiser_id = _text(row.get("advertiser_id") or row.get("target_advertiser_id") or row.get("account_id"))
        site_id = _text(row.get("site_id"))
        if advertiser_id and site_id:
            mappings.append({"advertiser_id": advertiser_id, "site_id": site_id})
    artifact_path = _text(cfg.get("handsel_artifact") or cfg.get("artifact_path"))
    if artifact_path:
        existing = {(row["advertiser_id"], row["site_id"]) for row in mappings}
        for row in _mappings_from_artifact(artifact_path):
            key = (row["advertiser_id"], row["site_id"])
            if key not in existing:
                mappings.append(row)
                existing.add(key)
    advertiser_id = _text(cfg.get("advertiser_id") or cfg.get("account_id"))
    site_id = _text(cfg.get("site_id"))
    if advertiser_id and site_id and (advertiser_id, site_id) not in {
        (row["advertiser_id"], row["site_id"]) for row in mappings
    }:
        mappings.append({"advertiser_id": advertiser_id, "site_id": site_id})
    return mappings


def _transport_config(config: dict[str, Any], *, base_url: str) -> dict[str, Any]:
    source = config.get("create_http_transport") if isinstance(config.get("create_http_transport"), dict) else {}
    result = dict(source)
    result["base_url"] = base_url
    return result


def _rows(response: dict[str, Any]) -> list[dict[str, Any]]:
    data = response.get("data") if isinstance(response.get("data"), dict) else {}
    for key in ("list", "rows", "items"):
        value = data.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]
    return []


def _game_instance_id(response: dict[str, Any], game_name: str) -> str:
    rows = _rows(response)
    if not rows:
        return ""
    normalized_name = game_name.strip()
    candidates = []
    for row in rows:
        name = _text(row.get("name") or row.get("app_name") or row.get("remark") or row.get("asset_name"))
        if not normalized_name or normalized_name in name:
            candidates.append(row)
    selected = candidates[0] if candidates else rows[0]
    for key in ("instance_id", "id", "asset_id", "micro_app_instance_id"):
        value = _text(selected.get(key))
        if value:
            return value
    for key in ("wechat_game", "wechat_applet", "asset"):
        nested = selected.get(key)
        if isinstance(nested, dict):
            for nested_key in ("instance_id", "id", "asset_id", "micro_app_instance_id"):
                value = _text(nested.get(nested_key))
                if value:
                    return value
    return ""


def _search_types(value: Any) -> list[str]:
    raw_items = value if isinstance(value, list) else str(value or "").replace("\n", ",").split(",")
    items = [_text(item) for item in raw_items]
    result = [item for item in items if item]
    return result or ["CREATE_ONLY", "SHARE_ONLY"]


def _walk_bricks(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_bricks(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_bricks(child)


def _is_wechat_game_component(item: dict[str, Any]) -> bool:
    names = {
        _text(item.get("name")),
        _text(item.get("type")),
        _text(item.get("component_type")),
    }
    return bool(names & {"XrWechatGame", "WECHAT_GAME", "wechat_game"})


def update_wechat_game_bricks(bricks: Any, *, game_path: str, instance_id: str = "") -> tuple[Any, int]:
    updated = copy.deepcopy(bricks)
    count = 0
    for item in _walk_bricks(updated):
        if not _is_wechat_game_component(item):
            continue
        item["game_path"] = game_path
        if instance_id:
            try:
                item["instance_id"] = int(instance_id)
            except ValueError:
                item["instance_id"] = instance_id
        count += 1
    return updated, count


COLOR_FIELD_KEYS = {
    "background_color",
    "bg_color",
    "border_color",
    "buttonBackColor",
    "buttonForeColor",
    "color",
    "positioningColor",
    "radioColor",
}


def normalize_site_update_bricks(value: Any) -> Any:
    if isinstance(value, list):
        return [normalize_site_update_bricks(item) for item in value]
    if not isinstance(value, dict):
        return value
    normalized: dict[str, Any] = {}
    for key, child in value.items():
        if key in COLOR_FIELD_KEYS and isinstance(child, dict) and "color" in child:
            normalized[key] = _text(child.get("color"))
            continue
        normalized[key] = normalize_site_update_bricks(child)
    return normalized


def build_site_game_path_update_plan(request: dict[str, Any]) -> dict[str, Any]:
    cfg = _cfg(request)
    game_path = _text(cfg.get("game_path"))
    game_name = _text(cfg.get("game_name")) or "点点英雄"
    mappings = _mappings_from_cfg(cfg)
    execute = _as_bool(cfg.get("execute"), False)
    publish = _as_bool(cfg.get("publish"), True)
    allow_unsafe_full_site_update = _as_bool(cfg.get("allow_unsafe_full_site_update"), False)
    lookup_game_instance = _as_bool(cfg.get("lookup_game_instance"), True)
    instance_id = _text(cfg.get("instance_id"))
    game_search_types = _search_types(cfg.get("game_search_types"))
    blocking_reasons: list[str] = []
    if not game_path:
        blocking_reasons.append("missing game_path")
    if not mappings:
        blocking_reasons.append("missing sites or handsel_artifact")
    if execute and not allow_unsafe_full_site_update:
        blocking_reasons.append(
            "unsafe full site update is disabled; use site_template_foundation instead"
        )
    return {
        "ok": not blocking_reasons,
        "workflow": "site_game_path_update",
        "phase": "plan" if not execute else "execute",
        "status": "blocked" if blocking_reasons else ("ready_to_execute" if execute else "planned"),
        "execution_enabled": execute,
        "external_api_calls": 0,
        "blocking_reasons": blocking_reasons,
        "summary": {
            "site_count": len(mappings),
            "game_name": game_name,
            "game_path": game_path,
            "publish": publish,
            "allow_unsafe_full_site_update": allow_unsafe_full_site_update,
            "lookup_game_instance": lookup_game_instance,
            "instance_id": instance_id,
            "game_search_types": game_search_types,
        },
        "sites": mappings,
        "readable_reference": {
            "用途": "给转赠后的橙子落地页补微信小游戏路径参数。",
            "小游戏": game_name,
            "路径参数": game_path,
            "站点数": len(mappings),
            "安全提示": "该旧入口会全量更新站点，可能导致图片等组件丢失；默认禁止真实执行。",
            "执行方式": "真实执行" if execute else "dry-run（预演）",
        },
    }


def run_site_game_path_update_request(
    request: dict[str, Any],
    *,
    config: dict[str, Any],
    runs_dir: str | Path = "data/runs",
    site_transport: Transport | None = None,
    api_transport: Transport | None = None,
    http_opener=None,
    oauth_opener=None,
    http_sleeper=None,
) -> dict[str, Any]:
    plan = build_site_game_path_update_plan(request)
    if plan["blocking_reasons"] or not plan["execution_enabled"]:
        artifact = write_run_artifact(runs_dir, "site_game_path_update", plan)
        plan["artifact_path"] = str(artifact)
        artifact.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return plan

    real_site_transport = site_transport or build_create_http_transport(
        _transport_config(config, base_url=SITE_BASE_URL),
        response_dir=Path(runs_dir) / "openapi_http" / "site-game-path-update-site",
        opener=http_opener,
        oauth_opener=oauth_opener,
        sleeper=http_sleeper,
    )
    real_api_transport = api_transport or build_create_http_transport(
        _transport_config(config, base_url=API_BASE_URL),
        response_dir=Path(runs_dir) / "openapi_http" / "site-game-path-update-api",
        opener=http_opener,
        oauth_opener=oauth_opener,
        sleeper=http_sleeper,
    )

    successes: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    responses: list[dict[str, Any]] = []
    for site in plan["sites"]:
        advertiser_id = site["advertiser_id"]
        site_id = site["site_id"]
        try:
            instance_id = _text(site.get("instance_id")) or _text(plan["summary"].get("instance_id"))
            if plan["summary"]["lookup_game_instance"] and not instance_id:
                for search_type in plan["summary"]["game_search_types"]:
                    game_response = real_api_transport(
                        {
                            "operation": "list_wechat_game",
                            "endpoint": WECHAT_GAME_LIST_ENDPOINT,
                            "payload": {
                                "account_id": advertiser_id,
                                "account_type": "AD",
                                "filtering": {
                                    "name": plan["summary"]["game_name"],
                                    "audit_status": "AUDIT_ACCEPTED",
                                    "search_type": search_type,
                                },
                                "page": 1,
                                "page_size": 100,
                            },
                        }
                    )
                    responses.append(
                        {
                            "advertiser_id": advertiser_id,
                            "site_id": site_id,
                            "step": "list_wechat_game",
                            "search_type": search_type,
                            "response": game_response,
                        }
                    )
                    instance_id = _game_instance_id(game_response, plan["summary"]["game_name"])
                    if instance_id:
                        break
                if not instance_id:
                    raise RuntimeError("wechat game instance_id not found")

            read_response = real_site_transport(
                {
                    "operation": "read_site",
                    "endpoint": SITE_READ_ENDPOINT,
                    "payload": {"advertiser_id": advertiser_id, "site_id": site_id},
                }
            )
            responses.append({"advertiser_id": advertiser_id, "site_id": site_id, "step": "read_site", "response": read_response})
            data = read_response.get("data") if isinstance(read_response.get("data"), dict) else {}
            bricks = data.get("bricks")
            updated_bricks, updated_count = update_wechat_game_bricks(
                bricks,
                game_path=plan["summary"]["game_path"],
                instance_id=instance_id,
            )
            updated_bricks = normalize_site_update_bricks(updated_bricks)
            if updated_count == 0:
                raise RuntimeError("XrWechatGame component not found in site bricks")

            update_payload: dict[str, Any] = {
                "advertiser_id": advertiser_id,
                "site_id": site_id,
                "bricks": updated_bricks,
            }
            name = _text(data.get("name"))
            if name:
                update_payload["name"] = name
            update_response = real_site_transport(
                {"operation": "update_site", "endpoint": SITE_UPDATE_ENDPOINT, "payload": update_payload}
            )
            responses.append({"advertiser_id": advertiser_id, "site_id": site_id, "step": "update_site", "response": update_response})
            try:
                update_code = int(update_response.get("code", 0))
            except (TypeError, ValueError):
                update_code = -1
            if update_code != 0:
                raise RuntimeError(_text(update_response.get("message")) or f"site update failed code={update_code}")

            publish_response: dict[str, Any] | None = None
            if plan["summary"]["publish"]:
                publish_response = real_site_transport(
                    {
                        "operation": "publish_site",
                        "endpoint": SITE_PUBLISH_ENDPOINT,
                        "payload": {"advertiser_id": advertiser_id, "site_ids": [site_id], "status": "published"},
                    }
                )
                responses.append({"advertiser_id": advertiser_id, "site_id": site_id, "step": "publish_site", "response": publish_response})
                try:
                    publish_code = int(publish_response.get("code", 0))
                except (TypeError, ValueError):
                    publish_code = -1
                if publish_code != 0:
                    raise RuntimeError(_text(publish_response.get("message")) or f"site publish failed code={publish_code}")

            successes.append(
                {
                    "advertiser_id": advertiser_id,
                    "site_id": site_id,
                    "instance_id": instance_id,
                    "game_path": plan["summary"]["game_path"],
                    "updated_component_count": updated_count,
                    "published": bool(plan["summary"]["publish"]),
                }
            )
        except Exception as exc:
            errors.append({"advertiser_id": advertiser_id, "site_id": site_id, "error_reason": str(exc)})

    status = "completed" if not errors else ("partial" if successes else "failed")
    result = {
        **plan,
        "ok": not errors,
        "phase": "execute",
        "status": status,
        "external_api_calls": len(responses),
        "summary": {
            **plan["summary"],
            "success_count": len(successes),
            "error_count": len(errors),
        },
        "success_list": successes,
        "error_list": errors,
        "responses": responses,
        "readable_reference": {
            **plan["readable_reference"],
            "成功数": len(successes),
            "失败数": len(errors),
            "失败原因": errors,
        },
    }
    artifact = write_run_artifact(runs_dir, "site_game_path_update", result)
    result["artifact_path"] = str(artifact)
    artifact.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result
