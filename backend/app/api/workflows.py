from __future__ import annotations

from fastapi import APIRouter
from fastapi import Request

from backend.app.services.artifacts import find_latest_artifact
from backend.app.services.artifacts import read_json
from backend.app.services.account_names import load_account_name_map
from backend.app.services.summary_builder import build_json_summary

router = APIRouter()

WORKFLOW_CATALOG = [
    {
        "value": "site_status_update",
        "label": "落地页状态更新",
        "description": "查看删除、开启、关闭等落地页状态更新结果。",
    },
    {
        "value": "site_template_foundation",
        "label": "模板建站",
        "description": "查看从模板新建或修复落地页并写入微信小游戏路径的执行结果。",
    },
    {
        "value": "site_handsel",
        "label": "落地页转赠结果",
        "description": "查看落地页转赠到各账户后的成功、失败和新落地页 ID。",
    },
    {
        "value": "account_remark_update",
        "label": "真实修改账户备注",
        "description": "查看账户备注真实修改固定脚本的执行结果；未通过安全配置时不会修改账户。",
    },
    {
        "value": "account_remark_config_generate",
        "label": "账户备注配置生成",
        "description": "查看账户备注 JSON 配置生成任务结果。",
    },
    {
        "value": "delivery_patrol",
        "label": "投放巡检",
        "description": "查看最近一次本地投放巡检结果。",
    },
    {
        "value": "product_automation_job_material_daily_sync",
        "label": "素材明细同步",
        "description": "查看产品级每日素材明细同步结果。",
    },
    {
        "value": "product_automation_job_daily_report_sync",
        "label": "每日报表同步",
        "description": "查看产品级每日账户报表同步结果。",
    },
    {
        "value": "product_automation_job_operation_log_sync",
        "label": "操作日志同步",
        "description": "查看产品级操作日志同步结果。",
    },
    {
        "value": "product_automation_job_source_material_rollup",
        "label": "源素材表现汇总",
        "description": "查看源素材表现汇总重建结果。",
    },
    {
        "value": "suggestions_refresh",
        "label": "同步数据并重算建议",
        "description": "查看只读同步、巡检和建议重算链路结果。",
    },
    {
        "value": "gravity_api_probe",
        "label": "引力素材库只读探测",
        "description": "查看引力素材库本地鉴权探测结果。",
    },
    {
        "value": "gravity_token_refresh",
        "label": "引力 Token 获取/刷新",
        "description": "查看引力 Token 获取/刷新结果，不展示 token 明文。",
    },
    {
        "value": "gravity_material_sync",
        "label": "更新引力素材",
        "description": "查看引力素材名称、归属、MD5、状态和表现数据写入本地素材库的结果。",
    },
    {
        "value": "gravity_material_qualification",
        "label": "检查可用素材",
        "description": "查看引力素材是否可铺货、是否缺 MD5、是否已铺货到目标账户的本地结果。",
    },
    {
        "value": "project_update_execute",
        "label": "项目管理执行",
        "description": "查看项目删除、暂停、预算、出价等固定脚本执行结果。",
    },
    {
        "value": "create_mode",
        "label": "创建计划",
        "description": "查看最近一次生成的创建计划 JSON 和中文摘要。",
    },
    {
        "value": "create_live_execute_once",
        "label": "创建执行",
        "description": "查看创建项目和单元的固定脚本执行结果。",
    },
    {
        "value": "frontend_operation_log",
        "label": "前端操作日志",
        "description": "查看 React 触发过的动作、关联任务和复盘信息。",
    },
]


@router.get("/workflows/catalog")
def workflow_catalog() -> dict:
    rows = [
        {"结果类型": item["value"], "名称": item["label"], "说明": item["description"]}
        for item in WORKFLOW_CATALOG
    ]
    return {
        "summary": {
            "title": "结果类型目录",
            "status": "loaded",
            "risk_level": "low",
            "execution_enabled": False,
            "items": [{"label": "结果类型数", "value": len(rows)}],
            "warnings": [],
            "blocking_reasons": [],
        },
        "table": {"columns": ["结果类型", "名称", "说明"], "rows": rows},
        "artifact_path": "",
        "raw": {"workflows": WORKFLOW_CATALOG},
    }


@router.get("/workflows/latest")
def latest_workflow(request: Request, workflow: str) -> dict:
    settings = request.app.state.settings
    catalog_item = _workflow_catalog_item(workflow)
    if catalog_item is None:
        return _workflow_empty_result(workflow, workflow, "未知结果类型，请从结果类型目录中选择。", status="blocked")
    path = find_latest_artifact(settings.runs_dir, workflow)
    if path is None:
        return _workflow_empty_result(
            workflow,
            catalog_item["label"],
            f"还没有找到{catalog_item['label']}的执行结果，请先完成对应任务。",
        )
    payload = read_json(path)
    account_names = load_account_name_map(settings.configs_dir)
    return build_json_summary(f"{catalog_item['label']} 最新结果", payload, artifact_path=str(path), account_names=account_names)


def _workflow_catalog_item(workflow: str) -> dict[str, str] | None:
    for item in WORKFLOW_CATALOG:
        if item["value"] == workflow:
            return item
    return None


def _workflow_empty_result(
    workflow: str,
    label: str,
    message: str,
    *,
    status: str = "empty",
) -> dict:
    return {
        "summary": {
            "title": f"{label}暂无结果" if status == "empty" else "结果类型不可用",
            "status": status,
            "risk_level": "medium" if status == "blocked" else "low",
            "execution_enabled": False,
            "items": [{"label": "结果类型", "value": workflow}],
            "warnings": [message] if status == "empty" else [],
            "blocking_reasons": [message] if status == "blocked" else [],
        },
        "table": {
            "columns": ["下一步", "说明"],
            "rows": [{"下一步": "先执行对应流程", "说明": message}],
        },
        "artifact_path": "",
        "raw": {"workflow": workflow, "label": label, "message": message},
    }
