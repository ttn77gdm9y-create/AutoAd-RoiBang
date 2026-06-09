from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from roibang_v2.db.bootstrap import bootstrap_database
from roibang_v2.ui.background_tasks import build_runner_command
from roibang_v2.ui.background_tasks import build_task_record
from roibang_v2.ui.background_tasks import start_runner
from roibang_v2.ui.background_tasks import write_task_record
from roibang_v2.ui.create_plan_preview import build_create_plan_preview
from roibang_v2.ui.script_runner import build_create_live_execute_command
from roibang_v2.ui.script_runner import build_create_live_execute_report_command
from roibang_v2.ui.script_runner import build_create_plan_command
from roibang_v2.workflows.frontend_operation_log import create_operation_details_from_plan
from roibang_v2.workflows.frontend_operation_log import record_frontend_operation
from roibang_v2.workflows.review_create_plan_execution import run_create_plan_execution_review_request

from backend.app.services.artifacts import find_latest_artifact
from backend.app.services.artifacts import read_json
from backend.app.services.account_names import account_name_for
from backend.app.services.account_names import load_account_name_map
from backend.app.services.accounts_store import load_accounts
from backend.app.services.ui_labels import CREATE_MODE_LABELS
from backend.app.services.ui_labels import create_mode_label

MATERIAL_SOURCE_LABELS = {
    "source_account": "源素材账户",
    "source_material_account": "源素材账户",
    "gravity_engine": "引力素材库",
}


def build_create_plan_generate_preview(request: dict[str, Any], *, project_root: str | Path) -> dict[str, Any]:
    mode = _text(request.get("mode") or request.get("mode_key"))
    owner = _text(request.get("owner"))
    target_date = _text(request.get("target_date"))
    product_key = _text(request.get("product_key"))
    product_name = _resolve_product_name(request, product_key, project_root=project_root)
    mode_metadata = _resolve_create_mode_metadata(project_root=project_root, mode=mode, product_key=product_key)
    template_catalog = _text(request.get("template_catalog"))
    cpa_bid = _text(request.get("cpa_bid"))
    roi_coefficient = _text(request.get("roi_coefficient"))
    material_source = _material_source(request)
    material_source_label = _material_source_label(material_source)
    advertiser_ids, account_source, account_warnings = _resolve_generate_accounts(request, project_root=project_root)
    validation_reasons = _generate_validation_reasons(
        mode=mode,
        owner=owner,
        template_catalog=template_catalog,
        advertiser_ids=advertiser_ids,
    )
    if material_source not in {"source_account", "gravity_engine"}:
        validation_reasons.append("素材来源只能选择源素材账户或引力素材库")
    if validation_reasons:
        return _blocked_generate_preview(mode, product_name, owner, target_date, validation_reasons, request)
    if roi_coefficient and not _is_7r_mode(mode):
        return _blocked_generate_preview(
            mode,
            product_name,
            owner,
            target_date,
            "非 7R 创建模式不允许填写 ROI 系数；请清空该字段，或切换到 7R 创建模式。",
            request,
        )
    account_names = load_account_name_map(Path(project_root) / "configs")

    try:
        command = build_create_plan_command(
            mode=mode,
            accounts="\n".join(advertiser_ids),
            owner=owner,
            target_date=target_date,
            product_key=product_key,
            template_catalog=template_catalog,
            cpa_bid=cpa_bid,
            roi_coefficient=roi_coefficient,
            material_source="" if material_source == "source_account" else material_source,
        )
    except ValueError as exc:
        return _blocked_generate_preview(mode, product_name, owner, target_date, str(exc), request)

    rows = [
        {
            "账户 ID": advertiser_id,
            "账户名": account_name_for(account_names, advertiser_id),
            "创建模式": mode,
            "产品": product_name,
            "素材来源": material_source_label,
            "负责人": owner,
            "目标日期": target_date,
            "出价": cpa_bid,
            "ROI 系数": roi_coefficient,
        }
        for advertiser_id in advertiser_ids
    ]
    sections: list[dict[str, Any]] = []
    gravity_selection: dict[str, Any] | None = None
    summary_status = "planned"
    gravity_items: list[dict[str, Any]] = []
    gravity_warnings: list[str] = []
    gravity_blocking_reasons: list[str] = []
    if material_source == "gravity_engine":
        gravity_selection = _gravity_material_selection_preview(
            project_root=project_root,
            product=product_name,
            mode_metadata=mode_metadata,
            advertiser_ids=advertiser_ids,
            account_names=account_names,
        )
        gravity_items = [
            {"label": "候选引力素材", "value": gravity_selection["candidate_count"]},
            {
                "label": "已可直接用",
                "value": f"{gravity_selection['ready_material_count']} 个素材 / {gravity_selection['ready_pair_count']} 个账户覆盖",
            },
            {"label": "需要实时推送", "value": f"{gravity_selection['pending_push_pairs']} 个素材账户组合"},
        ]
        gravity_warnings = list(gravity_selection.get("warnings") or [])
        gravity_blocking_reasons = list(gravity_selection.get("blocking_reasons") or [])
        if gravity_selection["candidate_count"] > 0:
            sections.append(
                {
                    "title": "引力素材自动选材",
                    "table": {
                        "columns": ["素材名", "引力素材 ID", "7天消耗", "7天转化", "ROI", "推送覆盖", "下一步"],
                        "rows": gravity_selection["rows"],
                    },
                }
            )
        if gravity_blocking_reasons:
            summary_status = "blocked"
        elif gravity_selection["pending_push_pairs"] > 0:
            summary_status = "warning"
    return {
        "summary": {
            "title": "创建计划生成预览",
            "status": summary_status,
            "risk_level": "medium",
            "execution_enabled": False,
            "items": [
                {"label": "创建模式", "value": mode},
                {"label": "模式名称", "value": mode_metadata["name"]},
                {"label": "模式来源", "value": mode_metadata["source"]},
                {"label": "模式文件", "value": mode_metadata["path"]},
                {"label": "产品", "value": product_name},
                {"label": "素材来源", "value": material_source_label},
                {"label": "账户数", "value": len(advertiser_ids)},
                {"label": "账户来源", "value": _account_source_label(account_source)},
                {"label": "负责人", "value": owner},
                {"label": "目标日期", "value": target_date},
                *gravity_items,
            ],
            "warnings": [
                *account_warnings,
                *(
                    [
                        "系统会按固定创建模式里的素材规则自动筛选引力素材。",
                        "本步骤只做自动选材预览，不上传素材、不创建广告。",
                    ]
                    if material_source == "gravity_engine"
                    else []
                ),
                *gravity_warnings,
                "这里只生成创建计划 JSON，不会创建项目、单元或绑定素材。",
            ],
            "blocking_reasons": gravity_blocking_reasons,
        },
        "table": {
            "columns": ["账户 ID", "账户名", "创建模式", "产品", "素材来源", "负责人", "目标日期", "出价", "ROI 系数"],
            "rows": rows,
        },
        "sections": sections,
        "artifact_path": "",
        "raw": {
            "project_root": str(project_root),
            "request": request,
            "command": command,
            "resolved_accounts": advertiser_ids,
            "account_source": account_source,
            "product": product_name,
            "product_key": product_key,
            "material_source": material_source,
            "mode_metadata": mode_metadata,
            "gravity_material_selection": gravity_selection,
        },
    }


def start_create_plan_generate_task(request: dict[str, Any], *, project_root: str | Path) -> dict[str, Any]:
    preview = build_create_plan_generate_preview(request, project_root=project_root)
    if preview["summary"]["status"] != "planned":
        return preview

    root = Path(project_root)
    runs_dir = root / "data" / "runs"
    task = build_task_record(
        runs_dir=runs_dir,
        operation_type="create_plan_generate",
        command=list(preview["raw"]["command"]),
        cwd=str(root),
        request=request,
    )
    task_path = write_task_record(runs_dir, task)
    pid = start_runner(build_runner_command(task_path), cwd=root)
    task["pid"] = pid
    write_task_record(runs_dir, task)
    operation_log = _record_generate_operation(runs_dir, task, request, preview)

    return {
        "summary": {
            "title": "创建计划生成任务",
            "status": "queued",
            "risk_level": preview["summary"]["risk_level"],
            "execution_enabled": False,
            "items": [
                *preview["summary"]["items"],
                {"label": "任务 ID", "value": task["task_id"]},
                {"label": "任务状态", "value": task["status"]},
            ],
            "warnings": ["创建计划生成任务已进入任务中心；这里仍未真实创建项目或单元。"],
            "blocking_reasons": [],
        },
        "table": preview["table"],
        "artifact_path": str(task_path),
        "task": task,
        "raw": {"preview": preview, "task": task, "operation_log": operation_log},
    }


def build_create_plan_detail(plan_id: str, request: dict[str, Any], *, project_root: str | Path) -> dict[str, Any]:
    plan_path = _text(request.get("plan_path") or request.get("path"))
    return _build_plan_preview_result(
        title="创建计划详情",
        plan_id=plan_id,
        plan_path=plan_path,
        request=request,
        project_root=project_root,
        execution_preview=False,
    )


def build_latest_create_plan_detail(*, project_root: str | Path) -> dict[str, Any]:
    root = Path(project_root)
    latest_path = find_latest_artifact(root / "data" / "runs", "create_mode")
    if latest_path is None:
        return _blocked_plan_preview(
            "最近创建计划",
            "latest",
            "",
            "还没有生成过创建计划：请先启动计划生成任务，或手动填写已有创建计划 JSON 路径。",
            {},
        )

    plan_path = _relative_plan_path(root, latest_path)
    result = _build_plan_preview_result(
        title="最近创建计划",
        plan_id=latest_path.stem,
        plan_path=plan_path,
        request={"plan_path": plan_path},
        project_root=root,
        execution_preview=False,
    )
    result.setdefault("raw", {})["latest_plan_path"] = plan_path
    return result


def build_create_plan_suggestion_preview_detail(path: str, *, project_root: str | Path) -> dict[str, Any]:
    root = Path(project_root)
    if not _text(path):
        return _blocked_suggestion_preview("未填写创建建议预览路径", path)
    preview_path = _resolve_plan_path(root, path)
    display_path = _relative_plan_path(root, preview_path)
    if not preview_path.is_file():
        return _blocked_suggestion_preview(f"创建建议预览不存在：{path}", display_path)

    payload = read_json(preview_path)
    create_plan_request = payload.get("create_plan_request") if isinstance(payload.get("create_plan_request"), dict) else {}
    if not create_plan_request:
        return _blocked_suggestion_preview("创建建议预览缺少 create_plan_request，不能填入创建计划页。", display_path)

    generate_preview = build_create_plan_generate_preview(create_plan_request, project_root=root)
    generate_summary = generate_preview.get("summary") if isinstance(generate_preview.get("summary"), dict) else {}
    workflow_reasons = [str(item) for item in payload.get("blocking_reasons") or [] if str(item)]
    generate_reasons = [str(item) for item in generate_summary.get("blocking_reasons") or [] if str(item)]
    status = "blocked" if workflow_reasons or generate_reasons else _text(generate_summary.get("status")) or "loaded"
    table = _suggestion_generate_table(generate_preview.get("table")) if isinstance(generate_preview.get("table"), dict) else {
        "columns": ["账户 ID", "账户名", "创建模式", "产品", "负责人", "目标日期", "出价", "ROI 系数"],
        "rows": [],
    }
    return {
        "summary": {
            "title": "创建建议预览导入",
            "status": status,
            "risk_level": "medium",
            "execution_enabled": False,
            "items": [
                {"label": "来源建议", "value": int(payload.get("summary", {}).get("source_suggestion_count") or 0)},
                {"label": "账户数", "value": int(payload.get("summary", {}).get("account_count") or 0)},
                {"label": "产品", "value": _text(create_plan_request.get("product_name"))},
                {"label": "推荐模式", "value": create_mode_label(_text(create_plan_request.get("mode")))},
                {"label": "来源策略", "value": _source_strategy_text(payload)},
                {"label": "预览状态", "value": "已接收"},
            ],
            "warnings": [
                "已从创建建议预览填入创建计划表单；仍需在本页检查、生成计划并人工确认真实创建。",
                *[str(item) for item in generate_summary.get("warnings") or [] if str(item)],
            ],
            "blocking_reasons": [*workflow_reasons, *generate_reasons],
        },
        "table": table,
        "sections": _suggestion_preview_sections(payload),
        "artifact_path": display_path,
        "raw": {
            "create_plan_request": create_plan_request,
            "create_plan_from_suggestions": payload,
            "generate_preview": generate_preview,
        },
    }


def build_create_plan_execution_review_preview(request: dict[str, Any], *, project_root: str | Path) -> dict[str, Any]:
    root = Path(project_root)
    review = run_create_plan_execution_review_request(
        request,
        runs_dir=root / "data" / "runs",
        project_root=root,
    )
    return _execution_review_result(review)


def list_create_plan_templates(*, project_root: str | Path) -> dict[str, Any]:
    root = Path(project_root)
    template_root = root / "configs" / "create-templates"
    rows = []
    if template_root.exists():
        for path in sorted(template_root.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError, UnicodeDecodeError):
                continue
            product = _text(payload.get("product")) or path.stem
            templates = payload.get("templates")
            rows.append(
                {
                    "模板": f"{product} - {path.name}",
                    "产品": product,
                    "产品 Key": _text(payload.get("product_key")) or _derive_template_product_key(path),
                    "平台": _text(payload.get("platform")),
                    "模板数": len(templates) if isinstance(templates, dict) else 0,
                    "路径": path.relative_to(root).as_posix(),
                }
            )
    return {
        "summary": {
            "title": "创建模板列表",
            "status": "loaded",
            "risk_level": "low",
            "execution_enabled": False,
            "items": [{"label": "模板数", "value": len(rows)}],
            "warnings": [] if rows else ["没有在 configs/create-templates 下找到模板 JSON。"],
            "blocking_reasons": [],
        },
        "table": {"columns": ["模板", "产品", "产品 Key", "平台", "模板数", "路径"], "rows": rows},
        "artifact_path": str(template_root),
        "raw": {"templates": rows},
    }


def list_create_plan_modes(*, project_root: str | Path, product_key: str = "") -> dict[str, Any]:
    root = Path(project_root)
    product_key_text = _text(product_key)
    mode_root = root / "configs" / "create-modes"
    rows_by_key: dict[str, dict[str, Any]] = {}
    for mode_key, label in CREATE_MODE_LABELS.items():
        rows_by_key[mode_key] = {
            "创建模式": label,
            "模式 Key": mode_key,
            "产品": "通用",
            "产品 Key": "",
            "来源": "固定内置",
            "路径": "",
            "模板 Key": "",
        }

    if mode_root.exists():
        for path in sorted(mode_root.glob("*.json")):
            row = _create_mode_row(root, path, source="固定配置", product_key="")
            if row:
                rows_by_key[row["模式 Key"]] = row

    product_rows: list[dict[str, Any]] = []
    if product_key_text and mode_root.exists():
        product_mode_dir = mode_root / product_key_text
        for path in sorted(product_mode_dir.glob("*.json")):
            row = _create_mode_row(root, path, source="产品专属", product_key=product_key_text)
            if row:
                rows_by_key[row["模式 Key"]] = row
                product_rows.append(row)

    rows = sorted(
        rows_by_key.values(),
        key=lambda row: (
            0 if row["来源"] == "产品专属" else 1,
            str(row["创建模式"]),
            str(row["模式 Key"]),
        ),
    )
    warnings = [] if product_key_text else ["选择产品后会显示该产品专属创建模式。"]
    return {
        "summary": {
            "title": "创建模式列表",
            "status": "loaded",
            "risk_level": "low",
            "execution_enabled": False,
            "items": [
                {"label": "模式数", "value": len(rows)},
                {"label": "产品专属模式", "value": len(product_rows)},
                {"label": "产品 Key", "value": product_key_text or "未选择"},
            ],
            "warnings": warnings,
            "blocking_reasons": [],
        },
        "table": {
            "columns": ["创建模式", "模式 Key", "产品", "产品 Key", "来源", "路径", "模板 Key"],
            "rows": rows,
        },
        "artifact_path": str(mode_root),
        "raw": {
            "modes": [
                {
                    "label": f"{row['创建模式']}（{row['模式 Key']}）",
                    "value": row["模式 Key"],
                    "product_key": row["产品 Key"],
                    "product": row["产品"],
                    "source": row["来源"],
                    "path": row["路径"],
                    "template_key": row["模板 Key"],
                }
                for row in rows
            ]
        },
    }


def build_create_plan_template_detail(path: str, *, project_root: str | Path) -> dict[str, Any]:
    template_path = _resolve_template_path(project_root, path)
    root = Path(project_root)
    display_path = _relative_plan_path(root, template_path) if template_path else path
    if not path:
        return _blocked_template_detail("未选择创建模板 JSON 路径", path)
    if not template_path.exists():
        return _blocked_template_detail(f"创建模板 JSON 不存在：{path}", display_path)

    try:
        payload = json.loads(template_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return _blocked_template_detail(f"创建模板 JSON 解析失败：{exc}", display_path)

    templates = payload.get("templates") if isinstance(payload.get("templates"), dict) else {}
    rows = []
    for template_key, template in templates.items():
        template_payload = template if isinstance(template, dict) else {}
        rows.append(
            {
                "模板 Key": _text(template_key),
                "项目模板": _text(
                    template_payload.get("project_template_name")
                    or template_payload.get("unit_template_name")
                    or create_mode_label(template_key)
                ),
                "文案数": len(template_payload.get("title_pool")) if isinstance(template_payload.get("title_pool"), list) else 0,
                "CTA 数": len(template_payload.get("cta_pool")) if isinstance(template_payload.get("cta_pool"), list) else 0,
                "卖点数": len(template_payload.get("product_selling_points"))
                if isinstance(template_payload.get("product_selling_points"), list)
                else 0,
                "是否 7R": "是" if bool(template_payload.get("requires_roi_goal")) else "否",
            }
        )

    return {
        "summary": {
            "title": "固定模式模板内容",
            "status": "loaded",
            "risk_level": "low",
            "execution_enabled": False,
            "items": [
                {"label": "产品", "value": _text(payload.get("product")) or template_path.stem},
                {"label": "产品 Key", "value": _text(payload.get("product_key")) or _derive_template_product_key(template_path)},
                {"label": "平台", "value": _text(payload.get("platform"))},
                {"label": "模板文件", "value": display_path},
                {"label": "模板数", "value": len(rows)},
            ],
            "warnings": [] if rows else ["这个模板文件里没有 templates 配置。"],
            "blocking_reasons": [],
        },
        "table": {
            "columns": ["模板 Key", "项目模板", "文案数", "CTA 数", "卖点数", "是否 7R"],
            "rows": rows,
        },
        "artifact_path": display_path,
        "raw": {"template": payload},
    }


def build_create_plan_execute_preview(
    plan_id: str,
    request: dict[str, Any],
    *,
    project_root: str | Path,
) -> dict[str, Any]:
    plan_path = _text(request.get("plan_path") or request.get("path"))
    return _build_plan_preview_result(
        title="创建计划执行预览",
        plan_id=plan_id,
        plan_path=plan_path,
        request=request,
        project_root=project_root,
        execution_preview=True,
    )


def start_create_plan_execute_task(plan_id: str, request: dict[str, Any], *, project_root: str | Path) -> dict[str, Any]:
    preview = build_create_plan_execute_preview(plan_id, request, project_root=project_root)
    if preview["summary"]["status"] == "blocked":
        return preview

    root = Path(project_root)
    runs_dir = root / "data" / "runs"
    execution_review = run_create_plan_execution_review_request(
        {
            **request,
            "plan_path": preview.get("artifact_path") or request.get("plan_path"),
            "operator": request.get("operator") or request.get("owner") or "local-ui",
        },
        runs_dir=runs_dir,
        project_root=root,
    )
    if execution_review.get("status") == "blocked":
        result = _execution_review_result(execution_review)
        result["summary"]["title"] = "创建计划执行被复核阻断"
        return result

    task = build_task_record(
        runs_dir=runs_dir,
        operation_type="create_live_execute",
        command=list(preview["raw"]["execute_command"]),
        cwd=str(root),
        request={**request, "plan_id": plan_id},
        post_commands=[list(preview["raw"]["post_command"])],
    )
    task_path = write_task_record(runs_dir, task)
    pid = start_runner(build_runner_command(task_path), cwd=root)
    task["pid"] = pid
    write_task_record(runs_dir, task)
    operation_log = _record_execute_operation(runs_dir, task, request, preview, execution_review=execution_review)

    return {
        "summary": {
            "title": "创建计划执行任务",
            "status": "queued",
            "risk_level": preview["summary"]["risk_level"],
            "execution_enabled": True,
            "items": [
                *preview["summary"]["items"],
                {"label": "执行前复核", "value": _text(execution_review.get("status"))},
                {"label": "复核文件", "value": _text(execution_review.get("artifact_path"))},
                {"label": "任务 ID", "value": task["task_id"]},
                {"label": "任务状态", "value": task["status"]},
            ],
            "warnings": [
                *[str(item) for item in execution_review.get("warnings") or [] if str(item)],
                "真实创建任务已提交；可在当前页面或任务中心查看中文进度和执行报告。",
            ],
            "blocking_reasons": [],
        },
        "table": preview["table"],
        "artifact_path": str(task_path),
        "task": task,
        "raw": {"preview": preview, "execution_review": execution_review, "task": task, "operation_log": operation_log},
    }


def _build_plan_preview_result(
    *,
    title: str,
    plan_id: str,
    plan_path: str,
    request: dict[str, Any],
    project_root: str | Path,
    execution_preview: bool,
) -> dict[str, Any]:
    if not plan_path:
        return _blocked_plan_preview(title, plan_id, plan_path, "未填写创建计划 JSON 路径", request)

    path = _resolve_plan_path(project_root, plan_path)
    if not path.exists():
        return _blocked_plan_preview(title, plan_id, plan_path, f"创建计划 JSON 不存在：{plan_path}", request)

    try:
        plan = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return _blocked_plan_preview(title, plan_id, plan_path, f"创建计划 JSON 解析失败：{exc}", request)

    preview = build_create_plan_preview(plan)
    if not preview:
        return _blocked_plan_preview(title, plan_id, plan_path, "创建计划 JSON 无法生成中文摘要", request)

    summary = preview.get("summary") if isinstance(preview.get("summary"), dict) else {}
    mode_key = _plan_mode_key(plan, preview)
    template_name = _plan_template_name(plan, preview)
    template_path = _plan_template_path(plan, preview)
    blocking_reasons = [str(item) for item in preview.get("blocking_reasons") or []]
    warnings = [str(item) for item in preview.get("warnings") or []]
    status = "blocked" if blocking_reasons else "ready"
    execution_enabled = execution_preview and status == "ready" and bool(summary.get("can_execute"))
    account_names = load_account_name_map(Path(project_root) / "configs")
    rows = [_unit_row(row, account_names) for row in preview.get("units") or [] if isinstance(row, dict)]
    raw: dict[str, Any] = {
        "request": request,
        "plan": plan,
        "preview": preview,
    }
    if execution_preview and execution_enabled:
        resume_existing_plan = bool(request.get("resume_existing_plan"))
        raw["execute_command"] = build_create_live_execute_command(
            plan_path=plan_path,
            resume_existing_plan=resume_existing_plan,
        )
        raw["post_command"] = build_create_live_execute_report_command(
            plan_path=plan_path,
            execute_artifact_path="{result.artifact_path}",
            push_feishu=True,
        )

    return {
        "summary": {
            "title": title,
            "status": status,
            "risk_level": "high" if execution_preview else ("medium" if warnings else "low"),
            "execution_enabled": execution_enabled,
            "items": [
                {"label": "计划来源", "value": _plan_source_label(request.get("plan_source"), execution_preview=execution_preview)},
                {"label": "计划 ID", "value": _text(summary.get("plan_id")) or plan_id},
                {"label": "产品", "value": _text(summary.get("product"))},
                {"label": "产品 Key", "value": _text(summary.get("product_key"))},
                {"label": "固定模式", "value": mode_key},
                {"label": "固定模板", "value": template_name},
                {"label": "模板文件", "value": template_path},
                {"label": "创建计划 JSON", "value": plan_path},
                {"label": "素材来源", "value": _material_source_label(_text(summary.get("material_source")) or "source_account")},
                {"label": "账户数", "value": _int(summary.get("target_account_count"))},
                {"label": "项目数", "value": _int(summary.get("planned_project_count"))},
                {"label": "单元数", "value": _int(summary.get("planned_unit_count"))},
                {"label": "候选素材数", "value": _int(summary.get("source_material_count"))},
                {"label": "素材分配数", "value": _int(summary.get("material_assignment_count"))},
                {"label": "唯一素材数", "value": _int(summary.get("unique_material_count"))},
                {"label": "素材复用规则", "value": _material_reuse_rule(plan, summary)},
                {"label": "缺视频 ID", "value": _int(summary.get("missing_video_id_material_count"))},
            ],
            "warnings": warnings
            + (["这是高风险真实创建入口；执行前必须核对中文摘要、账户、单元、素材、文案、CTA 和卖点。"] if execution_preview else []),
            "blocking_reasons": blocking_reasons,
        },
        "table": {
            "columns": ["账户 ID", "账户名", "项目", "单元", "素材数", "文案数", "CTA 数", "卖点数"],
            "rows": rows,
        },
        "sections": _review_sections(preview, account_names),
        "artifact_path": plan_path,
        "raw": raw,
    }


def _blocked_generate_preview(
    mode: str,
    product_name: str,
    owner: str,
    target_date: str,
    reason: str | list[str],
    request: dict[str, Any],
) -> dict[str, Any]:
    reasons = reason if isinstance(reason, list) else [reason]
    return {
        "summary": {
            "title": "创建计划生成预览",
            "status": "blocked",
            "risk_level": "medium",
            "execution_enabled": False,
            "items": [
                {"label": "创建模式", "value": mode},
                {"label": "产品", "value": product_name},
                {"label": "负责人", "value": owner},
                {"label": "目标日期", "value": target_date},
            ],
            "warnings": [],
            "blocking_reasons": reasons,
        },
        "table": {"columns": ["账户 ID", "账户名", "创建模式", "产品", "负责人", "目标日期", "出价", "ROI 系数"], "rows": []},
        "artifact_path": "",
        "raw": {"request": request},
    }


def _blocked_plan_preview(
    title: str,
    plan_id: str,
    plan_path: str,
    reason: str,
    request: dict[str, Any],
) -> dict[str, Any]:
    return {
        "summary": {
            "title": title,
            "status": "blocked",
            "risk_level": "high",
            "execution_enabled": False,
            "items": [
                {"label": "计划 ID", "value": plan_id},
                {"label": "创建计划 JSON", "value": plan_path},
            ],
            "warnings": [],
            "blocking_reasons": [reason],
        },
        "table": {"columns": ["账户 ID", "账户名", "项目", "单元", "素材数", "文案数", "CTA 数", "卖点数"], "rows": []},
        "sections": [],
        "artifact_path": plan_path,
        "raw": {"request": request},
    }


def _blocked_suggestion_preview(reason: str, path: str) -> dict[str, Any]:
    return {
        "summary": {
            "title": "创建建议预览导入",
            "status": "blocked",
            "risk_level": "medium",
            "execution_enabled": False,
            "items": [{"label": "创建预览", "value": path}],
            "warnings": [],
            "blocking_reasons": [reason],
        },
        "table": {"columns": ["账户 ID", "账户名", "创建模式", "产品", "负责人", "目标日期", "出价", "ROI 系数"], "rows": []},
        "artifact_path": path,
        "raw": {},
    }


def _execution_review_result(review: dict[str, Any]) -> dict[str, Any]:
    summary = review.get("summary") if isinstance(review.get("summary"), dict) else {}
    status = _text(review.get("status") or summary.get("status"))
    checks = [dict(row) for row in review.get("checks") or [] if isinstance(row, dict)]
    rows = [
        {
            "检查项": _text(check.get("title")),
            "结果": _review_check_status_label(check.get("status")),
            "等级": _review_severity_label(check.get("severity")),
            "说明": _text(check.get("message")),
            "证据": _compact_json(check.get("evidence")),
        }
        for check in checks
    ]
    warnings = [str(item) for item in review.get("warnings") or [] if str(item)]
    blocking_reasons = [str(item) for item in review.get("blocking_reasons") or [] if str(item)]
    if status in {"ready_for_confirmation", "warning_only"}:
        warnings = [
            *warnings,
            "执行前复核只生成只读复核产物；真实创建仍需要你在创建计划页人工确认。",
        ]
    return {
        "summary": {
            "title": "创建计划执行前复核",
            "status": status,
            "risk_level": "high" if status == "blocked" else ("medium" if status == "warning_only" else "low"),
            "execution_enabled": False,
            "items": [
                {"label": "批次名称", "value": _text(summary.get("batch_name"))},
                {"label": "计划 ID", "value": _text(summary.get("plan_id"))},
                {"label": "产品", "value": _text(summary.get("product"))},
                {"label": "产品 Key", "value": _text(summary.get("product_key"))},
                {"label": "固定模式", "value": _text(summary.get("mode_key"))},
                {"label": "账户数", "value": _int(summary.get("account_count"))},
                {"label": "项目数", "value": _int(summary.get("planned_project_count"))},
                {"label": "单元数", "value": _int(summary.get("planned_unit_count"))},
                {"label": "候选素材数", "value": _int(summary.get("source_material_count"))},
                {"label": "唯一素材数", "value": _int(summary.get("unique_material_count"))},
                {"label": "通过", "value": _int(summary.get("passed_check_count"))},
                {"label": "警告", "value": _int(summary.get("warning_count"))},
                {"label": "阻断", "value": _int(summary.get("blocking_reason_count"))},
                {"label": "来源策略", "value": "、".join(str(item) for item in summary.get("source_strategy_ids") or [] if str(item))},
            ],
            "warnings": warnings,
            "blocking_reasons": blocking_reasons,
        },
        "table": {
            "columns": ["检查项", "结果", "等级", "说明", "证据"],
            "rows": rows,
        },
        "sections": _execution_review_sections(review),
        "artifact_path": _text(review.get("artifact_path")),
        "raw": review,
    }


def _execution_review_sections(review: dict[str, Any]) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    operation_record = review.get("operation_record") if isinstance(review.get("operation_record"), dict) else {}
    if operation_record:
        rows = [
            {"字段": "操作类型", "内容": _text(operation_record.get("operation_type"))},
            {"字段": "批次名称", "内容": _text(operation_record.get("batch_name"))},
            {"字段": "复核状态", "内容": _text(operation_record.get("status"))},
            {"字段": "触发人", "内容": _text(operation_record.get("operator"))},
            {"字段": "计划 ID", "内容": _text(operation_record.get("plan_id"))},
            {"字段": "创建计划 JSON", "内容": _text(operation_record.get("plan_path"))},
            {"字段": "来源建议预览", "内容": _text(operation_record.get("source_suggestion_preview_path"))},
            {
                "字段": "来源建议",
                "内容": "、".join(_text(item) for item in operation_record.get("source_suggestion_ids") or [] if _text(item)),
            },
            {
                "字段": "来源策略",
                "内容": "、".join(_text(item) for item in operation_record.get("source_strategy_ids") or [] if _text(item)),
            },
        ]
        sections.append(
            {
                "title": "运营记录",
                "table": {"columns": ["字段", "内容"], "rows": [row for row in rows if row["内容"]]},
            }
        )
    manifest = review.get("execution_manifest") if isinstance(review.get("execution_manifest"), dict) else {}
    account_rows = [
        {
            "账户 ID": _text(row.get("advertiser_id")),
            "项目数": _int(row.get("project_count")),
            "单元数": _int(row.get("unit_count")),
            "唯一素材数": _int(row.get("unique_material_count")),
        }
        for row in manifest.get("accounts") or []
        if isinstance(row, dict)
    ]
    if account_rows:
        sections.append(
            {
                "title": "确认执行清单",
                "table": {
                    "columns": ["账户 ID", "项目数", "单元数", "唯一素材数"],
                    "rows": account_rows,
                },
            }
        )
    source = review.get("source_suggestion_evidence") if isinstance(review.get("source_suggestion_evidence"), dict) else {}
    source_rows = [
        {
            "建议 ID": _text(row.get("suggestion_id")),
            "账户 ID": _text(row.get("advertiser_id")),
            "账户名": _text(row.get("account_name")),
            "命中策略": _text(row.get("strategy_id")),
            "项目容量": row.get("project_capacity") or 0,
            "合格素材": row.get("qualified_material_count") or 0,
            "ROI": row.get("roi_1day") or 0,
            "转化": row.get("convert_cnt") or 0,
            "推荐原因": _text(row.get("reason")),
        }
        for row in source.get("rows") or []
        if isinstance(row, dict)
    ]
    if source_rows:
        sections.append(
            {
                "title": "来源建议证据",
                "table": {
                    "columns": ["建议 ID", "账户 ID", "账户名", "命中策略", "项目容量", "合格素材", "ROI", "转化", "推荐原因"],
                    "rows": source_rows,
                },
            }
        )
    return sections


def _review_check_status_label(value: Any) -> str:
    labels = {"passed": "通过", "warning": "警告", "blocked": "阻断"}
    text = _text(value)
    return labels.get(text, text)


def _review_severity_label(value: Any) -> str:
    labels = {"low": "低", "medium": "中", "high": "高"}
    text = _text(value)
    return labels.get(text, text)


def _compact_json(value: Any) -> str:
    if not value:
        return ""
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        return str(value)


def _suggestion_preview_sections(payload: dict[str, Any]) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    group_rows = _suggestion_group_rows(payload)
    if group_rows:
        sections.append(
            {
                "title": "创建建议批次",
                "table": {
                    "columns": ["批次", "产品", "推荐模式", "账户数", "来源建议", "命中策略", "模板", "证据"],
                    "rows": group_rows,
                },
            }
        )
    evidence_rows = _suggestion_evidence_rows(payload)
    if evidence_rows:
        sections.append(
            {
                "title": "来源建议证据",
                "table": {
                    "columns": ["建议 ID", "账户 ID", "账户名", "命中策略", "项目容量", "合格素材", "推荐原因"],
                    "rows": evidence_rows,
                },
            }
        )
    return sections


def _suggestion_generate_table(value: Any) -> dict[str, Any]:
    table = value if isinstance(value, dict) else {}
    rows: list[dict[str, Any]] = []
    for row in _rows(table.get("rows")):
        next_row = dict(row)
        if "创建模式" in next_row:
            next_row["创建模式"] = create_mode_label(next_row.get("创建模式"))
        rows.append(next_row)
    return {
        "columns": [str(item) for item in table.get("columns") or [] if str(item)],
        "rows": rows,
    }


def _suggestion_group_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, group in enumerate(payload.get("suggestion_groups") or [], start=1):
        if not isinstance(group, dict):
            continue
        product_name = _text(group.get("product_name") or group.get("product_key"))
        mode_key = _text(group.get("mode_key"))
        rows.append(
            {
                "批次": _suggestion_group_label(group, index=index),
                "产品": product_name,
                "推荐模式": create_mode_label(mode_key),
                "账户数": _int(group.get("account_count")),
                "来源建议": _int(group.get("source_suggestion_count")),
                "命中策略": _strategy_list_display_text(group.get("strategy_ids"), product_name=product_name, mode_key=mode_key),
                "模板": _template_display_text(_text(group.get("template_catalog")), product_name=product_name),
                "证据": _suggestion_group_evidence_text(group.get("evidence_summary")),
            }
        )
    return rows


def _suggestion_evidence_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for suggestion in payload.get("source_suggestions") or []:
        if not isinstance(suggestion, dict):
            continue
        metrics = suggestion.get("metrics") if isinstance(suggestion.get("metrics"), dict) else {}
        evidence = suggestion.get("evidence") if isinstance(suggestion.get("evidence"), dict) else {}
        rows.append(
            {
                "建议 ID": _text(suggestion.get("suggestion_id")),
                "账户 ID": _text(suggestion.get("advertiser_id")),
                "账户名": _text(suggestion.get("account_name") or suggestion.get("advertiser_name")),
                "命中策略": _strategy_display_text(
                    _text(suggestion.get("strategy_id") or suggestion.get("rule_id")),
                    product_name=_text(suggestion.get("product_name") or suggestion.get("product")),
                    mode_key=_text(suggestion.get("mode_key") or suggestion.get("recommended_mode_key")),
                ),
                "项目容量": _text(metrics.get("project_capacity") or evidence.get("project_capacity")),
                "合格素材": _text(metrics.get("qualified_material_count") or evidence.get("qualified_material_count")),
                "推荐原因": _text(suggestion.get("reason") or suggestion.get("message")),
            }
        )
    return rows


def _source_strategy_text(payload: dict[str, Any]) -> str:
    strategy_ids: list[tuple[str, str, str]] = []
    for group in payload.get("suggestion_groups") or []:
        if not isinstance(group, dict):
            continue
        product_name = _text(group.get("product_name") or group.get("product_key"))
        mode_key = _text(group.get("mode_key"))
        strategy_ids.extend((_text(item), product_name, mode_key) for item in group.get("strategy_ids") or [] if _text(item))
    if not strategy_ids:
        for suggestion in payload.get("source_suggestions") or []:
            if isinstance(suggestion, dict):
                strategy_ids.append(
                    (
                        _text(suggestion.get("strategy_id") or suggestion.get("rule_id")),
                        _text(suggestion.get("product_name") or suggestion.get("product")),
                        _text(suggestion.get("mode_key") or suggestion.get("recommended_mode_key")),
                    )
                )
    labels = [
        _strategy_display_text(strategy_id, product_name=product_name, mode_key=mode_key)
        for strategy_id, product_name, mode_key in strategy_ids
        if strategy_id
    ]
    return "、".join(_unique_account_ids(labels))


def _strategy_display_text(strategy_id: str, *, product_name: str = "", mode_key: str = "") -> str:
    strategy_id = _text(strategy_id)
    if not strategy_id:
        return ""
    product = _text(product_name)
    mode = _text(mode_key)
    normalized = strategy_id.replace("-", "_")
    mode_label = create_mode_label(mode) if mode else ""
    if mode and mode.replace("-", "_") in normalized and mode_label:
        return f"{product}{mode_label}策略" if product else f"{mode_label}策略"
    if "recent_scale" in normalized:
        label = "近期放量"
    elif "test_new" in normalized:
        label = "测新"
    elif "scale" in normalized:
        label = "历史放量"
    elif mode_label:
        label = mode_label
    else:
        return strategy_id
    return f"{product}{label}策略" if product else f"{label}策略"


def _strategy_list_display_text(value: Any, *, product_name: str = "", mode_key: str = "") -> str:
    labels = [
        _strategy_display_text(_text(item), product_name=product_name, mode_key=mode_key)
        for item in value or []
        if _text(item)
    ]
    return "、".join(_unique_account_ids(labels))


def _template_display_text(path: str, *, product_name: str = "") -> str:
    path_text = _text(path)
    if not path_text:
        return "未指定模板"
    product = _text(product_name)
    if product:
        return f"{product}创建模板"
    return Path(path_text).name.replace(".local.json", "").replace(".json", "") or "创建模板"


def _suggestion_group_label(group: dict[str, Any], *, index: int) -> str:
    product = _text(group.get("product_name") or group.get("product_key"))
    mode = create_mode_label(_text(group.get("mode_key")))
    account_count = _int(group.get("account_count"))
    parts = [part for part in [product, mode, f"{account_count} 个账户"] if part]
    return f"第 {index} 批" + (f"：{'｜'.join(parts)}" if parts else "")


def _suggestion_group_evidence_text(value: Any) -> str:
    evidence = value if isinstance(value, dict) else {}
    parts = []
    if "min_project_capacity" in evidence:
        parts.append(f"最小容量 {evidence.get('min_project_capacity')}")
    if "min_qualified_material_count" in evidence:
        parts.append(f"最少合格素材 {evidence.get('min_qualified_material_count')}")
    if "max_current_project_count" in evidence:
        parts.append(f"当前项目最多 {evidence.get('max_current_project_count')}")
    return "，".join(parts)


def _unit_row(row: dict[str, Any], account_names: dict[str, str]) -> dict[str, Any]:
    advertiser_id = _text(row.get("advertiser_id"))
    return {
        "账户 ID": advertiser_id,
        "账户名": account_name_for(account_names, advertiser_id),
        "项目": _text(row.get("project_name") or row.get("project_key")),
        "单元": _text(row.get("promotion_name") or row.get("unit_key")),
        "素材数": _int(row.get("material_count")),
        "文案数": _int(row.get("title_count")),
        "CTA 数": _int(row.get("cta_count")),
        "卖点数": _int(row.get("selling_point_count")),
    }


def _record_generate_operation(
    runs_dir: Path,
    task: dict[str, Any],
    request: dict[str, Any],
    preview: dict[str, Any],
) -> dict[str, Any]:
    raw = preview.get("raw") if isinstance(preview.get("raw"), dict) else {}
    resolved_accounts = list(raw.get("resolved_accounts") or _split_account_ids(request.get("advertiser_ids")))
    details = {
        "product": _text(request.get("product") or request.get("product_name")),
        "product_key": _text(request.get("product_key")),
        "mode_key": _text(request.get("mode") or request.get("mode_key")),
        "display_name": _display_create_mode(request),
        "template_catalog_path": _text(request.get("template_catalog")),
        "material_source": _material_source(request),
        "account_source": _text(raw.get("account_source")) or "manual",
        "accounts": [{"advertiser_id": advertiser_id} for advertiser_id in resolved_accounts],
        "review": {
            "can_execute": False,
            "summary": {"warning_count": len(preview.get("summary", {}).get("warnings") or [])},
            "warnings": list(preview.get("summary", {}).get("warnings") or []),
            "blocking_reasons": list(preview.get("summary", {}).get("blocking_reasons") or []),
        },
    }
    return record_frontend_operation(
        runs_dir=runs_dir,
        operation_type="create_plan_generate",
        status=_text(task.get("status")) or "queued",
        actor=_text(request.get("owner")) or "local-ui",
        request={**request, "task_id": task["task_id"]},
        result={"task_id": task["task_id"], "task_artifact_path": task.get("artifact_path"), "status": task.get("status")},
        details=details,
    )


def _record_execute_operation(
    runs_dir: Path,
    task: dict[str, Any],
    request: dict[str, Any],
    preview: dict[str, Any],
    *,
    execution_review: dict[str, Any] | None = None,
) -> dict[str, Any]:
    raw = preview.get("raw") if isinstance(preview.get("raw"), dict) else {}
    plan = raw.get("plan") if isinstance(raw.get("plan"), dict) else {}
    details = create_operation_details_from_plan(plan) if plan else {}
    details["review"] = _operation_review_from_preview(preview)
    if isinstance(execution_review, dict):
        operation_record = execution_review.get("operation_record") if isinstance(execution_review.get("operation_record"), dict) else {}
        details["execution_review"] = execution_review
        details["execution_review_artifact_path"] = _text(execution_review.get("artifact_path"))
        details["source_suggestion_ids"] = [
            _text(item) for item in operation_record.get("source_suggestion_ids") or [] if _text(item)
        ]
        details["source_strategy_ids"] = [
            _text(item) for item in operation_record.get("source_strategy_ids") or [] if _text(item)
        ]
    return record_frontend_operation(
        runs_dir=runs_dir,
        operation_type="create_live_execute",
        status=_text(task.get("status")) or "queued",
        actor=_text(request.get("owner")) or "local-ui",
        request={**request, "task_id": task["task_id"]},
        result={
            "task_id": task["task_id"],
            "task_artifact_path": task.get("artifact_path"),
            "status": task.get("status"),
            "plan_path": preview.get("artifact_path"),
        },
        details=details,
    )


def _operation_review_from_preview(preview: dict[str, Any]) -> dict[str, Any]:
    summary = preview.get("summary") if isinstance(preview.get("summary"), dict) else {}
    warnings = list(summary.get("warnings") or [])
    blocking_reasons = list(summary.get("blocking_reasons") or [])
    return {
        "can_execute": bool(summary.get("execution_enabled")),
        "summary": {
            "status": summary.get("status"),
            "warning_count": len(warnings),
            "blocking_reason_count": len(blocking_reasons),
        },
        "warnings": warnings,
        "blocking_reasons": blocking_reasons,
    }


def _review_sections(preview: dict[str, Any], account_names: dict[str, str]) -> list[dict[str, Any]]:
    return [
        {
            "title": "已选素材",
            "table": {
                "columns": ["素材 ID", "视频 ID", "素材名", "产品", "使用次数", "分配账户", "覆盖账户数", "覆盖单元数", "缺视频 ID"],
                "rows": [_material_row(row, account_names) for row in preview.get("materials") or [] if isinstance(row, dict)],
            },
        },
        {
            "title": "文案",
            "table": {
                "columns": ["文案", "使用次数", "覆盖单元数"],
                "rows": [_title_row(row) for row in preview.get("copywriting") or [] if isinstance(row, dict)],
            },
        },
        {
            "title": "CTA",
            "table": {
                "columns": ["CTA", "使用次数", "覆盖单元数"],
                "rows": [_cta_row(row) for row in preview.get("ctas") or [] if isinstance(row, dict)],
            },
        },
        {
            "title": "卖点",
            "table": {
                "columns": ["卖点", "使用次数", "覆盖单元数"],
                "rows": [_selling_point_row(row) for row in preview.get("selling_points") or [] if isinstance(row, dict)],
            },
        },
        {
            "title": "账户素材分布",
            "table": {
                "columns": ["账户 ID", "账户名", "项目数", "单元数", "素材分配数", "唯一素材数"],
                "rows": [_account_row(row, account_names) for row in preview.get("accounts") or [] if isinstance(row, dict)],
            },
        },
    ]


def _material_row(row: dict[str, Any], account_names: dict[str, str]) -> dict[str, Any]:
    return {
        "素材 ID": _text(row.get("material_id")),
        "视频 ID": _text(row.get("video_id")),
        "素材名": _text(row.get("name")),
        "产品": _text(row.get("product")),
        "使用次数": _int(row.get("usage_count")),
        "分配账户": _format_accounts(row.get("covered_accounts"), account_names),
        "覆盖账户数": _int(row.get("covered_account_count")),
        "覆盖单元数": _int(row.get("covered_unit_count")),
        "缺视频 ID": "是" if row.get("missing_video_id") else "否",
    }


def _title_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "文案": _text(row.get("title")),
        "使用次数": _int(row.get("usage_count")),
        "覆盖单元数": _int(row.get("covered_unit_count")),
    }


def _cta_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "CTA": _text(row.get("cta")),
        "使用次数": _int(row.get("usage_count")),
        "覆盖单元数": _int(row.get("covered_unit_count")),
    }


def _selling_point_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "卖点": _text(row.get("selling_point")),
        "使用次数": _int(row.get("usage_count")),
        "覆盖单元数": _int(row.get("covered_unit_count")),
    }


def _account_row(row: dict[str, Any], account_names: dict[str, str]) -> dict[str, Any]:
    advertiser_id = _text(row.get("advertiser_id"))
    return {
        "账户 ID": advertiser_id,
        "账户名": account_name_for(account_names, advertiser_id),
        "项目数": _int(row.get("project_count")),
        "单元数": _int(row.get("unit_count")),
        "素材分配数": _int(row.get("material_assignment_count")),
        "唯一素材数": _int(row.get("unique_material_count")),
    }


def _resolve_plan_path(project_root: str | Path, path: str) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return Path(project_root) / candidate


def _resolve_template_path(project_root: str | Path, path: str) -> Path:
    return _resolve_plan_path(project_root, path)


def _blocked_template_detail(reason: str, path: str) -> dict[str, Any]:
    return {
        "summary": {
            "title": "固定模式模板内容",
            "status": "blocked",
            "risk_level": "medium",
            "execution_enabled": False,
            "items": [{"label": "模板文件", "value": path}],
            "warnings": [],
            "blocking_reasons": [reason],
        },
        "table": {"columns": ["模板 Key", "项目模板", "文案数", "CTA 数", "卖点数", "是否 7R"], "rows": []},
        "artifact_path": path,
        "raw": {"path": path},
    }


def _create_mode_row(root: Path, path: Path, *, source: str, product_key: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    mode_key = _text(payload.get("mode_key")) or _derive_mode_key(path)
    if not mode_key:
        return None
    mode_product_key = _text(payload.get("product_key")) or product_key
    product = _text(payload.get("product")) or ("通用" if not mode_product_key else mode_product_key)
    return {
        "创建模式": _text(payload.get("display_name")) or create_mode_label(mode_key),
        "模式 Key": mode_key,
        "产品": product,
        "产品 Key": mode_product_key,
        "来源": source,
        "路径": _relative_plan_path(root, path),
        "模板 Key": _text(payload.get("template_key")),
    }


def _resolve_create_mode_metadata(*, project_root: str | Path, mode: str, product_key: str) -> dict[str, str]:
    root = Path(project_root)
    rows = list_create_plan_modes(project_root=root, product_key=product_key)["raw"]["modes"]
    for row in rows:
        if _text(row.get("value")) == mode:
            return {
                "name": _text(row.get("label")).split("（", 1)[0] or create_mode_label(mode),
                "source": _text(row.get("source")),
                "path": _text(row.get("path")),
                "template_key": _text(row.get("template_key")),
            }
    return {
        "name": create_mode_label(mode),
        "source": "未匹配",
        "path": "",
        "template_key": "",
    }


def _gravity_material_selection_preview(
    *,
    project_root: str | Path,
    product: str,
    mode_metadata: dict[str, str],
    advertiser_ids: list[str],
    account_names: dict[str, str],
) -> dict[str, Any]:
    root = Path(project_root)
    db_path = root / "data" / "roibang_v2.sqlite3"
    bootstrap_database(db_path)
    mode_config = _load_create_mode_config_for_preview(root, _text(mode_metadata.get("path")))
    material_selection = mode_config.get("material_selection") if isinstance(mode_config.get("material_selection"), dict) else {}
    material_selection = {**material_selection, "source_scope": "gravity_engine"}
    material_requirements = mode_config.get("material_requirements") if isinstance(mode_config.get("material_requirements"), dict) else {}
    material_type = _text(material_requirements.get("material_type")) or "video"
    lookback_days = _int(material_selection.get("lookback_days")) or 7
    min_stat_cost = _float(material_selection.get("min_stat_cost"))
    min_convert_cnt = material_selection.get("min_convert_cnt")
    max_convert_cnt = material_selection.get("max_convert_cnt")
    candidate_pool_limit = _int(material_selection.get("candidate_pool_limit"))

    candidates = _gravity_material_candidates(
        db_path=db_path,
        product=product,
        material_type=material_type,
        lookback_days=lookback_days,
    )
    filtered_candidates: list[dict[str, Any]] = []
    rejected_count = 0
    for candidate in candidates:
        if not _gravity_material_is_usable(candidate):
            rejected_count += 1
            continue
        if float(candidate.get("stat_cost") or 0) < min_stat_cost:
            rejected_count += 1
            continue
        if min_convert_cnt is not None and float(candidate.get("convert_cnt") or 0) < _float(min_convert_cnt):
            rejected_count += 1
            continue
        if max_convert_cnt is not None and float(candidate.get("convert_cnt") or 0) > _float(max_convert_cnt):
            rejected_count += 1
            continue
        filtered_candidates.append(candidate)

    filtered_candidates = _sort_gravity_candidates(filtered_candidates, material_selection=material_selection)
    if candidate_pool_limit > 0:
        filtered_candidates = filtered_candidates[:candidate_pool_limit]

    upload_map = _gravity_upload_coverage(
        db_path=db_path,
        product=product,
        material_ids=[_text(item.get("material_id")) for item in filtered_candidates],
        advertiser_ids=advertiser_ids,
    )
    rows: list[dict[str, Any]] = []
    ready_pair_count = 0
    pending_push_pairs = 0
    ready_material_ids: set[str] = set()
    for candidate in filtered_candidates:
        material_id = _text(candidate.get("material_id"))
        ready_accounts = sorted(upload_map.get(material_id, set()))
        ready_count = len(ready_accounts)
        account_count = len(advertiser_ids)
        missing_count = max(account_count - ready_count, 0)
        ready_pair_count += ready_count
        pending_push_pairs += missing_count
        if ready_count > 0:
            ready_material_ids.add(material_id)
        rows.append(
            {
                "素材名": _text(candidate.get("name")) or material_id,
                "引力素材 ID": material_id,
                "7天消耗": _format_metric(candidate.get("stat_cost")),
                "7天转化": _format_metric(candidate.get("convert_cnt")),
                "ROI": _format_roi(candidate.get("roi_1day_cost_weighted")),
                "推送覆盖": f"已可用 {ready_count}/{account_count} 个账户",
                "下一步": "可直接用于已覆盖账户" if missing_count == 0 else "缺失账户需实时推送",
                "账户明细": "；".join(
                    f"{account_name_for(account_names, advertiser_id)}（{advertiser_id}）"
                    for advertiser_id in ready_accounts
                ),
            }
        )

    warnings: list[str] = []
    blocking_reasons: list[str] = []
    if rejected_count:
        warnings.append(f"已按固定素材规则过滤 {rejected_count} 个不符合条件的引力素材。")
    if pending_push_pairs:
        warnings.append(
            f"有 {pending_push_pairs} 个素材到账户的组合还没有媒体素材 ID；下一步需要先生成实时推送预览并确认执行。"
        )
    display_row_limit = 100
    if len(rows) > display_row_limit:
        warnings.append(f"自动选材命中 {len(rows)} 个素材，页面先展示前 {display_row_limit} 个；总数和缺口统计仍按全部素材计算。")
    if not filtered_candidates:
        blocking_reasons.append("没有命中可用于创建计划的本地引力素材；请先更新引力素材并确认固定模式里的素材规则。")
    if filtered_candidates and ready_pair_count == 0:
        blocking_reasons.append("命中了引力素材，但目标账户都还没有可直接使用的媒体素材 ID；请先走实时推送预览确认。")

    return {
        "candidate_count": len(filtered_candidates),
        "ready_material_count": len(ready_material_ids),
        "ready_pair_count": ready_pair_count,
        "pending_push_pairs": pending_push_pairs,
        "lookback_days": lookback_days,
        "selection_type": _text(material_selection.get("selection_type")) or "未配置",
        "min_stat_cost": min_stat_cost,
        "rows": rows[:display_row_limit],
        "warnings": warnings,
        "blocking_reasons": blocking_reasons,
        "mode_material_selection": material_selection,
        "mode_material_requirements": material_requirements,
    }


def _load_create_mode_config_for_preview(project_root: Path, path: str) -> dict[str, Any]:
    if not path:
        return {}
    mode_path = project_root / path
    try:
        payload = json.loads(mode_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return dict(payload) if isinstance(payload, dict) else {}


def _gravity_material_candidates(
    *,
    db_path: Path,
    product: str,
    material_type: str,
    lookback_days: int,
) -> list[dict[str, Any]]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT
              psm.material_id,
              psm.name,
              psm.material_type,
              psm.review_status,
              psm.signature,
              psm.create_time,
              psm.first_seen_at,
              psm.synced_at,
              psm.payload_json,
              COALESCE(MAX(CASE WHEN psmr.window_days = ? THEN psmr.stat_cost END), MAX(psmr.stat_cost), psm.cost_lookback, 0) AS stat_cost,
              COALESCE(MAX(CASE WHEN psmr.window_days = ? THEN psmr.convert_cnt END), MAX(psmr.convert_cnt), 0) AS convert_cnt,
              COALESCE(
                MAX(CASE WHEN psmr.window_days = ? THEN psmr.roi_1day_cost_weighted END),
                MAX(psmr.roi_1day_cost_weighted),
                0
              ) AS roi_1day_cost_weighted
            FROM product_source_materials psm
            LEFT JOIN product_source_material_metric_rollups psmr
              ON psmr.product = psm.product
             AND psmr.source_advertiser_id = psm.source_advertiser_id
             AND psmr.material_id = psm.material_id
            WHERE psm.product = ?
              AND psm.source = 'gravity_engine'
              AND psm.material_type = ?
              AND psm.is_active = 1
              AND psm.signature != ''
            GROUP BY
              psm.material_id, psm.name, psm.material_type, psm.review_status,
              psm.signature, psm.create_time, psm.first_seen_at, psm.synced_at,
              psm.payload_json, psm.cost_lookback
            """,
            (lookback_days, lookback_days, lookback_days, product, material_type),
        ).fetchall()
    return [dict(row) for row in rows]


def _gravity_upload_coverage(
    *,
    db_path: Path,
    product: str,
    material_ids: list[str],
    advertiser_ids: list[str],
) -> dict[str, set[str]]:
    material_ids = _unique_account_ids(material_ids)
    advertiser_ids = _unique_account_ids(advertiser_ids)
    if not material_ids or not advertiser_ids:
        return {}
    material_placeholders = ",".join("?" for _ in material_ids)
    account_placeholders = ",".join("?" for _ in advertiser_ids)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"""
            SELECT gravity_material_id, target_advertiser_id
            FROM gravity_upload_tasks
            WHERE product = ?
              AND status = 'completed'
              AND video_id != ''
              AND gravity_material_id IN ({material_placeholders})
              AND target_advertiser_id IN ({account_placeholders})
            """,
            (product, *material_ids, *advertiser_ids),
        ).fetchall()
    coverage: dict[str, set[str]] = {}
    for row in rows:
        coverage.setdefault(_text(row["gravity_material_id"]), set()).add(_text(row["target_advertiser_id"]))
    return coverage


def _gravity_material_is_usable(row: dict[str, Any]) -> bool:
    status = _text(row.get("review_status")).lower()
    blocked_terms = ["禁用", "拒", "reject", "disable", "disabled", "unavailable"]
    return not any(term in status for term in blocked_terms)


def _sort_gravity_candidates(rows: list[dict[str, Any]], *, material_selection: dict[str, Any]) -> list[dict[str, Any]]:
    selection_type = _text(material_selection.get("selection_type"))
    sort_by = _text(material_selection.get("sort_by"))
    if selection_type == "test_new" or sort_by in {"create_time_desc", "effective_create_date_desc"}:
        return sorted(
            rows,
            key=lambda row: (_text(row.get("create_time") or row.get("first_seen_at")), _float(row.get("stat_cost"))),
            reverse=True,
        )
    return sorted(
        rows,
        key=lambda row: (_float(row.get("stat_cost")), _float(row.get("convert_cnt")), _text(row.get("material_id"))),
        reverse=True,
    )


def _derive_mode_key(path: Path) -> str:
    name = path.name
    for suffix in (".local.json", ".example.json", ".json"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return path.stem


def _format_accounts(value: Any, account_names: dict[str, str]) -> str:
    accounts = value if isinstance(value, list) else []
    labels = []
    for account_id in _unique_account_ids(accounts):
        name = account_name_for(account_names, account_id)
        labels.append(f"{name}（{account_id}）")
    return "；".join(labels)


def _relative_plan_path(project_root: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(project_root.resolve()))
    except ValueError:
        return str(path)


def _split_account_ids(value: Any) -> list[str]:
    if isinstance(value, list):
        raw_items = value
    else:
        raw_items = str(value or "").replace("\n", ",").split(",")
    return [str(item).strip() for item in raw_items if str(item).strip()]


def _resolve_generate_accounts(request: dict[str, Any], *, project_root: str | Path) -> tuple[list[str], str, list[str]]:
    explicit_accounts = _split_account_ids(request.get("advertiser_ids") or request.get("accounts"))
    if explicit_accounts:
        return explicit_accounts, "manual", []

    return [], "manual", []


def _generate_validation_reasons(
    *,
    mode: str,
    owner: str,
    template_catalog: str,
    advertiser_ids: list[str],
) -> list[str]:
    reasons: list[str] = []
    if not mode:
        reasons.append("必须明确选择固定创建模式")
    if not owner:
        reasons.append("必须明确填写负责人")
    if not template_catalog:
        reasons.append("必须明确选择固定模板 JSON")
    if not advertiser_ids:
        reasons.append("必须明确填写本次账户 ID")
    return reasons


def _resolve_product_name(request: dict[str, Any], product_key: str, *, project_root: str | Path) -> str:
    explicit = _text(request.get("product") or request.get("product_name"))
    if explicit:
        return explicit
    if product_key:
        for account in load_accounts(Path(project_root) / "configs"):
            if account.get("product_key") == product_key and account.get("product_name"):
                return account["product_name"]
    return product_key


def _is_7r_mode(mode: str) -> bool:
    return "7r" in mode.lower()


def _derive_template_product_key(path: Path) -> str:
    name = path.name
    for suffix in (".local.json", ".example.json", ".json"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return path.stem


def _unique_account_ids(values: Any) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        advertiser_id = _text(value)
        if advertiser_id and advertiser_id not in seen:
            output.append(advertiser_id)
            seen.add(advertiser_id)
    return output


def _rows(value: Any) -> list[dict[str, Any]]:
    return [dict(item) for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _account_source_label(source: str) -> str:
    if source == "product_active_accounts":
        return "产品账户库 active 账户"
    return "手动填写账户 ID"


def _plan_source_label(value: Any, *, execution_preview: bool) -> str:
    source = _text(value)
    if source == "current_generated":
        return "本页刚生成的新计划"
    if source == "manual":
        return "手动指定的历史计划"
    if source == "latest":
        return "最近创建计划"
    return "执行预览计划" if execution_preview else "创建计划"


def _plan_mode_key(plan: dict[str, Any], preview: dict[str, Any]) -> str:
    summary = preview.get("summary") if isinstance(preview.get("summary"), dict) else {}
    request = plan.get("create_request") if isinstance(plan.get("create_request"), dict) else {}
    return _text(summary.get("mode_key") or plan.get("mode_key") or request.get("mode") or request.get("mode_key"))


def _plan_template_name(plan: dict[str, Any], preview: dict[str, Any]) -> str:
    request = plan.get("create_request") if isinstance(plan.get("create_request"), dict) else {}
    review = preview.get("review") if isinstance(preview.get("review"), dict) else {}
    details = review.get("details") if isinstance(review.get("details"), dict) else {}
    return _text(
        request.get("project_template_name")
        or request.get("template_key")
        or details.get("project_template_name")
        or details.get("template_key")
    )


def _plan_template_path(plan: dict[str, Any], preview: dict[str, Any]) -> str:
    request = plan.get("create_request") if isinstance(plan.get("create_request"), dict) else {}
    review = preview.get("review") if isinstance(preview.get("review"), dict) else {}
    details = review.get("details") if isinstance(review.get("details"), dict) else {}
    summary = plan.get("summary") if isinstance(plan.get("summary"), dict) else {}
    return _text(
        summary.get("template_catalog_path")
        or request.get("template_catalog_path")
        or request.get("template_catalog")
        or request.get("template_catalog_json")
        or details.get("template_catalog_path")
    )


def _material_reuse_rule(plan: dict[str, Any], summary: dict[str, Any]) -> str:
    request = plan.get("create_request") if isinstance(plan.get("create_request"), dict) else {}
    selection = request.get("material_selection") if isinstance(request.get("material_selection"), dict) else {}
    requirements = request.get("material_requirements") if isinstance(request.get("material_requirements"), dict) else {}
    selection_type = _text(summary.get("selection_type") or selection.get("selection_type"))
    lookback_days = _int(selection.get("lookback_days"))
    allow_reuse = bool(requirements.get("allow_reuse_across_accounts")) or _text(requirements.get("on_insufficient")) == "allow_reuse"
    reuse_text = "，素材不足时允许按固定规则复用" if allow_reuse else ""
    if selection_type == "random_materials":
        return f"随机素材{reuse_text}"
    if selection_type == "high_spend":
        window = f"近 {lookback_days} 天" if lookback_days else "历史"
        return f"{window}高消耗素材{reuse_text}"
    if selection_type == "test_new":
        window = f"近 {lookback_days} 天" if lookback_days else "历史"
        return f"{window}测新素材{reuse_text}"
    return selection_type or ("允许复用" if allow_reuse else "未配置")


def _display_create_mode(request: dict[str, Any]) -> str:
    mode = _text(request.get("mode") or request.get("mode_key"))
    product_name = _text(request.get("product") or request.get("product_name"))
    mode_label = create_mode_label(mode)
    return f"{product_name}{mode_label}" if product_name and mode_label != "未指定模式" else mode_label


def _material_source(request: dict[str, Any]) -> str:
    source = _text(request.get("material_source"))
    if not source or source == "source_material_account":
        return "source_account"
    return source


def _material_source_label(source: str) -> str:
    return MATERIAL_SOURCE_LABELS.get(_text(source), "未知素材来源")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _format_metric(value: Any) -> int | float:
    number = _float(value)
    return int(number) if number.is_integer() else round(number, 2)


def _format_roi(value: Any) -> str:
    number = _float(value)
    if number <= 0:
        return "-"
    return f"{number:.2f}"
