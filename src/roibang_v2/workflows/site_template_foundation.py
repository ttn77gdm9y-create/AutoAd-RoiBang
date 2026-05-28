from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from roibang_v2.runs import write_run_artifact
from roibang_v2.workflows.create_http_transport import build_create_http_transport


Transport = Callable[[dict[str, Any]], dict[str, Any]]

SITE_TEMPLATE_CREATE_ENDPOINT = "/open_api/2/tools/site_template/create/"
SITE_TEMPLATE_GET_ENDPOINT = "/open_api/2/tools/site_template/get/"
SITE_TEMPLATE_SITE_CREATE_ENDPOINT = "/open_api/2/tools/site_template/site/create/"
SITE_PUBLISH_ENDPOINT = "/open_api/2/tools/site/update_status/"
DEFAULT_SITE_BASE_URL = "https://ad.oceanengine.com"


def _cfg(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("site_template_foundation")
    return dict(value) if isinstance(value, dict) else dict(request)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _api_id(value: Any) -> Any:
    text = _text(value)
    return int(text) if text.isdigit() else text


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _split_targets(value: Any) -> list[str]:
    raw_items = value if isinstance(value, list) else str(value or "").replace("\n", ",").split(",")
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


def _site_mappings_from_artifact(path: str | Path) -> list[dict[str, str]]:
    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(f"site mapping artifact not found: {source}")
    payload = json.loads(source.read_text(encoding="utf-8"))
    rows = payload.get("success_list") if isinstance(payload.get("success_list"), list) else []
    result: list[dict[str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        advertiser_id = _text(row.get("target_advertiser_id") or row.get("advertiser_id"))
        site_id = _text(row.get("site_id"))
        if advertiser_id and site_id:
            result.append({"advertiser_id": advertiser_id, "site_id": site_id})
    return result


def _site_targets_from_cfg(cfg: dict[str, Any]) -> list[dict[str, str]]:
    mappings: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for row in cfg.get("sites") or cfg.get("mappings") or []:
        if not isinstance(row, dict):
            continue
        advertiser_id = _text(row.get("advertiser_id") or row.get("target_advertiser_id") or row.get("account_id"))
        site_id = _text(row.get("site_id"))
        if not advertiser_id:
            continue
        key = (advertiser_id, site_id)
        if key in seen:
            continue
        seen.add(key)
        mappings.append({"advertiser_id": advertiser_id, "site_id": site_id})
    artifact_path = _text(cfg.get("site_mapping_artifact") or cfg.get("handsel_artifact"))
    if artifact_path:
        for row in _site_mappings_from_artifact(artifact_path):
            key = (row["advertiser_id"], row["site_id"])
            if key in seen:
                continue
            seen.add(key)
            mappings.append(row)
    return mappings


def _target_accounts_from_cfg(cfg: dict[str, Any]) -> list[str]:
    targets = _split_targets(cfg.get("target_advertiser_ids") or cfg.get("target_accounts") or cfg.get("targets"))
    target_accounts_path = _text(cfg.get("target_accounts_path") or cfg.get("target_advertiser_ids_path"))
    if target_accounts_path:
        existing = set(targets)
        for item in _targets_from_file(target_accounts_path):
            if item not in existing:
                targets.append(item)
                existing.add(item)
    return targets


def _transport_config(config: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:
    source = config.get("create_http_transport") if isinstance(config.get("create_http_transport"), dict) else {}
    result = dict(source)
    result["base_url"] = _text(cfg.get("base_url")) or _text(config.get("site_template_base_url")) or DEFAULT_SITE_BASE_URL
    return result


def _code(response: dict[str, Any]) -> int:
    try:
        return int(response.get("code", 0))
    except (TypeError, ValueError):
        return -1


def _data(response: dict[str, Any]) -> dict[str, Any]:
    return response.get("data") if isinstance(response.get("data"), dict) else {}


def _rows(response: dict[str, Any]) -> list[dict[str, Any]]:
    rows = _data(response).get("list")
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _bricks_from_response(response: dict[str, Any]) -> list[dict[str, Any]]:
    data = _data(response)
    if isinstance(data.get("bricks"), list):
        return [row for row in data["bricks"] if isinstance(row, dict)]
    rows = _rows(response)
    if rows and isinstance(rows[0].get("bricks"), list):
        return [row for row in rows[0]["bricks"] if isinstance(row, dict)]
    return []


def find_wechat_game_index(bricks: list[dict[str, Any]]) -> str:
    for brick in bricks:
        brick_type = _text(brick.get("type") or brick.get("name") or brick.get("component_type"))
        if brick_type in {"WECHAT_GAME", "XrWechatGame", "wechat_game"} or isinstance(brick.get("wechat_game"), dict):
            return _text(brick.get("index"))
    return ""


def build_wechat_game_brick(*, index: str, game_path: str, instance_id: str = "") -> dict[str, Any]:
    wechat_game: dict[str, Any] = {"game_path": game_path}
    if instance_id:
        wechat_game["instance_id"] = int(instance_id) if instance_id.isdigit() else instance_id
    return {"type": "WECHAT_GAME", "index": index, "wechat_game": wechat_game}


def _site_name(cfg: dict[str, Any], advertiser_id: str, index: int) -> str:
    explicit = _text(cfg.get("site_name"))
    if explicit:
        return explicit
    prefix = _text(cfg.get("site_name_prefix")) or "点点英雄本地落地页"
    return f"{prefix}-{advertiser_id}-{index + 1:03d}"


def build_site_template_foundation_plan(request: dict[str, Any]) -> dict[str, Any]:
    cfg = _cfg(request)
    source_advertiser_id = _text(cfg.get("source_advertiser_id") or cfg.get("advertiser_id"))
    source_site_id = _text(cfg.get("source_site_id") or cfg.get("site_id"))
    template_id = _text(cfg.get("template_id"))
    template_name = _text(cfg.get("template_name")) or "点点英雄本地基础落地页模板"
    wechat_game_index = _text(cfg.get("wechat_game_index") or cfg.get("game_component_index"))
    game_path = _text(cfg.get("game_path"))
    game_instance_id = _text(cfg.get("game_instance_id") or cfg.get("instance_id") or cfg.get("micro_app_instance_id"))
    publish = _as_bool(cfg.get("publish"), True)
    execute = _as_bool(cfg.get("execute"), False)
    edit_existing = _as_bool(cfg.get("edit_existing"), False)
    site_targets = _site_targets_from_cfg(cfg)
    target_advertiser_ids = _target_accounts_from_cfg(cfg)
    if edit_existing:
        target_items = site_targets
    else:
        target_items = [{"advertiser_id": item, "site_id": ""} for item in target_advertiser_ids]

    blocking_reasons: list[str] = []
    if not source_advertiser_id and not template_id:
        blocking_reasons.append("missing source_advertiser_id or template_id")
    if not source_site_id and not template_id:
        blocking_reasons.append("missing source_site_id or template_id")
    if not game_path:
        blocking_reasons.append("missing game_path")
    if not game_instance_id:
        blocking_reasons.append("missing game_instance_id")
    if template_id and not wechat_game_index and not source_advertiser_id:
        blocking_reasons.append("missing source_advertiser_id to look up template component index")
    if not target_items:
        blocking_reasons.append("missing target_advertiser_ids or sites")
    if edit_existing and any(not item.get("site_id") for item in target_items):
        blocking_reasons.append("edit_existing requires site_id for every target")

    requests: list[dict[str, Any]] = []
    if not template_id:
        requests.append(
            {
                "operation": "create_site_template",
                "endpoint": SITE_TEMPLATE_CREATE_ENDPOINT,
                "payload": {
                    "advertiser_id": _api_id(source_advertiser_id),
                    "site_id": _api_id(source_site_id),
                    "template_name": template_name,
                },
            }
        )
    if template_id and not wechat_game_index:
        requests.append(
            {
                "operation": "get_site_template",
                "endpoint": SITE_TEMPLATE_GET_ENDPOINT,
                "payload": {
                    "advertiser_id": _api_id(source_advertiser_id),
                    "filter": {"template_ids": [_api_id(template_id)]},
                    "page": 1,
                    "page_size": 20,
                },
            }
        )
    planned_template_id = template_id or "<created_template_id>"
    planned_index = wechat_game_index or "<wechat_game_index>"
    for index, item in enumerate(target_items):
        payload: dict[str, Any] = {
            "advertiser_id": _api_id(item["advertiser_id"]),
            "template_id": _api_id(planned_template_id),
            "name": _site_name(cfg, item["advertiser_id"], index),
            "bricks": [
                build_wechat_game_brick(
                    index=planned_index,
                    game_path=game_path,
                    instance_id=game_instance_id,
                )
            ],
        }
        if edit_existing:
            payload["site_id"] = _api_id(item["site_id"])
        requests.append(
            {
                "operation": "create_site_from_template",
                "endpoint": SITE_TEMPLATE_SITE_CREATE_ENDPOINT,
                "payload": payload,
            }
        )
        if publish:
            requests.append(
                {
                    "operation": "publish_site",
                    "endpoint": SITE_PUBLISH_ENDPOINT,
                    "payload": {
                        "advertiser_id": _api_id(item["advertiser_id"]),
                        "site_ids": [_api_id(item["site_id"]) if item["site_id"] else "<created_site_id>"],
                        "status": "published",
                    },
                }
            )

    return {
        "ok": not blocking_reasons,
        "workflow": "site_template_foundation",
        "phase": "plan" if not execute else "execute",
        "status": "blocked" if blocking_reasons else ("ready_to_execute" if execute else "planned"),
        "execution_enabled": execute,
        "external_api_calls": 0,
        "blocking_reasons": blocking_reasons,
        "summary": {
            "source_advertiser_id": source_advertiser_id,
            "source_site_id": source_site_id,
            "template_id": template_id,
            "template_name": template_name,
            "wechat_game_index": wechat_game_index,
            "game_instance_id": game_instance_id,
            "game_path": game_path,
            "target_count": len(target_items),
            "publish": publish,
            "edit_existing": edit_existing,
        },
        "targets": target_items,
        "requests": requests,
        "readable_reference": {
            "用途": "用橙子建站模板给目标账户创建或修复本地落地页，并只补微信小游戏路径参数。",
            "源账户": source_advertiser_id,
            "源站点": source_site_id,
            "模板ID": template_id or "执行时创建",
            "微信小游戏组件位置": wechat_game_index or "执行时从模板返回中识别",
            "路径参数": game_path,
            "目标账户数": len(target_items),
            "执行方式": "真实执行" if execute else "dry-run（预演）",
        },
    }


def _resolve_template(
    *,
    plan: dict[str, Any],
    cfg: dict[str, Any],
    transport: Transport,
    responses: list[dict[str, Any]],
) -> tuple[str, str]:
    template_id = _text(plan["summary"].get("template_id"))
    wechat_game_index = _text(plan["summary"].get("wechat_game_index"))
    bricks: list[dict[str, Any]] = []

    if not template_id:
        response = transport(
            {
                "operation": "create_site_template",
                "endpoint": SITE_TEMPLATE_CREATE_ENDPOINT,
                "payload": {
                    "advertiser_id": _api_id(plan["summary"]["source_advertiser_id"]),
                    "site_id": _api_id(plan["summary"]["source_site_id"]),
                    "template_name": plan["summary"]["template_name"],
                },
            }
        )
        responses.append({"step": "create_site_template", "response": response})
        if _code(response) != 0:
            raise RuntimeError(_text(response.get("message")) or f"create_site_template failed code={_code(response)}")
        data = _data(response)
        template_id = _text(data.get("template_id"))
        bricks = _bricks_from_response(response)
        if not template_id:
            raise RuntimeError("create_site_template response missing template_id")

    if not wechat_game_index:
        if not bricks:
            response = transport(
                {
                    "operation": "get_site_template",
                    "endpoint": SITE_TEMPLATE_GET_ENDPOINT,
                    "payload": {
                        "advertiser_id": _api_id(plan["summary"]["source_advertiser_id"]),
                        "filter": {"template_ids": [_api_id(template_id)]},
                        "page": 1,
                        "page_size": 20,
                    },
                }
            )
            responses.append({"step": "get_site_template", "response": response})
            if _code(response) != 0:
                raise RuntimeError(_text(response.get("message")) or f"get_site_template failed code={_code(response)}")
            bricks = _bricks_from_response(response)
        wechat_game_index = find_wechat_game_index(bricks)
        if not wechat_game_index:
            raise RuntimeError("WECHAT_GAME component index not found in site template")

    return template_id, wechat_game_index


def run_site_template_foundation_request(
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
    plan = build_site_template_foundation_plan(request)
    if plan["blocking_reasons"] or not plan["execution_enabled"]:
        artifact = write_run_artifact(runs_dir, "site_template_foundation", plan)
        plan["artifact_path"] = str(artifact)
        artifact.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return plan

    real_transport = transport or build_create_http_transport(
        _transport_config(config, cfg),
        response_dir=Path(runs_dir) / "openapi_http" / "site-template-foundation",
        opener=http_opener,
        oauth_opener=oauth_opener,
        sleeper=http_sleeper,
    )

    responses: list[dict[str, Any]] = []
    successes: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    try:
        template_id, wechat_game_index = _resolve_template(
            plan=plan,
            cfg=cfg,
            transport=real_transport,
            responses=responses,
        )
    except Exception as exc:
        errors.append({"step": "resolve_template", "error_reason": str(exc)})
        template_id = _text(plan["summary"].get("template_id"))
        wechat_game_index = _text(plan["summary"].get("wechat_game_index"))

    if not errors:
        for index, item in enumerate(plan["targets"]):
            advertiser_id = item["advertiser_id"]
            site_id = item.get("site_id") or ""
            try:
                create_payload: dict[str, Any] = {
                    "advertiser_id": _api_id(advertiser_id),
                    "template_id": _api_id(template_id),
                    "name": _site_name(cfg, advertiser_id, index),
                    "bricks": [
                        build_wechat_game_brick(
                            index=wechat_game_index,
                            game_path=plan["summary"]["game_path"],
                            instance_id=plan["summary"]["game_instance_id"],
                        )
                    ],
                }
                if plan["summary"]["edit_existing"]:
                    create_payload["site_id"] = _api_id(site_id)
                create_response = real_transport(
                    {
                        "operation": "create_site_from_template",
                        "endpoint": SITE_TEMPLATE_SITE_CREATE_ENDPOINT,
                        "payload": create_payload,
                    }
                )
                responses.append(
                    {
                        "advertiser_id": advertiser_id,
                        "site_id": site_id,
                        "step": "create_site_from_template",
                        "response": create_response,
                    }
                )
                if _code(create_response) != 0:
                    raise RuntimeError(
                        _text(create_response.get("message"))
                        or f"create_site_from_template failed code={_code(create_response)}"
                    )
                created_site_id = _text(_data(create_response).get("site_id")) or site_id
                if not created_site_id:
                    raise RuntimeError("create_site_from_template response missing site_id")

                publish_response: dict[str, Any] | None = None
                if plan["summary"]["publish"]:
                    publish_response = real_transport(
                        {
                            "operation": "publish_site",
                            "endpoint": SITE_PUBLISH_ENDPOINT,
                            "payload": {
                                "advertiser_id": _api_id(advertiser_id),
                                "site_ids": [_api_id(created_site_id)],
                                "status": "published",
                            },
                        }
                    )
                    responses.append(
                        {
                            "advertiser_id": advertiser_id,
                            "site_id": created_site_id,
                            "step": "publish_site",
                            "response": publish_response,
                        }
                    )
                    if _code(publish_response) != 0:
                        raise RuntimeError(
                            _text(publish_response.get("message"))
                            or f"publish_site failed code={_code(publish_response)}"
                        )

                successes.append(
                    {
                        "advertiser_id": advertiser_id,
                        "site_id": created_site_id,
                        "template_id": template_id,
                        "wechat_game_index": wechat_game_index,
                        "game_instance_id": plan["summary"]["game_instance_id"],
                        "game_path": plan["summary"]["game_path"],
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
            "template_id": template_id,
            "wechat_game_index": wechat_game_index,
            "success_count": len(successes),
            "error_count": len(errors),
        },
        "success_list": successes,
        "error_list": errors,
        "responses": responses,
        "readable_reference": {
            **plan["readable_reference"],
            "模板ID": template_id,
            "微信小游戏组件位置": wechat_game_index,
            "成功数": len(successes),
            "失败数": len(errors),
            "新站点": [{"advertiser_id": row["advertiser_id"], "site_id": row["site_id"]} for row in successes],
            "失败原因": errors,
        },
    }
    artifact = write_run_artifact(runs_dir, "site_template_foundation", result)
    result["artifact_path"] = str(artifact)
    artifact.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result
