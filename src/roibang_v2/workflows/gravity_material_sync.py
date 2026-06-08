from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from datetime import date
from datetime import datetime
from datetime import timedelta
from pathlib import Path
from typing import Any

from roibang_v2.fetch.gravity_material_library import GravityMaterialClient
from roibang_v2.fetch.gravity_material_library import GravityMaterialLibraryError
from roibang_v2.fetch.gravity_material_library import auth_summary
from roibang_v2.fetch.gravity_material_library import load_gravity_auth_file
from roibang_v2.fetch.gravity_material_library import source_advertiser_id_for_auth
from roibang_v2.fetch.gravity_material_library import validate_gravity_auth
from roibang_v2.materials.gravity_album_scope import binding_scope_blocking_reasons
from roibang_v2.materials.gravity_album_scope import load_target_album_names
from roibang_v2.materials.product_source import import_product_source_materials
from roibang_v2.runs import write_run_artifact

WORKFLOW = "gravity_material_sync"
REPORT_METRICS = ["AdCost", "AdShow", "AdClick", "AdConvert"]


def run_gravity_material_sync_request(
    request: dict[str, Any],
    *,
    db_path: str | Path,
    runs_dir: str | Path,
    client: Any | None = None,
) -> dict[str, Any]:
    cfg = request.get("gravity_material_sync") if isinstance(request.get("gravity_material_sync"), dict) else request
    auth_payload: dict[str, Any] = {}
    blocking_reasons: list[str] = []
    try:
        auth_payload = _auth_payload(cfg)
    except GravityMaterialLibraryError as exc:
        blocking_reasons.append(str(exc))
    if not blocking_reasons:
        blocking_reasons.extend(_auth_blocking_reasons(auth_payload))
    bindings = _active_bindings(db_path, product=_text(cfg.get("product")))
    if not bindings:
        blocking_reasons.append("请先在引力素材库页面绑定产品和专辑。")
    target_album_names = _target_album_names(cfg)
    if bindings:
        blocking_reasons.extend(binding_scope_blocking_reasons(bindings, target_album_names))

    if blocking_reasons:
        payload = _blocked_payload(cfg, auth_payload, bindings, blocking_reasons)
        payload["artifact_path"] = str(write_run_artifact(runs_dir, WORKFLOW, payload))
        return payload

    page_size = _int_value(cfg.get("page_size"), default=100, minimum=1, maximum=500)
    max_pages = _int_value(cfg.get("max_pages"), default=50, minimum=1, maximum=500)
    max_folders = _int_value(cfg.get("max_folders"), default=500, minimum=1, maximum=5000)
    max_depth = _int_value(cfg.get("max_depth"), default=8, minimum=1, maximum=20)
    date_range = _report_date_range(cfg)
    probe_client = client or GravityMaterialClient(auth_payload)
    external_api_calls = 0
    warnings: list[str] = []
    rows_by_product: dict[str, list[dict[str, Any]]] = defaultdict(list)
    rows_by_binding: dict[str, list[dict[str, Any]]] = defaultdict(list)
    disabled_by_binding: dict[str, int] = defaultdict(int)
    folders_scanned_by_binding: dict[str, int] = defaultdict(int)
    pages_read_by_binding: dict[str, int] = defaultdict(int)
    disabled_count = 0

    album_tree = probe_client.get_album_tree()
    external_api_calls += 1
    raw: dict[str, Any] = {"album_tree": _sanitized_payload(album_tree), "bindings": bindings}

    for binding in bindings:
        product = binding["product"]
        scanned = _scan_binding_materials(
            client=probe_client,
            binding=binding,
            page_size=page_size,
            max_pages=max_pages,
            max_folders=max_folders,
            max_depth=max_depth,
            raw=raw,
        )
        external_api_calls += int(scanned["external_api_calls"])
        warnings.extend(scanned["warnings"])
        folders_scanned_by_binding[binding["id"]] = int(scanned["folders_scanned"])
        pages_read_by_binding[binding["id"]] = int(scanned["pages_read"])
        for material in scanned["materials"]:
            if _is_active_material(material):
                row = _source_material_row(material, binding=material.get("_binding_scope", binding))
                rows_by_product[product].append(row)
                rows_by_binding[binding["id"]].append(row)
            else:
                disabled_count += 1
                disabled_by_binding[binding["id"]] += 1

    source_advertiser_id = source_advertiser_id_for_auth(auth_payload)
    organization_id = _text(auth_payload.get("gravity_cid"))
    imports = []
    rollup_rows_written = 0
    for product, rows in rows_by_product.items():
        imports.append(
            import_product_source_materials(
                db_path=db_path,
                product=product,
                source_advertiser_id=source_advertiser_id,
                organization_id=organization_id,
                materials=rows,
                source="gravity_engine",
                mark_absent_inactive=True,
            )
        )
        rollup_rows_written += _write_report_rollups(
            db_path=db_path,
            client=probe_client,
            product=product,
            source_advertiser_id=source_advertiser_id,
            organization_id=organization_id,
            materials=rows,
            date_range=date_range,
        )[0]
        if rows:
            external_api_calls += 1

    imported_count = sum(int(item["product_source_materials_imported"]) for item in imports)
    inactive_rows = sum(int(item["inactive_product_source_materials"]) for item in imports)
    status = "completed"
    payload = {
        "ok": True,
        "workflow": WORKFLOW,
        "phase": "gravity_material_library_sync",
        "status": status,
        "execution_enabled": False,
        "external_api_calls": external_api_calls,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "中文摘要": (
            f"更新引力素材完成：读取 {len(bindings)} 个绑定，保存 {imported_count} 个可用素材资料，"
            f"跳过 {disabled_count} 个禁用素材；未下载素材文件、未上传素材、未创建广告。"
        ),
        "summary": {
            "title": "更新引力素材",
            "status": status,
            "binding_count": len(bindings),
            "materials_received": imported_count + disabled_count,
            "active_materials_imported": imported_count,
            "inactive_materials_skipped": disabled_count,
            "inactive_product_source_materials": inactive_rows,
            "folders_scanned": sum(folders_scanned_by_binding.values()),
            "pages_read": sum(pages_read_by_binding.values()),
            "rollup_rows_written": rollup_rows_written,
            "source_advertiser_id": source_advertiser_id,
            "organization_id": organization_id,
            "upload_material_called": False,
        },
        "table": {
            "columns": ["产品", "绑定", "扫描文件夹", "发现素材", "入库素材", "禁用素材", "本地置为停用"],
            "rows": _summary_rows(
                bindings=bindings,
                rows_by_binding=rows_by_binding,
                disabled_by_binding=disabled_by_binding,
                folders_scanned_by_binding=folders_scanned_by_binding,
                inactive_rows=inactive_rows,
            ),
        },
        "warnings": warnings + ["更新引力素材只读取素材资料并写入本地数据库，不下载素材文件、不上传素材、不创建广告。"],
        "blocking_reasons": [],
        "guardrails": ["不调用 upload_material。", "不创建广告。", "不修改预算、出价或项目状态。"],
        "raw": raw,
    }
    payload["artifact_path"] = str(write_run_artifact(runs_dir, WORKFLOW, payload))
    return payload


def _blocked_payload(
    cfg: dict[str, Any],
    auth_payload: dict[str, Any],
    bindings: list[dict[str, str]],
    blocking_reasons: list[str],
) -> dict[str, Any]:
    return {
        "ok": False,
        "workflow": WORKFLOW,
        "phase": "gravity_material_library_sync",
        "status": "blocked",
        "execution_enabled": False,
        "external_api_calls": 0,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "中文摘要": f"更新引力素材被阻止：{'；'.join(blocking_reasons)}",
        "summary": {
            "title": "更新引力素材",
            "status": "blocked",
            "binding_count": len(bindings),
            "auth": auth_summary(auth_payload),
            "upload_material_called": False,
        },
        "table": {"columns": ["阻塞原因"], "rows": [{"阻塞原因": reason} for reason in blocking_reasons]},
        "warnings": ["未下载素材文件、未上传素材、未创建广告、未修改投放。"],
        "blocking_reasons": blocking_reasons,
        "raw": {"request": _sanitized_payload(cfg)},
    }


def _auth_payload(cfg: dict[str, Any]) -> dict[str, Any]:
    value = cfg.get("auth")
    if isinstance(value, dict):
        return value
    auth_file = _text(cfg.get("auth_file")) or "data/gravity_token.json"
    return load_gravity_auth_file(auth_file)


def _auth_blocking_reasons(auth_payload: dict[str, Any]) -> list[str]:
    missing = validate_gravity_auth(auth_payload)
    if missing:
        return [f"引力 Token 文件缺少字段：{', '.join(missing)}"]
    return []


def _target_album_names(cfg: dict[str, Any]) -> list[str]:
    raw_names = cfg.get("target_album_names")
    if isinstance(raw_names, list):
        names = [_text(item) for item in raw_names if _text(item)]
        if names:
            return names
    project_root = _text(cfg.get("project_root"))
    return load_target_album_names(project_root or None)


def _active_bindings(db_path: str | Path, *, product: str = "") -> list[dict[str, str]]:
    where = "WHERE is_active = 1"
    params: list[Any] = []
    if product:
        where += " AND product = ?"
        params.append(product)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"""
            SELECT id, product, album_id, album_name, folder_id, folder_name
            FROM product_gravity_album_bindings
            {where}
            ORDER BY product, album_name, folder_name
            """,
            tuple(params),
        ).fetchall()
    return [
        {
            "id": str(row["id"]),
            "product": _text(row["product"]),
            "album_id": _text(row["album_id"]),
            "album_name": _text(row["album_name"]),
            "folder_id": _text(row["folder_id"]),
            "folder_name": _text(row["folder_name"]),
        }
        for row in rows
    ]


def _scan_binding_materials(
    *,
    client: Any,
    binding: dict[str, str],
    page_size: int,
    max_pages: int,
    max_folders: int,
    max_depth: int,
    raw: dict[str, Any],
) -> dict[str, Any]:
    materials: list[dict[str, Any]] = []
    warnings: list[str] = []
    calls = 0
    pages_read = 0
    folders_scanned = 0
    seen_folders: set[str] = set()
    root_scope = {
        "folder_id": binding["folder_id"],
        "folder_name": binding["folder_name"],
        "folder_path": binding["folder_name"],
        "depth": 0,
    }
    queue: list[dict[str, Any]] = [root_scope]

    while queue:
        scope = queue.pop(0)
        folder_id = _text(scope.get("folder_id"))
        folder_key = folder_id or "__album_root__"
        if folder_key in seen_folders:
            continue
        seen_folders.add(folder_key)
        if folder_id:
            folders_scanned += 1
        page = 1
        while page <= max_pages:
            payload = client.get_album_material_list(
                album_id=binding["album_id"],
                folder_id=folder_id,
                page=page,
                page_size=page_size,
            )
            calls += 1
            pages_read += 1
            entries = _album_list_items(payload)
            page_materials: list[dict[str, Any]] = []
            page_folders: list[dict[str, Any]] = []
            for item in entries:
                folder = _folder_payload(item)
                if folder:
                    page_folders.append(folder)
                    if len(seen_folders) + len(queue) >= max_folders:
                        warnings.append(
                            f"{binding['product']}：{binding['album_name']} 文件夹扫描达到上限 {max_folders}，后续文件夹本次未继续读取。"
                        )
                        continue
                    next_depth = int(scope.get("depth") or 0) + 1
                    if next_depth > max_depth:
                        warnings.append(
                            f"{binding['product']}：{binding['album_name']} 文件夹层级超过上限 {max_depth}，已跳过 {folder['folder_name']}。"
                        )
                        continue
                    queue.append(
                        {
                            "folder_id": folder["folder_id"],
                            "folder_name": folder["folder_name"],
                            "folder_path": _folder_path(scope, folder),
                            "depth": next_depth,
                        }
                    )
                    continue
                material = _entry_material_payload(item)
                if not material:
                    continue
                material_scope = _binding_scope(binding, scope)
                page_materials.append({**material, "_binding_scope": material_scope})

            materials.extend(page_materials)
            raw.setdefault("material_pages", []).append(
                {
                    "product": binding["product"],
                    "album_id": binding["album_id"],
                    "folder_id": folder_id,
                    "folder_name": _text(scope.get("folder_name")),
                    "folder_path": _text(scope.get("folder_path")),
                    "page": page,
                    "row_count": len(entries),
                    "material_count": len(page_materials),
                    "folder_count": len(page_folders),
                    "payload": _sanitized_payload(payload),
                }
            )
            if not entries or not _has_next_page(payload, page=page, row_count=len(entries), page_size=page_size):
                break
            page += 1
        if page > max_pages:
            target = _text(scope.get("folder_name")) or binding["album_name"]
            warnings.append(f"{binding['product']}：{target} 分页达到上限 {max_pages}，后续素材本次未继续读取。")

    return {
        "materials": materials,
        "warnings": warnings,
        "external_api_calls": calls,
        "folders_scanned": folders_scanned,
        "pages_read": pages_read,
    }


def _album_list_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("data")
    candidates: Any = []
    if isinstance(data, dict):
        candidates = data.get("list") or data.get("rows") or data.get("items") or data.get("records") or []
    elif isinstance(data, list):
        candidates = data
    return [item for item in candidates if isinstance(item, dict)]


def _folder_payload(item: dict[str, Any]) -> dict[str, str]:
    group = item.get("group")
    if isinstance(group, dict):
        folder_id = _first_text(group, "id", "folder_id", "album_id")
        folder_name = _first_text(group, "name", "label", "folder_name")
        return {"folder_id": folder_id, "folder_name": folder_name} if folder_id else {}
    if isinstance(item.get("material"), dict):
        return {}
    type_value = _text(item.get("type")).lower()
    if type_value not in {"2", "folder", "group"}:
        return {}
    folder_id = _first_text(item, "folder_id", "id", "album_id")
    folder_name = _first_text(item, "folder_name", "name", "label")
    return {"folder_id": folder_id, "folder_name": folder_name} if folder_id else {}


def _entry_material_payload(item: dict[str, Any]) -> dict[str, Any]:
    nested = item.get("material")
    if isinstance(nested, dict):
        return {**nested, "list_item_type": _text(item.get("type"))}
    if _folder_payload(item):
        return {}
    material_id = _material_id(item)
    return item if material_id else {}


def _binding_scope(binding: dict[str, str], scope: dict[str, Any]) -> dict[str, str]:
    return {
        **binding,
        "folder_id": _text(scope.get("folder_id")),
        "folder_name": _text(scope.get("folder_name")),
        "folder_path": _text(scope.get("folder_path")),
    }


def _folder_path(scope: dict[str, Any], folder: dict[str, str]) -> str:
    parent = _text(scope.get("folder_path"))
    name = _text(folder.get("folder_name"))
    if parent and name:
        return f"{parent} / {name}"
    return name or parent


def _has_next_page(payload: dict[str, Any], *, page: int, row_count: int, page_size: int) -> bool:
    data = payload.get("data")
    page_info = data.get("page_info") if isinstance(data, dict) and isinstance(data.get("page_info"), dict) else {}
    total_page = _optional_int(page_info.get("total_page"))
    if total_page is not None:
        return page < total_page
    has_more = page_info.get("has_more")
    if isinstance(has_more, bool):
        return has_more
    return row_count >= page_size


def _report_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("data")
    candidates: Any = []
    if isinstance(data, dict):
        candidates = data.get("list") or data.get("rows") or data.get("items") or []
    elif isinstance(data, list):
        candidates = data
    return [item for item in candidates if isinstance(item, dict)]


def _source_material_row(material: dict[str, Any], *, binding: dict[str, str]) -> dict[str, Any]:
    material_payload = dict(material)
    material_payload.pop("_binding_scope", None)
    if "id" in material_payload:
        material_payload["gravity_raw_id"] = material_payload.pop("id")
    row = {
        "material_id": _material_id(material),
        "video_id": "",
        "name": _first_text(material, "name", "material_name", "file_name", "title"),
        "material_type": _material_type(material),
        "review_status": _status_label(material),
        "signature": _material_md5(material),
        "duration": _material_duration(material),
        "file_size": _float_value(material, "file_size"),
        "create_time": _first_text(material, "create_time", "created_at", "upload_time"),
        "cost_lookback": _float_value(material, "AdCost") or _float_value(material, "stat_cost"),
        "score": 0,
        "album_id": binding["album_id"],
        "album_name": binding["album_name"],
        "folder_id": binding["folder_id"],
        "folder_name": binding["folder_name"],
        "folder_path": _text(binding.get("folder_path")),
        "gravity_status": _text(material.get("status")),
    }
    row["payload_json"] = json.dumps(
        {**material_payload, **{key: row[key] for key in ("album_id", "album_name", "folder_id", "folder_name", "folder_path")}},
        ensure_ascii=False,
    )
    return {**material_payload, **row}


def _write_report_rollups(
    *,
    db_path: str | Path,
    client: Any,
    product: str,
    source_advertiser_id: str,
    organization_id: str,
    materials: list[dict[str, Any]],
    date_range: dict[str, str],
) -> tuple[int, dict[str, Any]]:
    material_ids = [_material_id(item) for item in materials if _material_id(item)]
    if not material_ids:
        return 0, {}
    payload = client.get_material_report(
        material_ids=material_ids,
        date_from=date_range["start"],
        date_to=date_range["end"],
        metrics=REPORT_METRICS,
    )
    reports = {_text(row.get("material_id") or row.get("id")): row for row in _report_rows(payload)}
    written = 0
    with sqlite3.connect(db_path) as conn:
        for material in materials:
            material_id = _material_id(material)
            report = reports.get(material_id, {})
            cursor = conn.execute(
                """
                INSERT INTO product_source_material_metric_rollups (
                  product, source_advertiser_id, organization_id, window_key, window_days,
                  period_start, period_end, material_id, material_type, source_video_id,
                  name, review_status, signature, duration, file_size, create_time,
                  tag_ids_json, stat_cost, show_cnt, click_cnt, convert_cnt, source, synced_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, '', ?, ?, ?, ?, ?, ?, '[]', ?, ?, ?, ?, ?, ?)
                ON CONFLICT(product, source_advertiser_id, window_key, period_start, period_end, material_id)
                DO UPDATE SET
                  name = excluded.name,
                  review_status = excluded.review_status,
                  signature = excluded.signature,
                  duration = excluded.duration,
                  file_size = excluded.file_size,
                  create_time = excluded.create_time,
                  stat_cost = excluded.stat_cost,
                  show_cnt = excluded.show_cnt,
                  click_cnt = excluded.click_cnt,
                  convert_cnt = excluded.convert_cnt,
                  source = excluded.source,
                  synced_at = excluded.synced_at
                """,
                (
                    product,
                    source_advertiser_id,
                    organization_id,
                    "last_30d",
                    30,
                    date_range["start"],
                    date_range["end"],
                    material_id,
                    _material_type(material),
                    _first_text(material, "name", "material_name", "file_name", "title"),
                    _status_label(material),
                    _material_md5(material),
                    _material_duration(material),
                    _float_value(material, "file_size"),
                    _first_text(material, "create_time", "created_at", "upload_time"),
                    _float_value(report, "AdCost"),
                    _float_value(report, "AdShow"),
                    _float_value(report, "AdClick"),
                    _float_value(report, "AdConvert"),
                    "gravity_engine",
                    datetime.now().astimezone().isoformat(timespec="seconds"),
                ),
            )
            written += int(cursor.rowcount or 0)
    return written, payload


def _summary_rows(
    *,
    bindings: list[dict[str, str]],
    rows_by_binding: dict[str, list[dict[str, Any]]],
    disabled_by_binding: dict[str, int],
    folders_scanned_by_binding: dict[str, int],
    inactive_rows: int,
) -> list[dict[str, Any]]:
    rows = []
    for binding in bindings:
        binding_rows = rows_by_binding.get(binding["id"], [])
        disabled_count = int(disabled_by_binding.get(binding["id"]) or 0)
        rows.append(
            {
                "产品": binding["product"],
                "绑定": binding["folder_name"] or binding["album_name"],
                "扫描文件夹": int(folders_scanned_by_binding.get(binding["id"]) or 0),
                "发现素材": len(binding_rows) + disabled_count,
                "入库素材": len(binding_rows),
                "禁用素材": disabled_count,
                "本地置为停用": inactive_rows,
            }
        )
    return rows


def _report_date_range(cfg: dict[str, Any]) -> dict[str, str]:
    value = cfg.get("report_date_range") if isinstance(cfg.get("report_date_range"), dict) else {}
    end = _text(value.get("end"))
    start = _text(value.get("start"))
    if not end:
        end = date.today().isoformat()
    if not start:
        start = (date.fromisoformat(end) - timedelta(days=29)).isoformat()
    return {"start": start, "end": end}


def _is_active_material(material: dict[str, Any]) -> bool:
    status = _text(material.get("status") or material.get("is_active")).lower()
    if status in {"2", "false", "disabled", "disable", "inactive", "禁用"}:
        return False
    return True


def _status_label(material: dict[str, Any]) -> str:
    status = _text(material.get("status") or material.get("is_active"))
    if status == "1":
        return "可用"
    if status == "2":
        return "禁用"
    return _first_text(material, "review_status", "status") or "未知"


def _material_id(material: dict[str, Any]) -> str:
    return _first_text(material, "material_id", "id", "素材ID")


def _material_md5(material: dict[str, Any]) -> str:
    return _first_text(material, "file_md5", "md5", "signature", "素材MD5")


def _material_type(material: dict[str, Any]) -> str:
    value = _first_text(material, "material_type", "file_type")
    if value in {"2", "image", "IMAGE"}:
        return "image"
    return "video"


def _material_duration(material: dict[str, Any]) -> float:
    return _float_value(material, "duration") or _float_value(material, "video_duration_second") or _float_value(material, "video_duration")


def _first_text(row: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = _text(row.get(key))
        if value:
            return value
    return ""


def _float_value(row: dict[str, Any], key: str) -> float:
    try:
        return float(str(row.get(key) or "0").replace(",", ""))
    except ValueError:
        return 0.0


def _int_value(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return min(maximum, max(minimum, parsed))


def _optional_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _sanitized_payload(payload: Any) -> Any:
    if isinstance(payload, dict):
        secret_keys = {"jwt_token", "authorization", "access_token"}
        return {key: _sanitized_payload(value) for key, value in payload.items() if str(key).lower() not in secret_keys}
    if isinstance(payload, list):
        return [_sanitized_payload(item) for item in payload]
    return payload


def _text(value: Any) -> str:
    return str(value or "").strip()
