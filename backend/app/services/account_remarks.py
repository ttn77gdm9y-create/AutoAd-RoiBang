from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Any

from roibang_v2.ui.background_tasks import build_runner_command
from roibang_v2.ui.background_tasks import build_task_record
from roibang_v2.ui.background_tasks import start_runner
from roibang_v2.ui.background_tasks import write_task_record
from roibang_v2.ui.script_runner import build_account_remark_config_command
from roibang_v2.ui.script_runner import build_account_remark_execute_command
from roibang_v2.workflows.frontend_operation_log import record_frontend_operation

from backend.app.services.account_names import account_name_for
from backend.app.services.account_names import load_account_name_map


def build_account_remark_config_preview(request: dict[str, Any], *, project_root: str | Path) -> dict[str, Any]:
    update_id = _text(request.get("update_id")) or _default_update_id()
    remark = _text(request.get("remark"))
    advertiser_ids = _split_account_ids(request.get("advertiser_ids"))
    output_path = _text(request.get("output_path")) or _default_output_path(update_id)

    validation_reasons = _config_validation_reasons(
        update_id=update_id,
        remark=remark,
        advertiser_ids=advertiser_ids,
        output_path=output_path,
    )
    if validation_reasons:
        return _blocked_config_preview(update_id, remark, output_path, validation_reasons, request)

    account_names = load_account_name_map(Path(project_root) / "configs")
    command = build_account_remark_config_command(
        update_id=update_id,
        remark=remark,
        accounts="\n".join(advertiser_ids),
        output_path=output_path,
    )
    rows = [
        {
            "账户 ID": advertiser_id,
            "账户名": account_name_for(account_names, advertiser_id),
            "目标备注": remark,
            "输出 JSON": output_path,
        }
        for advertiser_id in advertiser_ids
    ]
    return {
        "summary": {
            "title": "账户备注配置预览",
            "status": "planned",
            "risk_level": "medium",
            "execution_enabled": False,
            "items": [
                {"label": "配置 ID", "value": update_id},
                {"label": "目标备注", "value": remark},
                {"label": "账户数", "value": len(advertiser_ids)},
                {"label": "输出 JSON", "value": output_path},
            ],
            "warnings": ["这里只生成账户备注 JSON 预览，不执行真实备注修改。"],
            "blocking_reasons": [],
        },
        "table": {"columns": ["账户 ID", "账户名", "目标备注", "输出 JSON"], "rows": rows},
        "artifact_path": "",
        "raw": {"project_root": str(project_root), "request": request, "command": command},
    }


def start_account_remark_config_task(request: dict[str, Any], *, project_root: str | Path) -> dict[str, Any]:
    preview = build_account_remark_config_preview(request, project_root=project_root)
    if preview["summary"]["status"] == "blocked":
        return preview

    root = Path(project_root)
    runs_dir = root / "data" / "runs"
    task = build_task_record(
        runs_dir=runs_dir,
        operation_type="account_remark_config_generate",
        command=list(preview["raw"]["command"]),
        cwd=str(root),
        request=request,
    )
    task_path = write_task_record(runs_dir, task)
    pid = start_runner(build_runner_command(task_path), cwd=root)
    task["pid"] = pid
    write_task_record(runs_dir, task)
    operation_log = _record_config_operation(runs_dir, task, request, preview)

    return {
        "summary": {
            "title": "账户备注配置生成任务",
            "status": "queued",
            "risk_level": preview["summary"]["risk_level"],
            "execution_enabled": False,
            "items": [
                *preview["summary"]["items"],
                {"label": "任务 ID", "value": task["task_id"]},
                {"label": "任务状态", "value": task["status"]},
            ],
            "warnings": ["配置生成任务已进入任务中心；这里仍未执行真实备注修改。"],
            "blocking_reasons": [],
        },
        "table": preview["table"],
        "artifact_path": str(task_path),
        "task": task,
        "raw": {"preview": preview, "task": task, "operation_log": operation_log},
    }


def build_account_remark_execute_preview(request: dict[str, Any], *, project_root: str | Path) -> dict[str, Any]:
    account_remark_update_path = _text(request.get("account_remark_update_path")) or _text(request.get("path"))
    if not account_remark_update_path:
        return _blocked_execute_preview("未填写账户备注 JSON 路径", request, account_remark_update_path)

    path = _resolve_path(project_root, account_remark_update_path)
    if not path.exists():
        return _blocked_execute_preview(f"账户备注 JSON 不存在：{account_remark_update_path}", request, account_remark_update_path)

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return _blocked_execute_preview(f"账户备注 JSON 解析失败：{exc}", request, account_remark_update_path)

    cfg = _unwrap_account_remark_update(payload)
    remark = _text(cfg.get("remark"))
    advertiser_ids = _split_account_ids(cfg.get("advertiser_ids"))
    if not remark:
        return _blocked_execute_preview("账户备注 JSON 中没有 remark，不能执行", request, account_remark_update_path)
    if not advertiser_ids:
        return _blocked_execute_preview("账户备注 JSON 中没有 advertiser_ids，不能执行", request, account_remark_update_path)

    account_names = load_account_name_map(Path(project_root) / "configs")
    execute_command = build_account_remark_execute_command(
        account_remark_update_path=account_remark_update_path,
        execute=True,
    )
    rows = [
        {"账户 ID": advertiser_id, "账户名": account_name_for(account_names, advertiser_id), "目标备注": remark}
        for advertiser_id in advertiser_ids
    ]
    return {
        "summary": {
            "title": "账户备注执行预览",
            "status": "ready",
            "risk_level": "medium",
            "execution_enabled": True,
            "items": [
                {"label": "配置来源", "value": _config_source_label(request.get("config_source"))},
                {"label": "配置 ID", "value": _text(cfg.get("update_id"))},
                {"label": "目标备注", "value": remark},
                {"label": "账户数", "value": len(advertiser_ids)},
                {"label": "账户备注 JSON", "value": account_remark_update_path},
            ],
            "warnings": ["这是账户备注真实修改入口；执行前必须核对中文摘要和账户明细，并输入“确认执行”。"],
            "blocking_reasons": [],
        },
        "table": {"columns": ["账户 ID", "账户名", "目标备注"], "rows": rows},
        "artifact_path": account_remark_update_path,
        "raw": {"request": request, "account_remark_update": payload, "execute_command": execute_command},
    }


def start_account_remark_execute_task(request: dict[str, Any], *, project_root: str | Path) -> dict[str, Any]:
    preview = build_account_remark_execute_preview(request, project_root=project_root)
    if preview["summary"]["status"] == "blocked":
        return preview

    root = Path(project_root)
    runs_dir = root / "data" / "runs"
    task = build_task_record(
        runs_dir=runs_dir,
        operation_type="account_remark_update",
        command=list(preview["raw"]["execute_command"]),
        cwd=str(root),
        request=request,
    )
    task_path = write_task_record(runs_dir, task)
    pid = start_runner(build_runner_command(task_path), cwd=root)
    task["pid"] = pid
    write_task_record(runs_dir, task)
    operation_log = _record_execute_operation(runs_dir, task, request, preview)

    return {
        "summary": {
            "title": "账户备注执行任务",
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


def _record_config_operation(
    runs_dir: Path,
    task: dict[str, Any],
    request: dict[str, Any],
    preview: dict[str, Any],
) -> dict[str, Any]:
    advertiser_ids = _split_account_ids(request.get("advertiser_ids"))
    update_id = _text(request.get("update_id"))
    remark = _text(request.get("remark"))
    return record_frontend_operation(
        runs_dir=runs_dir,
        operation_type="account_remark_config_generate",
        status=_text(task.get("status")) or "queued",
        actor=_text(request.get("owner")) or _text(request.get("operator")) or "local-ui",
        request={**request, "task_id": task["task_id"]},
        result={
            "task_id": task["task_id"],
            "task_artifact_path": task.get("artifact_path"),
            "status": task.get("status"),
            "execute_artifact_path": _summary_item_value(preview, "输出 JSON") or _text(request.get("output_path")),
        },
        details={
            "product": _text(request.get("product") or request.get("product_name")),
            "product_key": _text(request.get("product_key")),
            "accounts": [{"advertiser_id": advertiser_id} for advertiser_id in advertiser_ids],
            "account_remark": {
                "update_id": update_id,
                "remark": remark,
                "mode": "config_generate",
            },
            "review": _review_from_preview(preview, can_execute=False),
        },
    )


def _record_execute_operation(
    runs_dir: Path,
    task: dict[str, Any],
    request: dict[str, Any],
    preview: dict[str, Any],
) -> dict[str, Any]:
    raw = preview.get("raw") if isinstance(preview.get("raw"), dict) else {}
    payload = raw.get("account_remark_update") if isinstance(raw.get("account_remark_update"), dict) else {}
    cfg = _unwrap_account_remark_update(payload)
    advertiser_ids = _split_account_ids(cfg.get("advertiser_ids"))
    return record_frontend_operation(
        runs_dir=runs_dir,
        operation_type="account_remark_update",
        status=_text(task.get("status")) or "queued",
        actor=_text(cfg.get("operator")) or _text(request.get("owner")) or "local-ui",
        request={**request, "task_id": task["task_id"]},
        result={
            "task_id": task["task_id"],
            "task_artifact_path": task.get("artifact_path"),
            "status": task.get("status"),
            "execute_artifact_path": preview.get("artifact_path"),
        },
        details={
            "product": _text(cfg.get("product") or request.get("product") or request.get("product_name")),
            "product_key": _text(cfg.get("product_key") or request.get("product_key")),
            "accounts": [{"advertiser_id": advertiser_id} for advertiser_id in advertiser_ids],
            "account_remark": {
                "update_id": _text(cfg.get("update_id")),
                "remark": _text(cfg.get("remark")),
                "mode": "execute",
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


def _summary_item_value(preview: dict[str, Any], label: str) -> str:
    summary = preview.get("summary") if isinstance(preview.get("summary"), dict) else {}
    for item in summary.get("items") or []:
        if isinstance(item, dict) and _text(item.get("label")) == label:
            return _text(item.get("value"))
    return ""


def _blocked_config_preview(
    update_id: str,
    remark: str,
    output_path: str,
    reason: str | list[str],
    request: dict[str, Any],
) -> dict[str, Any]:
    reasons = reason if isinstance(reason, list) else [reason]
    return {
        "summary": {
            "title": "账户备注配置预览",
            "status": "blocked",
            "risk_level": "medium",
            "execution_enabled": False,
            "items": [
                {"label": "配置 ID", "value": update_id},
                {"label": "目标备注", "value": remark},
                {"label": "输出 JSON", "value": output_path},
            ],
            "warnings": [],
            "blocking_reasons": reasons,
        },
        "table": {"columns": ["账户 ID", "账户名", "目标备注", "输出 JSON"], "rows": []},
        "artifact_path": "",
        "raw": {"request": request},
    }


def _blocked_execute_preview(reason: str, request: dict[str, Any], account_remark_update_path: str) -> dict[str, Any]:
    return {
        "summary": {
            "title": "账户备注执行预览",
            "status": "blocked",
            "risk_level": "medium",
            "execution_enabled": False,
            "items": [{"label": "账户备注 JSON", "value": account_remark_update_path}],
            "warnings": [],
            "blocking_reasons": [reason],
        },
        "table": {"columns": ["账户 ID", "目标备注"], "rows": []},
        "artifact_path": account_remark_update_path,
        "raw": {"request": request},
    }


def _resolve_path(project_root: str | Path, path: str) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return Path(project_root) / candidate


def _unwrap_account_remark_update(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("account_remark_update")
    return dict(value) if isinstance(value, dict) else dict(payload)


def _config_validation_reasons(
    *,
    update_id: str,
    remark: str,
    advertiser_ids: list[str],
    output_path: str,
) -> list[str]:
    reasons: list[str] = []
    if not remark:
        reasons.append("必须明确填写目标备注")
    if not advertiser_ids:
        reasons.append("必须明确填写本次账户 ID")
    return reasons


def _split_account_ids(value: Any) -> list[str]:
    if isinstance(value, list):
        raw_items = value
    else:
        raw_items = str(value or "").replace("\n", ",").split(",")
    return [str(item).strip() for item in raw_items if str(item).strip()]


def _text(value: Any) -> str:
    return str(value or "").strip()


def _default_update_id() -> str:
    return f"account-remark-{datetime.now().strftime('%Y%m%d-%H%M%S')}"


def _default_output_path(update_id: str) -> str:
    return f"configs/account-updates/{update_id}.local.json"


def _config_source_label(value: Any) -> str:
    source = _text(value)
    if source == "current_generated":
        return "本页刚生成的新配置"
    if source == "manual":
        return "手动指定的历史配置"
    return "账户备注配置"
