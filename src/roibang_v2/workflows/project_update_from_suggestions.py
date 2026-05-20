from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from roibang_v2.runs import write_run_artifact


def _rows(value: Any) -> list[dict[str, Any]]:
    return [dict(item) for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _project_update_id(cfg: dict[str, Any]) -> str:
    value = str(cfg.get("project_update_id") or "").strip()
    if not value:
        raise ValueError("project update from suggestions requires project_update_id")
    return value


def _suggested_action_name(suggestion: dict[str, Any]) -> str:
    return str(suggestion.get("suggested_action") or suggestion.get("suggestion_type") or "").strip()


def _suggested_action_filter(cfg: dict[str, Any]) -> list[str]:
    raw = cfg.get("suggested_actions", cfg.get("suggested_action"))
    values: list[str]
    if isinstance(raw, list):
        values = [str(item).strip() for item in raw]
    elif isinstance(raw, str):
        values = [item.strip() for item in raw.split(",")]
    else:
        values = []
    return [item for item in values if item]


def _filter_suggestions(suggestions: list[dict[str, Any]], suggested_actions: list[str]) -> list[dict[str, Any]]:
    if not suggested_actions:
        return suggestions
    allowed = set(suggested_actions)
    return [suggestion for suggestion in suggestions if _suggested_action_name(suggestion) in allowed]


def _schedule_hollow_actions(suggestions: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    actions: list[dict[str, Any]] = []
    restore_actions: list[dict[str, Any]] = []
    for suggestion in suggestions:
        if suggestion.get("suggestion_type") != "schedule_hollow":
            continue
        restore = suggestion.get("restore") if isinstance(suggestion.get("restore"), dict) else {}
        action = {
            "action_type": "schedule_hollow",
            "advertiser_id": str(suggestion.get("advertiser_id") or ""),
            "entity_type": "project",
            "project_id": str(suggestion.get("entity_id") or ""),
            "target_date": str(suggestion.get("target_date") or ""),
            "hollow_hours": [int(hour) for hour in suggestion.get("hollow_hours") or []],
            "preserve_original_schedule_required": True,
            "restore_required": bool(restore.get("required", True)),
            "restore_date": str(restore.get("restore_date") or ""),
            "reason": str(suggestion.get("reason") or ""),
            "metrics": suggestion.get("metrics") if isinstance(suggestion.get("metrics"), dict) else {},
        }
        actions.append(action)
        restore_actions.append(
            {
                "action_type": "schedule_restore",
                "advertiser_id": action["advertiser_id"],
                "entity_type": "project",
                "project_id": action["project_id"],
                "restore_date": action["restore_date"],
                "restore_source": "preserved_original_schedule",
                "preserve_original_schedule_required": True,
                "reason": str(restore.get("reason") or "第二天恢复原始时段"),
            }
        )
    return actions, restore_actions


def _delete_project_actions(suggestions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for suggestion in suggestions:
        if _suggested_action_name(suggestion) != "suggest_delete_project":
            continue
        if str(suggestion.get("entity_type") or "").strip() != "project":
            continue
        advertiser_id = str(suggestion.get("advertiser_id") or "").strip()
        project_id = str(suggestion.get("project_id") or suggestion.get("entity_id") or "").strip()
        if not advertiser_id or not project_id:
            continue
        key = (advertiser_id, project_id)
        if key in seen:
            continue
        seen.add(key)
        action = {
            "action_type": "delete_project",
            "advertiser_id": advertiser_id,
            "entity_type": "project",
            "project_id": project_id,
            "project_name": str(suggestion.get("project_name") or suggestion.get("entity_name") or "").strip(),
            "reason": str(suggestion.get("reason") or ""),
            "source_suggestion_id": str(suggestion.get("suggestion_id") or ""),
            "source_rule_id": str(suggestion.get("rule_id") or ""),
            "metrics": suggestion.get("metrics") if isinstance(suggestion.get("metrics"), dict) else {},
            "evidence": suggestion.get("evidence") if isinstance(suggestion.get("evidence"), dict) else {},
        }
        if str(suggestion.get("status") or "").strip():
            action["status"] = str(suggestion.get("status") or "").strip()
        actions.append(action)
    return actions


def build_project_update_from_suggestions(
    suggestions_artifact: dict[str, Any],
    request: dict[str, Any] | None,
) -> dict[str, Any]:
    cfg = dict(request or {})
    update_id = _project_update_id(cfg)
    suggestions = _rows(suggestions_artifact.get("suggestions"))
    suggested_actions = _suggested_action_filter(cfg)
    selected_suggestions = _filter_suggestions(suggestions, suggested_actions)
    schedule_actions, restore_actions = _schedule_hollow_actions(selected_suggestions)
    delete_actions = _delete_project_actions(selected_suggestions)
    actions = [*schedule_actions, *delete_actions]
    target_dates = sorted({str(action["target_date"]) for action in actions if action.get("target_date")})
    restore_dates = sorted({str(action["restore_date"]) for action in actions if action.get("restore_date")})
    project_update = {
        "project_update_id": update_id,
        "operator": str(cfg.get("operator") or ""),
        "source": {
            "workflow": str(suggestions_artifact.get("workflow") or ""),
            "artifact_path": str(cfg.get("suggestions_artifact_path") or ""),
        },
        "allowed_target_accounts_path": str(cfg.get("allowed_target_accounts_path") or ""),
        "execution": {"enabled": False, "status": "planned_only"},
        "safety": {
            "requires_preflight": True,
            "requires_explicit_execute_approval": True,
            "must_preserve_original_schedule_before_hollow": True,
            "must_restore_next_day": True,
        },
        "actions": actions,
        "restore_actions": restore_actions,
    }
    return {
        "ok": True,
        "workflow": "project_update_from_suggestions",
        "phase": "control_analysis",
        "execution_enabled": False,
        "external_api_calls": 0,
        "summary": {
            "project_update_id": update_id,
            "source_suggestion_count": len(suggestions),
            "selected_suggestion_count": len(selected_suggestions),
            "suggested_actions": suggested_actions,
            "schedule_hollow_action_count": len(schedule_actions),
            "delete_project_action_count": len(delete_actions),
            "action_count": len(actions),
            "restore_action_count": len(restore_actions),
            "target_date": target_dates[0] if len(target_dates) == 1 else "",
            "restore_date": restore_dates[0] if len(restore_dates) == 1 else "",
        },
        "project_update": project_update,
    }


def run_project_update_from_suggestions_request(
    request: dict[str, Any] | None,
    *,
    runs_dir: str | Path,
) -> dict[str, Any]:
    cfg = dict(request or {})
    artifact = cfg.get("suggestions_artifact")
    if not isinstance(artifact, dict):
        path = Path(str(cfg.get("suggestions_artifact_path") or ""))
        if not path.exists():
            raise ValueError("project update from suggestions requires suggestions_artifact or suggestions_artifact_path")
        artifact = json.loads(path.read_text(encoding="utf-8"))
        cfg["suggestions_artifact_path"] = str(path)
    payload = build_project_update_from_suggestions(artifact, cfg)
    output_path = Path(str(cfg.get("output_path") or "data/runs/project_update_from_suggestions/project_update.local.json"))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload["project_update"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    payload["project_update_path"] = str(output_path)
    payload["artifact_path"] = str(write_run_artifact(runs_dir, "project_update_from_suggestions", payload))
    return payload
