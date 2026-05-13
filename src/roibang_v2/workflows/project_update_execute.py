from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Callable

from roibang_v2.runs import write_run_artifact


Transport = Callable[[dict[str, Any]], dict[str, Any]]

PROJECT_LIST_ENDPOINT = "/open_api/v3.0/project/list/"
PROJECT_WEEK_SCHEDULE_UPDATE_ENDPOINT = "/open_api/v3.0/project/week_schedule/update/"
PROJECT_STATUS_UPDATE_ENDPOINT = "/open_api/v3.0/project/status/update/"
PROJECT_BUDGET_UPDATE_ENDPOINT = "/open_api/v3.0/project/budget/update/"
PROJECT_CPA_BID_UPDATE_ENDPOINT = "/open_api/v3.0/project/cpa_bid/update/"
PROJECT_ROI_GOAL_UPDATE_ENDPOINT = "/open_api/v3.0/project/roigoal/update/"
PROJECT_DELETE_ENDPOINT = "/open_api/v3.0/project/delete/"
FULL_SCHEDULE_TIME = "1" * (48 * 7)
MANAGEMENT_ACTION_OPERATIONS = {
    "status_update": ("update_project_status", PROJECT_STATUS_UPDATE_ENDPOINT),
    "budget_update": ("update_project_budget", PROJECT_BUDGET_UPDATE_ENDPOINT),
    "bid_update": ("update_project_cpa_bid", PROJECT_CPA_BID_UPDATE_ENDPOINT),
    "roi_coeff_update": ("update_project_roi_goal", PROJECT_ROI_GOAL_UPDATE_ENDPOINT),
    "delete_project": ("delete_project", PROJECT_DELETE_ENDPOINT),
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _rows(value: Any) -> list[dict[str, Any]]:
    return [dict(item) for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _chunks(items: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


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


def _normalize_schedule_time(value: Any) -> str:
    text = _text(value)
    if len(text) != len(FULL_SCHEDULE_TIME) or any(char not in {"0", "1"} for char in text):
        return FULL_SCHEDULE_TIME
    if set(text) <= {"0"}:
        return FULL_SCHEDULE_TIME
    return text


def _target_weekday_index(target_date: str) -> int:
    try:
        return date.fromisoformat(_text(target_date)).weekday()
    except ValueError as exc:
        raise ValueError("schedule_hollow requires target_date in YYYY-MM-DD format") from exc


def build_hollow_schedule_time(original_schedule_time: str, hollow_hours: list[int], *, target_date: str) -> str:
    schedule = list(_normalize_schedule_time(original_schedule_time))
    day = _target_weekday_index(target_date)
    for hour in sorted({int(item) for item in hollow_hours}):
        if hour < 0 or hour > 23:
            raise ValueError("schedule_hollow hollow_hours must be between 0 and 23")
        offset = day * 48 + hour * 2
        schedule[offset] = "0"
        schedule[offset + 1] = "0"
    return "".join(schedule)


def _preflight_passed(preflight: dict[str, Any], project_update: dict[str, Any]) -> bool:
    return (
        bool(preflight.get("ok", False))
        and _text(preflight.get("workflow")) == "project_update_preflight"
        and _text(preflight.get("status")) == "passed"
        and _text(preflight.get("summary", {}).get("project_update_id")) == _text(project_update.get("project_update_id"))
    )


def _blocked_payload(
    project_update: dict[str, Any],
    *,
    runs_dir: str | Path,
    project_update_path: str = "",
    preflight_artifact_path: str = "",
    reasons: list[str],
) -> dict[str, Any]:
    payload = {
        "ok": False,
        "workflow": "project_update_execute",
        "phase": "control_execute",
        "status": "blocked",
        "execution_enabled": False,
        "external_api_calls": 0,
        "project_update_path": project_update_path,
        "preflight_artifact_path": preflight_artifact_path,
        "summary": {
            "project_update_id": _text(project_update.get("project_update_id")),
            "action_count": len(_rows(project_update.get("actions"))),
            "updated_project_count": 0,
            "lookup_call_count": 0,
            "update_call_count": 0,
        },
        "blocking_reasons": reasons,
        "results": [],
    }
    payload["artifact_path"] = str(write_run_artifact(runs_dir, "project_update_execute", payload))
    return payload


def _group_actions_by_account(project_update: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for action in _rows(project_update.get("actions")):
        if action.get("action_type") not in {"schedule_hollow", "schedule_restore"}:
            continue
        advertiser_id = _text(action.get("advertiser_id"))
        if not advertiser_id:
            continue
        grouped.setdefault(advertiser_id, []).append(action)
    return grouped


def _lookup_request(advertiser_id: str, project_ids: list[str]) -> dict[str, Any]:
    return {
        "operation": "lookup_project_schedule",
        "method": "GET",
        "endpoint": PROJECT_LIST_ENDPOINT,
        "payload": {
            "advertiser_id": _wire_id(advertiser_id),
            "filtering": {"ids": project_ids},
            "page": 1,
            "page_size": min(max(len(project_ids), 1), 100),
        },
    }


def _update_request(advertiser_id: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "operation": "update_project_week_schedule",
        "method": "POST",
        "endpoint": PROJECT_WEEK_SCHEDULE_UPDATE_ENDPOINT,
        "payload": {
            "advertiser_id": _wire_id(advertiser_id),
            "data": rows,
        },
    }


def _management_update_request(action_type: str, advertiser_id: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    operation, endpoint = MANAGEMENT_ACTION_OPERATIONS[action_type]
    if action_type == "delete_project":
        return {
            "operation": operation,
            "method": "POST",
            "endpoint": endpoint,
            "payload": {
                "advertiser_id": _wire_id(advertiser_id),
                "project_ids": [_wire_id(row.get("project_id")) for row in rows if _text(row.get("project_id"))],
            },
        }
    return {
        "operation": operation,
        "method": "POST",
        "endpoint": endpoint,
        "payload": {
            "advertiser_id": _wire_id(advertiser_id),
            "data": rows,
        },
    }


def _wire_id(value: Any) -> int | str:
    text = _text(value)
    return int(text) if text.isdigit() else text


def _build_schedule_ledger(
    project_update: dict[str, Any],
    *,
    transport: Transport,
    schedule_scene: str,
) -> tuple[list[dict[str, Any]], list[str], int]:
    entries: list[dict[str, Any]] = []
    blocking_reasons: list[str] = []
    lookup_call_count = 0
    for advertiser_id, actions in _group_actions_by_account(project_update).items():
        hollow_actions = [action for action in actions if action.get("action_type") == "schedule_hollow"]
        restore_actions = [action for action in actions if action.get("action_type") == "schedule_restore"]
        rows_by_project: dict[str, dict[str, Any]] = {}
        if hollow_actions:
            project_ids = [_text(action.get("project_id")) for action in hollow_actions if _text(action.get("project_id"))]
            response = transport(_lookup_request(advertiser_id, project_ids))
            lookup_call_count += 1
            _raise_for_api_error(response)
            rows_by_project = {_text(row.get("project_id")): row for row in _response_rows(response)}
        for action in hollow_actions:
            project_id = _text(action.get("project_id"))
            row = rows_by_project.get(project_id)
            key = f"{advertiser_id}/{project_id}"
            if row is None:
                blocking_reasons.append(f"project schedule lookup missed project: {key}")
                continue
            if _text(row.get("delivery_type")) == "DURATION":
                blocking_reasons.append(f"DURATION project schedule cannot be updated: {key}")
                continue
            original_schedule_time = _normalize_schedule_time(row.get("schedule_time"))
            new_schedule_time = build_hollow_schedule_time(
                original_schedule_time,
                [int(hour) for hour in action.get("hollow_hours") or []],
                target_date=_text(action.get("target_date")),
            )
            entries.append(
                {
                    "action_type": "schedule_hollow",
                    "advertiser_id": advertiser_id,
                    "project_id": project_id,
                    "project_name": _text(row.get("name")),
                    "target_date": _text(action.get("target_date")),
                    "restore_date": _text(action.get("restore_date")),
                    "restore_at": _text(action.get("restore_at")),
                    "hollow_hours": [int(hour) for hour in action.get("hollow_hours") or []],
                    "schedule_scene": schedule_scene,
                    "original_schedule_time": original_schedule_time,
                    "new_schedule_time": new_schedule_time,
                    "delivery_type": _text(row.get("delivery_type")),
                }
            )
        for action in restore_actions:
            project_id = _text(action.get("project_id"))
            original_schedule_time = _text(action.get("original_schedule_time"))
            key = f"{advertiser_id}/{project_id}"
            if not project_id:
                blocking_reasons.append(f"schedule restore missed project_id: {advertiser_id}")
                continue
            if not original_schedule_time:
                blocking_reasons.append(f"schedule restore missed original_schedule_time: {key}")
                continue
            entries.append(
                {
                    "action_type": "schedule_restore",
                    "advertiser_id": advertiser_id,
                    "project_id": project_id,
                    "project_name": _text(action.get("project_name")),
                    "target_date": _text(action.get("target_date")),
                    "restore_date": _text(action.get("restore_date")),
                    "restore_at": _text(action.get("restore_at")),
                    "hollow_hours": [],
                    "schedule_scene": schedule_scene,
                    "original_schedule_time": _normalize_schedule_time(original_schedule_time),
                    "new_schedule_time": _normalize_schedule_time(original_schedule_time),
                    "delivery_type": _text(action.get("delivery_type")),
                }
            )
    return entries, blocking_reasons, lookup_call_count


def _write_schedule_ledger(
    runs_dir: str | Path,
    project_update: dict[str, Any],
    entries: list[dict[str, Any]],
) -> str:
    target_dir = Path(runs_dir) / "project_update_execute"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{_text(project_update.get('project_update_id'))}.schedule_ledger.json"
    target.write_text(
        json.dumps(
            {
                "project_update_id": _text(project_update.get("project_update_id")),
                "source": "project_update_execute",
                "entries": entries,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return str(target)


def _restore_queue_path(runs_dir: str | Path, cfg: dict[str, Any]) -> Path:
    return Path(_text(cfg.get("restore_queue_path")) or Path(runs_dir) / "project_schedule_restore_queue.json")


def _read_restore_queue(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "source": "project_update_execute", "items": []}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {"version": 1, "source": "project_update_execute", "items": []}
    items = payload.get("items")
    if not isinstance(items, list):
        payload["items"] = []
    return payload


def _write_restore_queue(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _append_restore_queue(
    *,
    runs_dir: str | Path,
    cfg: dict[str, Any],
    project_update: dict[str, Any],
    ledger_path: str,
    entries: list[dict[str, Any]],
) -> str:
    queue_entries = [entry for entry in entries if entry.get("action_type") == "schedule_hollow" and _text(entry.get("restore_at"))]
    if not queue_entries:
        return ""
    path = _restore_queue_path(runs_dir, cfg)
    payload = _read_restore_queue(path)
    items = payload["items"]
    by_id = {
        _text(item.get("restore_id")): index
        for index, item in enumerate(items)
        if isinstance(item, dict) and _text(item.get("restore_id"))
    }
    project_update_id = _text(project_update.get("project_update_id"))
    for entry in queue_entries:
        restore_id = f"{project_update_id}:{entry['advertiser_id']}:{entry['project_id']}"
        item = {
            "restore_id": restore_id,
            "status": "pending",
            "project_update_id": project_update_id,
            "advertiser_id": entry["advertiser_id"],
            "project_id": entry["project_id"],
            "project_name": _text(entry.get("project_name")),
            "target_date": _text(entry.get("target_date")),
            "restore_date": _text(entry.get("restore_date")),
            "restore_at": _text(entry.get("restore_at")),
            "schedule_scene": _text(entry.get("schedule_scene")),
            "ledger_path": ledger_path,
        }
        if restore_id in by_id:
            items[by_id[restore_id]] = item
        else:
            items.append(item)
    _write_restore_queue(path, payload)
    return str(path)


def _execute_updates(
    entries: list[dict[str, Any]],
    *,
    transport: Transport,
) -> tuple[list[dict[str, Any]], int]:
    results: list[dict[str, Any]] = []
    update_call_count = 0
    by_account: dict[str, list[dict[str, Any]]] = {}
    for entry in entries:
        by_account.setdefault(entry["advertiser_id"], []).append(entry)
    for advertiser_id, account_entries in by_account.items():
        payload_rows = [
            {
                "project_id": _wire_id(entry["project_id"]),
                "schedule_time": entry["new_schedule_time"],
                "schedule_scene": entry["schedule_scene"],
            }
            for entry in account_entries
        ]
        for chunk in _chunks(payload_rows, 10):
            response = transport(_update_request(advertiser_id, chunk))
            update_call_count += 1
            _raise_for_api_error(response)
            results.append(
                {
                    "operation": "update_project_week_schedule",
                    "advertiser_id": advertiser_id,
                    "project_count": len(chunk),
                    "status": "completed",
                }
            )
    return results, update_call_count


def _management_payload_row(action: dict[str, Any]) -> dict[str, Any]:
    project_id = _wire_id(action.get("project_id"))
    action_type = _text(action.get("action_type"))
    if action_type == "status_update":
        return {"project_id": project_id, "opt_status": _text(action.get("opt_status"))}
    if action_type == "budget_update":
        row: dict[str, Any] = {"project_id": project_id, "budget_mode": _text(action.get("budget_mode"))}
        if _text(action.get("budget")):
            row["budget"] = action.get("budget")
        return row
    if action_type == "bid_update":
        return {"project_id": project_id, "cpa_bid": action.get("cpa_bid")}
    if action_type == "roi_coeff_update":
        return {"project_id": project_id, "roi_goal": action.get("roi_goal")}
    if action_type == "delete_project":
        return {"project_id": project_id}
    raise ValueError(f"unsupported project management action_type: {action_type}")


def _execute_management_updates(
    project_update: dict[str, Any],
    *,
    transport: Transport,
) -> tuple[list[dict[str, Any]], int, int]:
    results: list[dict[str, Any]] = []
    update_call_count = 0
    updated_project_count = 0
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for action in _rows(project_update.get("actions")):
        action_type = _text(action.get("action_type"))
        if action_type not in MANAGEMENT_ACTION_OPERATIONS:
            continue
        advertiser_id = _text(action.get("advertiser_id"))
        project_id = _text(action.get("project_id"))
        if not advertiser_id or not project_id:
            continue
        grouped.setdefault((advertiser_id, action_type), []).append(_management_payload_row(action))
    for (advertiser_id, action_type), rows in grouped.items():
        operation, _endpoint = MANAGEMENT_ACTION_OPERATIONS[action_type]
        for chunk in _chunks(rows, 10):
            response = transport(_management_update_request(action_type, advertiser_id, chunk))
            update_call_count += 1
            _raise_for_api_error(response)
            updated_project_count += len(chunk)
            results.append(
                {
                    "operation": operation,
                    "advertiser_id": advertiser_id,
                    "project_count": len(chunk),
                    "status": "completed",
                }
            )
    return results, update_call_count, updated_project_count


def run_project_update_execute_request(
    request: dict[str, Any] | None,
    *,
    runs_dir: str | Path,
    transport: Transport | None = None,
) -> dict[str, Any]:
    cfg = dict(request or {})
    project_update = cfg.get("project_update")
    project_update_path = _text(cfg.get("project_update_path"))
    if not isinstance(project_update, dict):
        if not project_update_path:
            raise ValueError("project update execute requires project_update or project_update_path")
        project_update = json.loads(Path(project_update_path).read_text(encoding="utf-8"))
    if not bool(cfg.get("execute_enabled", False)) or not bool(cfg.get("approved", False)):
        return _blocked_payload(
            project_update,
            runs_dir=runs_dir,
            project_update_path=project_update_path,
            preflight_artifact_path=_text(cfg.get("preflight_artifact_path")),
            reasons=["project update execute requires execute_enabled=true and approved=true"],
        )
    if transport is None:
        return _blocked_payload(
            project_update,
            runs_dir=runs_dir,
            project_update_path=project_update_path,
            preflight_artifact_path=_text(cfg.get("preflight_artifact_path")),
            reasons=["project update execute requires explicit transport"],
        )
    preflight = cfg.get("preflight_artifact")
    preflight_artifact_path = _text(cfg.get("preflight_artifact_path"))
    if not isinstance(preflight, dict) and preflight_artifact_path:
        preflight = json.loads(Path(preflight_artifact_path).read_text(encoding="utf-8"))
    if isinstance(preflight, dict) and not _preflight_passed(preflight, project_update):
        return _blocked_payload(
            project_update,
            runs_dir=runs_dir,
            project_update_path=project_update_path,
            preflight_artifact_path=preflight_artifact_path,
            reasons=["project update preflight artifact is invalid"],
        )

    schedule_scene = _text(cfg.get("schedule_scene") or "REALTIME")
    entries, blocking_reasons, lookup_call_count = _build_schedule_ledger(
        project_update,
        transport=transport,
        schedule_scene=schedule_scene,
    )
    if blocking_reasons:
        payload = {
            "ok": False,
            "workflow": "project_update_execute",
            "phase": "control_execute",
            "status": "failed_before_update",
            "execution_enabled": True,
            "external_api_calls": lookup_call_count,
            "project_update_path": project_update_path,
            "preflight_artifact_path": preflight_artifact_path,
            "summary": {
                "project_update_id": _text(project_update.get("project_update_id")),
                "action_count": len(_rows(project_update.get("actions"))),
                "updated_project_count": 0,
                "lookup_call_count": lookup_call_count,
                "update_call_count": 0,
            },
            "blocking_reasons": blocking_reasons,
            "results": [],
        }
        payload["artifact_path"] = str(write_run_artifact(runs_dir, "project_update_execute", payload))
        return payload

    ledger_path = _write_schedule_ledger(runs_dir, project_update, entries) if entries else ""
    results, update_call_count = _execute_updates(entries, transport=transport)
    management_results, management_update_call_count, management_updated_project_count = _execute_management_updates(
        project_update,
        transport=transport,
    )
    results.extend(management_results)
    restore_queue_path = _append_restore_queue(
        runs_dir=runs_dir,
        cfg=cfg,
        project_update=project_update,
        ledger_path=ledger_path,
        entries=entries,
    )
    payload = {
        "ok": True,
        "workflow": "project_update_execute",
        "phase": "control_execute",
        "status": "completed",
        "execution_enabled": True,
        "external_api_calls": lookup_call_count + update_call_count + management_update_call_count,
        "project_update_path": project_update_path,
        "preflight_artifact_path": preflight_artifact_path,
        "schedule_ledger_path": ledger_path,
        "restore_queue_path": restore_queue_path,
        "summary": {
            "project_update_id": _text(project_update.get("project_update_id")),
            "action_count": len(_rows(project_update.get("actions"))),
            "updated_project_count": len(entries) + management_updated_project_count,
            "lookup_call_count": lookup_call_count,
            "update_call_count": update_call_count + management_update_call_count,
            "restore_queue_item_count": len([entry for entry in entries if entry.get("action_type") == "schedule_hollow" and _text(entry.get("restore_at"))]),
        },
        "blocking_reasons": [],
        "results": results,
    }
    payload["artifact_path"] = str(write_run_artifact(runs_dir, "project_update_execute", payload))
    return payload
