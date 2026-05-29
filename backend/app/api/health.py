from __future__ import annotations

from fastapi import APIRouter
from fastapi import Request

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/settings")
def settings(request: Request) -> dict[str, str]:
    value = request.app.state.settings
    return {
        "project_root": str(value.project_root),
        "runs_dir": str(value.runs_dir),
        "configs_dir": str(value.configs_dir),
        "streamlit_status": value.streamlit_status,
    }


@router.get("/settings/summary")
def settings_summary(request: Request) -> dict:
    payload = settings(request)
    rows = [
        {"配置项": "项目目录", "值": payload["project_root"]},
        {"配置项": "运行结果目录", "值": payload["runs_dir"]},
        {"配置项": "配置目录", "值": payload["configs_dir"]},
        {"配置项": "Streamlit 状态", "值": payload["streamlit_status"]},
    ]
    return {
        "summary": {
            "title": "系统设置",
            "status": "loaded",
            "risk_level": "low",
            "execution_enabled": False,
            "items": [{"label": "配置项", "value": len(rows)}],
            "warnings": [],
            "blocking_reasons": [],
        },
        "table": {"columns": ["配置项", "值"], "rows": rows},
        "artifact_path": "",
        "raw": {"settings": payload},
    }


@router.get("/settings/readiness")
def settings_readiness(request: Request) -> dict:
    payload = settings(request)
    rows = [
        {
            "验收项": "主要页面不依赖 Streamlit",
            "状态": "ready",
            "说明": "首页、账户库、创建计划、项目管理、落地页、账户备注、任务、操作日志和结果中心均由 React 路由承载。",
        },
        {
            "验收项": "产品账户库可导入、查询、筛选、导出",
            "状态": "ready",
            "说明": "支持 CSV、TXT、XLSX 上传、多行粘贴、导入预览、提交和导出。",
        },
        {
            "验收项": "数据看板可按产品、账户、项目、素材查看核心指标",
            "状态": "ready",
            "说明": "首页、产品、账户、项目、素材与建议中心接口已由 React 页面消费。",
        },
        {
            "验收项": "创建计划主链路可用",
            "状态": "ready",
            "说明": "支持产品账户库 active 账户、生成计划、执行前审查、真实创建任务和结果复盘。",
        },
        {
            "验收项": "项目管理、落地页管理、账户备注可用",
            "状态": "ready",
            "说明": "高风险动作均走中文预览、确认执行，并在发起页面展示进度和结果复盘。",
        },
        {
            "验收项": "任务中心展示业务进度和高级日志",
            "状态": "ready",
            "说明": "任务列表和详情优先展示任务内容、业务内容、进度和结果摘要；技术日志只在高级折叠区查看。",
        },
        {
            "验收项": "操作日志可追溯前端动作",
            "状态": "ready",
            "说明": "操作日志展示业务内容和结果摘要，并可按关联任务查看触发人、状态和明细。",
        },
        {
            "验收项": "所有 JSON 页面中文摘要优先",
            "状态": "ready",
            "说明": "结果中心、任务详情、操作日志和各执行入口均使用 SummaryPanel 展示中文摘要与明细表。",
        },
        {
            "验收项": "所有真实执行必须输入确认执行",
            "状态": "ready",
            "说明": "真实执行入口统一使用确认组件，后端仍校验确认文本。",
        },
        {
            "验收项": "React 和 FastAPI 不绕过固定脚本",
            "状态": "ready",
            "说明": "真实业务动作由固定脚本读取 JSON 后启动，并写入任务记录与操作日志。",
        },
    ]
    ready_count = sum(1 for row in rows if row["状态"] == "ready")
    return {
        "summary": {
            "title": "React 替换验收清单",
            "status": "trial_ready",
            "risk_level": "medium",
            "execution_enabled": False,
            "items": [
                {"label": "验收项", "value": len(rows)},
                {"label": "已满足", "value": ready_count},
                {"label": "Streamlit 状态", "value": payload["streamlit_status"]},
            ],
            "warnings": ["Streamlit 已标记为旧版保留入口，验收完成前暂不删除。"],
            "blocking_reasons": [],
        },
        "table": {"columns": ["验收项", "状态", "说明"], "rows": rows},
        "artifact_path": "",
        "raw": {"settings": payload, "streamlit_status": payload["streamlit_status"], "checks": rows},
    }
