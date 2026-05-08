from __future__ import annotations

import json
import sqlite3
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from roibang_v2.config import load_json


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _pick(data: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in data and data.get(key) not in (None, ""):
            return data.get(key)
    return ""


def _float(value: Any) -> float:
    try:
        return float(str(value or "0").replace(",", "").replace("%", ""))
    except ValueError:
        return 0.0


def _period(data: dict[str, Any]) -> dict[str, str]:
    value = data.get("period") if isinstance(data.get("period"), dict) else {}
    start = str(value.get("start") or "").strip()
    end = str(value.get("end") or "").strip()
    if not start or not end:
        raise ValueError("report snapshot requires period.start and period.end")
    return {"start": start, "end": end}


def normalize_project(row: dict[str, Any]) -> dict[str, str]:
    return {
        "advertiser_id": str(_pick(row, "advertiser_id")),
        "project_id": str(_pick(row, "project_id", "cdp_project_id")),
        "name": str(_pick(row, "project_name", "cdp_project_name", "name")),
        "status": str(_pick(row, "project_status", "project_status_name", "status")),
    }


def normalize_promotion(row: dict[str, Any]) -> dict[str, str]:
    return {
        "advertiser_id": str(_pick(row, "advertiser_id")),
        "project_id": str(_pick(row, "project_id", "cdp_project_id")),
        "promotion_id": str(_pick(row, "promotion_id", "cdp_promotion_id")),
        "name": str(_pick(row, "promotion_name", "cdp_promotion_name", "name")),
        "status": str(_pick(row, "promotion_status_name", "promotion_status", "status")),
    }


def normalize_operation_log(row: dict[str, Any], *, advertiser_id: str) -> dict[str, Any]:
    occurred_at = str(_pick(row, "occurred_at", "create_time", "operation_time", "time")).strip()
    entity_type = str(_pick(row, "entity_type", "target_type", "object_type")).strip()
    entity_id = str(_pick(row, "entity_id", "target_id", "object_id")).strip()
    action = str(_pick(row, "action", "operation", "operation_type")).strip()
    stable = json.dumps(
        {
            "advertiser_id": advertiser_id,
            "occurred_at": occurred_at,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "action": action,
            "detail": str(_pick(row, "detail", "description", "message")),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    operation_id = str(_pick(row, "operation_id", "log_id", "id")).strip()
    if not operation_id:
        operation_id = "op_" + hashlib.sha256(stable.encode("utf-8")).hexdigest()[:24]
    return {
        "operation_id": operation_id,
        "occurred_at": occurred_at,
        "advertiser_id": advertiser_id,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "action": action,
        "operator": str(_pick(row, "operator", "operator_name", "user_name")),
        "detail": str(_pick(row, "detail", "description", "message")),
        "before": row.get("before") if isinstance(row.get("before"), dict) else {},
        "after": row.get("after") if isinstance(row.get("after"), dict) else {},
        "payload": row,
    }


def iter_materials(promotion: dict[str, Any]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    roots = [promotion]
    if isinstance(promotion.get("promotion_materials"), dict):
        roots.append(promotion["promotion_materials"])
    for root in roots:
        for key, kind in (
            ("video_material_list", "video"),
            ("title_material_list", "title"),
            ("image_material_list", "image"),
            ("trial_play_material_list", "trial_play"),
            ("instant_play_material_list", "instant_play"),
        ):
            raw_rows = root.get(key)
            if not isinstance(raw_rows, list):
                continue
            for raw in raw_rows:
                if not isinstance(raw, dict):
                    continue
                title = str(_pick(raw, "title", "name", "material_name"))
                material_id = str(_pick(raw, "material_id", "video_id", "image_id", "item_id", "title"))
                if not material_id:
                    continue
                out.append(
                    {
                        "advertiser_id": str(_pick(promotion, "advertiser_id")),
                        "project_id": str(_pick(promotion, "project_id", "cdp_project_id")),
                        "promotion_id": str(_pick(promotion, "promotion_id", "cdp_promotion_id")),
                        "material_kind": kind,
                        "material_id": material_id,
                        "video_id": str(_pick(raw, "video_id")),
                        "image_id": str(_pick(raw, "image_id")),
                        "title": title,
                    }
                )
    return out


def summarize_materials(
    material_rows: list[dict[str, Any]],
    promotion_metrics: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, str], dict[str, Any]] = {}
    for row in material_rows:
        key = (str(row.get("material_kind") or ""), str(row.get("material_id") or ""))
        if not key[0] or not key[1]:
            continue
        bucket = buckets.setdefault(
            key,
            {
                "material_kind": key[0],
                "material_id": key[1],
                "video_id": str(row.get("video_id") or ""),
                "title": str(row.get("title") or ""),
                "promotion_ids": set(),
                "project_ids": set(),
                "advertiser_ids": set(),
                "stat_cost": 0.0,
                "active_register": 0.0,
                "attribution_convert_cnt": 0.0,
                "roi1_num": 0.0,
                "roi7_num": 0.0,
            },
        )
        promotion_id = str(row.get("promotion_id") or "")
        bucket["promotion_ids"].add(promotion_id)
        bucket["project_ids"].add(str(row.get("project_id") or ""))
        bucket["advertiser_ids"].add(str(row.get("advertiser_id") or ""))
        metrics = promotion_metrics.get(promotion_id) or {}
        cost = _float(metrics.get("stat_cost"))
        bucket["stat_cost"] += cost
        bucket["active_register"] += _float(metrics.get("active_register"))
        bucket["attribution_convert_cnt"] += _float(metrics.get("attribution_convert_cnt") or metrics.get("convert_cnt"))
        bucket["roi1_num"] += cost * _float(
            metrics.get("attribution_billing_game_in_app_roi_1day") or metrics.get("pay_amount_roi")
        )
        bucket["roi7_num"] += cost * _float(metrics.get("attribution_billing_game_in_app_roi_7days"))

    result: list[dict[str, Any]] = []
    for bucket in buckets.values():
        cost = float(bucket["stat_cost"])
        result.append(
            {
                "material_kind": bucket["material_kind"],
                "material_id": bucket["material_id"],
                "video_id": bucket["video_id"],
                "title": bucket["title"],
                "promotion_count": len(bucket["promotion_ids"]),
                "project_count": len(bucket["project_ids"]),
                "account_count": len(bucket["advertiser_ids"]),
                "stat_cost": round(cost, 2),
                "active_register": round(float(bucket["active_register"]), 4),
                "attribution_convert_cnt": round(float(bucket["attribution_convert_cnt"]), 4),
                "roi_1day_cost_weighted": round(float(bucket["roi1_num"]) / cost, 4) if cost else 0,
                "roi_7days_cost_weighted": round(float(bucket["roi7_num"]) / cost, 4) if cost else 0,
            }
        )
    return sorted(result, key=lambda item: _float(item["stat_cost"]), reverse=True)


def import_report_snapshot_file(path: str | Path, *, db_path: str | Path) -> dict[str, Any]:
    source = Path(path)
    data = load_json(source)
    period = _period(data)
    accounts = data.get("accounts")
    if not isinstance(accounts, list):
        raise ValueError("report snapshot requires accounts list")
    synced_at = _now_iso()
    projects: list[dict[str, str]] = []
    promotions: list[dict[str, str]] = []
    bindings: list[dict[str, str]] = []
    operation_logs: list[dict[str, Any]] = []
    metrics_by_promotion: dict[str, dict[str, Any]] = {}

    for account in accounts:
        if not isinstance(account, dict):
            continue
        for project in account.get("projects") or []:
            if isinstance(project, dict):
                normalized = normalize_project(project)
                if normalized["project_id"]:
                    projects.append(normalized)
        for promotion in account.get("promotions") or []:
            if isinstance(promotion, dict):
                normalized = normalize_promotion(promotion)
                if normalized["promotion_id"]:
                    promotions.append(normalized)
                    bindings.extend(iter_materials(promotion))
        for row in account.get("promotion_metrics") or []:
            if isinstance(row, dict):
                promotion_id = str(_pick(row, "promotion_id", "cdp_promotion_id"))
                if promotion_id:
                    metrics_by_promotion[promotion_id] = row
        advertiser_id = str(_pick(account, "advertiser_id"))
        for row in account.get("operation_logs") or []:
            if isinstance(row, dict):
                normalized = normalize_operation_log(row, advertiser_id=advertiser_id)
                if normalized["operation_id"] and normalized["occurred_at"] and normalized["entity_type"] and normalized["entity_id"]:
                    operation_logs.append(normalized)

    material_summary = summarize_materials(bindings, metrics_by_promotion)
    with sqlite3.connect(db_path) as conn:
        for project in projects:
            conn.execute(
                """
                INSERT INTO projects (project_id, advertiser_id, name, status, source, synced_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id) DO UPDATE SET
                  advertiser_id = excluded.advertiser_id,
                  name = excluded.name,
                  status = excluded.status,
                  source = excluded.source,
                  synced_at = excluded.synced_at
                """,
                (project["project_id"], project["advertiser_id"], project["name"], project["status"], str(source), synced_at),
            )
        for promotion in promotions:
            conn.execute(
                """
                INSERT INTO promotions (promotion_id, advertiser_id, project_id, name, status, source, synced_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(promotion_id) DO UPDATE SET
                  advertiser_id = excluded.advertiser_id,
                  project_id = excluded.project_id,
                  name = excluded.name,
                  status = excluded.status,
                  source = excluded.source,
                  synced_at = excluded.synced_at
                """,
                (
                    promotion["promotion_id"],
                    promotion["advertiser_id"],
                    promotion["project_id"],
                    promotion["name"],
                    promotion["status"],
                    str(source),
                    synced_at,
                ),
            )
        for binding in bindings:
            conn.execute(
                """
                INSERT INTO material_bindings (
                  advertiser_id, project_id, promotion_id, material_kind, material_id,
                  video_id, image_id, title, source, synced_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(promotion_id, material_kind, material_id) DO UPDATE SET
                  advertiser_id = excluded.advertiser_id,
                  project_id = excluded.project_id,
                  video_id = excluded.video_id,
                  image_id = excluded.image_id,
                  title = excluded.title,
                  source = excluded.source,
                  synced_at = excluded.synced_at
                """,
                (
                    binding["advertiser_id"],
                    binding["project_id"],
                    binding["promotion_id"],
                    binding["material_kind"],
                    binding["material_id"],
                    binding["video_id"],
                    binding["image_id"],
                    binding["title"],
                    str(source),
                    synced_at,
                ),
            )
        for promotion_id, metric in metrics_by_promotion.items():
            conn.execute(
                """
                DELETE FROM metric_snapshots
                WHERE entity_type = ?
                  AND entity_id = ?
                  AND metric_date = ?
                """,
                ("promotion", promotion_id, period["end"]),
            )
            conn.execute(
                """
                INSERT INTO metric_snapshots (
                  entity_type, entity_id, metric_date, cost, conversions, roi, payload_json, synced_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "promotion",
                    promotion_id,
                    period["end"],
                    _float(metric.get("stat_cost")),
                    int(_float(metric.get("attribution_convert_cnt") or metric.get("convert_cnt"))),
                    _float(metric.get("attribution_billing_game_in_app_roi_1day") or metric.get("pay_amount_roi")),
                    json.dumps(metric, ensure_ascii=False, sort_keys=True),
                    synced_at,
                ),
            )
        for row in material_summary:
            conn.execute(
                """
                INSERT INTO material_metric_summaries (
                  material_kind, material_id, video_id, title, period_start, period_end,
                  promotion_count, project_count, account_count, stat_cost, active_register,
                  attribution_convert_cnt, roi_1day_cost_weighted, roi_7days_cost_weighted,
                  source, synced_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(period_start, period_end, material_kind, material_id) DO UPDATE SET
                  video_id = excluded.video_id,
                  title = excluded.title,
                  promotion_count = excluded.promotion_count,
                  project_count = excluded.project_count,
                  account_count = excluded.account_count,
                  stat_cost = excluded.stat_cost,
                  active_register = excluded.active_register,
                  attribution_convert_cnt = excluded.attribution_convert_cnt,
                  roi_1day_cost_weighted = excluded.roi_1day_cost_weighted,
                  roi_7days_cost_weighted = excluded.roi_7days_cost_weighted,
                  source = excluded.source,
                  synced_at = excluded.synced_at
                """,
                (
                    row["material_kind"],
                    row["material_id"],
                    row["video_id"],
                    row["title"],
                    period["start"],
                    period["end"],
                    row["promotion_count"],
                    row["project_count"],
                    row["account_count"],
                    row["stat_cost"],
                    row["active_register"],
                    row["attribution_convert_cnt"],
                    row["roi_1day_cost_weighted"],
                    row["roi_7days_cost_weighted"],
                    str(source),
                    synced_at,
                ),
            )
        for row in operation_logs:
            conn.execute(
                """
                INSERT INTO operation_logs (
                  operation_id, occurred_at, advertiser_id, entity_type, entity_id,
                  action, operator, detail, before_json, after_json, payload_json,
                  source, synced_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(operation_id) DO UPDATE SET
                  occurred_at = excluded.occurred_at,
                  advertiser_id = excluded.advertiser_id,
                  entity_type = excluded.entity_type,
                  entity_id = excluded.entity_id,
                  action = excluded.action,
                  operator = excluded.operator,
                  detail = excluded.detail,
                  before_json = excluded.before_json,
                  after_json = excluded.after_json,
                  payload_json = excluded.payload_json,
                  source = excluded.source,
                  synced_at = excluded.synced_at
                """,
                (
                    row["operation_id"],
                    row["occurred_at"],
                    row["advertiser_id"],
                    row["entity_type"],
                    row["entity_id"],
                    row["action"],
                    row["operator"],
                    row["detail"],
                    json.dumps(row["before"], ensure_ascii=False, sort_keys=True),
                    json.dumps(row["after"], ensure_ascii=False, sort_keys=True),
                    json.dumps(row["payload"], ensure_ascii=False, sort_keys=True),
                    str(source),
                    synced_at,
                ),
            )

    return {
        "ok": True,
        "period": period,
        "accounts": len(accounts),
        "projects_imported": len(projects),
        "promotions_imported": len(promotions),
        "material_bindings_imported": len(bindings),
        "promotion_metrics_imported": len(metrics_by_promotion),
        "operation_logs_imported": len(operation_logs),
        "material_summary_count": len(material_summary),
        "external_api_calls": 0,
    }
