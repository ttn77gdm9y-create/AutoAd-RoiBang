from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from roibang_v2.materials.gravity_qualification import qualification_summary
from roibang_v2.materials.gravity_qualification import qualify_gravity_material
from roibang_v2.runs import write_run_artifact

WORKFLOW = "gravity_material_qualification"


def run_gravity_material_qualification_request(
    request: dict[str, Any],
    *,
    db_path: str | Path,
    runs_dir: str | Path,
) -> dict[str, Any]:
    cfg = request.get("gravity_material_qualification") if isinstance(request.get("gravity_material_qualification"), dict) else request
    product = _text(cfg.get("product"))
    rows = _gravity_material_rows(db_path, product=product)
    if not rows:
        result = _blocked_payload(product=product)
        result["artifact_path"] = str(write_run_artifact(runs_dir, WORKFLOW, result))
        return result

    counts = qualification_summary(rows)
    by_product = _summary_rows_by_product(rows)
    product_label = product or "全部产品"
    result = {
        "ok": True,
        "workflow": WORKFLOW,
        "phase": "gravity_material_qualification",
        "status": "completed",
        "execution_enabled": False,
        "external_api_calls": 0,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "中文摘要": (
            f"{product_label}引力素材资格汇总完成：素材 {counts['material_count']} 个，"
            f"可用于后续 {counts['eligible_count']} 个，不可用 {counts['ineligible_count']} 个，"
            f"缺 MD5 {counts['missing_md5_count']} 个，已上传 {counts['uploaded_count']} 个，"
            f"未上传 {counts['not_uploaded_count']} 个；未上传素材、未创建广告。"
        ),
        "summary": {
            "title": "引力素材资格汇总",
            "status": "completed",
            "product": product_label,
            **counts,
            "upload_material_called": False,
        },
        "table": {
            "columns": ["产品", "素材数", "可用于后续", "不可用", "缺 MD5", "已上传", "未上传", "有表现数据"],
            "rows": by_product,
        },
        "sections": [
            {
                "title": "不可用原因明细",
                "table": {
                    "columns": ["产品", "素材名", "引力素材 ID", "不可用原因"],
                    "rows": [
                        {
                            "产品": row["product"],
                            "素材名": row["name"],
                            "引力素材 ID": row["material_id"],
                            "不可用原因": row["qualification_reason"],
                        }
                        for row in rows
                        if not row["is_eligible_for_next_step"]
                    ],
                },
            }
        ],
        "warnings": ["本汇总只读取本地引力素材数据，不上传素材、不创建广告。"],
        "blocking_reasons": [],
        "guardrails": ["不调用 upload_material。", "不创建广告。", "不修改预算、出价或项目状态。"],
        "raw": {"request": {"product": product}, "materials": rows},
    }
    result["artifact_path"] = str(write_run_artifact(runs_dir, WORKFLOW, result))
    return result


def _blocked_payload(*, product: str) -> dict[str, Any]:
    product_label = product or "全部产品"
    reason = f"{product_label}还没有本地引力素材，请先运行引力素材同步入库。"
    return {
        "ok": False,
        "workflow": WORKFLOW,
        "phase": "gravity_material_qualification",
        "status": "blocked",
        "execution_enabled": False,
        "external_api_calls": 0,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "中文摘要": f"引力素材资格汇总被阻止：{reason}",
        "summary": {
            "title": "引力素材资格汇总",
            "status": "blocked",
            "product": product_label,
            "material_count": 0,
            "eligible_count": 0,
            "ineligible_count": 0,
            "missing_md5_count": 0,
            "uploaded_count": 0,
            "not_uploaded_count": 0,
            "has_performance_count": 0,
            "upload_material_called": False,
        },
        "table": {"columns": ["阻塞原因"], "rows": [{"阻塞原因": reason}]},
        "warnings": ["未上传素材、未创建广告、未修改投放。"],
        "blocking_reasons": [reason],
        "raw": {"request": {"product": product}},
    }


def _gravity_material_rows(db_path: str | Path, *, product: str) -> list[dict[str, Any]]:
    clauses = ["psm.source = 'gravity_engine'"]
    params: list[Any] = []
    if product:
        clauses.append("psm.product = ?")
        params.append(product)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"""
            SELECT
              psm.product, psm.source_advertiser_id, psm.organization_id,
              psm.material_id, psm.video_id, psm.name, psm.review_status, psm.signature,
              psm.is_active, psm.synced_at, psm.payload_json,
              COALESCE(MAX(psmr.stat_cost), psm.cost_lookback, 0) AS stat_cost,
              COALESCE(MAX(psmr.show_cnt), 0) AS show_cnt,
              COALESCE(MAX(psmr.click_cnt), 0) AS click_cnt,
              COALESCE(MAX(psmr.convert_cnt), 0) AS convert_cnt
            FROM product_source_materials psm
            LEFT JOIN product_source_material_metric_rollups psmr
              ON psmr.product = psm.product
             AND psmr.source_advertiser_id = psm.source_advertiser_id
             AND psmr.material_id = psm.material_id
            WHERE {" AND ".join(clauses)}
            GROUP BY
              psm.product, psm.source_advertiser_id, psm.organization_id,
              psm.material_id, psm.video_id, psm.name, psm.review_status, psm.signature,
              psm.is_active, psm.synced_at, psm.payload_json, psm.cost_lookback
            ORDER BY psm.product, psm.is_active DESC, stat_cost DESC, psm.material_id ASC
            """,
            tuple(params),
        ).fetchall()
    return [_row_payload(dict(row)) for row in rows]


def _row_payload(row: dict[str, Any]) -> dict[str, Any]:
    payload = _load_payload(row.get("payload_json"))
    material = {
        **row,
        "album_name": _text(payload.get("album_name")),
        "folder_name": _text(payload.get("folder_name")),
        "gravity_status": _text(payload.get("status")),
        "stat_cost": float(row.get("stat_cost") or 0),
        "show_cnt": float(row.get("show_cnt") or 0),
        "click_cnt": float(row.get("click_cnt") or 0),
        "convert_cnt": float(row.get("convert_cnt") or 0),
    }
    return {**material, **qualify_gravity_material(material)}


def _summary_rows_by_product(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        buckets[_text(row.get("product"))].append(row)
    result = []
    for product in sorted(buckets):
        counts = qualification_summary(buckets[product])
        result.append(
            {
                "产品": product,
                "素材数": counts["material_count"],
                "可用于后续": counts["eligible_count"],
                "不可用": counts["ineligible_count"],
                "缺 MD5": counts["missing_md5_count"],
                "已上传": counts["uploaded_count"],
                "未上传": counts["not_uploaded_count"],
                "有表现数据": counts["has_performance_count"],
            }
        )
    return result


def _load_payload(value: Any) -> dict[str, Any]:
    try:
        payload = json.loads(str(value or "{}"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()
