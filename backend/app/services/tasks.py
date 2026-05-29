from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from backend.app.services.account_names import account_name_for
from backend.app.services.account_names import load_account_name_map
from backend.app.services.artifacts import read_json
from backend.app.services.ui_labels import create_mode_label
from backend.app.services.ui_labels import operation_label
from backend.app.services.ui_labels import project_action_label
from backend.app.services.ui_labels import status_label


def list_tasks(runs_dir: str | Path, configs_dir: str | Path | None = None) -> list[dict[str, Any]]:
    task_dir = Path(runs_dir) / "frontend_tasks"
    rows = []
    account_names = load_account_name_map(configs_dir) if configs_dir else {}
    for path in sorted(task_dir.glob("frontend-*.json"), reverse=True):
        payload = read_json(path)
        if payload:
            stdout = _read_text(Path(runs_dir) / str(payload.get("stdout_path") or ""))
            stderr = _read_text(Path(runs_dir) / str(payload.get("stderr_path") or ""))
            result = _task_result(payload, stdout)
            result_artifact = _result_artifact_path(Path(runs_dir), result)
            result_artifact_payload = read_json(result_artifact) if result_artifact is not None else {}
            business_context = _task_business_context(Path(runs_dir), payload, result, result_artifact_payload)
            progress = _task_progress(payload, result, f"{stdout}\n{stderr}")
            rows.append(
                {
                    "task_id": str(payload.get("task_id") or path.stem),
                    "operation_type": str(payload.get("operation_type") or ""),
                    "operation_label": operation_label(payload.get("operation_type")),
                    "status": str(payload.get("status") or ""),
                    "status_label": status_label(payload.get("status")),
                    "created_at": str(payload.get("created_at") or ""),
                    "updated_at": str(payload.get("updated_at") or ""),
                    "return_code": payload.get("return_code"),
                    "artifact_path": str(payload.get("artifact_path") or path),
                    "result_artifact_path": _display_artifact_path(Path(runs_dir), result_artifact),
                    "business_context": business_context,
                    "progress": progress,
                    "result_summary": _short_result_summary(Path(runs_dir), payload, result, account_names, result_artifact_payload),
                }
            )
    return rows


def load_task_detail(runs_dir: str | Path, task_id: str, configs_dir: str | Path | None = None) -> dict[str, Any]:
    base = Path(runs_dir)
    payload = read_json(base / "frontend_tasks" / f"{task_id}.json")
    if not payload:
        return {}
    stdout = _read_text(base / str(payload.get("stdout_path") or ""))
    stderr = _read_text(base / str(payload.get("stderr_path") or ""))
    result = _task_result(payload, stdout)
    account_names = load_account_name_map(configs_dir) if configs_dir else {}
    result_artifact_path = _result_artifact_path(base, result)
    result_artifact = read_json(result_artifact_path) if result_artifact_path is not None else {}
    context_items = _task_context_items(base, payload, result, result_artifact)
    business_context = _context_items_to_text(context_items)
    progress = _task_progress(payload, result, f"{stdout}\n{stderr}")
    blocking_reasons = _business_blocking_reasons(result)
    warnings = _business_warnings(result)
    business_status = str(result.get("status") or "")
    business_status_label = status_label(business_status) if business_status else ""
    task_operation_label = operation_label(payload.get("operation_type"))
    task_status_label = status_label(payload.get("status"))
    display_artifact_path = _display_artifact_path(base, result_artifact_path)
    result_summary = _short_result_summary(base, payload, result, account_names, result_artifact)
    row = {
        "任务 ID": str(payload.get("task_id") or task_id),
        "任务内容": task_operation_label,
        "业务内容": business_context,
        "当前状态": task_status_label,
        "业务结果": business_status_label or task_status_label,
        "结果摘要": result_summary,
    }
    sections = _task_detail_sections(result, result_artifact, account_names)
    return {
        "summary": {
            "title": task_operation_label,
            "status": str(payload.get("status") or "unknown"),
            "risk_level": "high" if payload.get("status") == "failed" or blocking_reasons else "low",
            "execution_enabled": False,
            "items": [
                {"label": "任务 ID", "value": row["任务 ID"]},
                {"label": "任务内容", "value": task_operation_label},
                *context_items,
                {"label": "当前状态", "value": task_status_label},
                *([{"label": "当前进度", "value": progress["label"]}] if progress.get("label") else []),
                *([{"label": "业务状态", "value": business_status}] if business_status else []),
                *([{"label": "业务结果", "value": business_status_label}] if business_status_label else []),
                *_summary_items(result, result_artifact),
            ],
            "warnings": warnings,
            "blocking_reasons": blocking_reasons,
            "progress": progress,
        },
        "table": {"columns": ["任务 ID", "任务内容", "业务内容", "当前状态", "业务结果", "结果摘要"], "rows": [row]},
        "sections": sections,
        "artifact_path": display_artifact_path or str(base / "frontend_tasks" / f"{task_id}.json"),
        "raw": {"task": payload, "result": result, "result_artifact": result_artifact},
        "task": payload,
        "stdout": stdout,
        "stderr": stderr,
    }


def load_task_log(runs_dir: str | Path, task_id: str, stream: str) -> str | None:
    payload = read_json(Path(runs_dir) / "frontend_tasks" / f"{task_id}.json")
    if not payload:
        return None
    if stream == "stdout":
        return _read_text(Path(runs_dir) / str(payload.get("stdout_path") or ""))
    if stream == "stderr":
        return _read_text(Path(runs_dir) / str(payload.get("stderr_path") or ""))
    return None


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (FileNotFoundError, IsADirectoryError, OSError):
        return ""


def _task_result(payload: dict[str, Any], stdout: str) -> dict[str, Any]:
    result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
    if result:
        return result
    return _parse_stdout(stdout)


def _parse_stdout(stdout: str) -> dict[str, Any]:
    text = (stdout or "").strip()
    if text:
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            value = None
        if isinstance(value, dict):
            return value
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                value = json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                value = None
            if isinstance(value, dict):
                return value
    for line in reversed(stdout.splitlines()):
        candidate = line.strip()
        if not candidate.startswith("{"):
            continue
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return {}


def _result_artifact_path(runs_dir: Path, result: dict[str, Any]) -> Path | None:
    text = str(result.get("artifact_path") or result.get("execute_artifact_path") or "").strip()
    if not text:
        return None
    path = Path(text)
    if path.is_absolute():
        return path
    root = runs_dir.parent.parent
    if text.startswith("data/runs/"):
        return root / text
    return runs_dir / text


def _display_artifact_path(runs_dir: Path, path: Path | None) -> str:
    if path is None:
        return ""
    root = runs_dir.parent.parent
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)


def _summary_items(result: dict[str, Any], artifact: dict[str, Any]) -> list[dict[str, Any]]:
    summary = _dict(artifact.get("summary")) or _dict(result.get("summary"))
    mapping = [
        ("账户数", "account_count"),
        ("账户数", "target_account_count"),
        ("项目数", "project_count"),
        ("命中项目数", "project_matched_count"),
        ("动作数", "action_count"),
        ("已更新项目数", "updated_project_count"),
        ("计划 ID", "plan_id"),
        ("项目数", "planned_project_count"),
        ("单元数", "planned_unit_count"),
        ("素材数", "planned_material_count"),
        ("成功数", "success_count"),
        ("失败数", "failure_count"),
    ]
    items: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for label, key in mapping:
        if key not in summary:
            continue
        identity = (label, key)
        if identity in seen:
            continue
        items.append({"label": label, "value": summary[key]})
        seen.add(identity)
    failure = _dict(artifact.get("failure")) or _dict(result.get("failure"))
    if failure:
        failure_operation = str(failure.get("operation") or "").strip()
        if failure_operation:
            items.append(
                {
                    "label": "失败步骤",
                    "value": PROGRESS_OPERATION_LABELS.get(failure_operation, operation_label(failure_operation)),
                }
            )
        failure_code = str(failure.get("code") or "").strip()
        failure_message = str(failure.get("message") or failure.get("msg") or "").strip()
        if failure_message or failure_code:
            items.append(
                {
                    "label": "失败原因",
                    "value": f"{failure_message}（{failure_code}）" if failure_message and failure_code else failure_message or failure_code,
                }
            )
    ledger = _existing_plan_ledger(result) or _existing_plan_ledger(artifact)
    if ledger:
        counts_text = _existing_plan_counts_text(ledger)
        if counts_text:
            items.append({"label": "已存在创建记录", "value": counts_text})
        external_calls = result.get("external_api_calls", artifact.get("external_api_calls"))
        if _to_int(external_calls) == 0:
            items.append({"label": "真实外部创建", "value": "未发起"})
    return items


PROGRESS_PATTERN = re.compile(
    r"operation=(?P<operation>[^\s]+)\s+done=(?P<current>\d+)/(?P<total>\d+)\s+status=(?P<status>[^\s]+)"
)

PROGRESS_OPERATION_LABELS = {
    "create_project": "创建项目",
    "create_unit": "创建单元",
    "bind_material": "绑定素材",
    "lookup_target_material": "查询素材",
    "precheck_existing_target_material": "检查素材",
}


def _task_progress(payload: dict[str, Any], result: dict[str, Any], stdout: str) -> dict[str, Any]:
    parsed = _progress_from_stdout(stdout)
    if parsed:
        return _progress_with_task_status(parsed, str(payload.get("status") or result.get("status") or ""))
    status = str(payload.get("status") or result.get("status") or "").strip()
    if status == "completed":
        return {"percent": 100, "current": 1, "total": 1, "label": "已完成 100%", "status": "success"}
    if status == "failed":
        return {"percent": 100, "current": 1, "total": 1, "label": "已失败", "status": "exception"}
    if status == "queued":
        return {"percent": 0, "current": 0, "total": 1, "label": "排队中 0%", "status": "normal"}
    if status.startswith("running"):
        return {"percent": 0, "current": 0, "total": 1, "label": "运行中，等待进度 0%", "status": "active"}
    return {}


def _progress_from_stdout(stdout: str) -> dict[str, Any]:
    latest: dict[str, Any] = {}
    for match in PROGRESS_PATTERN.finditer(stdout or ""):
        current = _to_int(match.group("current"))
        total = _to_int(match.group("total"))
        if total <= 0:
            continue
        operation = str(match.group("operation") or "")
        percent = min(100, max(0, round(current * 100 / total)))
        operation_label = PROGRESS_OPERATION_LABELS.get(operation, operation)
        latest = {
            "percent": percent,
            "current": current,
            "total": total,
            "label": f"{operation_label} {current}/{total}",
            "status": "active" if str(match.group("status") or "") == "running" else "normal",
        }
    return latest


def _progress_with_task_status(progress: dict[str, Any], task_status: str) -> dict[str, Any]:
    output = dict(progress)
    if task_status == "completed":
        output["percent"] = 100
        output["status"] = "success"
    elif task_status == "failed":
        output["status"] = "exception"
    elif task_status.startswith("running"):
        output["status"] = "active"
    return output


def _short_result_summary(
    runs_dir: Path,
    payload: dict[str, Any],
    result: dict[str, Any],
    account_names: dict[str, str],
    artifact: dict[str, Any] | None = None,
) -> str:
    artifact_path = _result_artifact_path(runs_dir, result)
    artifact = artifact if artifact is not None else (read_json(artifact_path) if artifact_path is not None else {})
    summary = _dict(artifact.get("summary")) or _dict(result.get("summary"))
    operation = operation_label(payload.get("operation_type"))
    status = status_label(result.get("status") or payload.get("status"))
    ledger = _existing_plan_ledger(result) or _existing_plan_ledger(artifact)
    if ledger and _has_existing_plan_block(result):
        counts_text = _existing_plan_counts_text(ledger)
        return f"{operation}：已阻止重复执行，已有{counts_text}，未发起外部创建" if counts_text else f"{operation}：已阻止重复执行，未发起外部创建"
    parts = [f"{operation}：{status}"]
    if summary.get("action_count") is not None:
        parts.append(f"动作 {summary.get('action_count')}")
    if summary.get("updated_project_count") is not None:
        parts.append(f"已更新项目 {summary.get('updated_project_count')}")
    if summary.get("planned_project_count") is not None:
        parts.append(f"计划项目 {summary.get('planned_project_count')}")
    account_ids = _artifact_account_ids(artifact)[:2]
    if account_ids:
        names = [account_name_for(account_names, account_id) for account_id in account_ids]
        parts.append("账户 " + "、".join(names))
    business_context = _task_business_context(runs_dir, payload, result, artifact)
    context_phrase = _summary_context_phrase(business_context)
    if context_phrase:
        parts.append(context_phrase)
    return "，".join(parts)


CREATE_OPERATION_TYPES = {"create_mode", "create_plan_generate", "create_live_execute", "create_live_execute_once"}
PROJECT_OPERATION_TYPES = {
    "project_management_config_generate",
    "project_management_execute",
    "project_realtime_filter_config",
    "project_update_execute",
}
ACCOUNT_REMARK_OPERATION_TYPES = {"account_remark_config_generate", "account_remark_update"}
SITE_STATUS_OPERATION_TYPES = {"site_status_update"}
SITE_TEMPLATE_OPERATION_TYPES = {"site_template_foundation"}


def _task_business_context(
    runs_dir: Path,
    payload: dict[str, Any],
    result: dict[str, Any],
    artifact: dict[str, Any] | None = None,
) -> str:
    return _context_items_to_text(_task_context_items(runs_dir, payload, result, artifact or {}))


def _task_context_items(
    runs_dir: Path,
    payload: dict[str, Any],
    result: dict[str, Any],
    artifact: dict[str, Any],
) -> list[dict[str, Any]]:
    operation_type = str(payload.get("operation_type") or "").strip()
    if operation_type in CREATE_OPERATION_TYPES:
        return _create_task_context_items(runs_dir, payload, result, artifact)
    if operation_type in PROJECT_OPERATION_TYPES:
        action_text = _project_task_action_text(runs_dir, payload, result, artifact)
        return [{"label": "项目管理动作", "value": action_text or "未指定动作"}]
    if operation_type in ACCOUNT_REMARK_OPERATION_TYPES:
        return _account_remark_task_context_items(runs_dir, payload, result, artifact)
    if operation_type in SITE_STATUS_OPERATION_TYPES:
        return _site_status_task_context_items(payload, result, artifact)
    if operation_type in SITE_TEMPLATE_OPERATION_TYPES:
        return _site_template_task_context_items(payload, result, artifact)
    return []


def _account_remark_task_context_items(
    runs_dir: Path,
    payload: dict[str, Any],
    result: dict[str, Any],
    artifact: dict[str, Any],
) -> list[dict[str, Any]]:
    request = _dict(payload.get("request"))
    cfg_payload = _read_first_json(
        runs_dir,
        [
            request.get("account_remark_update_path"),
            request.get("path"),
            request.get("output_path"),
            result.get("execute_artifact_path"),
            result.get("artifact_path"),
        ],
    )
    cfg = _dict(cfg_payload.get("account_remark_update")) or cfg_payload
    summary = _dict(artifact.get("summary")) or _dict(result.get("summary"))
    remark = str(cfg.get("remark") or request.get("remark") or summary.get("remark") or "").strip()
    account_ids = _split_ids(cfg.get("advertiser_ids") or request.get("advertiser_ids"))
    account_count = len(account_ids) or _to_int(summary.get("account_count"))
    items = []
    if remark:
        items.append({"label": "目标备注", "value": remark})
    if account_count:
        items.append({"label": "账户数", "value": account_count})
    return items


def _site_status_task_context_items(
    payload: dict[str, Any],
    result: dict[str, Any],
    artifact: dict[str, Any],
) -> list[dict[str, Any]]:
    request = _dict(payload.get("request"))
    summary = _dict(artifact.get("summary")) or _dict(result.get("summary"))
    status = str(request.get("status") or summary.get("status") or "").strip()
    site_count = _site_pair_count(request) or _to_int(summary.get("site_count") or summary.get("target_site_count"))
    items = []
    if status:
        items.append({"label": "目标状态", "value": _site_status_label(status)})
    if site_count:
        items.append({"label": "落地页数", "value": site_count})
    return items


def _site_template_task_context_items(
    payload: dict[str, Any],
    result: dict[str, Any],
    artifact: dict[str, Any],
) -> list[dict[str, Any]]:
    request = _dict(payload.get("request"))
    summary = _dict(artifact.get("summary")) or _dict(result.get("summary"))
    game_path = str(request.get("game_path") or summary.get("game_path") or "").strip()
    edit_existing = _first_present_bool(request, summary, key="edit_existing")
    publish = _first_present_bool(request, summary, key="publish")
    target_count = len(_split_ids(request.get("target_advertiser_ids"))) or _to_int(summary.get("target_count"))
    items = []
    if edit_existing is not None:
        items.append({"label": "建站动作", "value": "修复现有落地页" if edit_existing else "新建落地页"})
    if target_count:
        items.append({"label": "目标账户数", "value": target_count})
    if game_path:
        items.append({"label": "小游戏路径", "value": game_path})
    if publish is not None:
        items.append({"label": "发布", "value": "是" if publish else "否"})
    return items


def _create_task_context_items(
    runs_dir: Path,
    payload: dict[str, Any],
    result: dict[str, Any],
    artifact: dict[str, Any],
) -> list[dict[str, Any]]:
    plan = artifact if _looks_like_create_plan(artifact) else {}
    if not plan:
        plan = _read_first_json(runs_dir, _create_plan_path_candidates(payload, result, artifact))
    summary = _dict(plan.get("summary"))
    request = _dict(plan.get("create_request"))
    mode_key = str(plan.get("mode_key") or request.get("mode") or request.get("mode_key") or "").strip()
    display_name = str(summary.get("display_name") or "").strip()
    if not display_name and mode_key:
        mode_label = create_mode_label(mode_key)
        product = str(summary.get("product") or request.get("product") or "").strip()
        display_name = f"{product}{mode_label}" if product and mode_label != "未指定模式" else mode_label
    template_name = str(request.get("project_template_name") or "").strip()
    template_key = str(request.get("template_key") or "").strip()
    template_path = str(
        summary.get("template_catalog_path")
        or request.get("template_catalog_path")
        or request.get("template_catalog")
        or request.get("template_catalog_json")
        or ""
    ).strip()
    items = []
    if display_name:
        items.append({"label": "固定模式", "value": display_name})
    if template_name or template_key:
        items.append({"label": "基础模板", "value": template_name or template_key})
    if template_path:
        items.append({"label": "模板文件", "value": template_path})
    return items


def _project_task_action_text(
    runs_dir: Path,
    payload: dict[str, Any],
    result: dict[str, Any],
    artifact: dict[str, Any],
) -> str:
    action_types: list[str] = []
    project_payload = artifact if artifact else {}
    if not _project_action_candidates(project_payload):
        project_payload = _read_first_json(runs_dir, _project_update_path_candidates(payload, result, artifact))
    for row in _project_action_candidates(project_payload):
        if isinstance(row, dict):
            action_type = str(row.get("action_type") or row.get("operation") or "").strip()
            if action_type:
                action_types.append(project_action_label(action_type))
    direct_action = str(project_payload.get("action_type") or result.get("action_type") or "").strip()
    if direct_action:
        action_types.append(project_action_label(direct_action))
    output = []
    for action in action_types:
        if action and action not in output:
            output.append(action)
    return "；".join(output)


def _create_plan_path_candidates(payload: dict[str, Any], result: dict[str, Any], artifact: dict[str, Any]) -> list[Any]:
    request = _dict(payload.get("request"))
    raw = _dict(artifact.get("raw"))
    return [
        request.get("plan_path"),
        request.get("path"),
        result.get("plan_path"),
        result.get("artifact_path"),
        raw.get("plan_path"),
    ]


def _project_update_path_candidates(payload: dict[str, Any], result: dict[str, Any], artifact: dict[str, Any]) -> list[Any]:
    request = _dict(payload.get("request"))
    return [
        request.get("project_update_path"),
        request.get("path"),
        request.get("config"),
        result.get("project_update_path"),
        result.get("execute_artifact_path"),
        artifact.get("project_update_path"),
    ]


def _read_first_json(runs_dir: Path, candidates: list[Any]) -> dict[str, Any]:
    for candidate in candidates:
        text = str(candidate or "").strip()
        if not text:
            continue
        payload = read_json(_resolve_project_path(runs_dir, text))
        if payload:
            return payload
    return {}


def _resolve_project_path(runs_dir: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    root = runs_dir.parent.parent
    if value.startswith("data/runs/") or value.startswith("configs/"):
        return root / value
    return runs_dir / value


def _looks_like_create_plan(value: dict[str, Any]) -> bool:
    return bool(value.get("create_request") or value.get("create_strategy_plan") or value.get("mode_key"))


def _project_action_candidates(value: dict[str, Any]) -> list[Any]:
    if isinstance(value.get("actions"), list):
        return value["actions"]
    project_update = _dict(value.get("project_update"))
    if isinstance(project_update.get("actions"), list):
        return project_update["actions"]
    if isinstance(value.get("results"), list):
        return value["results"]
    return []


def _context_items_to_text(items: list[dict[str, Any]]) -> str:
    visible_items = [item for item in items if item.get("label") != "模板文件" and str(item.get("value") or "").strip()]
    return "；".join(f"{item['label']}：{item['value']}" for item in visible_items)


def _summary_context_phrase(context: str) -> str:
    first = context.split("；", 1)[0].strip()
    return first.replace("：", " ") if first else ""


def _task_detail_sections(
    result: dict[str, Any],
    artifact: dict[str, Any],
    account_names: dict[str, str],
) -> list[dict[str, Any]]:
    workflow = str(artifact.get("workflow") or result.get("workflow") or "").strip()
    if workflow == "create_live_execute_once":
        ledger_section = _existing_plan_ledger_section(_existing_plan_ledger(result) or _existing_plan_ledger(artifact), account_names)
        return [ledger_section] if ledger_section else []
    if not artifact:
        return []
    if workflow == "project_update_execute":
        rows = [_project_execute_row(row, account_names) for row in _list(artifact.get("results")) if isinstance(row, dict)]
        return [
            {
                "title": "项目执行结果",
                "table": {
                    "columns": ["账户 ID", "账户名", "动作", "项目 ID", "项目名", "项目数", "状态"],
                    "rows": rows,
                },
            }
        ] if rows else []
    if workflow == "project_realtime_filter_config":
        matched_rows = [_matched_project_row(row, account_names) for row in _list(artifact.get("matched_projects")) if isinstance(row, dict)]
        action_rows = [
            _project_config_action_row(row, account_names)
            for row in _list(_dict(artifact.get("project_update")).get("actions"))
            if isinstance(row, dict)
        ]
        sections = []
        if action_rows:
            sections.append(
                {
                    "title": "将写入的项目动作",
                    "table": {
                        "columns": ["账户 ID", "账户名", "动作", "项目 ID", "项目名", "目标值"],
                        "rows": action_rows,
                    },
                }
            )
        if matched_rows:
            sections.append(
                {
                    "title": "命中项目",
                    "table": {
                        "columns": ["账户 ID", "账户名", "项目 ID", "项目名", "消耗", "筛选原因"],
                        "rows": matched_rows,
                    },
                }
            )
        return sections
    return []


def _project_execute_row(row: dict[str, Any], account_names: dict[str, str]) -> dict[str, Any]:
    advertiser_id = str(row.get("advertiser_id") or "").strip()
    action = str(row.get("action_type") or row.get("operation") or "").strip()
    return {
        "账户 ID": advertiser_id,
        "账户名": account_name_for(account_names, advertiser_id),
        "动作": project_action_label(action),
        "项目 ID": str(row.get("project_id") or ""),
        "项目名": str(row.get("project_name") or row.get("name") or ""),
        "项目数": row.get("project_count") or "",
        "状态": status_label(row.get("status")),
    }


def _project_config_action_row(row: dict[str, Any], account_names: dict[str, str]) -> dict[str, Any]:
    advertiser_id = str(row.get("advertiser_id") or "").strip()
    action = str(row.get("action_type") or "").strip()
    return {
        "账户 ID": advertiser_id,
        "账户名": account_name_for(account_names, advertiser_id),
        "动作": project_action_label(action),
        "项目 ID": str(row.get("project_id") or ""),
        "项目名": str(row.get("project_name") or row.get("name") or ""),
        "目标值": _project_target(row, action),
    }


def _matched_project_row(row: dict[str, Any], account_names: dict[str, str]) -> dict[str, Any]:
    advertiser_id = str(row.get("advertiser_id") or "").strip()
    metrics = _dict(row.get("metrics"))
    return {
        "账户 ID": advertiser_id,
        "账户名": account_name_for(account_names, advertiser_id),
        "项目 ID": str(row.get("project_id") or ""),
        "项目名": str(row.get("project_name") or row.get("name") or ""),
        "消耗": metrics.get("stat_cost") if metrics else "",
        "筛选原因": "；".join(str(item) for item in _list(row.get("match_reasons")) if str(item or "").strip()),
    }


def _project_target(row: dict[str, Any], action: str) -> str:
    if action == "status_update":
        return {"ENABLE": "开启", "DISABLE": "关闭"}.get(str(row.get("opt_status") or ""), str(row.get("opt_status") or ""))
    if action == "budget_update":
        return f"预算 {row.get('budget') or row.get('adjustment_ratio') or ''}".strip()
    if action == "bid_update":
        return f"出价 {row.get('cpa_bid') or row.get('adjustment_ratio') or ''}".strip()
    if action == "roi_coeff_update":
        return f"ROI 系数 {row.get('roi_goal') or ''}".strip()
    return ""


def _artifact_account_ids(artifact: dict[str, Any]) -> list[str]:
    rows = []
    for key in ("results", "matched_projects", "actions"):
        rows.extend(_list(artifact.get(key)))
    output: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        advertiser_id = str(row.get("advertiser_id") or "").strip()
        if advertiser_id and advertiser_id not in output:
            output.append(advertiser_id)
    return output


def _existing_plan_ledger(value: dict[str, Any]) -> dict[str, Any]:
    ledger = value.get("existing_plan_ledger") if isinstance(value, dict) else None
    return ledger if isinstance(ledger, dict) else {}


def _has_existing_plan_block(result: dict[str, Any]) -> bool:
    for item in result.get("blocking_reasons") or []:
        if "existing active project/unit provider IDs" in str(item):
            return True
    return bool(_existing_plan_ledger(result))


def _existing_plan_counts_text(ledger: dict[str, Any]) -> str:
    by_entity_type = _dict(ledger.get("by_entity_type"))
    pieces = []
    project_count = _to_int(by_entity_type.get("project"))
    promotion_count = _to_int(by_entity_type.get("promotion"))
    material_bind_count = _to_int(by_entity_type.get("material_bind"))
    if project_count:
        pieces.append(f"项目 {project_count} 个")
    if promotion_count:
        pieces.append(f"单元 {promotion_count} 个")
    if material_bind_count:
        pieces.append(f"素材绑定 {material_bind_count} 条")
    if pieces:
        return "、".join(pieces)
    total = _to_int(ledger.get("count"))
    return f"记录 {total} 条" if total else ""


def _existing_plan_ledger_section(ledger: dict[str, Any], account_names: dict[str, str]) -> dict[str, Any] | None:
    samples = [row for row in _list(ledger.get("samples")) if isinstance(row, dict)]
    if not samples:
        return None
    rows = []
    for row in samples:
        advertiser_id = _ledger_sample_account_id(row)
        rows.append(
            {
                "账户 ID": advertiser_id,
                "账户名": account_name_for(account_names, advertiser_id),
                "对象": _ledger_entity_label(row.get("entity_type")),
                "本地键": str(row.get("local_key") or ""),
                "已创建 ID": str(row.get("provider_id") or ""),
            }
        )
    return {
        "title": "已存在创建记录",
        "table": {"columns": ["账户 ID", "账户名", "对象", "本地键", "已创建 ID"], "rows": rows},
    }


def _ledger_sample_account_id(row: dict[str, Any]) -> str:
    advertiser_id = str(row.get("advertiser_id") or "").strip()
    if advertiser_id:
        return advertiser_id
    local_key = str(row.get("local_key") or "").strip()
    if "-" in local_key:
        return local_key.split("-", 1)[0]
    return ""


def _ledger_entity_label(value: Any) -> str:
    return {"project": "项目", "promotion": "单元", "material_bind": "素材绑定"}.get(str(value or ""), str(value or ""))


def _split_ids(value: Any) -> list[str]:
    if isinstance(value, list):
        raw_items = value
    else:
        raw_items = str(value or "").replace("\n", ",").split(",")
    output: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        output.append(text)
    return output


def _site_pair_count(request: dict[str, Any]) -> int:
    pairs = request.get("site_pairs") if isinstance(request.get("site_pairs"), list) else []
    if pairs:
        return sum(
            1
            for row in pairs
            if isinstance(row, dict) and str(row.get("advertiser_id") or "").strip() and str(row.get("site_id") or "").strip()
        )
    text = str(request.get("site_pairs_text") or "").strip()
    if not text:
        return len(_split_ids(request.get("site_ids")))
    count = 0
    seen: set[tuple[str, str]] = set()
    for line in text.splitlines():
        parts = [part.strip() for part in line.replace("\t", ",").split(",") if part.strip()]
        if len(parts) < 2:
            continue
        pair = (parts[0], parts[1])
        if pair in seen:
            continue
        seen.add(pair)
        count += 1
    return count


def _site_status_label(value: Any) -> str:
    return {
        "published": "发布",
        "unpublished": "下线",
        "delete": "删除",
        "undeleted": "恢复删除",
    }.get(str(value or "").strip(), str(value or "").strip())


def _first_present_bool(*sources: dict[str, Any], key: str) -> bool | None:
    for source in sources:
        if key not in source:
            continue
        value = source.get(key)
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in {"1", "true", "yes", "y", "是"}:
            return True
        if text in {"0", "false", "no", "n", "否"}:
            return False
    return None


def _to_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _business_blocking_reasons(result: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    for item in result.get("blocking_reasons") or []:
        text = str(item or "").strip()
        if text:
            reasons.append(_localized_blocking_reason(text, result))
    summary = result.get("summary") if isinstance(result.get("summary"), dict) else {}
    for item in summary.get("blocking_reasons") or []:
        text = str(item or "").strip()
        if text:
            reasons.append(_localized_blocking_reason(text, result))
    return list(dict.fromkeys(reasons))


def _business_warnings(result: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    readiness = result.get("local_config_readiness") if isinstance(result.get("local_config_readiness"), dict) else {}
    plain_language = str(readiness.get("plain_language") or "").strip()
    if plain_language:
        warnings.append(plain_language)
    for item in result.get("warnings") or []:
        text = str(item or "").strip()
        if text:
            warnings.append(text)
    if _has_existing_plan_block(result) and _to_int(result.get("external_api_calls")) == 0:
        warnings.append("这次没有发起外部创建请求，没有新增项目或单元。")
    return list(dict.fromkeys(warnings))


def _localized_blocking_reason(text: str, result: dict[str, Any]) -> str:
    if "existing active project/unit provider IDs" not in text:
        return text
    counts_text = _existing_plan_counts_text(_existing_plan_ledger(result))
    counts_part = f"（{counts_text}）" if counts_text else ""
    return (
        f"这个创建计划已有创建记录{counts_part}，系统未发起外部创建，已阻止重复执行。"
        "要新建一批，请重新生成计划。"
    )
