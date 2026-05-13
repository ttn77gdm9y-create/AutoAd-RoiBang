from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from roibang_v2.runs import write_run_artifact


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _strategy_request(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("strategy_request")
    return dict(value) if isinstance(value, dict) else dict(request)


def _request_id(request: dict[str, Any]) -> str:
    value = str(request.get("request_id") or "").strip()
    if not value:
        raise ValueError("strategy request requires request_id")
    return value


def _recommendations(learning_artifact: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for signal in learning_artifact.get("account_signals") or []:
        if not isinstance(signal, dict):
            continue
        items.append(
            {
                "recommendation_type": "investigate_account",
                "advertiser_id": str(signal.get("advertiser_id") or ""),
                "reason_flags": list(signal.get("flags") or []),
                "evidence": {
                    "stat_cost": signal.get("stat_cost", 0),
                    "conversions": signal.get("conversions", 0),
                    "roi": signal.get("roi", 0),
                },
                "allowed_phase1_output": "strategy_review_only",
            }
        )
    for hint in learning_artifact.get("decision_hints") or []:
        if not isinstance(hint, dict) or hint.get("hint_type") != "review_material":
            continue
        items.append(
            {
                "recommendation_type": "review_material_pool",
                "material_id": str(hint.get("material_id") or ""),
                "material_kind": str(hint.get("material_kind") or ""),
                "evidence": hint.get("evidence") if isinstance(hint.get("evidence"), dict) else {},
                "allowed_phase1_output": "material_review_only",
            }
        )
    return items


def _material_source_plans(material_source_artifact: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(material_source_artifact, dict):
        return []
    plans = material_source_artifact.get("plans")
    if isinstance(plans, list):
        return [plan for plan in plans if isinstance(plan, dict)]
    plan = material_source_artifact.get("plan")
    return [plan] if isinstance(plan, dict) else []


def _material_source_recommendations(material_source_artifact: dict[str, Any] | None) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for plan in _material_source_plans(material_source_artifact):
        missing = [item for item in plan.get("missing_materials") or [] if isinstance(item, dict)]
        if not missing:
            continue
        items.append(
            {
                "recommendation_type": "plan_material_provision",
                "product": str(plan.get("product") or ""),
                "source_advertiser_id": str(plan.get("source_advertiser_id") or ""),
                "target_advertiser_id": str(plan.get("target_advertiser_id") or ""),
                "provision_needed": int(plan.get("provision_needed") or len(missing)),
                "missing_material_ids": [str(item.get("material_id") or "") for item in missing],
                "evidence": {
                    "status": str(plan.get("status") or ""),
                    "missing_materials": missing,
                },
                "allowed_phase1_output": "material_provision_plan_only",
            }
        )
    return items


def build_strategy_plan(
    *,
    request: dict[str, Any],
    learning_artifact: dict[str, Any],
    material_source_artifact: dict[str, Any] | None = None,
    policy: dict[str, Any],
) -> dict[str, Any]:
    request_id = _request_id(request)
    target_date = str(request.get("target_date") or learning_artifact.get("summary", {}).get("target_date") or "")
    recommendations = _recommendations(learning_artifact)
    recommendations.extend(_material_source_recommendations(material_source_artifact))
    return {
        "ok": True,
        "workflow": "strategy_plan",
        "plan_id": f"plan_{request_id}",
        "request_id": request_id,
        "phase": "phase1",
        "target_date": target_date,
        "execution_enabled": False,
        "external_api_calls": 0,
        "request": request,
        "strategy": {
            "source": "daily_learning+material_source" if material_source_artifact else "daily_learning",
            "objective": str(request.get("objective") or "review_daily_learning"),
            "recommendations": recommendations,
        },
        "preflight": {
            "required": bool(policy.get("require_preflight", True)),
            "status": "draft_only",
            "checks": [
                "validate_request_json",
                "validate_policy_allows_phase1_only",
                "validate_no_live_action_payloads",
            ],
        },
        "dry_run": {
            "required": bool(policy.get("require_dry_run", True)),
            "status": "draft_only",
            "payloads": [],
            "note": "Phase 1 dry-run draft contains no live API payloads.",
        },
        "execute": {
            "status": "disabled_in_phase1",
            "reason": "Phase 1 does not implement live create, pause, delete, push, bind, or update.",
        },
        "actions": [],
        "guardrails": learning_artifact.get("guardrails") or [],
    }


def _store_plan(
    *,
    db_path: str | Path,
    request: dict[str, Any],
    plan: dict[str, Any],
) -> None:
    now = _now_iso()
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO strategy_plans (
              plan_id, phase, execution_enabled, request_json, plan_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(plan_id) DO UPDATE SET
              phase = excluded.phase,
              execution_enabled = excluded.execution_enabled,
              request_json = excluded.request_json,
              plan_json = excluded.plan_json,
              created_at = excluded.created_at
            """,
            (
                plan["plan_id"],
                plan["phase"],
                1 if plan.get("execution_enabled") else 0,
                json.dumps(request, ensure_ascii=False, sort_keys=True),
                json.dumps(plan, ensure_ascii=False, sort_keys=True),
                now,
            ),
        )


def run_strategy_plan_request(
    request: dict[str, Any],
    *,
    db_path: str | Path,
    runs_dir: str | Path,
    learning_artifact: dict[str, Any],
    material_source_artifact: dict[str, Any] | None = None,
    policy: dict[str, Any],
) -> dict[str, Any]:
    strategy_request = _strategy_request(request)
    plan = build_strategy_plan(
        request=strategy_request,
        learning_artifact=learning_artifact,
        material_source_artifact=material_source_artifact,
        policy=policy,
    )
    _store_plan(db_path=db_path, request=strategy_request, plan=plan)
    payload = {
        "ok": True,
        "workflow": "strategy_plan",
        "phase": "phase1",
        "execution_enabled": False,
        "external_api_calls": 0,
        "plan": plan,
    }
    artifact = write_run_artifact(runs_dir, "strategy_plan", payload)
    return {**payload, "artifact_path": str(artifact)}
