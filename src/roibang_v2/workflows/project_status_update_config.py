from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from roibang_v2.runs import write_run_artifact
from roibang_v2.workflows.project_update_execute import PROJECT_LIST_ENDPOINT


Transport = Callable[[dict[str, Any]], dict[str, Any]]
MANAGEMENT_ACTION_TYPES = {"status_update", "budget_update", "bid_update", "roi_coeff_update", "delete_project"}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _rows(value: Any) -> list[dict[str, Any]]:
    return [dict(item) for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _wire_id(value: Any) -> int | str:
    text = _text(value)
    return int(text) if text.isdigit() else text


def _required_text(cfg: dict[str, Any], key: str) -> str:
    value = _text(cfg.get(key))
    if not value:
        raise ValueError(f"project status update config requires {key}")
    return value


def _api_code(response: dict[str, Any]) -> str:
    code = response.get("code")
    return "" if code in (None, "", 0, "0") else str(code)


def _raise_for_api_error(response: dict[str, Any]) -> None:
    code = _api_code(response)
    if not code:
        return
    message = _text(response.get("message") or response.get("msg"))
    raise RuntimeError(f"OpenAPI response code={code}: {message}")


def _response_rows(response: dict[str, Any]) -> list[dict[str, Any]]:
    data = response.get("data") if isinstance(response.get("data"), dict) else {}
    for key in ["list", "rows", "data"]:
        value = data.get(key)
        if isinstance(value, list):
            return [dict(row) for row in value if isinstance(row, dict)]
    return []


def _total_number(response: dict[str, Any]) -> int:
    data = response.get("data") if isinstance(response.get("data"), dict) else {}
    page_info = data.get("page_info") if isinstance(data.get("page_info"), dict) else {}
    for key in ["total_number", "total_count", "total"]:
        try:
            value = int(page_info.get(key))
        except (TypeError, ValueError):
            continue
        return value
    return 0


def _advertiser_ids(cfg: dict[str, Any]) -> list[str]:
    values = cfg.get("advertiser_ids")
    if not isinstance(values, list):
        values = cfg.get("accounts")
    if not isinstance(values, list):
        values = []
    result: list[str] = []
    for item in values:
        if isinstance(item, dict):
            value = _text(item.get("advertiser_id") or item.get("account_id"))
        else:
            value = _text(item)
        if value:
            result.append(value)
    return result


def _action_type(cfg: dict[str, Any]) -> str:
    action_type = _text(cfg.get("action_type") or "status_update")
    if action_type not in MANAGEMENT_ACTION_TYPES:
        raise ValueError(f"project management config action_type must be one of {sorted(MANAGEMENT_ACTION_TYPES)}")
    return action_type


def _default_filtering(action_type: str, opt_status: str) -> dict[str, Any]:
    if action_type == "status_update" and opt_status == "DISABLE":
        return {"status_first": "PROJECT_STATUS_ENABLE"}
    if action_type == "status_update" and opt_status == "ENABLE":
        return {"status_first": "PROJECT_STATUS_DISABLE", "status_second": "PROJECT_STATUS_STOP"}
    if action_type == "delete_project":
        return {"status_first": "PROJECT_STATUS_DISABLE"}
    return {"status_first": "PROJECT_STATUS_ENABLE"}


def _name_contains(cfg: dict[str, Any]) -> list[str]:
    value = cfg.get("name_contains")
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, list):
        values = value
    else:
        values = []
    result: list[str] = []
    for item in values:
        for part in _text(item).split(","):
            text = part.strip()
            if text:
                result.append(text)
    return result


def _filtering_with_name(cfg: dict[str, Any], action_type: str, opt_status: str, keywords: list[str]) -> dict[str, Any]:
    filtering = dict(cfg.get("filtering")) if isinstance(cfg.get("filtering"), dict) else _default_filtering(action_type, opt_status)
    if keywords and not _text(filtering.get("name")):
        filtering["name"] = keywords[0]
    return filtering


def _name_matched(project: dict[str, Any], keywords: list[str]) -> bool:
    if not keywords:
        return True
    name = _text(project.get("name"))
    return all(keyword in name for keyword in keywords)


def _lookup_request(advertiser_id: str, filtering: dict[str, Any], *, page: int, page_size: int) -> dict[str, Any]:
    return {
        "operation": "lookup_project_list",
        "method": "GET",
        "endpoint": PROJECT_LIST_ENDPOINT,
        "payload": {
            "advertiser_id": _wire_id(advertiser_id),
            "filtering": filtering,
            "page": page,
            "page_size": page_size,
        },
    }


def _fetch_projects(
    advertiser_id: str,
    *,
    filtering: dict[str, Any],
    page_size: int,
    transport: Transport,
) -> tuple[list[dict[str, Any]], int]:
    page = 1
    calls = 0
    projects: list[dict[str, Any]] = []
    while True:
        response = transport(_lookup_request(advertiser_id, filtering, page=page, page_size=page_size))
        calls += 1
        _raise_for_api_error(response)
        rows = _response_rows(response)
        projects.extend(rows)
        total_number = _total_number(response)
        if not rows or len(rows) < page_size:
            break
        if total_number and len(projects) >= total_number:
            break
        page += 1
    return projects, calls


def _number(value: Any, key: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"project management config requires numeric {key}")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"project management config requires numeric {key}") from exc


def _action_extra_fields(cfg: dict[str, Any], action_type: str) -> dict[str, Any]:
    if action_type == "status_update":
        opt_status = _required_text(cfg, "opt_status")
        if opt_status not in {"ENABLE", "DISABLE"}:
            raise ValueError("project status update config opt_status must be ENABLE or DISABLE")
        return {"opt_status": opt_status}
    if action_type == "budget_update":
        budget_mode = _text(cfg.get("budget_mode") or "BUDGET_MODE_DAY")
        if budget_mode not in {"BUDGET_MODE_DAY", "BUDGET_MODE_INFINITE"}:
            raise ValueError("project budget update config budget_mode must be BUDGET_MODE_DAY or BUDGET_MODE_INFINITE")
        fields: dict[str, Any] = {"budget_mode": budget_mode}
        if budget_mode == "BUDGET_MODE_DAY":
            budget = _number(cfg.get("budget"), "budget")
            if budget <= 0:
                raise ValueError("project budget update config budget must be greater than 0")
            fields["budget"] = int(budget) if budget.is_integer() else budget
        return fields
    if action_type == "bid_update":
        cpa_bid = _number(cfg.get("cpa_bid"), "cpa_bid")
        if cpa_bid <= 0:
            raise ValueError("project bid update config cpa_bid must be greater than 0")
        return {"cpa_bid": int(cpa_bid) if cpa_bid.is_integer() else cpa_bid}
    if action_type == "roi_coeff_update":
        roi_goal = _number(cfg.get("roi_goal"), "roi_goal")
        if roi_goal < 0.01 or roi_goal > 5:
            raise ValueError("project roi coeff update config roi_goal must be between 0.01 and 5")
        return {"roi_goal": roi_goal}
    if action_type == "delete_project":
        return {}
    raise ValueError(f"unsupported project management action_type: {action_type}")


def _workflow_name(cfg: dict[str, Any], action_type: str) -> str:
    explicit = _text(cfg.get("workflow"))
    if explicit:
        return explicit
    if action_type == "status_update":
        return "project_status_update_config"
    return "project_management_update_config"


def _build_action(
    *,
    action_type: str,
    advertiser_id: str,
    project: dict[str, Any],
    fields: dict[str, Any],
    reason: str,
) -> dict[str, Any]:
    action = {
        "action_type": action_type,
        "advertiser_id": advertiser_id,
        "entity_type": "project",
        "project_id": _text(project.get("project_id")),
        "project_name": _text(project.get("name")),
    }
    action.update(fields)
    if reason:
        action["reason"] = reason
    return action


def build_project_status_update_config(
    request: dict[str, Any] | None,
    *,
    transport: Transport,
) -> dict[str, Any]:
    cfg = dict(request or {})
    project_update_id = _required_text(cfg, "project_update_id")
    action_type = _action_type(cfg)
    fields = _action_extra_fields(cfg, action_type)
    opt_status = _text(fields.get("opt_status"))
    advertiser_ids = _advertiser_ids(cfg)
    if not advertiser_ids:
        raise ValueError("project status update config requires advertiser_ids")
    name_keywords = _name_contains(cfg)
    filtering = _filtering_with_name(cfg, action_type, opt_status, name_keywords)
    page_size = int(cfg.get("page_size") or 100)
    reason = _text(cfg.get("reason"))
    workflow_name = _workflow_name(cfg, action_type)

    actions: list[dict[str, Any]] = []
    skipped_duration_project_count = 0
    external_api_calls = 0
    for advertiser_id in advertiser_ids:
        projects, calls = _fetch_projects(
            advertiser_id,
            filtering=filtering,
            page_size=page_size,
            transport=transport,
        )
        external_api_calls += calls
        for project in projects:
            if not _name_matched(project, name_keywords):
                continue
            project_id = _text(project.get("project_id"))
            if not project_id:
                continue
            if _text(project.get("delivery_type")) == "DURATION":
                skipped_duration_project_count += 1
                continue
            actions.append(
                _build_action(
                    action_type=action_type,
                    advertiser_id=advertiser_id,
                    project=project,
                    fields=fields,
                    reason=reason,
                )
            )

    project_update = {
        "project_update_id": project_update_id,
        "operator": _text(cfg.get("operator")),
        "source": {
            "workflow": workflow_name,
            "request": "account_project_status_control",
        },
        "allowed_target_accounts_path": _text(cfg.get("allowed_target_accounts_path")),
        "execution": {"enabled": False, "status": "planned_only"},
        "actions": actions,
        "restore_actions": [],
    }
    return {
        "ok": True,
        "workflow": workflow_name,
        "phase": "control_config",
        "status": "completed",
        "execution_enabled": False,
        "external_api_calls": external_api_calls,
        "summary": {
            "project_update_id": project_update_id,
            "target_account_count": len(advertiser_ids),
            "action_count": len(actions),
            "skipped_duration_project_count": skipped_duration_project_count,
            "action_type": action_type,
            "opt_status": opt_status,
            "name_contains": name_keywords,
        },
        "project_update": project_update,
    }


def run_project_status_update_config_request(
    request: dict[str, Any] | None,
    *,
    runs_dir: str | Path,
    transport: Transport,
) -> dict[str, Any]:
    cfg = dict(request or {})
    result = build_project_status_update_config(cfg, transport=transport)
    output_path = Path(_text(cfg.get("output_path")) or "data/runs/project_status_update_config/project_update.local.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result["project_update"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result["project_update_path"] = str(output_path)
    result["artifact_path"] = str(write_run_artifact(runs_dir, _text(result.get("workflow")) or "project_status_update_config", result))
    return result
