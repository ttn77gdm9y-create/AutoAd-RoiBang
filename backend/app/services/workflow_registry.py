from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class WorkflowParameter:
    name: str
    label: str
    default: str = ""
    required: bool = False
    description: str = ""


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
    label="产品 Key",
    default="",
    required=False,
    description="为空时按已启用产品配置运行。",
)
YESTERDAY_PARAM = WorkflowParameter(
    name="target_date",
    label="目标日期",
    default="yesterday",
    required=False,
    description="today / yesterday / YYYY-MM-DD。",
)
TODAY_PARAM = WorkflowParameter(
    name="target_date",
    label="目标日期",
    default="today",
    required=False,
    description="today / yesterday / YYYY-MM-DD。",
)
GRAVITY_AUTH_FILE_PARAM = WorkflowParameter(
    name="auth_file",
    label="引力 Token 文件",
    default="data/gravity_token.json",
    required=False,
    description="只读取本地鉴权文件，不上传素材。",
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
        parameters=(GRAVITY_AUTH_FILE_PARAM,),
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


def workflow_catalog_result() -> dict[str, Any]:
    rows = [
        {
            "工作流 ID": item.workflow_id,
            "任务名称": item.name,
            "分类": item.category,
            "风险": _risk_label(item.risk_level),
            "真实投放动作": "是" if item.true_action else "否",
            "AI 自动运行": "允许" if item.ai_auto_run and not item.true_action else "不允许",
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
            "columns": ["工作流 ID", "任务名称", "分类", "风险", "真实投放动作", "AI 自动运行", "说明"],
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
                        }
                        for parameter in item.parameters
                    ],
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


def normalize_workflow_request(definition: WorkflowDefinition, request: dict[str, Any]) -> tuple[dict[str, str], list[str]]:
    request = request if isinstance(request, dict) else {}
    allowed = {parameter.name for parameter in definition.parameters}
    unknown = sorted(str(key) for key in request if str(key) not in allowed)
    blocking_reasons = [f"未登记参数：{', '.join(unknown)}"] if unknown else []
    normalized: dict[str, str] = {}
    for parameter in definition.parameters:
        value = request.get(parameter.name, parameter.default)
        text = str(value or "").strip()
        if parameter.required and not text:
            blocking_reasons.append(f"请填写{parameter.label}")
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
        ]
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
                    {"label": parameter.label, "value": normalized_request.get(parameter.name, "") or "全部/默认"}
                    for parameter in definition.parameters
                ],
            ],
            "warnings": [] if can_run else ["该任务暂不能启动，请先处理阻断原因。"],
            "blocking_reasons": blocking_reasons,
        },
        "table": {"columns": ["任务名称", "分类", "参数", "真实投放动作", "启动方式"], "rows": rows},
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
        value = request.get(parameter.name, "") or "全部/默认"
        pieces.append(f"{parameter.label}：{value}")
    return "；".join(pieces)


def _risk_label(value: str) -> str:
    return {"low": "低", "medium": "中", "high": "高"}.get(value, value)


def _python() -> str:
    return sys.executable or "python3"
