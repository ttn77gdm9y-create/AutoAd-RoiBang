from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import datetime
from datetime import timezone
from pathlib import Path
from typing import Any

from backend.app.services.ui_labels import status_label


@dataclass(frozen=True)
class WorkflowParameter:
    name: str
    label: str
    default: str = ""
    required: bool = False
    description: str = ""
    control: str = "text"
    options: tuple[dict[str, str], ...] = ()


@dataclass(frozen=True)
class WorkflowDefinition:
    workflow_id: str
    name: str
    category: str
    description: str
    operation_type: str
    latest_workflow: str
    run_kind: str
    parameters: tuple[WorkflowParameter, ...]
    ai_auto_run: bool = True
    true_action: bool = False
    risk_level: str = "low"


PRODUCT_KEY_PARAM = WorkflowParameter(
    name="product_key",
    label="产品",
    default="",
    required=False,
    description="为空时按全部启用产品运行。",
    control="product_select",
)
YESTERDAY_PARAM = WorkflowParameter(
    name="target_date",
    label="目标日期",
    default="yesterday",
    required=False,
    description="today / yesterday / YYYY-MM-DD。",
    control="date_select",
)
TODAY_PARAM = WorkflowParameter(
    name="target_date",
    label="目标日期",
    default="today",
    required=False,
    description="today / yesterday / YYYY-MM-DD。",
    control="date_select",
)
GRAVITY_AUTH_FILE_PARAM = WorkflowParameter(
    name="auth_file",
    label="引力 Token 文件",
    default="data/gravity_token.json",
    required=False,
    description="只读取本地鉴权文件；结果中不会展示 token 明文。",
)
GRAVITY_USERNAME_ENV_PARAM = WorkflowParameter(
    name="username_env",
    label="账号环境变量",
    default="GRAVITY_USERNAME",
    required=False,
    description="只传环境变量名称，不在页面填写账号。",
)
GRAVITY_PASSWORD_ENV_PARAM = WorkflowParameter(
    name="password_env",
    label="密码环境变量",
    default="GRAVITY_PASSWORD",
    required=False,
    description="只传环境变量名称，不在页面填写密码。",
)
GRAVITY_PROBE_SCOPE_PARAM = WorkflowParameter(
    name="probe_scope",
    label="探测范围",
    default="local_contract",
    required=False,
    description="本地核验不访问外部接口；外部只读探测只访问查询接口，不上传素材。",
    control="select",
    options=(
        {"label": "本地鉴权与文档字段核验", "value": "local_contract"},
        {"label": "外部只读接口探测", "value": "readonly_api"},
    ),
)
GRAVITY_SAMPLE_LIMIT_PARAM = WorkflowParameter(
    name="sample_limit",
    label="样本数量",
    default="3",
    required=False,
    description="只读取少量样本用于字段核验，不保存素材资料到本地。",
    control="select",
    options=(
        {"label": "1 条", "value": "1"},
        {"label": "3 条", "value": "3"},
        {"label": "5 条", "value": "5"},
    ),
)
GRAVITY_SYNC_PRODUCT_PARAM = WorkflowParameter(
    name="product",
    label="产品",
    default="",
    required=False,
    description="为空时同步全部已绑定产品。",
    control="product_name_select",
)
GRAVITY_SYNC_PAGE_SIZE_PARAM = WorkflowParameter(
    name="page_size",
    label="每页素材数",
    default="100",
    required=False,
    description="分页读取引力素材列表；不上传素材。",
    control="select",
    options=(
        {"label": "50", "value": "50"},
        {"label": "100", "value": "100"},
        {"label": "200", "value": "200"},
    ),
)
GRAVITY_SYNC_MAX_PAGES_PARAM = WorkflowParameter(
    name="max_pages",
    label="最多页数",
    default="20",
    required=False,
    description="限制单个绑定最多读取页数，避免一次同步过大。",
    control="select",
    options=(
        {"label": "10", "value": "10"},
        {"label": "20", "value": "20"},
        {"label": "50", "value": "50"},
    ),
)


WORKFLOW_CATALOG: tuple[WorkflowDefinition, ...] = (
    WorkflowDefinition(
        workflow_id="material_daily_sync",
        name="素材明细同步",
        category="数据同步",
        description="按产品配置同步每日素材明细，只读取外部报表数据，不改投放。",
        operation_type="material_daily_sync",
        latest_workflow="product_automation_job_material_daily_sync",
        run_kind="product_automation_material_daily_sync",
        parameters=(PRODUCT_KEY_PARAM, YESTERDAY_PARAM),
    ),
    WorkflowDefinition(
        workflow_id="daily_report_sync",
        name="每日报表同步",
        category="数据同步",
        description="按产品配置同步每日账户报表，只读取外部报表数据，不改投放。",
        operation_type="daily_report_sync",
        latest_workflow="product_automation_job_daily_report_sync",
        run_kind="product_automation_daily_report_sync",
        parameters=(PRODUCT_KEY_PARAM, YESTERDAY_PARAM),
    ),
    WorkflowDefinition(
        workflow_id="operation_log_sync",
        name="操作日志同步",
        category="数据同步",
        description="按产品配置同步操作日志，只读取外部日志数据，不改投放。",
        operation_type="operation_log_sync",
        latest_workflow="product_automation_job_operation_log_sync",
        run_kind="product_automation_operation_log_sync",
        parameters=(PRODUCT_KEY_PARAM, YESTERDAY_PARAM),
    ),
    WorkflowDefinition(
        workflow_id="source_material_rollup",
        name="源素材表现汇总",
        category="本地重算",
        description="基于已同步数据重建源素材表现汇总，只写本地汇总结果。",
        operation_type="source_material_rollup",
        latest_workflow="product_automation_job_source_material_rollup",
        run_kind="product_automation_source_material_rollup",
        parameters=(PRODUCT_KEY_PARAM, YESTERDAY_PARAM),
    ),
    WorkflowDefinition(
        workflow_id="suggestions_refresh",
        name="同步数据并重算建议",
        category="建议刷新",
        description="串联只读同步、本地汇总、巡检和建议重算，不执行创建、项目管理或素材推送。",
        operation_type="suggestions_refresh",
        latest_workflow="suggestions_refresh",
        run_kind="suggestions_refresh",
        parameters=(PRODUCT_KEY_PARAM, TODAY_PARAM),
        risk_level="medium",
    ),
    WorkflowDefinition(
        workflow_id="gravity_api_probe",
        name="引力素材库只读探测",
        category="引力素材库",
        description="检查引力素材库本地鉴权文件和字段完整性，不上传素材、不创建广告。",
        operation_type="gravity_api_probe",
        latest_workflow="gravity_api_probe",
        run_kind="gravity_api_probe",
        parameters=(GRAVITY_AUTH_FILE_PARAM, GRAVITY_PROBE_SCOPE_PARAM, GRAVITY_SAMPLE_LIMIT_PARAM),
    ),
    WorkflowDefinition(
        workflow_id="gravity_token_refresh",
        name="引力 Token 获取/刷新",
        category="引力素材库",
        description="通过固定 headless 浏览器脚本获取引力接口 Token，只写本地鉴权文件，不上传素材、不创建广告。",
        operation_type="gravity_token_refresh",
        latest_workflow="gravity_token_refresh",
        run_kind="gravity_token_refresh",
        parameters=(GRAVITY_AUTH_FILE_PARAM, GRAVITY_USERNAME_ENV_PARAM, GRAVITY_PASSWORD_ENV_PARAM),
        ai_auto_run=False,
        risk_level="medium",
    ),
    WorkflowDefinition(
        workflow_id="gravity_material_sync",
        name="更新引力素材",
        category="引力素材库",
        description="按产品-专辑绑定读取引力素材名称、归属、MD5、状态和表现数据，保存到本地素材库；不下载素材文件、不上传素材、不创建广告。",
        operation_type="gravity_material_sync",
        latest_workflow="gravity_material_sync",
        run_kind="gravity_material_sync",
        parameters=(GRAVITY_SYNC_PRODUCT_PARAM, GRAVITY_AUTH_FILE_PARAM, GRAVITY_SYNC_PAGE_SIZE_PARAM, GRAVITY_SYNC_MAX_PAGES_PARAM),
    ),
    WorkflowDefinition(
        workflow_id="gravity_material_qualification",
        name="检查可用素材",
        category="引力素材库",
        description="基于本地引力素材计算可用于后续、不可用、缺 MD5、已上传等资格汇总，不上传素材、不创建广告。",
        operation_type="gravity_material_qualification",
        latest_workflow="gravity_material_qualification",
        run_kind="gravity_material_qualification",
        parameters=(GRAVITY_SYNC_PRODUCT_PARAM,),
    ),
)


def list_workflow_definitions() -> list[WorkflowDefinition]:
    return list(WORKFLOW_CATALOG)


def get_workflow_definition(workflow_id: str) -> WorkflowDefinition | None:
    normalized = str(workflow_id or "").strip()
    for definition in WORKFLOW_CATALOG:
        if definition.workflow_id == normalized:
            return definition
    return None


def workflow_catalog_result(*, project_root: str | Path | None = None) -> dict[str, Any]:
    latest_statuses = _latest_statuses(project_root)
    rows = [
        {
            "工作流 ID": item.workflow_id,
            "任务名称": item.name,
            "分类": item.category,
            "风险": _risk_label(item.risk_level),
            "真实投放动作": "是" if item.true_action else "否",
            "AI 自动运行": "允许" if item.ai_auto_run and not item.true_action else "不允许",
            "最近状态": latest_statuses.get(item.workflow_id, {}).get("status_label", "未运行"),
            "最近运行时间": latest_statuses.get(item.workflow_id, {}).get("run_at_label", ""),
            "最近结果": latest_statuses.get(item.workflow_id, {}).get("summary", ""),
            "最近结果文件": latest_statuses.get(item.workflow_id, {}).get("artifact_path", ""),
            "说明": item.description,
        }
        for item in WORKFLOW_CATALOG
    ]
    return {
        "summary": {
            "title": "自动化工作台任务菜单",
            "status": "loaded",
            "risk_level": "low",
            "execution_enabled": False,
            "items": [
                {"label": "可运行任务", "value": len(rows)},
                {"label": "真实投放任务", "value": sum(1 for item in WORKFLOW_CATALOG if item.true_action)},
            ],
            "warnings": [],
            "blocking_reasons": [],
        },
        "table": {
            "columns": [
                "工作流 ID",
                "任务名称",
                "分类",
                "风险",
                "真实投放动作",
                "AI 自动运行",
                "最近状态",
                "最近运行时间",
                "最近结果",
                "最近结果文件",
                "说明",
            ],
            "rows": rows,
        },
        "artifact_path": "",
        "raw": {
            "workflows": [
                {
                    "workflow_id": item.workflow_id,
                    "name": item.name,
                    "category": item.category,
                    "description": item.description,
                    "operation_type": item.operation_type,
                    "latest_workflow": item.latest_workflow,
                    "risk_level": item.risk_level,
                    "true_action": item.true_action,
                    "ai_auto_run": item.ai_auto_run,
                    "parameters": [
                        {
                            "name": parameter.name,
                            "label": parameter.label,
                            "default": parameter.default,
                            "required": parameter.required,
                            "description": parameter.description,
                            "control": parameter.control,
                            "options": list(parameter.options),
                        }
                        for parameter in item.parameters
                    ],
                    "latest_status": latest_statuses.get(item.workflow_id, {}),
                }
                for item in WORKFLOW_CATALOG
            ],
            "guardrails": [
                "只登记只读同步、本地重算和预览类任务。",
                "不登记素材上传、创建广告、项目管理真实执行、预算或出价修改任务。",
                "前端和 AI 只能传登记过的参数，不能传任意命令。",
            ],
        },
    }


def _latest_statuses(project_root: str | Path | None) -> dict[str, dict[str, Any]]:
    if project_root is None:
        return {}
    root = Path(project_root)
    runs_dir = root / "data" / "runs"
    statuses: dict[str, dict[str, Any]] = {}
    for definition in WORKFLOW_CATALOG:
        candidates: list[dict[str, Any]] = []
        candidates.extend(_scheduled_status_candidates(root, runs_dir, definition))
        candidates.extend(_frontend_task_status_candidates(root, runs_dir, definition))
        if candidates:
            statuses[definition.workflow_id] = max(candidates, key=lambda item: str(item.get("sort_key") or ""))
    return statuses


def _scheduled_status_candidates(root: Path, runs_dir: Path, definition: WorkflowDefinition) -> list[dict[str, Any]]:
    artifact_dir = runs_dir / definition.latest_workflow
    candidates = []
    for path in artifact_dir.glob("*.json"):
        payload = _read_json(path)
        if not payload:
            continue
        candidates.append(_status_from_payload(root, path, payload, source="定时任务", sort_key=_sort_key_from_artifact(path)))
    return candidates


def _frontend_task_status_candidates(root: Path, runs_dir: Path, definition: WorkflowDefinition) -> list[dict[str, Any]]:
    task_dir = runs_dir / "frontend_tasks"
    candidates = []
    for path in task_dir.glob("frontend-*.json"):
        payload = _read_json(path)
        if str(payload.get("operation_type") or "") != definition.operation_type:
            continue
        result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
        status_payload = result or payload
        candidates.append(
            _status_from_payload(
                root,
                path,
                status_payload,
                source="手动补跑",
                task_id=str(payload.get("task_id") or path.stem),
                sort_key=str(payload.get("updated_at") or payload.get("created_at") or _sort_key_from_artifact(path)),
            )
        )
    return candidates


def _status_from_payload(
    root: Path,
    path: Path,
    payload: dict[str, Any],
    *,
    source: str,
    sort_key: str,
    task_id: str = "",
) -> dict[str, Any]:
    status = str(payload.get("status") or ("completed" if payload.get("ok") is True else "unknown"))
    return {
        "status": status,
        "status_label": _latest_status_label(payload, status),
        "run_at": _run_at_from_path(path),
        "run_at_label": _run_at_label(path),
        "source": source,
        "task_id": task_id,
        "artifact_path": _display_path(root, path),
        "summary": _latest_status_summary(payload),
        "sort_key": sort_key,
    }


def _latest_status_summary(payload: dict[str, Any]) -> str:
    summary = _dict(payload.get("summary"))
    result = _first_result(payload)
    parsed_summary = _dict(_dict(result.get("parsed_stdout")).get("summary"))
    parts: list[str] = []
    if _text(payload.get("workflow")) == "gravity_api_probe":
        token_status = _text(summary.get("token_status_label"))
        if token_status:
            parts.append(f"Token {token_status}")
        elif _text(summary.get("auth_field_status")):
            parts.append(f"鉴权字段 {summary.get('auth_field_status')}")
        blocking_reasons = payload.get("blocking_reasons")
        if isinstance(blocking_reasons, list) and blocking_reasons:
            first_reason = _text(blocking_reasons[0])
            if first_reason:
                parts.append(f"阻塞原因 {first_reason}")
    if _text(payload.get("workflow")) == "gravity_token_refresh":
        blocking_reasons = payload.get("blocking_reasons")
        if isinstance(blocking_reasons, list) and any("缺少环境变量" in _text(reason) for reason in blocking_reasons):
            return "缺少引力登录环境变量，未访问引力，未生成 Token，未执行业务动作"
        token_status = _text(summary.get("token_status_label"))
        if token_status:
            parts.append(f"Token {token_status}")
        auth_file = _text(summary.get("auth_file"))
        if auth_file:
            parts.append(f"文件 {auth_file}")
        if isinstance(blocking_reasons, list) and blocking_reasons:
            first_reason = _text(blocking_reasons[0])
            if first_reason:
                parts.append(f"阻塞原因 {first_reason}")
    product = _text(result.get("product")) or _text(summary.get("product"))
    if product:
        parts.append(product)
    target_date = _text(summary.get("target_date")) or _text(parsed_summary.get("target_date"))
    if not target_date:
        date_range = _dict(parsed_summary.get("date_range"))
        start_date = _text(date_range.get("start"))
        end_date = _text(date_range.get("end"))
        if start_date and end_date and start_date == end_date:
            target_date = start_date
    if target_date:
        parts.append(f"目标日期 {target_date}")
    parts.extend(_summary_metric_parts(parsed_summary))
    external_calls = payload.get("external_api_calls")
    if external_calls is not None:
        parts.append(f"外部只读调用 {external_calls}")
    if not parts:
        parts.append(status_label(payload.get("status")))
    return "，".join(parts)


def _latest_status_label(payload: dict[str, Any], status: str) -> str:
    if _text(payload.get("workflow")) == "gravity_token_refresh" and status == "blocked":
        blocking_reasons = payload.get("blocking_reasons")
        if isinstance(blocking_reasons, list) and any("缺少环境变量" in _text(reason) for reason in blocking_reasons):
            return "已阻塞"
    return status_label(status)


def _summary_metric_parts(summary: dict[str, Any]) -> list[str]:
    mapping = [
        ("candidate_account_count", "候选账户"),
        ("active_account_count", "活跃账户"),
        ("active_accounts_upserted", "入库账户"),
        ("material_rows_imported", "导入素材"),
        ("active_accounts_discovered", "发现账户"),
        ("detail_fetch_account_count", "明细抓取账户"),
        ("planned_request_count", "计划账户"),
        ("operation_logs_imported", "导入日志"),
        ("rows_received", "接收日志"),
        ("source_material_count", "源素材"),
        ("rollup_rows_written", "汇总行"),
        ("suggestion_count", "建议"),
        ("material_count", "素材"),
        ("eligible_count", "可用于后续"),
        ("ineligible_count", "不可用"),
        ("missing_md5_count", "缺 MD5"),
        ("uploaded_count", "已上传"),
        ("not_uploaded_count", "未上传"),
    ]
    parts = []
    for key, label in mapping:
        value = summary.get(key)
        if value is not None:
            parts.append(f"{label} {value}")
    return parts


def _first_result(payload: dict[str, Any]) -> dict[str, Any]:
    results = payload.get("results")
    if isinstance(results, list):
        for item in results:
            if isinstance(item, dict):
                return item
    return {}


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    return value if isinstance(value, dict) else {}


def _sort_key_from_artifact(path: Path) -> str:
    return path.stem


def _run_at_from_path(path: Path) -> str:
    parsed = _artifact_datetime(path)
    return parsed.isoformat(timespec="seconds") if parsed is not None else ""


def _run_at_label(path: Path) -> str:
    parsed = _artifact_datetime(path)
    return parsed.strftime("%Y-%m-%d %H:%M") if parsed is not None else ""


def _artifact_datetime(path: Path) -> datetime | None:
    try:
        parsed = datetime.strptime(path.stem, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return parsed.astimezone()


def _display_path(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()


def normalize_workflow_request(definition: WorkflowDefinition, request: dict[str, Any]) -> tuple[dict[str, str], list[str]]:
    request = request if isinstance(request, dict) else {}
    allowed = {parameter.name for parameter in definition.parameters}
    unknown = sorted(str(key) for key in request if str(key) not in allowed)
    blocking_reasons = [f"未登记参数：{', '.join(unknown)}"] if unknown else []
    normalized: dict[str, str] = {}
    for parameter in definition.parameters:
        value = request.get(parameter.name, parameter.default)
        text = str(value or "").strip()
        if not text and parameter.default and parameter.control == "select":
            text = parameter.default
        if parameter.required and not text:
            blocking_reasons.append(f"请填写{parameter.label}")
        if parameter.options and text:
            allowed_values = {str(option.get("value") or "") for option in parameter.options}
            if text not in allowed_values:
                allowed_labels = "、".join(str(option.get("label") or option.get("value") or "") for option in parameter.options)
                blocking_reasons.append(f"{parameter.label}只能选择：{allowed_labels}")
        normalized[parameter.name] = text
    return normalized, blocking_reasons


def build_workflow_command(definition: WorkflowDefinition, request: dict[str, str]) -> list[str]:
    if definition.run_kind.startswith("product_automation_"):
        job = definition.run_kind.removeprefix("product_automation_")
        command = [
            _python(),
            "scripts/run_product_automation_job.py",
            "--job",
            job,
        ]
        product_key = request.get("product_key", "")
        target_date = request.get("target_date", "") or "yesterday"
        if product_key:
            command.extend(["--product-key", product_key])
        command.extend(["--target-date", target_date])
        if job in {"material_daily_sync", "daily_report_sync", "operation_log_sync"}:
            command.append("--enable-readonly")
        return command
    if definition.run_kind == "suggestions_refresh":
        command = [
            _python(),
            "scripts/run_suggestions_refresh.py",
            "--target-date",
            request.get("target_date", "") or "today",
            "--enable-readonly",
        ]
        product_key = request.get("product_key", "")
        if product_key:
            command.extend(["--product-key", product_key])
        return command
    if definition.run_kind == "gravity_api_probe":
        return [
            _python(),
            "scripts/run_gravity_api_probe.py",
            "--auth-file",
            request.get("auth_file", "") or "data/gravity_token.json",
            "--runs-dir",
            "data/runs",
            "--probe-scope",
            request.get("probe_scope", "") or "local_contract",
            "--sample-limit",
            request.get("sample_limit", "") or "3",
        ]
    if definition.run_kind == "gravity_token_refresh":
        return [
            _python(),
            "scripts/run_gravity_token_refresh.py",
            "--auth-file",
            request.get("auth_file", "") or "data/gravity_token.json",
            "--username-env",
            request.get("username_env", "") or "GRAVITY_USERNAME",
            "--password-env",
            request.get("password_env", "") or "GRAVITY_PASSWORD",
        ]
    if definition.run_kind == "gravity_material_sync":
        command = [
            _python(),
            "scripts/run_gravity_material_sync.py",
        ]
        product = request.get("product", "")
        if product:
            command.extend(["--product", product])
        command.extend(
            [
                "--auth-file",
                request.get("auth_file", "") or "data/gravity_token.json",
                "--page-size",
                request.get("page_size", "") or "100",
                "--max-pages",
                request.get("max_pages", "") or "20",
            ]
        )
        return command
    if definition.run_kind == "gravity_material_qualification":
        command = [
            _python(),
            "scripts/run_gravity_material_qualification.py",
        ]
        product = request.get("product", "")
        if product:
            command.extend(["--product", product])
        return command
    raise RuntimeError(f"未配置工作流命令：{definition.workflow_id}")


def workflow_preview_result(
    definition: WorkflowDefinition,
    normalized_request: dict[str, str],
    *,
    command: list[str] | None,
    blocking_reasons: list[str],
) -> dict[str, Any]:
    can_run = bool(command) and not blocking_reasons and not definition.true_action
    status = "preview_ready" if can_run else "blocked"
    rows = [
        {
            "任务名称": definition.name,
            "分类": definition.category,
            "参数": _request_text(definition, normalized_request),
            "真实投放动作": "否",
            "AI 自动运行": "允许" if definition.ai_auto_run and not definition.true_action else "不允许",
            "启动方式": "固定脚本",
        }
    ]
    return {
        "ok": can_run,
        "summary": {
            "title": f"{definition.name}运行预览",
            "status": status,
            "risk_level": "medium" if blocking_reasons else definition.risk_level,
            "execution_enabled": False,
            "items": [
                {"label": "任务", "value": definition.name},
                {"label": "真实投放动作", "value": "否"},
                {"label": "AI 自动运行", "value": "允许" if definition.ai_auto_run and not definition.true_action else "不允许"},
                *[
                    {"label": parameter.label, "value": _parameter_display_value(parameter, normalized_request.get(parameter.name, ""))}
                    for parameter in definition.parameters
                ],
            ],
            "warnings": [] if can_run else ["该任务暂不能启动，请先处理阻断原因。"],
            "blocking_reasons": blocking_reasons,
        },
        "table": {"columns": ["任务名称", "分类", "参数", "真实投放动作", "AI 自动运行", "启动方式"], "rows": rows},
        "artifact_path": "",
        "raw": {
            "workflow_id": definition.workflow_id,
            "request": normalized_request,
            "command": command or [],
            "can_run": can_run,
            "true_action": definition.true_action,
            "latest_workflow": definition.latest_workflow,
        },
    }


def blocked_unknown_workflow_result(workflow_id: str) -> dict[str, Any]:
    return {
        "ok": False,
        "summary": {
            "title": "自动化工作台任务不可用",
            "status": "blocked",
            "risk_level": "high",
            "execution_enabled": False,
            "items": [{"label": "工作流 ID", "value": workflow_id}],
            "warnings": [],
            "blocking_reasons": [f"{workflow_id} 不在自动化工作台任务菜单中"],
        },
        "table": {"columns": ["问题", "说明"], "rows": [{"问题": "未登记任务", "说明": "请选择任务菜单里的固定任务。"}]},
        "artifact_path": "",
        "raw": {"workflow_id": workflow_id, "can_run": False},
    }


def _request_text(definition: WorkflowDefinition, request: dict[str, str]) -> str:
    pieces = []
    for parameter in definition.parameters:
        value = _parameter_display_value(parameter, request.get(parameter.name, ""))
        pieces.append(f"{parameter.label}：{value}")
    return "；".join(pieces)


def _parameter_display_value(parameter: WorkflowParameter, value: str) -> str:
    text = _text(value)
    if parameter.options:
        for option in parameter.options:
            if _text(option.get("value")) == text:
                return _text(option.get("label")) or text
    if parameter.control == "product_select" and not text:
        return "全部启用产品"
    if parameter.control == "date_select":
        if text == "today":
            return "今天"
        if text == "yesterday":
            return "昨天"
    return text or "全部/默认"


def _risk_label(value: str) -> str:
    return {"low": "低", "medium": "中", "high": "高"}.get(value, value)


def _python() -> str:
    return sys.executable or "python3"
