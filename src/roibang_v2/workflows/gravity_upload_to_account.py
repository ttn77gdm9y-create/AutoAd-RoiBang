from __future__ import annotations

import json
import re
import sqlite3
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from roibang_v2.fetch.gravity_material_library import GravityMaterialClient
from roibang_v2.fetch.gravity_material_library import GravityMaterialLibraryError
from roibang_v2.fetch.gravity_material_library import load_gravity_auth_file
from roibang_v2.fetch.gravity_material_library import validate_gravity_auth
from roibang_v2.materials.gravity_qualification import qualify_gravity_material
from roibang_v2.runs import write_run_artifact

PREVIEW_WORKFLOW = "gravity_upload_to_account_preview"
EXECUTE_WORKFLOW = "gravity_upload_to_account"
STATUS_WORKFLOW = "gravity_upload_status_poll"
PRELOAD_TABLE_ROW_LIMIT = 500
PRELOAD_SINGLE_EXECUTE_PAIR_LIMIT = 5000
_VALID_VIDEO_ID = re.compile(r"^v[0-9A-Za-z]{12,}$")


def build_gravity_upload_preview(
    request: dict[str, Any],
    *,
    db_path: str | Path,
    runs_dir: str | Path,
) -> dict[str, Any]:
    cfg = _cfg(request)
    product = _text(cfg.get("product"))
    target_accounts = _target_accounts(cfg.get("target_accounts"))
    material_ids = _material_ids(cfg.get("material_ids"))
    preview_mode = _text(cfg.get("preview_mode"))
    is_preload = preview_mode == "preload"
    target_owner = _text(cfg.get("target_owner"))
    batch_size = _batch_size(cfg.get("batch_size"))
    blocking_reasons = _preview_blocking_reasons(product=product, target_accounts=target_accounts, material_ids=material_ids)
    materials = _gravity_material_rows(db_path, product=product, material_ids=material_ids) if not blocking_reasons else []
    if not blocking_reasons:
        if not materials:
            blocking_reasons.append("没有找到可预览的本地引力素材")
        found_ids = {row["material_id"] for row in materials}
        missing_ids = [material_id for material_id in material_ids if material_id not in found_ids]
        if missing_ids:
            blocking_reasons.append(f"以下引力素材 ID 未在本地素材库找到：{', '.join(missing_ids)}")
        for material in materials:
            qualification = qualify_gravity_material(material)
            if not qualification["is_eligible_for_next_step"]:
                blocking_reasons.append(f"{material['name'] or material['material_id']} 不可上传：{qualification['qualification_reason']}")

    if blocking_reasons:
        payload = _blocked_preview_payload(cfg, blocking_reasons)
        payload["artifact_path"] = str(write_run_artifact(runs_dir, PREVIEW_WORKFLOW, payload))
        return payload

    existing = _existing_target_materials_by_signature(db_path, target_accounts=[row["advertiser_id"] for row in target_accounts])
    table_rows: list[dict[str, Any]] = []
    upload_items: list[dict[str, Any]] = []
    for account in target_accounts:
        account_existing = existing.get(account["advertiser_id"], {})
        for material in materials:
            signature = _text(material.get("signature"))
            existing_material = account_existing.get(signature)
            status = "账户已有" if existing_material else ("需铺货" if is_preload else "需上传")
            row = {
                "账户名": account["account_name"],
                "账户 ID": account["advertiser_id"],
                "素材名": material["name"],
                "引力素材 ID": material["material_id"],
                "MD5": signature,
                "状态": status,
                "媒体素材 ID": _text((existing_material or {}).get("video_id")),
            }
            if is_preload:
                row["账户来源"] = _text(account.get("account_source")) or "人工导入"
            table_rows.append(row)
            if not existing_material:
                upload_items.append(
                    {
                        **row,
                        "product": product,
                        "target_advertiser_id": account["advertiser_id"],
                        "target_account_name": account["account_name"],
                        "target_account_source": _text(account.get("account_source")) or "人工导入",
                        "gravity_material_id": material["material_id"],
                        "signature": signature,
                    }
                )

    existing_count = len(table_rows) - len(upload_items)
    upload_batches = _upload_batches(upload_items, batch_size=batch_size)
    title = "引力素材提前铺货预览" if is_preload else "引力素材上传预览"
    required_label = "需铺货" if is_preload else "需上传"
    required_phrase = f"需铺货 {len(upload_items)} 条" if is_preload else f"需要上传 {len(upload_items)} 条"
    existing_label = "账户已有/已覆盖" if is_preload else "账户已有"
    target_account_label = f"{target_owner}启用账户" if is_preload and target_owner else ("启用账户" if is_preload else "目标账户")
    preload_too_large = is_preload and len(upload_items) > PRELOAD_SINGLE_EXECUTE_PAIR_LIMIT
    preview_status = "blocked" if preload_too_large else "ready_for_confirmation"
    preview_blocking_reasons = []
    if preload_too_large:
        preview_blocking_reasons.append(
            f"本次需铺货 {len(upload_items)} 条，超过单次确认上限 {PRELOAD_SINGLE_EXECUTE_PAIR_LIMIT} 条；"
            "本结果只用于预览，请后续按产品、账户或部分素材拆分执行。"
        )
    columns = ["账户名", "账户 ID", "素材名", "引力素材 ID", "MD5", "状态", "媒体素材 ID"]
    if is_preload:
        columns = ["账户名", "账户 ID", "账户来源", "素材名", "引力素材 ID", "MD5", "状态", "媒体素材 ID"]
    display_rows = _display_preview_rows(table_rows, is_preload=is_preload)
    raw_upload_items = [] if preload_too_large else upload_items
    raw_upload_batches = upload_batches[:PRELOAD_TABLE_ROW_LIMIT] if preload_too_large else upload_batches
    warnings = [
        "这是提前铺货预览，不会上传素材。真实铺货必须在页面输入“确认执行”。"
        if is_preload
        else "这是上传预览，不会上传素材。真实上传必须在页面输入“确认执行”。"
    ]
    if len(display_rows) < len(table_rows):
        warnings.append(f"明细较多，页面只展示前 {len(display_rows)} 条样例；完整执行需要拆分批次。")
    warnings.extend(preview_blocking_reasons)
    payload = {
        "ok": True,
        "workflow": PREVIEW_WORKFLOW,
        "phase": "gravity_upload_preview",
        "status": preview_status,
        "execution_enabled": False,
        "external_api_calls": 0,
        "generated_at": _now_iso(),
        "中文摘要": (
            f"{title}已生成：目标账户 {len(target_accounts)} 个，选择素材 {len(materials)} 个，"
            f"{existing_label} {existing_count} 条，{required_phrase}，批次 {len(upload_batches)} 个；"
            "尚未调用 upload_material。"
        ),
        "summary": {
            "title": title,
            "status": preview_status,
            "risk_level": "high",
            "execution_enabled": False,
            "items": [
                {"label": target_account_label, "value": len(target_accounts)},
                *(
                    [{"label": "目标负责人", "value": target_owner}]
                    if is_preload and target_owner
                    else []
                ),
                {"label": "可铺货素材" if is_preload else "选择素材", "value": len(materials)},
                {"label": existing_label, "value": existing_count},
                {"label": required_label, "value": len(upload_items)},
                {"label": "批次数", "value": len(upload_batches)},
                *(
                    [{"label": "页面展示", "value": f"前 {len(display_rows)} 条样例"}]
                    if len(display_rows) < len(table_rows)
                    else []
                ),
            ],
            "warnings": warnings,
            "blocking_reasons": preview_blocking_reasons,
            "target_account_count": len(target_accounts),
            "selected_material_count": len(materials),
            "pair_count": len(table_rows),
            "existing_count": existing_count,
            "upload_required_count": len(upload_items),
            "upload_batch_count": len(upload_batches),
            "upload_material_called": False,
        },
        "table": {
            "columns": columns,
            "rows": display_rows,
        },
        "warnings": warnings,
        "blocking_reasons": preview_blocking_reasons,
        "raw": {
            "request": {
                "product": product,
                "target_accounts": target_accounts,
                "material_ids": material_ids,
                "preview_mode": preview_mode,
                "batch_size": batch_size,
                "target_owner": target_owner,
            },
            "upload_material_called": False,
            "upload_items": raw_upload_items,
            "upload_batches": raw_upload_batches,
            "batch_size": batch_size,
            "upload_items_omitted": preload_too_large,
            "upload_item_count": len(upload_items),
            "upload_batch_count": len(upload_batches),
            "display_row_count": len(display_rows),
            "display_row_limit": PRELOAD_TABLE_ROW_LIMIT if is_preload else None,
            "single_execute_pair_limit": PRELOAD_SINGLE_EXECUTE_PAIR_LIMIT if is_preload else None,
            "target_owner": target_owner,
        },
    }
    payload["artifact_path"] = str(write_run_artifact(runs_dir, PREVIEW_WORKFLOW, payload))
    return payload


def run_gravity_upload_execute_request(
    request: dict[str, Any],
    *,
    db_path: str | Path,
    runs_dir: str | Path,
    client: Any | None = None,
) -> dict[str, Any]:
    cfg = _cfg(request)
    preview_path = _text(cfg.get("preview_path"))
    preview = _load_json(preview_path)
    blocking_reasons = _execute_blocking_reasons(preview_path, preview)
    if blocking_reasons:
        payload = _blocked_execute_payload(cfg, blocking_reasons)
        payload["artifact_path"] = str(write_run_artifact(runs_dir, EXECUTE_WORKFLOW, payload))
        return payload

    upload_items = _upload_items(preview)
    if not upload_items:
        payload = _blocked_execute_payload(cfg, ["上传预览中没有需要上传的素材"])
        payload["artifact_path"] = str(write_run_artifact(runs_dir, EXECUTE_WORKFLOW, payload))
        return payload

    upload_client = client
    if upload_client is None:
        auth_payload = _auth_payload(cfg)
        if _text(auth_payload.get("_blocking_reason")):
            payload = _blocked_execute_payload(cfg, [_text(auth_payload.get("_blocking_reason"))])
            payload["artifact_path"] = str(write_run_artifact(runs_dir, EXECUTE_WORKFLOW, payload))
            return payload
        missing_auth = validate_gravity_auth(auth_payload)
        if missing_auth:
            payload = _blocked_execute_payload(cfg, [f"引力 Token 文件缺少字段：{', '.join(missing_auth)}"])
            payload["artifact_path"] = str(write_run_artifact(runs_dir, EXECUTE_WORKFLOW, payload))
            return payload
        upload_client = GravityMaterialClient(auth_payload)

    batch_size = _batch_size((preview.get("raw") if isinstance(preview.get("raw"), dict) else {}).get("batch_size"))
    grouped_account_ids = {
        _text(item.get("target_advertiser_id") or item.get("账户 ID"))
        for item in upload_items
        if _text(item.get("target_advertiser_id") or item.get("账户 ID"))
    }
    upload_batches = _execution_batches(upload_items, batch_size=batch_size)
    results: list[dict[str, Any]] = []
    external_api_calls = 0
    submitted_batch_count = 0
    for batch in upload_batches:
        advertiser_id = _text(batch.get("target_advertiser_id"))
        items = [item for item in batch.get("items", []) if isinstance(item, dict)]
        material_ids = list(batch.get("material_ids") or [])
        try:
            response = upload_client.upload_material_to_account(advertiser_id=advertiser_id, material_ids=material_ids)
            external_api_calls += 1
            submitted_batch_count += 1
            task_id = _task_id(response)
            status = "uploading" if task_id else "failed"
            fail_reason = "" if task_id else _response_message(response) or "引力接口未返回 task_id"
        except Exception as exc:  # keep one account failure from hiding the rest
            external_api_calls += 1
            response = {"error_type": type(exc).__name__, "error": str(exc)}
            task_id = ""
            status = "failed"
            fail_reason = str(exc)
        for item in items:
            row = {
                "产品": _text(item.get("product")),
                "账户名": _text(item.get("target_account_name") or item.get("账户名")),
                "账户 ID": advertiser_id,
                "素材名": _text(item.get("素材名")),
                "引力素材 ID": _text(item.get("gravity_material_id") or item.get("引力素材 ID")),
                "MD5": _text(item.get("signature") or item.get("MD5")),
                "引力任务 ID": task_id,
                "状态": "已提交" if status == "uploading" else "失败",
                "失败原因": fail_reason,
            }
            results.append(row)
            _upsert_upload_task(
                db_path=db_path,
                item=item,
                advertiser_id=advertiser_id,
                task_id=task_id,
                status=status,
                fail_reason=fail_reason,
                preview_path=preview_path,
                response=response,
            )

    failed_count = sum(1 for row in results if row["状态"] == "失败")
    payload = {
        "ok": failed_count == 0,
        "workflow": EXECUTE_WORKFLOW,
        "phase": "gravity_upload_execute",
        "status": "submitted" if failed_count == 0 else "partial_failed",
        "execution_enabled": True,
        "external_api_calls": external_api_calls,
        "generated_at": _now_iso(),
        "中文摘要": (
            f"引力素材上传任务已提交：素材 {len(results)} 条，账户 {len(grouped_account_ids)} 个，"
            f"批次 {submitted_batch_count} 个，失败 {failed_count} 条；已记录引力 task_id，等待后续状态回填。"
        ),
        "summary": {
            "title": "引力素材上传执行",
            "status": "submitted" if failed_count == 0 else "partial_failed",
            "risk_level": "high",
            "execution_enabled": True,
            "items": [
                {"label": "目标账户", "value": len(grouped_account_ids)},
                {"label": "提交批次", "value": submitted_batch_count},
                {"label": "已提交素材", "value": len(results) - failed_count},
                {"label": "失败素材", "value": failed_count},
                {"label": "引力任务", "value": len({row["引力任务 ID"] for row in results if row["引力任务 ID"]})},
            ],
            "warnings": ["素材铺货是异步任务；要等系统回填合法媒体素材 ID 后，创建计划才能使用。"],
            "blocking_reasons": [],
            "target_account_count": len(grouped_account_ids),
            "submitted_batch_count": submitted_batch_count,
            "submitted_material_count": len(results) - failed_count,
            "failed_material_count": failed_count,
            "upload_task_count": len({row["引力任务 ID"] for row in results if row["引力任务 ID"]}),
            "upload_material_called": True,
        },
        "table": {
            "columns": ["账户名", "账户 ID", "素材名", "引力素材 ID", "MD5", "引力任务 ID", "状态", "失败原因"],
            "rows": results,
        },
        "warnings": ["素材铺货是异步任务；要等系统回填合法媒体素材 ID 后，创建计划才能使用。"],
        "blocking_reasons": [],
        "raw": {
            "preview_path": preview_path,
            "upload_items": upload_items,
            "upload_batches": [
                {key: value for key, value in batch.items() if key != "items"}
                for batch in upload_batches
            ],
            "batch_size": batch_size,
            "upload_material_called": True,
        },
    }
    payload["artifact_path"] = str(write_run_artifact(runs_dir, EXECUTE_WORKFLOW, payload))
    return payload


def run_gravity_upload_status_poll_request(
    request: dict[str, Any],
    *,
    db_path: str | Path,
    runs_dir: str | Path,
    client: Any | None = None,
) -> dict[str, Any]:
    cfg = _cfg(request)
    task_ids = _task_ids(cfg.get("task_ids") or cfg.get("task_id"))
    rows = _upload_task_rows(db_path, task_ids=task_ids)
    blocking_reasons = []
    if not task_ids:
        blocking_reasons.append("缺少引力上传 task_id")
    if task_ids and not rows:
        blocking_reasons.append("没有找到对应的引力上传任务账本记录")
    if blocking_reasons:
        payload = _blocked_status_payload(cfg, blocking_reasons)
        payload["artifact_path"] = str(write_run_artifact(runs_dir, STATUS_WORKFLOW, payload))
        return payload

    status_client = client
    if status_client is None:
        auth_payload = _auth_payload(cfg)
        if _text(auth_payload.get("_blocking_reason")):
            payload = _blocked_status_payload(cfg, [_text(auth_payload.get("_blocking_reason"))])
            payload["artifact_path"] = str(write_run_artifact(runs_dir, STATUS_WORKFLOW, payload))
            return payload
        missing_auth = validate_gravity_auth(auth_payload)
        if missing_auth:
            payload = _blocked_status_payload(cfg, [f"引力 Token 文件缺少字段：{', '.join(missing_auth)}"])
            payload["artifact_path"] = str(write_run_artifact(runs_dir, STATUS_WORKFLOW, payload))
            return payload
        status_client = GravityMaterialClient(auth_payload)

    response_by_task: dict[str, dict[str, Any]] = {}
    external_api_calls = 0
    warnings: list[str] = []
    result_rows: list[dict[str, Any]] = []
    for row in rows:
        task_id = _text(row.get("gravity_task_id"))
        if task_id not in response_by_task:
            try:
                response_by_task[task_id] = status_client.get_upload_material_status(task_id=task_id)
            except Exception as exc:
                response_by_task[task_id] = {"error_type": type(exc).__name__, "error": str(exc)}
            external_api_calls += 1
        response = response_by_task[task_id]
        remote_status = _remote_upload_status(response)
        next_status = _text(row.get("status")) or "uploading"
        video_id = _text(row.get("video_id"))
        material_id_in_account = _text(row.get("material_id_in_account"))
        fail_reason = _text(row.get("fail_reason"))

        if remote_status == "failed":
            next_status = "failed"
            fail_reason = _response_message(response) or "引力上传任务失败"
        elif remote_status == "completed":
            matched = _resolve_uploaded_target_material(
                db_path,
                advertiser_id=_text(row.get("target_advertiser_id")),
                signature=_text(row.get("signature")),
            )
            if matched:
                next_status = "completed"
                video_id = matched["video_id"]
                material_id_in_account = matched["material_id"]
                fail_reason = ""
            else:
                next_status = "uploading"
                fail_reason = "引力任务显示完成，但本地账户素材库还未同步到合法媒体素材 ID"
                if fail_reason not in warnings:
                    warnings.append(fail_reason)
        else:
            next_status = "uploading"
            fail_reason = ""

        _update_upload_task_resolution(
            db_path=db_path,
            row=row,
            status=next_status,
            video_id=video_id,
            material_id_in_account=material_id_in_account,
            fail_reason=fail_reason,
            response=response,
        )
        result_rows.append(
            {
                "产品": _text(row.get("product")),
                "账户名": _text(row.get("target_account_name")),
                "账户 ID": _text(row.get("target_advertiser_id")),
                "引力素材 ID": _text(row.get("gravity_material_id")),
                "MD5": _text(row.get("signature")),
                "引力任务 ID": task_id,
                "状态": _upload_status_label(next_status),
                "媒体素材 ID": video_id,
                "账户素材 ID": material_id_in_account,
                "失败原因": fail_reason,
            }
        )

    completed_count = sum(1 for row in result_rows if row["状态"] == "已完成")
    failed_count = sum(1 for row in result_rows if row["状态"] == "失败")
    running_count = len(result_rows) - completed_count - failed_count
    status = "completed" if result_rows and completed_count == len(result_rows) else "failed" if result_rows and failed_count == len(result_rows) else "partial_failed" if failed_count else "running"
    payload = {
        "ok": failed_count == 0,
        "workflow": STATUS_WORKFLOW,
        "phase": "gravity_upload_status_poll",
        "status": status,
        "execution_enabled": False,
        "external_api_calls": external_api_calls,
        "generated_at": _now_iso(),
        "中文摘要": (
            f"引力素材上传状态已刷新：上传记录 {len(result_rows)} 条，已完成 {completed_count} 条，"
            f"进行中 {running_count} 条，失败 {failed_count} 条；没有上传素材、没有创建广告。"
        ),
        "summary": {
            "title": "引力素材上传状态刷新",
            "status": status,
            "risk_level": "low",
            "execution_enabled": False,
            "items": [
                {"label": "上传记录", "value": len(result_rows)},
                {"label": "已完成", "value": completed_count},
                {"label": "进行中", "value": running_count},
                {"label": "失败", "value": failed_count},
                {"label": "外部只读调用", "value": external_api_calls},
            ],
            "warnings": warnings,
            "blocking_reasons": [],
        },
        "table": {
            "columns": ["产品", "账户名", "账户 ID", "引力素材 ID", "MD5", "引力任务 ID", "状态", "媒体素材 ID", "账户素材 ID", "失败原因"],
            "rows": result_rows,
        },
        "warnings": warnings,
        "blocking_reasons": [],
        "raw": {"request": {"task_ids": task_ids}, "status_responses": response_by_task},
    }
    payload["artifact_path"] = str(write_run_artifact(runs_dir, STATUS_WORKFLOW, payload))
    return payload


def _cfg(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("gravity_upload_to_account")
    return dict(value) if isinstance(value, dict) else dict(request)


def _preview_blocking_reasons(*, product: str, target_accounts: list[dict[str, str]], material_ids: list[str]) -> list[str]:
    reasons = []
    if not product:
        reasons.append("请选择产品")
    if not target_accounts:
        reasons.append("请选择目标账户")
    if not material_ids:
        reasons.append("请选择引力素材")
    return reasons


def _blocked_preview_payload(cfg: dict[str, Any], blocking_reasons: list[str]) -> dict[str, Any]:
    return {
        "ok": False,
        "workflow": PREVIEW_WORKFLOW,
        "phase": "gravity_upload_preview",
        "status": "blocked",
        "execution_enabled": False,
        "external_api_calls": 0,
        "generated_at": _now_iso(),
        "中文摘要": f"引力素材上传预览被阻止：{'；'.join(blocking_reasons)}",
        "summary": {
            "title": "引力素材上传预览",
            "status": "blocked",
            "risk_level": "high",
            "execution_enabled": False,
            "items": [],
            "warnings": ["未上传素材、未创建广告、未修改投放。"],
            "blocking_reasons": blocking_reasons,
            "upload_material_called": False,
        },
        "table": {"columns": ["阻塞原因"], "rows": [{"阻塞原因": reason} for reason in blocking_reasons]},
        "warnings": ["未上传素材、未创建广告、未修改投放。"],
        "blocking_reasons": blocking_reasons,
        "raw": {"request": cfg, "upload_material_called": False},
    }


def _blocked_execute_payload(cfg: dict[str, Any], blocking_reasons: list[str]) -> dict[str, Any]:
    return {
        "ok": False,
        "workflow": EXECUTE_WORKFLOW,
        "phase": "gravity_upload_execute",
        "status": "blocked",
        "execution_enabled": False,
        "external_api_calls": 0,
        "generated_at": _now_iso(),
        "中文摘要": f"引力素材上传执行被阻止：{'；'.join(blocking_reasons)}",
        "summary": {
            "title": "引力素材上传执行",
            "status": "blocked",
            "risk_level": "high",
            "execution_enabled": False,
            "items": [],
            "warnings": ["未上传素材、未创建广告、未修改投放。"],
            "blocking_reasons": blocking_reasons,
            "upload_material_called": False,
        },
        "table": {"columns": ["阻塞原因"], "rows": [{"阻塞原因": reason} for reason in blocking_reasons]},
        "warnings": ["未上传素材、未创建广告、未修改投放。"],
        "blocking_reasons": blocking_reasons,
        "raw": {"request": cfg, "upload_material_called": False},
    }


def _blocked_status_payload(cfg: dict[str, Any], blocking_reasons: list[str]) -> dict[str, Any]:
    return {
        "ok": False,
        "workflow": STATUS_WORKFLOW,
        "phase": "gravity_upload_status_poll",
        "status": "blocked",
        "execution_enabled": False,
        "external_api_calls": 0,
        "generated_at": _now_iso(),
        "中文摘要": f"引力素材上传状态刷新被阻止：{'；'.join(blocking_reasons)}",
        "summary": {
            "title": "引力素材上传状态刷新",
            "status": "blocked",
            "risk_level": "low",
            "execution_enabled": False,
            "items": [],
            "warnings": ["未上传素材、未创建广告、未修改投放。"],
            "blocking_reasons": blocking_reasons,
        },
        "table": {"columns": ["阻塞原因"], "rows": [{"阻塞原因": reason} for reason in blocking_reasons]},
        "warnings": ["未上传素材、未创建广告、未修改投放。"],
        "blocking_reasons": blocking_reasons,
        "raw": {"request": cfg},
    }


def _execute_blocking_reasons(preview_path: str, preview: dict[str, Any]) -> list[str]:
    reasons = []
    if not preview_path:
        reasons.append("缺少上传预览文件")
    if not preview:
        reasons.append("上传预览文件不存在或无法读取")
    elif _text(preview.get("workflow")) != PREVIEW_WORKFLOW or _text(preview.get("status")) != "ready_for_confirmation":
        reasons.append("上传预览文件不合法")
    return reasons


def _gravity_material_rows(db_path: str | Path, *, product: str, material_ids: list[str]) -> list[dict[str, Any]]:
    placeholders = ",".join("?" for _ in material_ids)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"""
            SELECT product, source_advertiser_id, organization_id, material_id, video_id,
                   name, material_type, review_status, signature, is_active, payload_json,
                   cost_lookback, score, synced_at
            FROM product_source_materials
            WHERE source = 'gravity_engine'
              AND product = ?
              AND material_id IN ({placeholders})
            ORDER BY material_id ASC
            """,
            tuple([product, *material_ids]),
        ).fetchall()
    return [_material_payload(dict(row)) for row in rows]


def _material_payload(row: dict[str, Any]) -> dict[str, Any]:
    payload = _load_json_value(row.get("payload_json"))
    return {
        **row,
        "gravity_status": _text(payload.get("status")),
        "album_name": _text(payload.get("album_name")),
        "folder_name": _text(payload.get("folder_name")),
    }


def _existing_target_materials_by_signature(db_path: str | Path, *, target_accounts: list[str]) -> dict[str, dict[str, dict[str, Any]]]:
    if not target_accounts:
        return {}
    placeholders = ",".join("?" for _ in target_accounts)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"""
            SELECT am.advertiser_id, am.material_id, am.video_id, m.name, m.payload_json
            FROM account_materials am
            LEFT JOIN materials m ON m.material_id = am.material_id
            WHERE am.advertiser_id IN ({placeholders})
              AND am.material_type = 'video'
              AND COALESCE(am.video_id, '') <> ''
            """,
            tuple(target_accounts),
        ).fetchall()
    result: dict[str, dict[str, dict[str, Any]]] = {account_id: {} for account_id in target_accounts}
    for row in rows:
        signature = _signature_from_payload(row["payload_json"])
        video_id = _text(row["video_id"])
        if not signature or not _VALID_VIDEO_ID.fullmatch(video_id):
            continue
        result.setdefault(_text(row["advertiser_id"]), {})[signature] = {
            "material_id": _text(row["material_id"]),
            "video_id": video_id,
            "name": _text(row["name"]),
        }
    return result


def _upload_task_rows(db_path: str | Path, *, task_ids: list[str]) -> list[dict[str, Any]]:
    if not task_ids:
        return []
    placeholders = ",".join("?" for _ in task_ids)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"""
            SELECT product, gravity_material_id, signature, target_advertiser_id,
                   target_account_name, gravity_task_id, status, video_id,
                   material_id_in_account, fail_reason, preview_artifact_path,
                   response_payload_json, created_at, updated_at
            FROM gravity_upload_tasks
            WHERE gravity_task_id IN ({placeholders})
            ORDER BY updated_at DESC, target_advertiser_id, gravity_material_id
            """,
            tuple(task_ids),
        ).fetchall()
    return [dict(row) for row in rows]


def _upsert_upload_task(
    *,
    db_path: str | Path,
    item: dict[str, Any],
    advertiser_id: str,
    task_id: str,
    status: str,
    fail_reason: str,
    preview_path: str,
    response: dict[str, Any],
) -> None:
    now = _now_iso()
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO gravity_upload_tasks (
              product, gravity_material_id, signature, target_advertiser_id,
              target_account_name, gravity_task_id, status, video_id,
              material_id_in_account, fail_reason, preview_artifact_path,
              response_payload_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, '', '', ?, ?, ?, ?, ?)
            ON CONFLICT(gravity_material_id, target_advertiser_id)
            DO UPDATE SET
              product = excluded.product,
              signature = excluded.signature,
              target_account_name = excluded.target_account_name,
              gravity_task_id = excluded.gravity_task_id,
              status = excluded.status,
              fail_reason = excluded.fail_reason,
              preview_artifact_path = excluded.preview_artifact_path,
              response_payload_json = excluded.response_payload_json,
              updated_at = excluded.updated_at
            """,
            (
                _text(item.get("product")),
                _text(item.get("gravity_material_id") or item.get("引力素材 ID")),
                _text(item.get("signature") or item.get("MD5")),
                advertiser_id,
                _text(item.get("target_account_name") or item.get("账户名")),
                task_id,
                status,
                fail_reason,
                preview_path,
                json.dumps(response, ensure_ascii=False, sort_keys=True),
                now,
                now,
            ),
        )


def _update_upload_task_resolution(
    *,
    db_path: str | Path,
    row: dict[str, Any],
    status: str,
    video_id: str,
    material_id_in_account: str,
    fail_reason: str,
    response: dict[str, Any],
) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            UPDATE gravity_upload_tasks
            SET status = ?,
                video_id = ?,
                material_id_in_account = ?,
                fail_reason = ?,
                response_payload_json = ?,
                updated_at = ?
            WHERE gravity_material_id = ? AND target_advertiser_id = ?
            """,
            (
                status,
                video_id,
                material_id_in_account,
                fail_reason,
                json.dumps(response, ensure_ascii=False, sort_keys=True),
                _now_iso(),
                _text(row.get("gravity_material_id")),
                _text(row.get("target_advertiser_id")),
            ),
        )


def _resolve_uploaded_target_material(db_path: str | Path, *, advertiser_id: str, signature: str) -> dict[str, str]:
    if not advertiser_id or not signature:
        return {}
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT am.material_id, am.video_id, m.payload_json
            FROM account_materials am
            LEFT JOIN materials m ON m.material_id = am.material_id
            WHERE am.advertiser_id = ?
              AND am.material_type = 'video'
              AND COALESCE(am.video_id, '') <> ''
            ORDER BY am.synced_at DESC, am.material_id ASC
            """,
            (advertiser_id,),
        ).fetchall()
    for row in rows:
        video_id = _text(row["video_id"])
        if _signature_from_payload(row["payload_json"]) == signature and _VALID_VIDEO_ID.fullmatch(video_id):
            return {"material_id": _text(row["material_id"]), "video_id": video_id}
    return {}


def _auth_payload(cfg: dict[str, Any]) -> dict[str, Any]:
    value = cfg.get("auth")
    if isinstance(value, dict):
        return value
    auth_file = _text(cfg.get("auth_file")) or "data/gravity_token.json"
    try:
        return load_gravity_auth_file(auth_file)
    except GravityMaterialLibraryError as exc:
        return {"_blocking_reason": str(exc)}


def _target_accounts(value: Any) -> list[dict[str, str]]:
    rows = value if isinstance(value, list) else []
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in rows:
        advertiser_id = _text(row.get("advertiser_id") if isinstance(row, dict) else row)
        if not advertiser_id or advertiser_id in seen:
            continue
        seen.add(advertiser_id)
        result.append(
            {
                "advertiser_id": advertiser_id,
                "account_name": _text(row.get("account_name") if isinstance(row, dict) else "") or advertiser_id,
                "account_source": _text(row.get("account_source") if isinstance(row, dict) else ""),
            }
        )
    return result


def _batch_size(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = 50
    return min(max(parsed, 1), 50)


def _chunks(items: list[Any], size: int) -> list[list[Any]]:
    chunk_size = max(size, 1)
    return [items[index : index + chunk_size] for index in range(0, len(items), chunk_size)]


def _upload_batches(upload_items: list[dict[str, Any]], *, batch_size: int) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in upload_items:
        grouped[_text(item.get("target_advertiser_id") or item.get("账户 ID"))].append(item)
    batches: list[dict[str, Any]] = []
    for advertiser_id, items in grouped.items():
        for index, chunk in enumerate(_chunks(items, batch_size), start=1):
            batches.append(
                {
                    "batch_key": f"{_text(chunk[0].get('product'))}_{advertiser_id}_{index}",
                    "target_advertiser_id": advertiser_id,
                    "target_account_name": _text(chunk[0].get("target_account_name") or chunk[0].get("账户名")),
                    "target_account_source": _text(chunk[0].get("target_account_source") or chunk[0].get("账户来源")),
                    "material_ids": [
                        _text(item.get("gravity_material_id") or item.get("引力素材 ID"))
                        for item in chunk
                        if _text(item.get("gravity_material_id") or item.get("引力素材 ID"))
                    ],
                    "material_count": len(chunk),
                }
            )
    return batches


def _execution_batches(upload_items: list[dict[str, Any]], *, batch_size: int) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in upload_items:
        advertiser_id = _text(item.get("target_advertiser_id") or item.get("账户 ID"))
        if advertiser_id:
            grouped[advertiser_id].append(item)
    batches: list[dict[str, Any]] = []
    for advertiser_id, items in grouped.items():
        for index, chunk in enumerate(_chunks(items, batch_size), start=1):
            material_ids = [
                _text(item.get("gravity_material_id") or item.get("引力素材 ID"))
                for item in chunk
                if _text(item.get("gravity_material_id") or item.get("引力素材 ID"))
            ]
            if not material_ids:
                continue
            batches.append(
                {
                    "batch_key": f"{_text(chunk[0].get('product'))}_{advertiser_id}_{index}",
                    "target_advertiser_id": advertiser_id,
                    "target_account_name": _text(chunk[0].get("target_account_name") or chunk[0].get("账户名")),
                    "material_ids": material_ids,
                    "material_count": len(material_ids),
                    "items": chunk,
                }
            )
    return batches


def _material_ids(value: Any) -> list[str]:
    rows = value if isinstance(value, list) else str(value or "").split(",")
    result: list[str] = []
    seen: set[str] = set()
    for item in rows:
        text = _text(item)
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _task_ids(value: Any) -> list[str]:
    rows = value if isinstance(value, list) else str(value or "").split(",")
    result: list[str] = []
    seen: set[str] = set()
    for item in rows:
        text = _text(item)
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _display_preview_rows(table_rows: list[dict[str, Any]], *, is_preload: bool) -> list[dict[str, Any]]:
    if not is_preload:
        return table_rows
    return table_rows[:PRELOAD_TABLE_ROW_LIMIT]


def _upload_items(preview: dict[str, Any]) -> list[dict[str, Any]]:
    raw = preview.get("raw") if isinstance(preview.get("raw"), dict) else {}
    rows = raw.get("upload_items") if isinstance(raw.get("upload_items"), list) else []
    return [dict(row) for row in rows if isinstance(row, dict)]


def _load_json(path: str | Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, IsADirectoryError):
        return {}
    return value if isinstance(value, dict) else {}


def _load_json_value(value: Any) -> dict[str, Any]:
    try:
        payload = json.loads(str(value or "{}"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _signature_from_payload(payload_json: Any) -> str:
    payload = _load_json_value(payload_json)
    return _text(
        payload.get("signature")
        or payload.get("material_signature")
        or payload.get("file_signature")
        or payload.get("video_signature")
        or payload.get("content_signature")
        or payload.get("md5")
        or payload.get("file_md5")
    )


def _task_id(response: dict[str, Any]) -> str:
    data = response.get("data") if isinstance(response.get("data"), dict) else {}
    return _text(data.get("task_id") or response.get("task_id"))


def _response_message(response: dict[str, Any]) -> str:
    return _text(response.get("msg") or response.get("message") or response.get("error"))


def _remote_upload_status(response: dict[str, Any]) -> str:
    if _text(response.get("error")):
        return "failed"
    values = [_text(value).lower() for value in _status_values(response) if _text(value)]
    if any(value in {"failed", "fail", "failure", "error", "rejected"} or "失败" in value for value in values):
        return "failed"
    if any(
        value in {"completed", "complete", "success", "succeeded", "done", "finished", "finish"}
        or "完成" in value
        or "成功" in value
        for value in values
    ):
        return "completed"
    return "uploading"


def _status_values(value: Any) -> list[Any]:
    keys = {"status", "task_status", "state", "result", "upload_status", "progress_status"}
    if isinstance(value, dict):
        output: list[Any] = []
        for key, child in value.items():
            if str(key).lower() in keys:
                output.append(child)
            output.extend(_status_values(child))
        return output
    if isinstance(value, list):
        output = []
        for child in value:
            output.extend(_status_values(child))
        return output
    return []


def _upload_status_label(status: str) -> str:
    labels = {
        "pending": "待上传",
        "uploading": "上传中",
        "completed": "已完成",
        "failed": "失败",
    }
    return labels.get(_text(status), _text(status))


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _text(value: Any) -> str:
    return str(value or "").strip()
