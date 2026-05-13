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


def build_project_update_from_suggestions(
    suggestions_artifact: dict[str, Any],
    request: dict[str, Any] | None,
) -> dict[str, Any]:
    cfg = dict(request or {})
    update_id = _project_update_id(cfg)
    suggestions = _rows(suggestions_artifact.get("suggestions"))
    actions, restore_actions = _schedule_hollow_actions(suggestions)
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
            "schedule_hollow_action_count": len(actions),
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
