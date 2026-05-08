from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from roibang_v2.runs import write_run_artifact


GUARDRAILS = [
    "Phase 1 learning artifacts are read-only.",
    "Do not create, pause, delete, push, bind, or update live ad objects.",
    "Future live actions must follow request -> strategy -> preflight -> dry-run -> approve -> execute.",
]


def _daily_learning_config(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("daily_learning")
    return dict(value) if isinstance(value, dict) else dict(request)


def _target_date(policy: dict[str, Any]) -> str:
    value = str(policy.get("target_date") or "").strip()
    if not value:
        raise ValueError("target_date must not be empty")
    return value


def _promotion_metrics(conn: sqlite3.Connection, target_date: str) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    return list(
        conn.execute(
            """
            SELECT
              ms.entity_id AS promotion_id,
              ms.cost,
              ms.conversions,
              ms.roi,
              p.advertiser_id
            FROM metric_snapshots ms
            LEFT JOIN promotions p ON p.promotion_id = ms.entity_id
            WHERE ms.entity_type = 'promotion'
              AND ms.metric_date = ?
            """,
            (target_date,),
        )
    )


def _account_signals(
    rows: list[sqlite3.Row],
    *,
    min_cost: float,
    min_conversions: int,
    low_roi_threshold: float,
) -> list[dict[str, Any]]:
    by_account: dict[str, dict[str, Any]] = {}
    for row in rows:
        advertiser_id = str(row["advertiser_id"] or "")
        if not advertiser_id:
            continue
        bucket = by_account.setdefault(advertiser_id, {"stat_cost": 0.0, "conversions": 0, "roi_num": 0.0})
        cost = float(row["cost"] or 0)
        conversions = int(row["conversions"] or 0)
        roi = float(row["roi"] or 0)
        bucket["stat_cost"] += cost
        bucket["conversions"] += conversions
        bucket["roi_num"] += cost * roi

    signals: list[dict[str, Any]] = []
    for advertiser_id, values in sorted(by_account.items()):
        cost = round(float(values["stat_cost"]), 2)
        conversions = int(values["conversions"])
        roi = round(float(values["roi_num"]) / cost, 4) if cost else 0.0
        flags: list[str] = []
        if cost >= min_cost and roi < low_roi_threshold:
            flags.append("high_spend_low_roi")
        if cost >= min_cost and conversions < min_conversions:
            flags.append("low_conversion_volume")
        if flags:
            signals.append(
                {
                    "advertiser_id": advertiser_id,
                    "stat_cost": cost,
                    "conversions": conversions,
                    "roi": roi,
                    "flags": flags,
                }
            )
    return signals


def _top_materials(conn: sqlite3.Connection, *, target_date: str, limit: int) -> list[dict[str, Any]]:
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT
          material_kind,
          material_id,
          video_id,
          title,
          promotion_count,
          project_count,
          account_count,
          stat_cost,
          active_register,
          attribution_convert_cnt,
          roi_1day_cost_weighted,
          roi_7days_cost_weighted
        FROM material_metric_summaries
        WHERE period_end = ?
        ORDER BY stat_cost DESC, material_id ASC
        LIMIT ?
        """,
        (target_date, limit),
    ).fetchall()
    return [
        {
            "material_kind": str(row["material_kind"] or ""),
            "material_id": str(row["material_id"] or ""),
            "video_id": str(row["video_id"] or ""),
            "title": str(row["title"] or ""),
            "promotion_count": int(row["promotion_count"] or 0),
            "project_count": int(row["project_count"] or 0),
            "account_count": int(row["account_count"] or 0),
            "stat_cost": float(row["stat_cost"] or 0),
            "active_register": float(row["active_register"] or 0),
            "attribution_convert_cnt": float(row["attribution_convert_cnt"] or 0),
            "roi_1day_cost_weighted": float(row["roi_1day_cost_weighted"] or 0),
            "roi_7days_cost_weighted": float(row["roi_7days_cost_weighted"] or 0),
        }
        for row in rows
    ]


def _operation_logs(conn: sqlite3.Connection, *, target_date: str, limit: int) -> list[dict[str, Any]]:
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT
          operation_id,
          occurred_at,
          operator,
          entity_type,
          entity_id,
          action,
          detail
        FROM operation_logs
        WHERE substr(occurred_at, 1, 10) = ?
        ORDER BY occurred_at DESC, operation_id DESC
        LIMIT ?
        """,
        (target_date, limit),
    ).fetchall()
    return [
        {
            "operation_id": str(row["operation_id"] or ""),
            "occurred_at": str(row["occurred_at"] or ""),
            "operator": str(row["operator"] or ""),
            "entity_type": str(row["entity_type"] or ""),
            "entity_id": str(row["entity_id"] or ""),
            "action": str(row["action"] or ""),
            "detail": str(row["detail"] or ""),
        }
        for row in rows
    ]


def _operation_log_summary(logs: list[dict[str, Any]], *, target_date: str) -> dict[str, Any]:
    by_entity_type: dict[str, int] = {}
    by_action: dict[str, int] = {}
    for log in logs:
        entity_type = str(log.get("entity_type") or "")
        action = str(log.get("action") or "")
        if entity_type:
            by_entity_type[entity_type] = by_entity_type.get(entity_type, 0) + 1
        if action:
            by_action[action] = by_action.get(action, 0) + 1
    return {
        "target_date": target_date,
        "total_count": len(logs),
        "by_entity_type": dict(sorted(by_entity_type.items())),
        "by_action": dict(sorted(by_action.items())),
        "recent_logs": logs,
    }


def _decision_hints(
    signals: list[dict[str, Any]],
    top_materials: list[dict[str, Any]],
    operation_log_summary: dict[str, Any],
) -> list[dict[str, Any]]:
    hints: list[dict[str, Any]] = []
    for signal in signals:
        hints.append(
            {
                "hint_type": "review_account",
                "advertiser_id": signal["advertiser_id"],
                "flags": signal["flags"],
                "next_step": "Review policy thresholds and strategy plan inputs; do not execute live actions.",
            }
        )
    for material in top_materials[:1]:
        hints.append(
            {
                "hint_type": "review_material",
                "material_id": material["material_id"],
                "material_kind": material["material_kind"],
                "evidence": {
                    "stat_cost": material["stat_cost"],
                    "roi_1day_cost_weighted": material["roi_1day_cost_weighted"],
                    "roi_7days_cost_weighted": material["roi_7days_cost_weighted"],
                },
                "next_step": "Use as material-pool evidence only; Phase 1 cannot push or bind materials.",
            }
        )
    if operation_log_summary["total_count"]:
        hints.append(
            {
                "hint_type": "review_operation_logs",
                "target_date": operation_log_summary["target_date"],
                "operation_log_count": operation_log_summary["total_count"],
                "by_entity_type": operation_log_summary["by_entity_type"],
                "by_action": operation_log_summary["by_action"],
                "next_step": "Compare same-day operations with account, project, promotion, and material performance before changing policy.",
            }
        )
    return hints


def build_daily_learning_artifact(*, db_path: str | Path, policy: dict[str, Any]) -> dict[str, Any]:
    target_date = _target_date(policy)
    min_cost = float(policy.get("min_cost_for_signal", 100))
    min_conversions = int(policy.get("min_conversions_for_signal", 3))
    low_roi_threshold = float(policy.get("low_roi_threshold", 0.4))
    top_material_limit = int(policy.get("top_material_limit", 10))

    with sqlite3.connect(db_path) as conn:
        metric_rows = _promotion_metrics(conn, target_date)
        account_signals = _account_signals(
            metric_rows,
            min_cost=min_cost,
            min_conversions=min_conversions,
            low_roi_threshold=low_roi_threshold,
        )
        top_materials = _top_materials(conn, target_date=target_date, limit=top_material_limit)
        operation_logs = _operation_logs(conn, target_date=target_date, limit=int(policy.get("operation_log_limit", 20)))

    material_delta = {
        "target_date": target_date,
        "top_materials": top_materials,
    }
    operation_log_summary = _operation_log_summary(operation_logs, target_date=target_date)
    decision_hints = _decision_hints(account_signals, top_materials, operation_log_summary)
    return {
        "ok": True,
        "workflow": "daily_learning",
        "phase": "phase1",
        "execution_enabled": False,
        "external_api_calls": 0,
        "summary": {
            "target_date": target_date,
            "promotion_metric_count": len(metric_rows),
            "account_signal_count": len(account_signals),
            "top_material_count": len(top_materials),
            "operation_log_count": operation_log_summary["total_count"],
            "decision_hint_count": len(decision_hints),
        },
        "account_signals": account_signals,
        "material_delta": material_delta,
        "operation_log_summary": operation_log_summary,
        "decision_hints": decision_hints,
        "guardrails": GUARDRAILS,
    }


def run_daily_learning_request(
    request: dict[str, Any],
    *,
    db_path: str | Path,
    runs_dir: str | Path,
) -> dict[str, Any]:
    policy = _daily_learning_config(request)
    artifact_payload = build_daily_learning_artifact(db_path=db_path, policy=policy)
    artifact = write_run_artifact(runs_dir, "daily_learning", artifact_payload)
    return {
        "ok": True,
        "workflow": "daily_learning",
        "phase": "phase1",
        "execution_enabled": False,
        "external_api_calls": 0,
        "artifact": json.loads(json.dumps(artifact_payload, ensure_ascii=False)),
        "artifact_path": str(artifact),
    }
