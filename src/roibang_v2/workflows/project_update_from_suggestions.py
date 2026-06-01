from __future__ import annotations

import json
from datetime import datetime
from datetime import timezone
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


ACTION_FILTER_ALIASES: dict[str, tuple[str, ...]] = {
    "suggest_delete_project": ("suggest_delete_project", "delete_project"),
    "delete_project": ("delete_project", "suggest_delete_project"),
    "suggest_close_project": ("suggest_close_project", "pause_project", "close_project"),
    "pause_project": ("pause_project", "suggest_close_project", "close_project"),
    "close_project": ("close_project", "suggest_close_project", "pause_project"),
    "suggest_lower_budget": ("suggest_lower_budget", "adjust_project_budget"),
    "adjust_project_budget": ("adjust_project_budget", "suggest_lower_budget"),
    "suggest_lower_bid": ("suggest_lower_bid", "adjust_project_bid"),
    "adjust_project_bid": ("adjust_project_bid", "suggest_lower_bid"),
}

CONVERTIBLE_PROJECT_UPDATE_ACTIONS = {
    "schedule_hollow",
    "suggest_delete_project",
    "delete_project",
    "suggest_close_project",
    "pause_project",
    "close_project",
    "suggest_lower_budget",
    "adjust_project_budget",
    "suggest_lower_bid",
    "adjust_project_bid",
}


def _expanded_action_filter(values: list[str]) -> list[str]:
    expanded: list[str] = []
    seen: set[str] = set()
    for value in values:
        for alias in ACTION_FILTER_ALIASES.get(value, (value,)):
            if alias and alias not in seen:
                expanded.append(alias)
                seen.add(alias)
    return expanded


def _selected_suggestion_id_filter(cfg: dict[str, Any]) -> list[str]:
    raw = cfg.get("selected_suggestion_ids", cfg.get("suggestion_ids", cfg.get("suggestion_id")))
    values: list[str]
    if isinstance(raw, list):
        values = [str(item).strip() for item in raw]
    elif isinstance(raw, str):
        values = [item.strip() for item in raw.split(",")]
    else:
        values = []
    return [item for item in values if item]


def _filter_suggestions(
    suggestions: list[dict[str, Any]],
    suggested_actions: list[str],
    selected_suggestion_ids: list[str],
) -> list[dict[str, Any]]:
    if selected_suggestion_ids:
        allowed_ids = set(selected_suggestion_ids)
        suggestions = [suggestion for suggestion in suggestions if str(suggestion.get("suggestion_id") or "").strip() in allowed_ids]
    if not suggested_actions:
        return suggestions
    allowed = set(_expanded_action_filter(suggested_actions))
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
        if _suggested_action_name(suggestion) not in {"suggest_delete_project", "delete_project"}:
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


def _project_action_base(suggestion: dict[str, Any], action_type: str) -> dict[str, Any] | None:
    if str(suggestion.get("entity_type") or "").strip() != "project":
        return None
    advertiser_id = str(suggestion.get("advertiser_id") or "").strip()
    project_id = str(suggestion.get("project_id") or suggestion.get("entity_id") or "").strip()
    if not advertiser_id or not project_id:
        return None
    action = {
        "action_type": action_type,
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
    return action


def _action_label(action: dict[str, Any]) -> str:
    action_type = str(action.get("action_type") or "").strip()
    if action_type == "delete_project":
        return "删除项目"
    if action_type == "status_update" and str(action.get("opt_status") or "").strip() == "DISABLE":
        return "暂停项目"
    if action_type == "status_update" and str(action.get("opt_status") or "").strip() == "ENABLE":
        return "开启项目"
    if action_type == "budget_update":
        return "调预算"
    if action_type == "bid_update":
        return "调出价"
    if action_type == "schedule_hollow":
        return "调整时段"
    if action_type == "schedule_restore":
        return "恢复时段"
    return action_type or "人工复核"


def _account_names(cfg: dict[str, Any]) -> dict[str, str]:
    raw = cfg.get("account_names")
    if not isinstance(raw, dict):
        return {}
    return {str(key).strip(): str(value).strip() for key, value in raw.items() if str(key).strip() and str(value).strip()}


def _enrich_actions(actions: list[dict[str, Any]], account_names: dict[str, str]) -> None:
    if not account_names:
        return
    for action in actions:
        advertiser_id = str(action.get("advertiser_id") or "").strip()
        action["中文动作"] = _action_label(action)
        account_name = account_names.get(advertiser_id, "")
        if account_name:
            action["account_name"] = account_name


def _action_accounts(actions: list[dict[str, Any]], account_names: dict[str, str]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for action in actions:
        account_id = str(action.get("advertiser_id") or "").strip()
        if not account_id or account_id in seen:
            continue
        seen.add(account_id)
        rows.append(
            {
                "account_id": account_id,
                "account_name": str(action.get("account_name") or account_names.get(account_id) or "未配置账户名").strip(),
            }
        )
    return rows


def _risk_summary(actions: list[dict[str, Any]]) -> str:
    label_counts: dict[str, int] = {}
    for action in actions:
        label = _action_label(action)
        label_counts[label] = label_counts.get(label, 0) + 1
    if not label_counts:
        return "未生成可执行动作；执行前必须人工复核来源建议。"
    parts = [f"{label} {count} 个" for label, count in label_counts.items()]
    return f"包含{'、'.join(parts)}；执行前必须人工核对账户、项目、动作和来源建议。"


def _chinese_summary(actions: list[dict[str, Any]], accounts: list[dict[str, str]]) -> str:
    return f"根据规则建议生成项目管理动作 JSON，涉及 {len(accounts)} 个账户、{len(actions)} 个动作；只生成配置，不执行真实业务动作。"


def _generated_at(cfg: dict[str, Any]) -> str:
    value = str(cfg.get("generated_at") or "").strip()
    if value:
        return value
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _close_project_actions(suggestions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for suggestion in suggestions:
        if _suggested_action_name(suggestion) not in {"suggest_close_project", "pause_project", "close_project"}:
            continue
        action = _project_action_base(suggestion, "status_update")
        if action is None:
            continue
        key = (action["advertiser_id"], action["project_id"])
        if key in seen:
            continue
        seen.add(key)
        action["opt_status"] = "DISABLE"
        actions.append(action)
    return actions


def _ratio_adjustment(suggestion: dict[str, Any]) -> float | None:
    adjustment = suggestion.get("adjustment") if isinstance(suggestion.get("adjustment"), dict) else {}
    if adjustment.get("type") != "ratio":
        direction = str(adjustment.get("direction") or "").strip()
        try:
            decrease_percent = float(adjustment.get("decrease_percent"))
        except (TypeError, ValueError):
            return None
        if direction == "decrease":
            return -abs(decrease_percent) / 100
        if direction == "increase":
            return abs(decrease_percent) / 100
        return None
    try:
        return float(adjustment.get("value"))
    except (TypeError, ValueError):
        return None


def _ratio_project_actions(suggestions: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    budget_actions: list[dict[str, Any]] = []
    bid_actions: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for suggestion in suggestions:
        suggested_action = _suggested_action_name(suggestion)
        if suggested_action not in {"suggest_lower_budget", "suggest_lower_bid", "adjust_project_budget", "adjust_project_bid"}:
            continue
        ratio = _ratio_adjustment(suggestion)
        if ratio is None:
            continue
        action_type = "budget_update" if suggested_action in {"suggest_lower_budget", "adjust_project_budget"} else "bid_update"
        action = _project_action_base(suggestion, action_type)
        if action is None:
            continue
        key = (action_type, action["advertiser_id"], action["project_id"])
        if key in seen:
            continue
        seen.add(key)
        action["adjustment"] = {"type": "ratio", "value": ratio}
        action["adjustment_ratio"] = ratio
        action["resolve_current_value_at_execute"] = True
        if action_type == "budget_update":
            action["budget_mode"] = "BUDGET_MODE_DAY"
            budget_actions.append(action)
        else:
            bid_actions.append(action)
    return budget_actions, bid_actions


def build_project_update_from_suggestions(
    suggestions_artifact: dict[str, Any],
    request: dict[str, Any] | None,
) -> dict[str, Any]:
    cfg = dict(request or {})
    update_id = _project_update_id(cfg)
    suggestions = _rows(suggestions_artifact.get("suggestions"))
    suggested_actions = _suggested_action_filter(cfg)
    selected_suggestion_ids = _selected_suggestion_id_filter(cfg)
    selected_suggestions = _filter_suggestions(suggestions, suggested_actions, selected_suggestion_ids)
    if selected_suggestion_ids or suggested_actions:
        readonly_ids = [
            str(suggestion.get("suggestion_id") or _suggested_action_name(suggestion) or "未命名建议")
            for suggestion in selected_suggestions
            if _suggested_action_name(suggestion) not in CONVERTIBLE_PROJECT_UPDATE_ACTIONS
        ]
        if readonly_ids:
            raise ValueError(f"只读建议不能生成项目管理 JSON：{', '.join(readonly_ids)}")
    schedule_actions, restore_actions = _schedule_hollow_actions(selected_suggestions)
    delete_actions = _delete_project_actions(selected_suggestions)
    close_actions = _close_project_actions(selected_suggestions)
    budget_actions, bid_actions = _ratio_project_actions(selected_suggestions)
    actions = [*schedule_actions, *delete_actions, *close_actions, *budget_actions, *bid_actions]
    account_names = _account_names(cfg)
    _enrich_actions(actions, account_names)
    accounts = _action_accounts(actions, account_names)
    target_dates = sorted({str(action["target_date"]) for action in actions if action.get("target_date")})
    restore_dates = sorted({str(action["restore_date"]) for action in actions if action.get("restore_date")})
    project_update = {
        "中文摘要": _chinese_summary(actions, accounts),
        "project_update_id": update_id,
        "operator": str(cfg.get("operator") or ""),
        "product_key": str(cfg.get("product_key") or ""),
        "product_name": str(cfg.get("product_name") or ""),
        "source_artifact": str(cfg.get("suggestions_artifact_path") or ""),
        "generated_at": _generated_at(cfg),
        "accounts": accounts,
        "risk_summary": _risk_summary(actions),
        "dry_run_required": True,
        "execution_allowed": False,
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
    result = {
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
            "close_project_action_count": len(close_actions),
            "lower_budget_action_count": len(budget_actions),
            "lower_bid_action_count": len(bid_actions),
            "action_count": len(actions),
            "restore_action_count": len(restore_actions),
            "target_date": target_dates[0] if len(target_dates) == 1 else "",
            "restore_date": restore_dates[0] if len(restore_dates) == 1 else "",
        },
        "project_update": project_update,
    }
    if selected_suggestion_ids:
        result["summary"]["selected_suggestion_ids"] = selected_suggestion_ids
    return result


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
