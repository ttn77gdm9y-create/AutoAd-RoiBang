from __future__ import annotations

from typing import Any


OPERATION_LABELS = {
    "account_remark_config_generate": "账户备注配置生成",
    "account_remark_update": "账户备注真实执行",
    "create_live_execute": "创建真实执行",
    "create_live_execute_once": "创建真实执行",
    "create_mode": "创建计划",
    "create_plan_generate": "创建计划生成",
    "delivery_patrol": "投放巡检",
    "dry_run_probe": "连通性检查",
    "frontend_operation_log": "前端操作日志",
    "project_management_config_generate": "项目管理配置生成",
    "project_management_execute": "项目管理执行",
    "project_realtime_filter_config": "项目筛选配置生成",
    "project_update_execute": "项目管理真实执行",
    "site_handsel": "落地页转赠",
    "site_status_update": "落地页状态更新",
    "site_template_foundation": "模板建站",
}

STATUS_LABELS = {
    "blocked": "已阻止",
    "completed": "已完成",
    "create_http_failed": "创建接口失败",
    "empty": "暂无结果",
    "executed": "已执行",
    "failed": "失败",
    "loaded": "已加载",
    "not_found": "未找到",
    "partial": "部分成功",
    "partial_failed": "部分失败",
    "planned": "已生成预览",
    "preview_ready": "预览就绪",
    "queued": "排队中",
    "ready": "待确认",
    "ready_to_execute": "待执行",
    "running": "运行中",
    "success": "成功",
    "succeeded": "成功",
    "trial_ready": "试用就绪",
    "unknown": "未知",
    "DELETED": "已删除",
    "DISABLE": "关闭",
    "ENABLE": "开启",
    "delete": "删除",
    "deleted": "已删除",
    "disable": "关闭",
    "enable": "开启",
    "published": "发布",
    "undeleted": "恢复删除",
    "unpublished": "下线",
}

PROJECT_ACTION_LABELS = {
    "bid_update": "调整出价",
    "budget_update": "调整预算",
    "delete_project": "删除项目",
    "roi_coeff_update": "调整 ROI 系数",
    "status_update": "开启/关闭项目",
}

CREATE_MODE_LABELS = {
    "wx_pay_male_random_materials": "每付男素材不限",
    "wx_pay_general_random_materials": "每付通投素材不限",
    "wx_pay_male_test_new": "每付男测新",
    "wx_pay_general_test_new": "每付通投测新",
    "wx_pay_male_recent_scale": "每付男近期放量",
    "wx_pay_general_recent_scale": "每付通投近期放量",
    "wx_pay_male_scale": "每付男历史放量",
    "wx_pay_general_scale": "每付通投历史放量",
    "wx_7r_male_recent_scale": "7R 男近期放量",
    "wx_7r_general_recent_scale": "7R 通投近期放量",
    "wx_7r_male_scale": "7R 男历史放量",
    "wx_7r_general_scale": "7R 通投历史放量",
}


def operation_label(value: Any) -> str:
    text = str(value or "").strip()
    return OPERATION_LABELS.get(text, text or "未指定任务")


def status_label(value: Any) -> str:
    text = str(value or "").strip()
    if text.startswith("running_post_"):
        suffix = text.removeprefix("running_post_")
        return f"运行后置步骤 {suffix}"
    return STATUS_LABELS.get(text, text or "未知")


def project_action_label(value: Any) -> str:
    text = str(value or "").strip()
    return PROJECT_ACTION_LABELS.get(text, text or "未指定动作")


def create_mode_label(value: Any) -> str:
    text = str(value or "").strip()
    return CREATE_MODE_LABELS.get(text, text or "未指定模式")
