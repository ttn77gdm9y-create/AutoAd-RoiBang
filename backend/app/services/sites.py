from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from roibang_v2.ui.background_tasks import build_runner_command
from roibang_v2.ui.background_tasks import build_task_record
from roibang_v2.ui.background_tasks import start_runner
from roibang_v2.ui.background_tasks import write_task_record
from roibang_v2.workflows.frontend_operation_log import record_frontend_operation
from roibang_v2.workflows.site_status_update import build_site_status_update_plan
from roibang_v2.workflows.site_template_foundation import build_site_template_foundation_plan

STATUS_LABELS = {
    "published": "发布",
    "unpublished": "下线",
    "delete": "删除",
    "undeleted": "恢复删除",
}


def build_site_handsel_results(
    *,
    project_root: str | Path,
    artifact_path: str = "",
) -> dict[str, Any]:
    runs_dir = Path(project_root) / "data" / "runs"
    path = _resolve_artifact_path(project_root, artifact_path) if artifact_path else _latest_artifact(runs_dir, "site_handsel")
    if not path or not path.exists():
        return {
            "summary": {
                "title": "落地页转赠结果",
                "status": "not_found",
                "risk_level": "medium",
                "execution_enabled": False,
                "items": [],
                "warnings": ["没有找到落地页转赠结果。"],
                "blocking_reasons": [],
            },
            "table": {"columns": ["目标账户 ID", "新落地页 ID", "原落地页 ID", "结果"], "rows": []},
            "artifact_path": "",
            "raw": {},
        }

    payload = _read_json(path)
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    rows = _handsel_result_rows(payload)
    error_count = int(summary.get("error_count") or len(payload.get("error_list") or []))
    return {
        "summary": {
            "title": "落地页转赠结果",
            "status": _text(payload.get("status")) or "loaded",
            "risk_level": "high" if error_count else "low",
            "execution_enabled": False,
            "items": [
                {"label": "源账户", "value": _text(summary.get("source_advertiser_id"))},
                {"label": "原落地页", "value": _text(summary.get("site_id"))},
                {"label": "目标账户数", "value": int(summary.get("target_count") or 0)},
                {"label": "成功数", "value": int(summary.get("success_count") or 0)},
                {"label": "失败数", "value": error_count},
            ],
            "warnings": [],
            "blocking_reasons": [],
        },
        "table": {"columns": ["目标账户 ID", "新落地页 ID", "原落地页 ID", "结果"], "rows": rows},
        "artifact_path": str(path),
        "raw": payload,
    }


def build_site_status_preview(request: dict[str, Any], *, project_root: str | Path) -> dict[str, Any]:
    workflow_request = {"site_status_update": _site_status_cfg(request, execute=False)}
    plan = build_site_status_update_plan(workflow_request)
    if plan["status"] == "blocked":
        return _blocked_preview(plan, request)

    rows = [
        {
            "账户 ID": _text(row.get("advertiser_id")),
            "落地页 ID": _text(row.get("site_id")),
            "目标状态": _status_label(plan["summary"]["status"]),
        }
        for row in plan["site_pairs"]
    ]
    execute_command = _build_site_status_command(request, execute=True)
    return {
        "summary": {
            "title": "落地页状态更新预览",
            "status": "ready",
            "risk_level": "high" if plan["summary"]["status"] == "delete" else "medium",
            "execution_enabled": True,
            "items": [
                {"label": "目标状态", "value": _status_label(plan["summary"]["status"])},
                {"label": "账户数", "value": plan["summary"]["advertiser_count"]},
                {"label": "落地页数", "value": plan["summary"]["site_count"]},
                {"label": "请求批次数", "value": plan["summary"]["request_count"]},
            ],
            "warnings": ["这是落地页状态真实修改入口；执行前必须核对中文摘要和落地页明细，并输入“确认执行”。"],
            "blocking_reasons": [],
        },
        "table": {"columns": ["账户 ID", "落地页 ID", "目标状态"], "rows": rows},
        "artifact_path": "",
        "raw": {"project_root": str(project_root), "request": request, "plan": plan, "execute_command": execute_command},
    }


def start_site_status_task(request: dict[str, Any], *, project_root: str | Path) -> dict[str, Any]:
    preview = build_site_status_preview(request, project_root=project_root)
    if preview["summary"]["status"] == "blocked":
        return preview

    root = Path(project_root)
    runs_dir = root / "data" / "runs"
    task = build_task_record(
        runs_dir=runs_dir,
        operation_type="site_status_update",
        command=list(preview["raw"]["execute_command"]),
        cwd=str(root),
        request=request,
    )
    task_path = write_task_record(runs_dir, task)
    pid = start_runner(build_runner_command(task_path), cwd=root)
    task["pid"] = pid
    write_task_record(runs_dir, task)
    operation_log = _record_site_status_operation(runs_dir, task, request, preview)

    return {
        "summary": {
            "title": "落地页状态更新任务",
            "status": "queued",
            "risk_level": preview["summary"]["risk_level"],
            "execution_enabled": True,
            "items": [
                *preview["summary"]["items"],
                {"label": "任务 ID", "value": task["task_id"]},
                {"label": "任务状态", "value": task["status"]},
            ],
            "warnings": ["真实执行任务已提交；可在当前页面或任务中心查看中文进度和结果。"],
            "blocking_reasons": [],
        },
        "table": preview["table"],
        "artifact_path": str(task_path),
        "task": task,
        "raw": {"preview": preview, "task": task, "operation_log": operation_log},
    }


def build_site_template_foundation_preview(request: dict[str, Any], *, project_root: str | Path) -> dict[str, Any]:
    workflow_request = {"site_template_foundation": _site_template_foundation_cfg(request, execute=False)}
    plan = build_site_template_foundation_plan(workflow_request)
    if plan["status"] == "blocked":
        return _blocked_site_template_preview(plan, request)

    rows = [_site_template_target_row(row, plan) for row in plan.get("targets") or [] if isinstance(row, dict)]
    execute_command = _build_site_template_foundation_command(request, execute=True)
    summary = plan.get("summary") if isinstance(plan.get("summary"), dict) else {}
    return {
        "summary": {
            "title": "模板建站预览",
            "status": "ready",
            "risk_level": "high",
            "execution_enabled": True,
            "items": [
                {"label": "源账户", "value": _text(summary.get("source_advertiser_id"))},
                {"label": "源落地页", "value": _text(summary.get("source_site_id"))},
                {"label": "模板 ID", "value": _text(summary.get("template_id")) or "执行时创建"},
                {"label": "目标账户数", "value": int(summary.get("target_count") or 0)},
                {"label": "小游戏路径", "value": _text(summary.get("game_path"))},
                {"label": "发布", "value": "是" if bool(summary.get("publish")) else "否"},
            ],
            "warnings": ["这是模板建站真实执行入口；执行前必须核对中文摘要和目标账户明细，并输入“确认执行”。"],
            "blocking_reasons": [],
        },
        "table": {"columns": ["账户 ID", "现有落地页 ID", "动作", "小游戏路径", "发布"], "rows": rows},
        "artifact_path": "",
        "raw": {"project_root": str(project_root), "request": request, "plan": plan, "execute_command": execute_command},
    }


def start_site_template_foundation_task(request: dict[str, Any], *, project_root: str | Path) -> dict[str, Any]:
    preview = build_site_template_foundation_preview(request, project_root=project_root)
    if preview["summary"]["status"] == "blocked":
        return preview

    root = Path(project_root)
    runs_dir = root / "data" / "runs"
    task = build_task_record(
        runs_dir=runs_dir,
        operation_type="site_template_foundation",
        command=list(preview["raw"]["execute_command"]),
        cwd=str(root),
        request=request,
    )
    task_path = write_task_record(runs_dir, task)
    pid = start_runner(build_runner_command(task_path), cwd=root)
    task["pid"] = pid
    write_task_record(runs_dir, task)
    operation_log = _record_site_template_foundation_operation(runs_dir, task, request, preview)

    return {
        "summary": {
            "title": "模板建站任务",
            "status": "queued",
            "risk_level": preview["summary"]["risk_level"],
            "execution_enabled": True,
            "items": [
                *preview["summary"]["items"],
                {"label": "任务 ID", "value": task["task_id"]},
                {"label": "任务状态", "value": task["status"]},
            ],
            "warnings": ["真实执行任务已提交；可在当前页面或任务中心查看中文进度和结果。"],
            "blocking_reasons": [],
        },
        "table": preview["table"],
        "artifact_path": str(task_path),
        "task": task,
        "raw": {"preview": preview, "task": task, "operation_log": operation_log},
    }


def _record_site_status_operation(
    runs_dir: Path,
    task: dict[str, Any],
    request: dict[str, Any],
    preview: dict[str, Any],
) -> dict[str, Any]:
    raw = preview.get("raw") if isinstance(preview.get("raw"), dict) else {}
    plan = raw.get("plan") if isinstance(raw.get("plan"), dict) else {}
    summary = plan.get("summary") if isinstance(plan.get("summary"), dict) else {}
    status = _text(summary.get("status"))
    site_pairs = [dict(row) for row in plan.get("site_pairs") or [] if isinstance(row, dict)]
    account_ids = sorted({_text(row.get("advertiser_id")) for row in site_pairs if _text(row.get("advertiser_id"))})
    return record_frontend_operation(
        runs_dir=runs_dir,
        operation_type="site_status_update",
        status=_text(task.get("status")) or "queued",
        actor=_text(request.get("owner")) or _text(request.get("operator")) or "local-ui",
        request={**request, "task_id": task["task_id"]},
        result={
            "task_id": task["task_id"],
            "task_artifact_path": task.get("artifact_path"),
            "status": task.get("status"),
        },
        details={
            "product": _text(request.get("product") or request.get("product_name")),
            "product_key": _text(request.get("product_key")),
            "accounts": [{"advertiser_id": advertiser_id} for advertiser_id in account_ids],
            "sites": site_pairs,
            "site_status": {"status": status, "status_label": _status_label(status)},
            "review": _review_from_preview(preview, can_execute=bool(preview.get("summary", {}).get("execution_enabled"))),
        },
    )


def _record_site_template_foundation_operation(
    runs_dir: Path,
    task: dict[str, Any],
    request: dict[str, Any],
    preview: dict[str, Any],
) -> dict[str, Any]:
    raw = preview.get("raw") if isinstance(preview.get("raw"), dict) else {}
    plan = raw.get("plan") if isinstance(raw.get("plan"), dict) else {}
    summary = plan.get("summary") if isinstance(plan.get("summary"), dict) else {}
    targets = [dict(row) for row in plan.get("targets") or [] if isinstance(row, dict)]
    account_ids = [_text(row.get("advertiser_id")) for row in targets if _text(row.get("advertiser_id"))]
    return record_frontend_operation(
        runs_dir=runs_dir,
        operation_type="site_template_foundation",
        status=_text(task.get("status")) or "queued",
        actor=_text(request.get("owner")) or _text(request.get("operator")) or "local-ui",
        request={**request, "task_id": task["task_id"]},
        result={
            "task_id": task["task_id"],
            "task_artifact_path": task.get("artifact_path"),
            "status": task.get("status"),
        },
        details={
            "product": _text(request.get("product") or request.get("product_name")),
            "product_key": _text(request.get("product_key")),
            "accounts": [{"advertiser_id": advertiser_id} for advertiser_id in account_ids],
            "sites": targets,
            "site_template_foundation": {
                "source_advertiser_id": _text(summary.get("source_advertiser_id")),
                "source_site_id": _text(summary.get("source_site_id")),
                "template_id": _text(summary.get("template_id")),
                "game_instance_id": _text(summary.get("game_instance_id")),
                "game_path": _text(summary.get("game_path")),
                "publish": bool(summary.get("publish")),
                "edit_existing": bool(summary.get("edit_existing")),
            },
            "review": _review_from_preview(preview, can_execute=bool(preview.get("summary", {}).get("execution_enabled"))),
        },
    )


def _review_from_preview(preview: dict[str, Any], *, can_execute: bool) -> dict[str, Any]:
    summary = preview.get("summary") if isinstance(preview.get("summary"), dict) else {}
    warnings = list(summary.get("warnings") or [])
    blocking_reasons = list(summary.get("blocking_reasons") or [])
    return {
        "can_execute": can_execute,
        "summary": {"warning_count": len(warnings)},
        "warnings": warnings,
        "blocking_reasons": blocking_reasons,
    }


def _blocked_site_template_preview(plan: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
    summary = plan.get("summary") if isinstance(plan.get("summary"), dict) else {}
    return {
        "summary": {
            "title": "模板建站预览",
            "status": "blocked",
            "risk_level": "high",
            "execution_enabled": False,
            "items": [
                {"label": "源账户", "value": _text(summary.get("source_advertiser_id"))},
                {"label": "源落地页", "value": _text(summary.get("source_site_id"))},
                {"label": "小游戏路径", "value": _text(summary.get("game_path"))},
            ],
            "warnings": [],
            "blocking_reasons": list(plan.get("blocking_reasons") or []),
        },
        "table": {"columns": ["账户 ID", "现有落地页 ID", "动作", "小游戏路径", "发布"], "rows": []},
        "artifact_path": "",
        "raw": {"request": request, "plan": plan},
    }


def _blocked_preview(plan: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
    status = _text(plan.get("summary", {}).get("status") if isinstance(plan.get("summary"), dict) else "")
    return {
        "summary": {
            "title": "落地页状态更新预览",
            "status": "blocked",
            "risk_level": "high",
            "execution_enabled": False,
            "items": [{"label": "目标状态", "value": _status_label(status)}],
            "warnings": [],
            "blocking_reasons": list(plan.get("blocking_reasons") or []),
        },
        "table": {"columns": ["账户 ID", "落地页 ID", "目标状态"], "rows": []},
        "artifact_path": "",
        "raw": {"request": request, "plan": plan},
    }


def _build_site_status_command(request: dict[str, Any], *, execute: bool) -> list[str]:
    cfg = _site_status_cfg(request, execute=execute)
    command = [
        sys.executable or "python3",
        "scripts/run_site_status_update.py",
        "--config",
        "configs/project-update-execute.local.json",
        "--status",
        _text(cfg.get("status")) or "delete",
    ]
    handsel_artifact = _text(cfg.get("handsel_artifact") or cfg.get("handsel_artifact_path"))
    advertiser_id = _text(cfg.get("advertiser_id"))
    site_ids = _text(cfg.get("site_ids"))
    if handsel_artifact:
        command.extend(["--handsel-artifact", handsel_artifact])
    if advertiser_id:
        command.extend(["--advertiser-id", advertiser_id])
    if site_ids:
        command.extend(["--site-ids", site_ids])
    if execute:
        command.append("--execute")
    return command


def _build_site_template_foundation_command(request: dict[str, Any], *, execute: bool) -> list[str]:
    cfg = _site_template_foundation_cfg(request, execute=execute)
    command = [
        sys.executable or "python3",
        "scripts/run_site_template_foundation.py",
        "--config",
        "configs/project-update-execute.local.json",
    ]
    options = [
        ("--source-advertiser-id", cfg.get("source_advertiser_id")),
        ("--source-site-id", cfg.get("source_site_id")),
        ("--template-id", cfg.get("template_id")),
        ("--template-name", cfg.get("template_name")),
        ("--wechat-game-index", cfg.get("wechat_game_index")),
        ("--game-instance-id", cfg.get("game_instance_id")),
        ("--game-path", cfg.get("game_path")),
        ("--target-advertiser-ids", cfg.get("target_advertiser_ids")),
        ("--target-accounts-file", cfg.get("target_accounts_path")),
        ("--site-mapping-artifact", cfg.get("site_mapping_artifact")),
        ("--site-name-prefix", cfg.get("site_name_prefix")),
    ]
    for flag, value in options:
        text = _text(value)
        if text:
            command.extend([flag, text])
    if bool(cfg.get("edit_existing")):
        command.append("--edit-existing")
    if not bool(cfg.get("publish")):
        command.append("--no-publish")
    if execute:
        command.append("--execute")
    return command


def _site_status_cfg(request: dict[str, Any], *, execute: bool) -> dict[str, Any]:
    return {
        "handsel_artifact": _text(request.get("handsel_artifact") or request.get("handsel_artifact_path")),
        "advertiser_id": _text(request.get("advertiser_id")),
        "site_ids": request.get("site_ids"),
        "status": _text(request.get("status")) or "delete",
        "execute": execute,
    }


def _site_template_foundation_cfg(request: dict[str, Any], *, execute: bool) -> dict[str, Any]:
    return {
        "source_advertiser_id": _text(request.get("source_advertiser_id") or request.get("advertiser_id")),
        "source_site_id": _text(request.get("source_site_id") or request.get("site_id")),
        "template_id": _text(request.get("template_id")),
        "template_name": _text(request.get("template_name")),
        "wechat_game_index": _text(request.get("wechat_game_index") or request.get("game_component_index")),
        "game_instance_id": _text(request.get("game_instance_id") or request.get("instance_id") or request.get("micro_app_instance_id")),
        "game_path": _text(request.get("game_path")),
        "target_advertiser_ids": _join_values(request.get("target_advertiser_ids") or request.get("target_accounts") or request.get("targets")),
        "target_accounts_path": _text(request.get("target_accounts_path") or request.get("target_advertiser_ids_path")),
        "site_mapping_artifact": _text(request.get("site_mapping_artifact") or request.get("handsel_artifact")),
        "site_name_prefix": _text(request.get("site_name_prefix")),
        "edit_existing": _to_bool(request.get("edit_existing")),
        "execute": execute,
        "publish": _to_bool(request.get("publish"), default=True),
    }


def _site_template_target_row(row: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    summary = plan.get("summary") if isinstance(plan.get("summary"), dict) else {}
    edit_existing = bool(summary.get("edit_existing"))
    return {
        "账户 ID": _text(row.get("advertiser_id")),
        "现有落地页 ID": _text(row.get("site_id")),
        "动作": "修复现有落地页" if edit_existing else "新建落地页",
        "小游戏路径": _text(summary.get("game_path")),
        "发布": "是" if bool(summary.get("publish")) else "否",
    }


def _handsel_result_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in payload.get("success_list") or []:
        if not isinstance(row, dict):
            continue
        rows.append(
            {
                "目标账户 ID": _text(row.get("target_advertiser_id") or row.get("advertiser_id")),
                "新落地页 ID": _text(row.get("site_id")),
                "原落地页 ID": _text(row.get("origin_site_id") or row.get("source_site_id")),
                "结果": "成功",
            }
        )
    for row in payload.get("error_list") or []:
        if not isinstance(row, dict):
            continue
        reason = _text(row.get("error_reason") or row.get("message")) or "失败"
        rows.append(
            {
                "目标账户 ID": _text(row.get("target_advertiser_id") or row.get("advertiser_id")),
                "新落地页 ID": _text(row.get("site_id")),
                "原落地页 ID": _text(row.get("origin_site_id") or row.get("source_site_id")),
                "结果": reason,
            }
        )
    return rows


def _latest_artifact(runs_dir: Path, workflow: str) -> Path:
    paths = sorted((runs_dir / workflow).glob("*.json"), key=lambda path: path.name, reverse=True)
    return paths[0] if paths else Path("")


def _resolve_artifact_path(project_root: str | Path, artifact_path: str) -> Path:
    path = Path(artifact_path)
    if path.is_absolute():
        return path
    return Path(project_root) / artifact_path


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, IsADirectoryError, OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _join_values(value: Any) -> str:
    if isinstance(value, list):
        return "\n".join(_text(item) for item in value if _text(item))
    return _text(value)


def _to_bool(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return _text(value).lower() in {"1", "true", "yes", "y", "on"}


def _status_label(status: str) -> str:
    return STATUS_LABELS.get(_text(status), _text(status) or "未选择")


def _text(value: Any) -> str:
    return str(value or "").strip()
