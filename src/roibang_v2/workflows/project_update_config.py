from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

from roibang_v2.runs import write_run_artifact


def _text(value: Any) -> str:
    return str(value or "").strip()


def _rows(value: Any) -> list[dict[str, Any]]:
    return [dict(item) for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _required_text(cfg: dict[str, Any], key: str) -> str:
    value = _text(cfg.get(key))
    if not value:
        raise ValueError(f"project update config requires {key}")
    return value


def _parse_time(value: str) -> tuple[int, int]:
    text = _text(value)
    try:
        hour_text, minute_text = text.split(":", 1)
        hour = int(hour_text)
        minute = int(minute_text)
    except (ValueError, TypeError) as exc:
        raise ValueError("time value must use HH:MM format") from exc
    if not 0 <= hour <= 24 or not 0 <= minute <= 59 or (hour == 24 and minute != 0):
        raise ValueError("time value must be between 00:00 and 24:00")
    return hour, minute


def _parse_hour_time(value: str) -> int:
    hour, minute = _parse_time(value)
    if not 0 <= hour <= 24 or minute != 0:
        raise ValueError("project update config currently supports whole-hour HH:00 times only")
    return hour


def _hollow_hours(start_time: str, end_time: str) -> list[int]:
    start_hour = _parse_hour_time(start_time)
    end_hour = _parse_hour_time(end_time)
    if start_hour >= end_hour:
        raise ValueError("block_start must be earlier than block_end")
    if end_hour > 24:
        raise ValueError("block_end must be no later than 24:00")
    return list(range(start_hour, end_hour))


def _restore_at(target_date: str, restore_time: str, restore_date: str = "") -> str:
    date.fromisoformat(target_date)
    actual_restore_date = _text(restore_date) or target_date
    date.fromisoformat(actual_restore_date)
    hour, minute = _parse_time(restore_time)
    if hour == 24:
        return f"{actual_restore_date}T23:59:59+08:00"
    return f"{actual_restore_date}T{hour:02d}:{minute:02d}:00+08:00"


def build_project_update_config(request: dict[str, Any] | None) -> dict[str, Any]:
    cfg = dict(request or {})
    project_update_id = _required_text(cfg, "project_update_id")
    target_date = _required_text(cfg, "target_date")
    restore_time = _required_text(cfg, "restore_time")
    restore_date = _text(cfg.get("restore_date"))
    block_start = _required_text(cfg, "block_start")
    block_end = _required_text(cfg, "block_end")
    hours = _hollow_hours(block_start, block_end)
    restore_at = _restore_at(target_date, restore_time, restore_date)
    resolved_restore_date = restore_at[:10]
    projects = _rows(cfg.get("projects"))
    if not projects:
        raise ValueError("project update config requires at least one project")

    actions: list[dict[str, Any]] = []
    restore_actions: list[dict[str, Any]] = []
    for project in projects:
        advertiser_id = _required_text(project, "advertiser_id")
        project_id = _required_text(project, "project_id")
        action = {
            "action_type": "schedule_hollow",
            "advertiser_id": advertiser_id,
            "entity_type": "project",
            "project_id": project_id,
            "project_name": _text(project.get("project_name")),
            "target_date": target_date,
            "hollow_hours": hours,
            "preserve_original_schedule_required": True,
            "restore_required": True,
            "restore_date": resolved_restore_date,
            "restore_at": restore_at,
            "reason": _text(cfg.get("reason") or f"临时拉空 {block_start}-{block_end}"),
        }
        actions.append(action)
        restore_actions.append(
            {
                "action_type": "schedule_restore",
                "advertiser_id": advertiser_id,
                "entity_type": "project",
                "project_id": project_id,
                "project_name": _text(project.get("project_name")),
                "target_date": target_date,
                "restore_date": resolved_restore_date,
                "restore_at": restore_at,
                "restore_source": "preserved_original_schedule",
                "preserve_original_schedule_required": True,
                "reason": _text(cfg.get("restore_reason") or "到点恢复原始投放时段"),
            }
        )

    return {
        "project_update_id": project_update_id,
        "operator": _text(cfg.get("operator")),
        "source": {
            "workflow": "project_update_config",
            "request": "manual_project_schedule_control",
        },
        "allowed_target_accounts_path": _text(cfg.get("allowed_target_accounts_path")),
        "execution": {"enabled": False, "status": "planned_only"},
        "safety": {
            "requires_preflight": True,
            "requires_explicit_execute_approval": True,
            "must_preserve_original_schedule_before_hollow": True,
            "must_restore_on_restore_at": True,
        },
        "actions": actions,
        "restore_actions": restore_actions,
    }


def run_project_update_config_request(
    request: dict[str, Any] | None,
    *,
    runs_dir: str | Path,
) -> dict[str, Any]:
    cfg = dict(request or {})
    project_update = build_project_update_config(cfg)
    output_path = Path(_text(cfg.get("output_path")) or "data/runs/project_update_config/project_update.local.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(project_update, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    payload = {
        "ok": True,
        "workflow": "project_update_config",
        "phase": "control_config",
        "execution_enabled": False,
        "external_api_calls": 0,
        "summary": {
            "project_update_id": project_update["project_update_id"],
            "action_count": len(project_update["actions"]),
            "restore_action_count": len(project_update["restore_actions"]),
            "target_date": project_update["actions"][0]["target_date"] if project_update["actions"] else "",
            "restore_at": project_update["actions"][0]["restore_at"] if project_update["actions"] else "",
        },
        "project_update_path": str(output_path),
        "project_update": project_update,
    }
    payload["artifact_path"] = str(write_run_artifact(runs_dir, "project_update_config", payload))
    return payload
