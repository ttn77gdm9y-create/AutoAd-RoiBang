from __future__ import annotations

import json
from pathlib import Path
from typing import Any

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

from backend.app.services.artifacts import find_latest_artifact
from backend.app.services.account_names import account_name_for
from backend.app.services.account_names import load_account_name_map
from backend.app.services.accounts_store import filter_accounts
from backend.app.services.accounts_store import load_accounts
from backend.app.services.ui_labels import create_mode_label


def build_create_plan_generate_preview(request: dict[str, Any], *, project_root: str | Path) -> dict[str, Any]:
    mode = _text(request.get("mode") or request.get("mode_key")) or "wx_pay_male_random_materials"
    owner = _text(request.get("owner")) or "郭靖"
    target_date = _text(request.get("target_date"))
    product_key = _text(request.get("product_key"))
    product_name = _resolve_product_name(request, product_key, project_root=project_root)
    template_catalog = _text(request.get("template_catalog"))
    cpa_bid = _text(request.get("cpa_bid"))
    roi_coefficient = _text(request.get("roi_coefficient"))
    if roi_coefficient and not _is_7r_mode(mode):
        return _blocked_generate_preview(
            mode,
            product_name,
            owner,
            target_date,
            "非 7R 创建模式不允许填写 ROI 系数；请清空该字段，或切换到 7R 创建模式。",
            request,
        )
    advertiser_ids, account_source, account_warnings = _resolve_generate_accounts(request, project_root=project_root)
    account_names = load_account_name_map(Path(project_root) / "configs")

    if not advertiser_ids:
        return _blocked_generate_preview(mode, product_name, owner, target_date, "至少填写一个账户 ID", request)

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
        )
    except ValueError as exc:
        return _blocked_generate_preview(mode, product_name, owner, target_date, str(exc), request)

    rows = [
        {
            "账户 ID": advertiser_id,
            "账户名": account_name_for(account_names, advertiser_id),
            "创建模式": mode,
            "产品": product_name,
            "负责人": owner,
            "目标日期": target_date,
            "出价": cpa_bid,
            "ROI 系数": roi_coefficient,
        }
        for advertiser_id in advertiser_ids
    ]
    return {
        "summary": {
            "title": "创建计划生成预览",
            "status": "planned",
            "risk_level": "medium",
            "execution_enabled": False,
            "items": [
                {"label": "创建模式", "value": mode},
                {"label": "产品", "value": product_name},
                {"label": "账户数", "value": len(advertiser_ids)},
                {"label": "账户来源", "value": _account_source_label(account_source)},
                {"label": "负责人", "value": owner},
                {"label": "目标日期", "value": target_date},
            ],
            "warnings": [
                *account_warnings,
                "这里只生成创建计划 JSON，不会创建项目、单元或绑定素材。",
            ],
            "blocking_reasons": [],
        },
        "table": {
            "columns": ["账户 ID", "账户名", "创建模式", "产品", "负责人", "目标日期", "出价", "ROI 系数"],
            "rows": rows,
        },
        "artifact_path": "",
        "raw": {
            "project_root": str(project_root),
            "request": request,
            "command": command,
            "resolved_accounts": advertiser_ids,
            "account_source": account_source,
            "product": product_name,
            "product_key": product_key,
        },
    }


def start_create_plan_generate_task(request: dict[str, Any], *, project_root: str | Path) -> dict[str, Any]:
    preview = build_create_plan_generate_preview(request, project_root=project_root)
    if preview["summary"]["status"] == "blocked":
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
    operation_log = _record_execute_operation(runs_dir, task, request, preview)

    return {
        "summary": {
            "title": "创建计划执行任务",
            "status": "queued",
            "risk_level": preview["summary"]["risk_level"],
            "execution_enabled": True,
            "items": [
                *preview["summary"]["items"],
                {"label": "任务 ID", "value": task["task_id"]},
                {"label": "任务状态", "value": task["status"]},
            ],
            "warnings": ["真实创建任务已提交；可在当前页面或任务中心查看中文进度和执行报告。"],
            "blocking_reasons": [],
        },
        "table": preview["table"],
        "artifact_path": str(task_path),
        "task": task,
        "raw": {"preview": preview, "task": task, "operation_log": operation_log},
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
                {"label": "计划 ID", "value": _text(summary.get("plan_id")) or plan_id},
                {"label": "产品", "value": _text(summary.get("product"))},
                {"label": "产品 Key", "value": _text(summary.get("product_key"))},
                {"label": "账户数", "value": _int(summary.get("target_account_count"))},
                {"label": "项目数", "value": _int(summary.get("planned_project_count"))},
                {"label": "单元数", "value": _int(summary.get("planned_unit_count"))},
                {"label": "素材分配数", "value": _int(summary.get("material_assignment_count"))},
                {"label": "唯一素材数", "value": _int(summary.get("unique_material_count"))},
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
    reason: str,
    request: dict[str, Any],
) -> dict[str, Any]:
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
            "blocking_reasons": [reason],
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
) -> dict[str, Any]:
    raw = preview.get("raw") if isinstance(preview.get("raw"), dict) else {}
    plan = raw.get("plan") if isinstance(raw.get("plan"), dict) else {}
    details = create_operation_details_from_plan(plan) if plan else {}
    details["review"] = _operation_review_from_preview(preview)
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

    product_key = _text(request.get("product_key"))
    if not product_key:
        return [], "manual", []

    accounts = filter_accounts(
        load_accounts(Path(project_root) / "configs"),
        product_key=product_key,
        status="active",
    )
    advertiser_ids = _unique_account_ids(row.get("advertiser_id") for row in accounts)
    if not advertiser_ids:
        return [], "product_active_accounts", []
    return advertiser_ids, "product_active_accounts", ["未手动填写账户 ID，已自动使用产品账户库中的 active 账户。"]


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


def _account_source_label(source: str) -> str:
    if source == "product_active_accounts":
        return "产品账户库 active 账户"
    return "手动填写账户 ID"


def _display_create_mode(request: dict[str, Any]) -> str:
    mode = _text(request.get("mode") or request.get("mode_key"))
    product_name = _text(request.get("product") or request.get("product_name"))
    mode_label = create_mode_label(mode)
    return f"{product_name}{mode_label}" if product_name and mode_label != "未指定模式" else mode_label


def _text(value: Any) -> str:
    return str(value or "").strip()


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
