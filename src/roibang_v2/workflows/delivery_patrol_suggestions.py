from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from roibang_v2.runs import write_run_artifact


def _load_local_json(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _number(value: Any) -> float:
    try:
        return float(str(value or "0").replace(",", "").replace("%", ""))
    except ValueError:
        return 0.0


def _metrics(item: dict[str, Any]) -> dict[str, Any]:
    metrics = item.get("metrics") if isinstance(item.get("metrics"), dict) else {}
    today = metrics.get("today") if isinstance(metrics.get("today"), dict) else {}
    return today


def _enabled_rule(rules: dict[str, Any], name: str, defaults: dict[str, Any]) -> dict[str, Any]:
    raw = rules.get(name) if isinstance(rules.get(name), dict) else {}
    rule = {**defaults, **raw}
    rule["enabled"] = bool(rule.get("enabled", True))
    return rule


def _entity_ref(entity_type: str, item: dict[str, Any]) -> dict[str, Any]:
    if entity_type == "account":
        return {
            "advertiser_id": str(item.get("advertiser_id") or ""),
            "entity_type": "account",
            "entity_id": str(item.get("advertiser_id") or ""),
            "entity_name": str(item.get("account_name") or item.get("advertiser_id") or ""),
        }
    if entity_type == "project":
        return {
            "advertiser_id": str(item.get("advertiser_id") or ""),
            "entity_type": "project",
            "entity_id": str(item.get("project_id") or ""),
            "project_id": str(item.get("project_id") or ""),
            "entity_name": str(item.get("project_name") or item.get("project_id") or ""),
        }
    return {
        "advertiser_id": str(item.get("advertiser_id") or ""),
        "entity_type": "promotion",
        "entity_id": str(item.get("promotion_id") or ""),
        "project_id": str(item.get("project_id") or ""),
        "promotion_id": str(item.get("promotion_id") or ""),
        "entity_name": str(item.get("promotion_name") or item.get("promotion_id") or ""),
    }


def _suggestion(
    *,
    suggestion_type: str,
    rule_id: str,
    target_date: str,
    entity_type: str,
    item: dict[str, Any],
    reason: str,
) -> dict[str, Any]:
    metrics = _metrics(item)
    return {
        "suggestion_type": suggestion_type,
        "rule_id": rule_id,
        "target_date": target_date,
        **_entity_ref(entity_type, item),
        "status": str(item.get("status") or ""),
        "reason": reason,
        "metrics": {
            "stat_cost": _number(metrics.get("stat_cost")),
            "billing_convert_cnt": _number(metrics.get("billing_convert_cnt")),
            "billing_conversion_cost": metrics.get("billing_conversion_cost"),
            "billing_1day_pay_roi": metrics.get("billing_1day_pay_roi"),
        },
        "execution": {"enabled": False, "status": "suggestion_only"},
    }


def _collect_entity_suggestions(
    *,
    target_date: str,
    entity_type: str,
    items: list[dict[str, Any]],
    rules: dict[str, Any],
) -> list[dict[str, Any]]:
    zero_convert = _enabled_rule(rules, "zero_billing_convert", {"enabled": True, "min_stat_cost": 500})
    low_roi = _enabled_rule(rules, "low_billing_roi", {"enabled": True, "min_stat_cost": 800, "roi_lt": 0.05})
    suggestions: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        metrics = _metrics(item)
        stat_cost = _number(metrics.get("stat_cost"))
        billing_convert_cnt = _number(metrics.get("billing_convert_cnt"))
        roi = metrics.get("billing_1day_pay_roi")
        roi_value = None if roi is None else _number(roi)
        if zero_convert["enabled"] and stat_cost >= _number(zero_convert.get("min_stat_cost")) and billing_convert_cnt <= 0:
            suggestions.append(
                _suggestion(
                    suggestion_type="attention_zero_billing_convert",
                    rule_id=f"{entity_type}_zero_billing_convert",
                    target_date=target_date,
                    entity_type=entity_type,
                    item=item,
                    reason="今天已有明显消耗，但计费时间转化数为 0，建议人工重点检查是否需要暂停或删除。",
                )
            )
            continue
        if (
            low_roi["enabled"]
            and stat_cost >= _number(low_roi.get("min_stat_cost"))
            and roi_value is not None
            and roi_value < _number(low_roi.get("roi_lt"))
        ):
            suggestions.append(
                _suggestion(
                    suggestion_type="attention_low_billing_roi",
                    rule_id=f"{entity_type}_low_billing_roi",
                    target_date=target_date,
                    entity_type=entity_type,
                    item=item,
                    reason="今天计费当日付费 ROI 低于阈值，建议人工重点检查是否需要控量。",
                )
            )
    return suggestions


def build_delivery_patrol_suggestions(patrol_artifact: dict[str, Any], request: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = dict(request or {})
    windows = patrol_artifact.get("windows") if isinstance(patrol_artifact.get("windows"), dict) else {}
    target_date = str(cfg.get("target_date") or windows.get("today") or "")
    rules = cfg.get("rules") if isinstance(cfg.get("rules"), dict) else {}
    suggestions: list[dict[str, Any]] = []
    suggestions.extend(
        _collect_entity_suggestions(
            target_date=target_date,
            entity_type="account",
            items=[item for item in patrol_artifact.get("accounts", []) if isinstance(item, dict)],
            rules=rules,
        )
    )
    suggestions.extend(
        _collect_entity_suggestions(
            target_date=target_date,
            entity_type="project",
            items=[item for item in patrol_artifact.get("projects", []) if isinstance(item, dict)],
            rules=rules,
        )
    )
    suggestions.extend(
        _collect_entity_suggestions(
            target_date=target_date,
            entity_type="promotion",
            items=[item for item in patrol_artifact.get("promotions", []) if isinstance(item, dict)],
            rules=rules,
        )
    )
    suggestions = sorted(
        suggestions,
        key=lambda item: (
            str(item.get("entity_type") or ""),
            -_number((item.get("metrics") or {}).get("stat_cost")),
            str(item.get("entity_id") or ""),
        ),
    )
    return {
        "ok": True,
        "workflow": "delivery_patrol_suggestions",
        "phase": "control_analysis",
        "execution_enabled": False,
        "external_api_calls": 0,
        "summary": {
            "target_date": target_date,
            "suggestion_count": len(suggestions),
            "account_suggestion_count": sum(1 for item in suggestions if item["entity_type"] == "account"),
            "project_suggestion_count": sum(1 for item in suggestions if item["entity_type"] == "project"),
            "promotion_suggestion_count": sum(1 for item in suggestions if item["entity_type"] == "promotion"),
        },
        "source": {
            "workflow": str(patrol_artifact.get("workflow") or ""),
            "artifact_path": str(patrol_artifact.get("artifact_path") or ""),
        },
        "rules": rules,
        "suggestions": suggestions,
        "guardrails": [
            "Suggestion only: no project or promotion API is called.",
            "Suggestions must be converted to a project_update JSON and confirmed before execution.",
        ],
    }


def run_delivery_patrol_suggestions_request(
    request: dict[str, Any],
    *,
    runs_dir: str | Path,
) -> dict[str, Any]:
    patrol = request.get("patrol_artifact") if isinstance(request.get("patrol_artifact"), dict) else None
    if patrol is None:
        path = str(request.get("patrol_artifact_path") or "").strip()
        if not path:
            raise ValueError("delivery patrol suggestions requires patrol_artifact or patrol_artifact_path")
        patrol = _load_local_json(path)
    result = build_delivery_patrol_suggestions(patrol, request)
    artifact_path = write_run_artifact(runs_dir, "delivery_patrol_suggestions", result)
    return {**result, "artifact_path": str(artifact_path)}
