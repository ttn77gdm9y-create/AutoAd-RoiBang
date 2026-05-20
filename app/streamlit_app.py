from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st

from roibang_v2.ui.artifact_reader import compact_summary
from roibang_v2.ui.artifact_reader import load_latest_artifact
from roibang_v2.ui.script_runner import build_ai_template_drafts_command
from roibang_v2.ui.script_runner import build_create_plan_command
from roibang_v2.ui.script_runner import build_delivery_patrol_command
from roibang_v2.ui.script_runner import build_project_filter_command
from roibang_v2.ui.script_runner import run_fixed_script
from roibang_v2.ui.streamlit_shell import list_create_modes
from roibang_v2.ui.streamlit_shell import load_ui_config
from roibang_v2.ui.streamlit_shell import mode_label


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ui-config", default="configs/ui/streamlit-v0.example.json")
    return parser.parse_args()


@st.cache_data(ttl=10)
def _latest(runs_dir: str, workflow: str) -> dict[str, Any]:
    return load_latest_artifact(runs_dir, workflow)


@st.cache_data(ttl=30)
def _modes(mode_dir: str) -> list[dict[str, str]]:
    return list_create_modes(mode_dir)


def _show_summary(title: str, payload: dict[str, Any]) -> None:
    summary = compact_summary(payload)
    with st.container(border=True):
        st.subheader(title)
        cols = st.columns(4)
        cols[0].metric("ok", str(summary.get("ok")))
        cols[1].metric("status", str(summary.get("status") or "-"))
        cols[2].metric("external_api_calls", str(summary.get("external_api_calls", 0)))
        cols[3].metric("execution_enabled", str(summary.get("execution_enabled", False)))
        artifact_path = str(summary.get("artifact_path") or "")
        if artifact_path:
            st.caption(f"artifact（结果文件）：{artifact_path}")
        st.json(summary.get("summary") or {})


def _show_script_result(result) -> None:
    st.code(" ".join(result.command), language="bash")
    if result.ok:
        st.success(f"脚本完成，exit_code（退出码）={result.return_code}")
    else:
        st.error(f"脚本失败，exit_code（退出码）={result.return_code}")
    if result.parsed_stdout:
        st.json(result.parsed_stdout)
    elif result.stdout.strip():
        st.code(result.stdout, language="text")
    if result.stderr.strip():
        st.code(result.stderr, language="text")


def _dashboard(runs_dir: str) -> None:
    st.header("Dashboard（首页）")
    st.caption("只读展示最近本地产物，不调用平台接口。")
    workflows = [
        ("定时任务日报", "scheduler_status"),
        ("投放巡检", "delivery_patrol"),
        ("投放巡检建议", "delivery_patrol_suggestions"),
        ("创建执行", "create_live_execute_once"),
        ("AI 创建模板草稿", "ai_create_template_drafts"),
    ]
    for title, workflow in workflows:
        _show_summary(title, _latest(runs_dir, workflow))


def _delivery_patrol(project_root: Path, runs_dir: str, timeout_seconds: int) -> None:
    st.header("Delivery Patrol（投放巡检）")
    st.caption("运行固定只读巡检脚本，结果写入 data/runs（运行结果目录）。")
    if st.button("运行只读巡检脚本", type="primary"):
        result = run_fixed_script(build_delivery_patrol_command(readonly=True), cwd=project_root, timeout_seconds=timeout_seconds)
        st.cache_data.clear()
        _show_script_result(result)
    patrol = _latest(runs_dir, "delivery_patrol")
    _show_summary("最近巡检结果", patrol)
    message = str(patrol.get("message") or "")
    if message:
        st.text_area("飞书摘要", value=message, height=260)
    suggestions = patrol.get("delivery_patrol_suggestions")
    if isinstance(suggestions, dict):
        st.subheader("同频建议摘要")
        st.json(suggestions.get("summary") or suggestions)


def _create(project_root: Path, config: dict[str, Any], timeout_seconds: int) -> None:
    st.header("Create（创建计划）")
    st.caption("只生成创建计划，不执行真实创建。预算、出价、项目数、单元数、素材规则来自固定创建模式。")
    modes = _modes(str(PROJECT_ROOT / str(config.get("create_modes_dir") or "configs/create-modes")))
    if not modes:
        st.warning("未找到 create-modes（创建模式）配置。")
        return
    labels = [mode_label(row) for row in modes]
    label_to_mode = {mode_label(row): row for row in modes}
    selected = st.selectbox("固定创建模式", labels)
    accounts = st.text_area("账户 ID，多个账户用逗号或换行分隔", height=100)
    owner = st.text_input("owner（负责人）", value=str(config.get("default_owner") or "郭靖"))
    target_date = st.text_input("target_date（目标日期，可空）", value="")
    if st.button("生成创建计划", type="primary"):
        mode = label_to_mode[selected]["mode_key"]
        command = build_create_plan_command(mode=mode, accounts=accounts, owner=owner, target_date=target_date)
        result = run_fixed_script(command, cwd=project_root, timeout_seconds=timeout_seconds)
        st.cache_data.clear()
        _show_script_result(result)
        artifact_path = result.parsed_stdout.get("artifact_path") if result.parsed_stdout else ""
        if artifact_path:
            st.info(f"下一步真实执行仍走固定终端脚本：scripts/run_create_live_execute_terminal.py --plan {artifact_path}")


def _project_management(project_root: Path, timeout_seconds: int) -> None:
    st.header("Project Management（项目管理配置）")
    st.caption("按实时数据生成项目管理 JSON；真实执行仍需单独确认后调用项目更新执行脚本。")
    advertiser_id = st.text_input("账户 ID")
    action_type = st.selectbox(
        "动作",
        [
            "delete_project",
            "status_update",
            "budget_update",
            "bid_update",
            "roi_coeff_update",
        ],
    )
    project_update_id = st.text_input("project_update_id（项目管理配置 ID）", value="ui-project-filter")
    name_contains = st.text_input("项目名包含，可空")
    spend_window = st.selectbox("数据窗口", ["today", "yesterday", "last_3_days"])
    metric_field = st.selectbox(
        "筛选字段",
        [
            "stat_cost",
            "active_register",
            "register_cost",
            "billing_convert_cnt",
            "billing_conversion_cost",
            "billing_1day_pay_roi",
        ],
    )
    metric_op = st.selectbox("比较符", ["lt", "lte", "gt", "gte", "eq"])
    metric_value = st.text_input("筛选值", value="100")
    opt_status = ""
    budget = ""
    cpa_bid = ""
    roi_goal = ""
    if action_type == "status_update":
        opt_status = st.selectbox("目标状态", ["DISABLE", "ENABLE"])
    elif action_type == "budget_update":
        budget = st.text_input("budget（预算）", value="")
    elif action_type == "bid_update":
        cpa_bid = st.text_input("cpa_bid（项目出价）", value="")
    elif action_type == "roi_coeff_update":
        roi_goal = st.text_input("roi_goal（ROI 系数）", value="")
    output_path = st.text_input("输出 JSON 路径", value="configs/project-updates/ui-project-filter.local.json")
    if st.button("生成项目管理 JSON", type="primary"):
        command = build_project_filter_command(
            project_update_id=project_update_id,
            advertiser_id=advertiser_id,
            action_type=action_type,
            name_contains=name_contains,
            spend_window=spend_window,
            metric_field=metric_field,
            metric_op=metric_op,
            metric_value=metric_value,
            output_path=output_path,
            opt_status=opt_status,
            budget=budget,
            cpa_bid=cpa_bid,
            roi_goal=roi_goal,
        )
        result = run_fixed_script(command, cwd=project_root, timeout_seconds=timeout_seconds)
        st.cache_data.clear()
        _show_script_result(result)


def _ai_template_drafts(project_root: Path, runs_dir: str, timeout_seconds: int) -> None:
    st.header("AI Template Drafts（AI 创建模板草稿）")
    st.caption("只生成草稿，不写人工模板，不生成创建计划，不执行真实创建。")
    if st.button("生成 AI 创建模板草稿", type="primary"):
        result = run_fixed_script(build_ai_template_drafts_command(), cwd=project_root, timeout_seconds=timeout_seconds)
        st.cache_data.clear()
        _show_script_result(result)
    payload = _latest(runs_dir, "ai_create_template_drafts")
    _show_summary("最近 AI 草稿结果", payload)
    drafts = payload.get("drafts") if isinstance(payload.get("drafts"), list) else []
    for draft in drafts:
        name = str(draft.get("draft_name") or draft.get("draft_key") or "draft")
        with st.expander(name):
            st.json(draft)


def _results(runs_dir: str) -> None:
    st.header("Results（执行结果）")
    workflow = st.selectbox(
        "workflow（流程名）",
        [
            "create_mode",
            "create_live_execute_once",
            "create_live_execute_report",
            "project_realtime_filter_config",
            "project_update_execute",
            "delivery_patrol",
            "delivery_patrol_suggestions",
            "scheduler_status",
            "ai_create_template_drafts",
        ],
    )
    payload = _latest(runs_dir, workflow)
    _show_summary("最近结果", payload)
    st.json(payload)


def main() -> None:
    args = _args()
    config = load_ui_config(args.ui_config)
    project_root = (PROJECT_ROOT / str(config.get("project_root") or ".")).resolve()
    runs_dir = str(project_root / str(config.get("runs_dir") or "data/runs"))
    timeout_seconds = int(config.get("readonly_timeout_seconds") or 900)

    st.set_page_config(page_title=str(config.get("title") or "RoiBang-v2"), layout="wide")
    st.title(str(config.get("title") or "RoiBang-v2 本地工作台"))
    st.caption("v0.1：只读展示、生成 JSON、调用固定脚本。前端不直接调用平台接口。")

    tabs = st.tabs(
        [
            "Dashboard（首页）",
            "Delivery Patrol（投放巡检）",
            "Create（创建）",
            "Project Management（项目管理）",
            "AI Drafts（AI 草稿）",
            "Results（结果）",
        ]
    )
    with tabs[0]:
        _dashboard(runs_dir)
    with tabs[1]:
        _delivery_patrol(project_root, runs_dir, timeout_seconds)
    with tabs[2]:
        _create(project_root, config, timeout_seconds)
    with tabs[3]:
        _project_management(project_root, timeout_seconds)
    with tabs[4]:
        _ai_template_drafts(project_root, runs_dir, timeout_seconds)
    with tabs[5]:
        _results(runs_dir)


if __name__ == "__main__":
    main()
