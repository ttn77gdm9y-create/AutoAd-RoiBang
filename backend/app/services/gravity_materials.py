from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from backend.app.services.artifacts import find_latest_artifact
from backend.app.services.artifacts import read_json
from roibang_v2.db.bootstrap import bootstrap_database
from roibang_v2.materials.gravity_qualification import matches_qualification_filter
from roibang_v2.materials.gravity_qualification import qualification_summary
from roibang_v2.materials.gravity_qualification import qualify_gravity_material


def database_path(project_root: str | Path) -> Path:
    return Path(project_root) / "data" / "roibang_v2.sqlite3"


def list_gravity_bindings(*, project_root: str | Path, product: str = "") -> dict[str, Any]:
    db_path = database_path(project_root)
    bootstrap_database(db_path)
    bindings = _binding_rows(db_path, product=product, active_only=True)
    return {
        "summary": {
            "title": "引力素材绑定",
            "status": "loaded",
            "risk_level": "low",
            "execution_enabled": False,
            "items": [{"label": "绑定数", "value": len(bindings)}],
            "warnings": [],
            "blocking_reasons": [],
        },
        "table": {
            "columns": ["产品", "专辑", "文件夹", "状态"],
            "rows": [
                {
                    "产品": item["product"],
                    "专辑": item["album_name"],
                    "文件夹": item["folder_name"] or "整个专辑",
                    "状态": "启用" if item["is_active"] else "停用",
                }
                for item in bindings
            ],
        },
        "artifact_path": "",
        "raw": {"bindings": bindings},
    }


def save_gravity_binding(*, project_root: str | Path, body: dict[str, Any]) -> dict[str, Any]:
    db_path = database_path(project_root)
    bootstrap_database(db_path)
    binding = _normalized_binding(body)
    blocking = _binding_blocking_reasons(binding)
    if blocking:
        return _blocked_result("引力素材绑定未保存", blocking)
    with sqlite3.connect(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO product_gravity_album_bindings (
              product, album_id, album_name, folder_id, folder_name, is_active
            ) VALUES (?, ?, ?, ?, ?, 1)
            ON CONFLICT(product, album_id, folder_id)
            DO UPDATE SET
              album_name = excluded.album_name,
              folder_name = excluded.folder_name,
              is_active = 1,
              updated_at = datetime('now')
            RETURNING id
            """,
            (
                binding["product"],
                binding["album_id"],
                binding["album_name"],
                binding["folder_id"],
                binding["folder_name"],
            ),
        )
        binding_id = int(cursor.fetchone()[0])
    saved = {**binding, "id": binding_id, "is_active": 1}
    return {
        "summary": {
            "title": "引力素材绑定已保存",
            "status": "committed",
            "risk_level": "low",
            "execution_enabled": False,
            "items": [
                {"label": "产品", "value": binding["product"]},
                {"label": "真实投放动作", "value": "未执行"},
            ],
            "warnings": ["保存绑定只写本地数据库；不会上传素材、不会创建广告。"],
            "blocking_reasons": [],
        },
        "table": {
            "columns": ["产品", "专辑", "文件夹"],
            "rows": [
                {
                    "产品": binding["product"],
                    "专辑": binding["album_name"],
                    "文件夹": binding["folder_name"] or "整个专辑",
                }
            ],
        },
        "artifact_path": "",
        "raw": {"binding": saved},
    }


def delete_gravity_binding(*, project_root: str | Path, binding_id: int) -> dict[str, Any]:
    db_path = database_path(project_root)
    bootstrap_database(db_path)
    with sqlite3.connect(db_path) as conn:
        cursor = conn.execute(
            """
            UPDATE product_gravity_album_bindings
            SET is_active = 0, updated_at = datetime('now')
            WHERE id = ?
            """,
            (binding_id,),
        )
        deleted = int(cursor.rowcount or 0)
    return {
        "summary": {
            "title": "引力素材绑定已删除",
            "status": "committed" if deleted else "blocked",
            "risk_level": "low",
            "execution_enabled": False,
            "items": [{"label": "删除数量", "value": deleted}],
            "warnings": ["删除绑定只影响后续同步范围，不删除已同步素材。"] if deleted else [],
            "blocking_reasons": [] if deleted else ["没有找到要删除的绑定"],
        },
        "table": {"columns": ["删除数量"], "rows": [{"删除数量": deleted}]},
        "artifact_path": "",
        "raw": {"binding_id": binding_id, "deleted": deleted},
    }


def list_gravity_materials(
    *,
    project_root: str | Path,
    product: str = "",
    status: str = "",
    keyword: str = "",
    limit: int = 100,
) -> dict[str, Any]:
    db_path = database_path(project_root)
    bootstrap_database(db_path)
    summary_rows = _material_rows(db_path, product=product, status="", keyword=keyword, limit=500)
    rows = _material_rows(db_path, product=product, status=status, keyword=keyword, limit=limit)
    counts = qualification_summary(summary_rows)
    latest_sync = _latest_sync(project_root)
    latest_qualification = _latest_qualification(project_root)
    return {
        "summary": {
            "title": "引力素材库",
            "status": "loaded",
            "risk_level": "low",
            "execution_enabled": False,
            "items": [
                {"label": "素材数", "value": len(summary_rows)},
                {"label": "可用于后续", "value": counts["eligible_count"]},
                {"label": "不可用", "value": counts["ineligible_count"]},
                {"label": "缺 MD5", "value": counts["missing_md5_count"]},
                {"label": "已上传", "value": counts["uploaded_count"]},
                {"label": "未上传", "value": counts["not_uploaded_count"]},
                {"label": "有表现数据", "value": counts["has_performance_count"]},
                {"label": "最近同步", "value": latest_sync.get("status_label") or "暂无"},
                {"label": "最近资格汇总", "value": latest_qualification.get("status_label") or "暂无"},
            ],
            "warnings": ["这里只展示本地已同步的引力素材；不会上传素材、不会创建广告。"],
            "blocking_reasons": [],
        },
        "table": {
            "columns": [
                "产品",
                "专辑",
                "文件夹",
                "素材名",
                "引力素材 ID",
                "MD5",
                "状态",
                "资格状态",
                "不可用原因",
                "上传状态",
                "媒体素材 ID",
                "消耗",
                "展示",
                "点击",
                "转化",
                "同步时间",
            ],
            "rows": [
                {
                    "产品": item["product"],
                    "专辑": item["album_name"],
                    "文件夹": item["folder_name"],
                    "素材名": item["name"],
                    "引力素材 ID": item["material_id"],
                    "MD5": item["signature"],
                    "状态": item["review_status"],
                    "资格状态": item["qualification_status"],
                    "不可用原因": item["qualification_reason"],
                    "上传状态": item["upload_status"],
                    "媒体素材 ID": item["video_id"],
                    "消耗": item["stat_cost"],
                    "展示": item["show_cnt"],
                    "点击": item["click_cnt"],
                    "转化": item["convert_cnt"],
                    "同步时间": item["synced_at"],
                }
                for item in rows
            ],
        },
        "sections": [
            {
                "title": "最近同步结果",
                "table": {
                    "columns": ["状态", "结果文件", "中文摘要"],
                    "rows": [
                        {
                            "状态": latest_sync.get("status_label") or "暂无",
                            "结果文件": latest_sync.get("artifact_path") or "",
                            "中文摘要": latest_sync.get("summary") or "",
                        }
                    ],
                },
            },
            {
                "title": "最近资格汇总",
                "table": {
                    "columns": ["状态", "结果文件", "中文摘要"],
                    "rows": [
                        {
                            "状态": latest_qualification.get("status_label") or "暂无",
                            "结果文件": latest_qualification.get("artifact_path") or "",
                            "中文摘要": latest_qualification.get("summary") or "",
                        }
                    ],
                },
            },
        ],
        "artifact_path": "",
        "raw": {"materials": rows, "qualification_summary": counts, "latest_sync": latest_sync, "latest_qualification": latest_qualification},
    }


def gravity_album_tree(*, project_root: str | Path) -> dict[str, Any]:
    artifact = find_latest_artifact(Path(project_root) / "data" / "runs", "gravity_api_probe")
    payload = read_json(artifact) if artifact else {}
    album_tree = _dict(_dict(payload.get("raw")).get("endpoint_results")).get("album_tree", {})
    nodes = _album_nodes(album_tree if isinstance(album_tree, dict) else {})
    return {
        "summary": {
            "title": "引力专辑树",
            "status": "loaded" if nodes else "empty",
            "risk_level": "low",
            "execution_enabled": False,
            "items": [{"label": "节点数", "value": len(nodes)}],
            "warnings": [] if nodes else ["还没有专辑树样本，请先在自动化工作台运行引力素材库只读探测。"],
            "blocking_reasons": [],
        },
        "table": {"columns": ["专辑/文件夹 ID", "名称", "层级"], "rows": nodes},
        "artifact_path": str(artifact or ""),
        "raw": {"album_tree": album_tree, "nodes": nodes},
    }


def _binding_rows(db_path: Path, *, product: str, active_only: bool) -> list[dict[str, Any]]:
    clauses = []
    params: list[Any] = []
    if product:
        clauses.append("product = ?")
        params.append(product)
    if active_only:
        clauses.append("is_active = 1")
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"""
            SELECT id, product, album_id, album_name, folder_id, folder_name, is_active
            FROM product_gravity_album_bindings
            {where}
            ORDER BY product, album_name, folder_name
            """,
            tuple(params),
        ).fetchall()
    return [dict(row) for row in rows]


def _material_rows(db_path: Path, *, product: str, status: str, keyword: str, limit: int) -> list[dict[str, Any]]:
    normalized_limit = max(1, min(500, int(limit or 100)))
    qualification_filters = {"eligible", "ineligible", "missing_md5", "uploaded", "not_uploaded", "has_performance"}
    sql_limit = 500 if status in qualification_filters else normalized_limit
    clauses = ["psm.source = 'gravity_engine'"]
    params: list[Any] = []
    if product:
        clauses.append("psm.product = ?")
        params.append(product)
    if status == "active":
        clauses.append("psm.is_active = 1")
    elif status == "inactive":
        clauses.append("psm.is_active = 0")
    if keyword:
        clauses.append("(psm.name LIKE ? OR psm.material_id LIKE ? OR psm.signature LIKE ?)")
        like = f"%{keyword}%"
        params.extend([like, like, like])
    params.append(sql_limit)
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
            ORDER BY psm.is_active DESC, stat_cost DESC, psm.synced_at DESC, psm.material_id ASC
            LIMIT ?
            """,
            tuple(params),
        ).fetchall()
    hydrated_rows = [_material_payload(dict(row)) for row in rows]
    filtered_rows = [row for row in hydrated_rows if matches_qualification_filter(row, status)]
    return filtered_rows[:normalized_limit]


def _material_payload(row: dict[str, Any]) -> dict[str, Any]:
    payload = _load_payload(row.get("payload_json"))
    return {
        **row,
        "album_id": _text(payload.get("album_id")),
        "album_name": _text(payload.get("album_name")),
        "folder_id": _text(payload.get("folder_id")),
        "folder_name": _text(payload.get("folder_name")),
        "gravity_status": _text(payload.get("status")),
        "stat_cost": float(row.get("stat_cost") or 0),
        "show_cnt": float(row.get("show_cnt") or 0),
        "click_cnt": float(row.get("click_cnt") or 0),
        "convert_cnt": float(row.get("convert_cnt") or 0),
        **qualify_gravity_material({**row, "gravity_status": _text(payload.get("status"))}),
    }


def _latest_sync(project_root: str | Path) -> dict[str, Any]:
    return _latest_workflow(project_root, "gravity_material_sync")


def _latest_qualification(project_root: str | Path) -> dict[str, Any]:
    return _latest_workflow(project_root, "gravity_material_qualification")


def _latest_workflow(project_root: str | Path, workflow: str) -> dict[str, Any]:
    artifact = find_latest_artifact(Path(project_root) / "data" / "runs", workflow)
    if not artifact:
        return {}
    payload = read_json(artifact)
    status = _text(payload.get("status"))
    return {
        "status": status,
        "status_label": "已完成" if status == "completed" else "已阻止" if status == "blocked" else status,
        "artifact_path": _display_path(Path(project_root), artifact),
        "summary": _text(payload.get("中文摘要")),
    }


def _normalized_binding(body: dict[str, Any]) -> dict[str, str]:
    return {
        "product": _text(body.get("product")),
        "album_id": _text(body.get("album_id")),
        "album_name": _text(body.get("album_name")),
        "folder_id": _text(body.get("folder_id")),
        "folder_name": _text(body.get("folder_name")),
    }


def _binding_blocking_reasons(binding: dict[str, str]) -> list[str]:
    reasons = []
    if not binding["product"]:
        reasons.append("请选择产品")
    if not binding["album_id"]:
        reasons.append("请选择引力专辑")
    if not binding["album_name"]:
        reasons.append("专辑名称不能为空")
    return reasons


def _blocked_result(title: str, blocking_reasons: list[str]) -> dict[str, Any]:
    return {
        "summary": {
            "title": title,
            "status": "blocked",
            "risk_level": "low",
            "execution_enabled": False,
            "items": [],
            "warnings": [],
            "blocking_reasons": blocking_reasons,
        },
        "table": {"columns": ["阻塞原因"], "rows": [{"阻塞原因": reason} for reason in blocking_reasons]},
        "artifact_path": "",
        "raw": {"blocking_reasons": blocking_reasons},
    }


def _album_nodes(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("data")
    roots = data if isinstance(data, list) else data.get("list") if isinstance(data, dict) and isinstance(data.get("list"), list) else []
    nodes: list[dict[str, Any]] = []

    def visit(node: Any, level: int, *, album_id: str = "", album_name: str = "") -> None:
        if not isinstance(node, dict):
            return
        node_id = _text(node.get("id") or node.get("album_id"))
        node_name = _text(node.get("name"))
        current_album_id = node_id if level == 1 else album_id
        current_album_name = node_name if level == 1 else album_name
        nodes.append(
            {
                "专辑/文件夹 ID": node_id,
                "名称": node_name,
                "层级": level,
                "album_id": current_album_id,
                "album_name": current_album_name,
                "folder_id": "" if level == 1 else node_id,
                "folder_name": "" if level == 1 else node_name,
            }
        )
        children = node.get("children")
        if isinstance(children, list):
            for child in children:
                visit(child, level + 1, album_id=current_album_id, album_name=current_album_name)

    for root in roots:
        visit(root, 1)
    return nodes


def _load_payload(value: Any) -> dict[str, Any]:
    try:
        payload = json.loads(str(value or "{}"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _display_path(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()
