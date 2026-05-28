from __future__ import annotations

import argparse
import copy
import hashlib
import json
import shlex
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
import streamlit.components.v1 as components

from roibang_v2.create_mode_rules import normalize_create_mode_config
from roibang_v2.ui.artifact_reader import compact_summary
from roibang_v2.ui.artifact_reader import load_latest_artifact
from roibang_v2.ui.background_tasks import build_runner_command
from roibang_v2.ui.background_tasks import build_task_record
from roibang_v2.ui.background_tasks import start_runner
from roibang_v2.ui.background_tasks import write_task_record
from roibang_v2.ui.create_plan_preview import build_create_plan_preview
from roibang_v2.ui.create_plan_preview import build_create_plan_preview_from_review
from roibang_v2.ui.create_plan_preview import filter_preview_materials
from roibang_v2.ui.create_plan_preview import filter_preview_units
from roibang_v2.ui.create_plan_review import build_create_plan_review
from roibang_v2.ui.create_template_health import build_create_mode_health
from roibang_v2.ui.create_template_health import build_create_template_health
from roibang_v2.ui.execution_review import build_account_remark_execution_review
from roibang_v2.ui.execution_review import build_payload_chinese_rows
from roibang_v2.ui.execution_review import build_payload_chinese_summary
from roibang_v2.ui.execution_review import build_project_update_execution_review
from roibang_v2.ui.execution_review import remember_execution_path
from roibang_v2.ui.execution_review import resolve_optional_execution_path
from roibang_v2.ui.operation_logs import filter_operation_logs
from roibang_v2.ui.operation_logs import load_operation_log_detail
from roibang_v2.ui.operation_logs import load_operation_logs
from roibang_v2.ui.scheduler_status_view import build_scheduler_status_view
from roibang_v2.ui.script_runner import build_account_remark_config_command
from roibang_v2.ui.script_runner import build_account_remark_execute_command
from roibang_v2.ui.script_runner import build_ai_template_drafts_command
from roibang_v2.ui.script_runner import build_create_live_config_check_command
from roibang_v2.ui.script_runner import build_create_live_execute_command
from roibang_v2.ui.script_runner import build_create_live_execute_report_command
from roibang_v2.ui.script_runner import build_create_live_terminal_command
from roibang_v2.ui.script_runner import build_create_plan_command
from roibang_v2.ui.script_runner import build_delivery_patrol_command
from roibang_v2.ui.script_runner import build_project_filter_command
from roibang_v2.ui.script_runner import build_project_update_execute_command
from roibang_v2.ui.script_runner import build_product_config_publish_command
from roibang_v2.ui.script_runner import run_fixed_script
from roibang_v2.ui.streamlit_shell import list_create_modes
from roibang_v2.ui.streamlit_shell import list_products
from roibang_v2.ui.streamlit_shell import build_allowed_create_accounts_config
from roibang_v2.ui.streamlit_shell import load_create_template_catalog
from roibang_v2.ui.streamlit_shell import load_create_mode
from roibang_v2.ui.streamlit_shell import load_product_config
from roibang_v2.ui.streamlit_shell import load_ui_config
from roibang_v2.ui.streamlit_shell import mode_label
from roibang_v2.ui.streamlit_shell import product_config_missing_fields
from roibang_v2.ui.streamlit_shell import product_create_template_catalog_path
from roibang_v2.ui.streamlit_shell import product_label
from roibang_v2.ui.streamlit_shell import save_allowed_create_accounts_config
from roibang_v2.ui.streamlit_shell import save_create_mode_draft
from roibang_v2.ui.streamlit_shell import save_product_draft
from roibang_v2.ui.streamlit_shell import save_product_create_mode_config
from roibang_v2.ui.streamlit_shell import save_product_create_template_catalog
from roibang_v2.ui.streamlit_shell import split_account_ids
from roibang_v2.ui.task_runs import load_frontend_task_rows
from roibang_v2.ui.task_runs import load_recent_task_runs
from roibang_v2.ui.task_runs import load_task_detail
from roibang_v2.ui.task_runs import read_create_live_progress
from roibang_v2.ui.task_status_summary import build_task_status_summary
from roibang_v2.workflows.frontend_operation_log import create_operation_details_from_plan
from roibang_v2.workflows.frontend_operation_log import record_frontend_operation


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


@st.cache_data(ttl=30)
def _products(product_dir: str) -> list[dict[str, str]]:
    return list_products(product_dir)


def _show_summary(title: str, payload: dict[str, Any]) -> None:
    summary = compact_summary(payload)
    with st.container(border=True):
        st.subheader(title)
        cols = st.columns(4)
        cols[0].metric("成功", _format_bool(summary.get("ok")))
        cols[1].metric("状态", _format_status(summary.get("status")))
        cols[2].metric("接口调用", str(summary.get("external_api_calls", 0)))
        cols[3].metric("执行动作", _format_bool(summary.get("execution_enabled")))
        artifact_path = str(summary.get("artifact_path") or "")
        if artifact_path:
            st.caption(f"结果文件：{artifact_path}")
        details = summary.get("summary") or {}
        if details:
            _show_json_with_summary("查看执行摘要 JSON", details, expanded=False)


def _show_json_with_summary(label: str, payload: Any, *, expanded: bool = False) -> None:
    summary = build_payload_chinese_summary(payload)
    rows = build_payload_chinese_rows(payload)
    if summary:
        st.markdown("**中文摘要**")
        st.dataframe([summary], use_container_width=True, hide_index=True)
    if rows:
        st.markdown("**明细摘要**")
        st.dataframe(rows, use_container_width=True, hide_index=True)
    counter_key = "_raw_json_toggle_counter"
    st.session_state[counter_key] = int(st.session_state.get(counter_key, 0)) + 1
    key_source = json.dumps(
        {
            "label": label,
            "payload": payload,
            "render_index": st.session_state[counter_key],
        },
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )
    key = "show_raw_json_" + hashlib.sha1(key_source.encode("utf-8")).hexdigest()[:16]
    if st.checkbox(f"显示原始 JSON：{label}", value=expanded, key=key):
        st.json(payload)


def _show_scheduler_status_panel(payload: dict[str, Any], *, compact: bool = False) -> None:
    view = build_scheduler_status_view(payload)
    summary = view.get("summary") if isinstance(view.get("summary"), dict) else {}
    with st.container(border=True):
        st.subheader("定时任务状态")
        cols = st.columns(6)
        cols[0].metric("总体", "正常" if view.get("ok") else "需要处理")
        cols[1].metric("报告日期", str(summary.get("report_date") or "-"))
        cols[2].metric("数据应到", str(summary.get("expected_data_date") or "-"))
        cols[3].metric("任务", str(summary.get("job_count", 0)))
        cols[4].metric("异常", str(summary.get("attention_count", 0)))
        cols[5].metric("产品", str(summary.get("product_count", 0)))
        message = str(view.get("message") or "").strip()
        if message and compact:
            with st.expander("查看定时任务日报文本", expanded=False):
                st.code(message, language="text")
        elif message:
            st.text_area("定时任务日报文本", value=message, height=220)

        product_rows = view.get("product_rows") if isinstance(view.get("product_rows"), list) else []
        if product_rows:
            st.markdown("**产品级结果**")
            st.dataframe(
                [
                    {
                        "产品": row.get("product"),
                        "产品 key": row.get("product_key"),
                        "任务": row.get("display_name"),
                        "任务类型": row.get("job"),
                        "状态": _format_status(row.get("status")),
                        "结果状态": _format_status(row.get("result_status")),
                        "artifact（执行结果文件）": row.get("artifact_path"),
                    }
                    for row in product_rows
                    if isinstance(row, dict)
                ],
                use_container_width=True,
                hide_index=True,
            )

        issue_rows = view.get("issue_rows") if isinstance(view.get("issue_rows"), list) else []
        if issue_rows:
            st.error(f"发现 {len(issue_rows)} 个定时任务问题。")
            st.dataframe(
                [
                    {
                        "任务": row.get("display_name"),
                        "任务 ID": row.get("job_id"),
                        "问题": row.get("issue"),
                    }
                    for row in issue_rows
                    if isinstance(row, dict)
                ],
                use_container_width=True,
                hide_index=True,
            )

        if not compact:
            job_rows = view.get("job_rows") if isinstance(view.get("job_rows"), list) else []
            if job_rows:
                st.markdown("**任务级状态**")
                st.dataframe(
                    [
                        {
                            "任务": row.get("display_name"),
                            "任务 ID": row.get("job_id"),
                            "状态": _format_status(row.get("status")),
                            "数据状态": _format_status(row.get("data_status")),
                            "数据类型": row.get("data_type"),
                            "launchd 退出码": row.get("last_exit_code"),
                            "workflow artifact（执行结果文件）": row.get("artifact_path"),
                            "scheduler artifact（执行结果文件）": row.get("scheduler_artifact_path"),
                        }
                        for row in job_rows
                        if isinstance(row, dict)
                    ],
                    use_container_width=True,
                    hide_index=True,
                )
            artifact_rows = view.get("artifact_rows") if isinstance(view.get("artifact_rows"), list) else []
            if artifact_rows:
                with st.expander("查看 artifact（执行结果文件）列表", expanded=False):
                    st.dataframe(artifact_rows, use_container_width=True, hide_index=True)


def _disable_streamlit_cache_shortcut() -> None:
    components.html(
        """
        <script>
        (() => {
          const install = () => {
            const doc = window.parent && window.parent.document;
            if (!doc || doc.__roibangCopyShortcutPatch) return;
            doc.__roibangCopyShortcutPatch = true;
            const isEditable = (target) => {
              const element = target && target.nodeType === 1 ? target : null;
              if (!element) return false;
              const tag = element.tagName ? element.tagName.toLowerCase() : "";
              return tag === "input" || tag === "textarea" || element.isContentEditable;
            };
            const stopStreamlitCacheShortcut = (event) => {
              const key = String(event.key || "").toLowerCase();
              if (key !== "c") return;
              if (event.metaKey || event.ctrlKey || !isEditable(event.target)) {
                event.stopImmediatePropagation();
              }
            };
            doc.addEventListener("keydown", stopStreamlitCacheShortcut, true);
          };
          install();
        })();
        </script>
        """,
        height=0,
        width=0,
    )


def _format_bool(value: Any) -> str:
    return "是" if bool(value) else "否"


def _format_status(value: Any) -> str:
    raw = str(value or "").strip()
    labels = {
        "completed": "已完成",
        "blocked": "已阻断",
        "passed": "已通过",
        "control_analysis": "分析完成",
        "control_config": "配置生成",
        "control_execute": "执行完成",
        "phase1": "正常",
        "missing": "未找到",
        "failed": "失败",
        "ok": "正常",
        "attention": "需要处理",
        "stale": "缺数据",
        "unknown": "未知",
        "planned_only": "仅生成计划",
        "drafted": "草稿已生成",
        "create_http_completed": "真实创建完成",
        "create_http_failed": "真实创建失败",
        "config_ready": "配置就绪",
        "completed_with_failures": "部分失败",
        "queued": "排队中",
        "running": "执行中",
        "running_post_1": "生成汇报中",
        "retrying": "重试中",
        "reported_completed": "汇报完成",
        "reported_partial_completed": "部分失败已汇报",
        "skipped_existing_provider_id": "跳过已创建项目",
        "skipped_existing_target_material": "跳过已推送素材",
        "sent": "已推送",
        "not_attempted": "未推送",
    }
    return labels.get(raw, raw or "-")


def _int_value(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _float_value(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _optional_float_value(value: Any) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    return float(text)


def _format_yes_no(value: Any) -> str:
    return "是" if bool(value) else "否"


def _source_scope_label(value: Any) -> str:
    labels = {"source_material_account": "源素材账户"}
    return labels.get(str(value or ""), str(value or "-"))


def _selection_type_label(value: Any) -> str:
    labels = {
        "high_spend": "高消耗素材",
        "test_new": "测新素材",
        "low_conversion_retest": "低转化复测",
        "no_conversion_retest": "无转化复测",
        "random_materials": "随机素材",
    }
    return labels.get(str(value or ""), str(value or "-"))


def _sort_label(value: Any) -> str:
    labels = {
        "stat_cost_desc": "按消耗倒序",
        "create_time_desc": "按创建时间倒序",
        "effective_create_date_desc": "按有效创建日期倒序",
        "random_stable": "稳定随机",
    }
    return labels.get(str(value or ""), str(value or "-"))


def _cross_account_reuse_mode_label(value: Any) -> str:
    labels = {"scale_top_materials": "放量高消耗素材可跨账户复用"}
    return labels.get(str(value or ""), str(value or "未启用"))


def _initial_status_label(value: Any) -> str:
    labels = {"ENABLE": "开启", "DISABLE": "关闭"}
    return labels.get(str(value or ""), str(value or "-"))


@st.cache_data(ttl=30)
def _create_template_catalog(path: str) -> dict[str, Any]:
    source = Path(path)
    if not source.exists():
        return {}
    value = json.loads(source.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {}


def _create_template_for_mode(mode: dict[str, Any], catalog: dict[str, Any]) -> dict[str, Any]:
    templates = catalog.get("templates") if isinstance(catalog.get("templates"), dict) else {}
    template_key = str(mode.get("template_key") or "").strip()
    value = templates.get(template_key)
    return value if isinstance(value, dict) else {}


def _create_template_catalog_path_for_mode(mode: dict[str, Any]) -> Path:
    return product_create_template_catalog_path(
        PROJECT_ROOT / "configs/create-templates",
        str(mode.get("product_key") or "").strip(),
    )


@st.cache_data(ttl=30)
def _product_config_for_mode(mode: dict[str, Any], product_dir: str) -> dict[str, Any]:
    product_key = str(mode.get("product_key") or "").strip()
    if not product_key:
        return {}
    directory = Path(product_dir)
    for suffix in [".local.json", ".json", ".example.json"]:
        path = directory / f"{product_key}{suffix}"
        if path.exists():
            value = json.loads(path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
    return {}


def _title_strategy_label(value: Any) -> str:
    labels = {
        "deterministic_shuffle_per_unit": "按单元稳定随机，尽量减少同账户内重复",
        "random": "随机选择",
    }
    return labels.get(str(value or ""), str(value or "-"))


def _show_mode_detail(
    mode: dict[str, Any],
    *,
    template_catalog: dict[str, Any] | None = None,
    product_config: dict[str, Any] | None = None,
) -> None:
    defaults = mode.get("defaults") if isinstance(mode.get("defaults"), dict) else {}
    requirements = mode.get("material_requirements") if isinstance(mode.get("material_requirements"), dict) else {}
    selection = mode.get("material_selection") if isinstance(mode.get("material_selection"), dict) else {}
    status = mode.get("initial_status") if isinstance(mode.get("initial_status"), dict) else {}
    creative = mode.get("unit_creative_selection") if isinstance(mode.get("unit_creative_selection"), dict) else {}
    catalog = template_catalog if isinstance(template_catalog, dict) else {}
    base_template = _create_template_for_mode(mode, catalog)
    title_pool = base_template.get("title_pool") if isinstance(base_template.get("title_pool"), list) else []
    cta_pool = base_template.get("cta_pool") if isinstance(base_template.get("cta_pool"), list) else []
    selling_points = (
        base_template.get("product_selling_points")
        if isinstance(base_template.get("product_selling_points"), list)
        else []
    )
    aweme_ids = base_template.get("aweme_ids") if isinstance(base_template.get("aweme_ids"), list) else []
    product = product_config if isinstance(product_config, dict) else {}
    foundation = product.get("foundation") if isinstance(product.get("foundation"), dict) else {}
    effective_touch_url = str(
        foundation.get("effective_touch_url")
        or base_template.get("effective_touch_url")
        or catalog.get("effective_touch_url")
        or ""
    ).strip()
    health = build_create_template_health(mode, catalog)
    health_summary = health.get("summary") if isinstance(health.get("summary"), dict) else {}

    with st.expander("当前模板内容", expanded=False):
        st.markdown("**模板健康检查**")
        cols = st.columns(6)
        cols[0].metric("状态", _format_status(health.get("status")))
        cols[1].metric("产品专属", _format_yes_no(health_summary.get("product_specific_template")))
        cols[2].metric("随机素材", _format_yes_no(health_summary.get("selection_type") == "random_materials"))
        cols[3].metric("写死出价", _format_yes_no(health_summary.get("hardcoded_cpa_bid")))
        cols[4].metric("写死 ROI", _format_yes_no(health_summary.get("hardcoded_roi_coefficient")))
        cols[5].metric("要求回看", _format_yes_no(health_summary.get("requires_lookback_days")))
        blocking_reasons = health.get("blocking_reasons") if isinstance(health.get("blocking_reasons"), list) else []
        warnings = health.get("warnings") if isinstance(health.get("warnings"), list) else []
        if blocking_reasons:
            st.error("模板健康检查未通过：" + "；".join(str(item) for item in blocking_reasons))
        else:
            st.success("模板健康检查通过。")
        if warnings:
            with st.expander("查看模板风险提示", expanded=False):
                for item in warnings:
                    st.warning(str(item))
        _show_json_with_summary("查看模板健康检查 JSON", health, expanded=False)

        cols = st.columns(5)
        cols[0].metric("日预算", str(defaults.get("daily_budget", "-")))
        cols[1].metric("项目出价", str(defaults.get("cpa_bid", "不写")))
        cols[2].metric("ROI 系数", str(defaults.get("roi_coefficient", "不写")))
        cols[3].metric("每账户项目数", str(defaults.get("project_count", "-")))
        cols[4].metric("每项目单元数", str(defaults.get("units_per_project", "-")))

        product_rows = [
            ("产品键", str(mode.get("product_key") or product.get("product_key") or "-")),
            ("产品名", str(product.get("product") or mode.get("product") or "-")),
            ("平台", str(product.get("platform") or mode.get("platform") or "-")),
            ("源素材账户", str(product.get("source_advertiser_id") or mode.get("source_advertiser_id") or "-")),
            ("组织 ID", str(product.get("organization_id") or mode.get("organization_id") or "-")),
            ("账户准允许名单", str(product.get("allowed_target_accounts_path") or "-")),
            ("账户备注规则", str(product.get("account_remark_pattern") or "-")),
        ]
        st.markdown("**产品基础配置**")
        st.table([{"配置项": key, "当前值": value} for key, value in product_rows])

        cols = st.columns(5)
        cols[0].metric("每单元素材数", str(requirements.get("materials_per_unit", "-")))
        cols[1].metric("项目初始状态", _initial_status_label(status.get("project_operation")))
        cols[2].metric("单元初始状态", _initial_status_label(status.get("unit_operation")))
        cols[3].metric("允许素材复用", _format_yes_no(requirements.get("allow_reuse_across_accounts")))
        cols[4].metric("账户间重复上限", f"{float(requirements.get('max_cross_account_overlap_ratio') or 0) * 100:g}%")

        st.markdown("**选素材规则**")
        rule_rows = [
            ("素材来源", _source_scope_label(selection.get("source_scope"))),
            ("素材类型", "视频素材" if requirements.get("material_type") == "video" else str(requirements.get("material_type") or "-")),
            ("表现回看天数", f"{selection.get('lookback_days')} 天" if selection.get("lookback_days") is not None else "不限制"),
            ("有效创建日期", f"近 {selection.get('first_seen_days')} 天" if selection.get("first_seen_days") is not None else "不限制"),
            ("筛选方式", _selection_type_label(selection.get("selection_type"))),
            ("最低消耗", str(selection.get("min_stat_cost", "-"))),
            ("最高消耗", str(selection.get("max_stat_cost", "不限制"))),
            ("转化数范围", f"{selection.get('min_convert_cnt', '-')}-{selection.get('max_convert_cnt', '-')}" if ("min_convert_cnt" in selection or "max_convert_cnt" in selection) else "不限制"),
            ("候选池上限", str(selection.get("candidate_pool_limit", "不限制"))),
            ("排序方式", _sort_label(selection.get("sort_by"))),
            ("跨账户复用模式", _cross_account_reuse_mode_label(requirements.get("cross_account_reuse_mode"))),
            ("随机打乱", _format_yes_no(selection.get("random_shuffle"))),
            ("排除最近已用", _format_yes_no(selection.get("exclude_recent_used"))),
        ]
        st.table([{"配置项": key, "当前值": value} for key, value in rule_rows])

        st.markdown("**创意规则**")
        creative_rows = [
            ("基础模板", str(mode.get("template_key") or "-")),
            ("文案池", f"{len(title_pool)} 条" if title_pool else "未配置"),
            ("文案分配", _title_strategy_label(creative.get("title_strategy"))),
            ("CTA（行动按钮）池", f"{len(cta_pool)} 条，随机 {creative.get('cta_min_count', '-')}-{creative.get('cta_max_count', '-')} 个"),
            ("产品卖点池", f"{len(selling_points)} 条，随机 {creative.get('product_selling_point_min_count', '-')}-{creative.get('product_selling_point_max_count', '-')} 个"),
            ("抖音号池", f"{len(aweme_ids)} 个，选择 {creative.get('aweme_select_count', '-')} 个"),
            ("锚点", f"{foundation.get('anchor_id') or base_template.get('anchor_id') or '-'} / {foundation.get('anchor_type') or base_template.get('anchor_type') or '-'} / {foundation.get('anchor_related_type') or base_template.get('anchor_related_type') or '-'}"),
            ("落地页", str(foundation.get("landing_url") or base_template.get("landing_url") or "-")),
            ("有效触点链接", effective_touch_url or "未配置"),
            ("产品图", str(foundation.get("product_image_id") or base_template.get("product_image_id") or "-")),
            ("固定封面", str(foundation.get("fixed_video_cover_id") or base_template.get("fixed_video_cover_id") or "-")),
        ]
        st.table([{"配置项": key, "当前值": value} for key, value in creative_rows])
        with st.expander("查看文案池样例", expanded=False):
            if title_pool:
                st.table([{"序号": index + 1, "文案": value} for index, value in enumerate(title_pool[:20])])
                if len(title_pool) > 20:
                    st.caption(f"仅展示前 20 条，完整文案池共 {len(title_pool)} 条。")
            else:
                st.caption("当前基础模板未配置文案池。")
        _show_json_with_summary(
            "查看 CTA（行动按钮）和产品卖点 JSON",
            {
                "cta_pool": cta_pool,
                "product_selling_points": selling_points,
                "aweme_ids": aweme_ids,
            },
            expanded=False,
        )
        st.caption(f"命名后缀：{mode.get('template_name_suffix') or '-'}")
        _show_json_with_summary("查看模板原始 JSON", mode, expanded=False)


def _show_create_mode_health(health: dict[str, Any], *, expanded_json: bool = False) -> None:
    summary = health.get("summary") if isinstance(health.get("summary"), dict) else {}
    cols = st.columns(6)
    cols[0].metric("模式健康", _format_status(health.get("status")))
    cols[1].metric("随机素材", _format_yes_no(summary.get("random_materials")))
    cols[2].metric("写死出价", _format_yes_no(summary.get("hardcoded_cpa_bid")))
    cols[3].metric("写死 ROI", _format_yes_no(summary.get("hardcoded_roi_coefficient")))
    cols[4].metric("要求回看", _format_yes_no(summary.get("requires_lookback_days")))
    cols[5].metric("产品专属", _format_yes_no(summary.get("product_specific_template")))
    blocking_reasons = health.get("blocking_reasons") if isinstance(health.get("blocking_reasons"), list) else []
    warnings = health.get("warnings") if isinstance(health.get("warnings"), list) else []
    if blocking_reasons:
        st.error("创建模式健康检查未通过：" + "；".join(str(item) for item in blocking_reasons))
    else:
        st.success("创建模式健康检查通过。")
    if warnings:
        with st.expander("查看创建模式风险提示", expanded=False):
            for item in warnings:
                st.warning(str(item))
    _show_json_with_summary("查看创建模式健康检查 JSON", health, expanded=expanded_json)


def _mode_draft_editor(
    mode: dict[str, Any],
    *,
    drafts_dir: Path,
    mode_dir: Path,
    template_catalog: dict[str, Any],
    runs_dir: str,
) -> None:
    defaults = dict(mode.get("defaults")) if isinstance(mode.get("defaults"), dict) else {}
    requirements = dict(mode.get("material_requirements")) if isinstance(mode.get("material_requirements"), dict) else {}
    selection = dict(mode.get("material_selection")) if isinstance(mode.get("material_selection"), dict) else {}
    creative = dict(mode.get("unit_creative_selection")) if isinstance(mode.get("unit_creative_selection"), dict) else {}
    product_key = str(mode.get("product_key") or "").strip()
    can_save_official = bool(product_key)

    title = "编辑并保存正式模板" if can_save_official else "复制为草稿并修改"
    with st.expander(title, expanded=False):
        if can_save_official:
            st.caption("这里会覆盖该产品专属 .local.json 创建模板；只改本地 JSON，不执行真实创建。")
        else:
            st.caption("这里保存的是草稿，不会覆盖正式创建模板，也不会被创建脚本自动读取。")
        _show_create_mode_health(build_create_mode_health(mode, template_catalog))
        base_key = str(mode.get("mode_key") or "create_mode")
        draft_key = st.text_input(
            "模式键",
            value=base_key if can_save_official else f"{base_key}_draft",
            disabled=can_save_official,
            key=f"draft_key_{base_key}_{product_key}",
        )
        display_name = st.text_input(
            "模板名称",
            value=str(mode.get("display_name") or base_key) if can_save_official else f"{mode.get('display_name') or base_key} 草稿",
            key=f"draft_name_{base_key}_{product_key}",
        )
        suffix = st.text_input("命名后缀", value=str(mode.get("template_name_suffix") or ""), key=f"draft_suffix_{base_key}")

        cols = st.columns(5)
        daily_budget = cols[0].number_input("日预算", min_value=1, value=_int_value(defaults.get("daily_budget"), 10000), step=100, key=f"draft_budget_{base_key}")
        cpa_bid = cols[1].text_input(
            "项目出价，空表示不写",
            value="" if defaults.get("cpa_bid") is None else str(defaults.get("cpa_bid")),
            key=f"draft_bid_{base_key}",
        )
        roi_default = "" if defaults.get("roi_coefficient") is None else str(defaults.get("roi_coefficient"))
        roi_coefficient = cols[2].text_input("ROI 系数，空表示不写", value=roi_default, key=f"draft_roi_{base_key}")
        project_count = cols[3].number_input("每账户项目数", min_value=1, value=_int_value(defaults.get("project_count"), 5), step=1, key=f"draft_projects_{base_key}")
        units_per_project = cols[4].number_input("每项目单元数", min_value=1, value=_int_value(defaults.get("units_per_project"), 1), step=1, key=f"draft_units_{base_key}")

        selection_options = {
            "高消耗素材": "high_spend",
            "测新素材": "test_new",
            "低转化复测": "low_conversion_retest",
            "无转化复测": "no_conversion_retest",
            "随机素材": "random_materials",
        }
        current_selection = next(
            (label for label, value in selection_options.items() if value == selection.get("selection_type")),
            "高消耗素材",
        )
        selection_type = selection_options[st.selectbox("筛选方式", list(selection_options), index=list(selection_options).index(current_selection), key=f"draft_selection_{base_key}")]
        random_materials = selection_type == "random_materials"
        if random_materials:
            st.caption("随机素材不使用回看天数、创建日期、消耗、转化数和候选池上限；保存时会自动从 JSON 移除这些条件。")

        cols = st.columns(5)
        materials_per_unit = cols[0].number_input("每单元素材数", min_value=1, value=_int_value(requirements.get("materials_per_unit"), 5), step=1, key=f"draft_materials_{base_key}")
        lookback_days = cols[1].text_input(
            "表现回看天数（随机素材不使用）" if random_materials else "表现回看天数，空为不限制",
            value="" if random_materials or selection.get("lookback_days") is None else str(selection.get("lookback_days")),
            disabled=random_materials,
            key=f"draft_lookback_{base_key}",
        )
        first_seen_days = cols[2].text_input(
            "有效创建日期近 N 天（随机素材不使用）" if random_materials else "有效创建日期近 N 天，空为不限制",
            value="" if random_materials or selection.get("first_seen_days") is None else str(selection.get("first_seen_days")),
            disabled=random_materials,
            key=f"draft_first_seen_{base_key}",
        )
        min_stat_cost = cols[3].number_input(
            "最低消耗（随机素材固定 0）" if random_materials else "最低消耗",
            min_value=0,
            value=0 if random_materials else _int_value(selection.get("min_stat_cost"), 0),
            step=50,
            disabled=random_materials,
            key=f"draft_min_cost_{base_key}",
        )
        max_stat_cost = cols[4].text_input(
            "最高消耗（随机素材不使用）" if random_materials else "最高消耗，空为不限制",
            value="" if random_materials or selection.get("max_stat_cost") is None else str(selection.get("max_stat_cost")),
            disabled=random_materials,
            key=f"draft_max_cost_{base_key}",
        )
        cols = st.columns(4)
        min_convert_cnt = cols[0].text_input(
            "最低转化数（随机素材不使用）" if random_materials else "最低转化数，空为不限制",
            value="" if random_materials or selection.get("min_convert_cnt") is None else str(selection.get("min_convert_cnt")),
            disabled=random_materials,
            key=f"draft_min_convert_{base_key}",
        )
        max_convert_cnt = cols[1].text_input(
            "最高转化数（随机素材不使用）" if random_materials else "最高转化数，空为不限制",
            value="" if random_materials or selection.get("max_convert_cnt") is None else str(selection.get("max_convert_cnt")),
            disabled=random_materials,
            key=f"draft_max_convert_{base_key}",
        )
        candidate_pool_limit = cols[2].text_input(
            "候选池上限（随机素材不使用）" if random_materials else "候选池上限，空为不限制",
            value="" if random_materials or selection.get("candidate_pool_limit") is None else str(selection.get("candidate_pool_limit")),
            disabled=random_materials,
            key=f"draft_pool_limit_{base_key}",
        )
        max_overlap = cols[3].number_input(
            "账户间重复上限",
            min_value=0.0,
            max_value=1.0,
            value=_float_value(requirements.get("max_cross_account_overlap_ratio"), 0.3),
            step=0.05,
            key=f"draft_overlap_{base_key}",
        )
        random_shuffle = st.checkbox("素材稳定随机打乱", value=bool(selection.get("random_shuffle", True)), key=f"draft_shuffle_{base_key}")
        allow_reuse = st.checkbox("素材不足时允许复用", value=bool(requirements.get("allow_reuse_across_accounts", True)), key=f"draft_reuse_{base_key}")

        button_label = "保存正式模板" if can_save_official else "保存草稿"
        if st.button(button_label, type="primary", key=f"save_draft_{base_key}_{product_key}"):
            draft = copy.deepcopy(mode)
            draft["mode_key"] = base_key if can_save_official else draft_key.strip()
            draft["display_name"] = display_name.strip()
            draft["template_name_suffix"] = suffix.strip()
            if can_save_official:
                draft.pop("draft", None)
            else:
                draft["draft"] = {
                    "enabled": True,
                    "source": "streamlit",
                    "base_mode_key": base_key,
                    "note": "草稿不参与真实创建；转正前需要人工确认并写入正式模板。",
                }
            draft_defaults = dict(draft.get("defaults")) if isinstance(draft.get("defaults"), dict) else {}
            draft_defaults.update(
                {
                    "daily_budget": int(daily_budget),
                    "project_count": int(project_count),
                    "units_per_project": int(units_per_project),
                }
            )
            cpa_bid_text = str(cpa_bid or "").strip()
            if cpa_bid_text:
                cpa_bid_value = float(cpa_bid_text)
                draft_defaults["cpa_bid"] = int(cpa_bid_value) if cpa_bid_value.is_integer() else cpa_bid_value
            else:
                draft_defaults.pop("cpa_bid", None)
            roi_value = _optional_float_value(roi_coefficient)
            if roi_value is None:
                draft_defaults.pop("roi_coefficient", None)
            else:
                draft_defaults["roi_coefficient"] = roi_value
            draft["defaults"] = draft_defaults

            draft_requirements = dict(draft.get("material_requirements")) if isinstance(draft.get("material_requirements"), dict) else {}
            draft_requirements.update(
                {
                    "materials_per_unit": int(materials_per_unit),
                    "max_cross_account_overlap_ratio": float(max_overlap),
                    "allow_reuse_across_accounts": bool(allow_reuse),
                    "on_insufficient": "allow_reuse" if allow_reuse else "skip_account",
                }
            )
            if selection_type == "high_spend" and allow_reuse and float(max_overlap) >= 1.0:
                draft_requirements["cross_account_reuse_mode"] = "scale_top_materials"
            elif draft_requirements.get("cross_account_reuse_mode") == "scale_top_materials":
                draft_requirements.pop("cross_account_reuse_mode", None)
            draft["material_requirements"] = draft_requirements

            draft_selection = dict(draft.get("material_selection")) if isinstance(draft.get("material_selection"), dict) else {}
            draft_selection.update(
                {
                    "selection_type": selection_type,
                    "min_stat_cost": int(min_stat_cost),
                    "random_shuffle": bool(random_shuffle),
                }
            )
            for key, raw_value, parser in [
                ("lookback_days", lookback_days, int),
                ("first_seen_days", first_seen_days, int),
                ("max_stat_cost", max_stat_cost, int),
                ("min_convert_cnt", min_convert_cnt, int),
                ("max_convert_cnt", max_convert_cnt, int),
                ("candidate_pool_limit", candidate_pool_limit, int),
            ]:
                text = str(raw_value or "").strip()
                if text:
                    draft_selection[key] = parser(text)
                else:
                    draft_selection.pop(key, None)
            draft["material_selection"] = draft_selection
            draft["unit_creative_selection"] = creative
            draft = normalize_create_mode_config(draft)
            health = build_create_mode_health(draft, template_catalog)
            if not bool(health.get("ok")):
                st.error("保存已阻断，请先修复创建模式健康检查问题。")
                _show_create_mode_health(health, expanded_json=True)
                return

            try:
                if can_save_official:
                    output = save_product_create_mode_config(mode_dir, draft)
                else:
                    output = save_create_mode_draft(drafts_dir, draft)
            except Exception as exc:
                st.error(f"保存失败：{exc}")
            else:
                operation_log = _record_simple_ui_operation(
                    runs_dir=runs_dir,
                    operation_type="create_mode_update",
                    status="completed",
                    actor="",
                    request={
                        "mode_key": draft.get("mode_key"),
                        "product_key": draft.get("product_key"),
                        "template_key": draft.get("template_key"),
                        "official": can_save_official,
                    },
                    result={
                        "ok": True,
                        "status": "saved",
                        "artifact_path": str(output),
                        "health": health,
                    },
                    details={
                        "product": str(draft.get("product") or ""),
                        "product_key": str(draft.get("product_key") or ""),
                        "mode_key": str(draft.get("mode_key") or ""),
                        "template_key": str(draft.get("template_key") or ""),
                        "official": can_save_official,
                        "health": health,
                    },
                )
                st.success(f"已保存：{output}")
                if can_save_official:
                    st.caption("已保存为该产品正式创建模板；后续生成计划会读取这个 .local.json。")
                else:
                    st.caption("这只是草稿；正式模板仍需后续转正脚本处理。")
                st.caption(f"前端操作日志：{operation_log.get('artifact_path')}")
                _show_create_mode_health(health)
                _show_json_with_summary("查看保存后的创建模板 JSON", draft, expanded=False)


def _lines_to_list(value: str) -> list[str]:
    rows: list[str] = []
    seen: set[str] = set()
    for line in str(value or "").replace("\r", "\n").split("\n"):
        item = line.strip()
        if item and item not in seen:
            seen.add(item)
            rows.append(item)
    return rows


def _list_to_text(values: Any) -> str:
    if not isinstance(values, list):
        return ""
    return "\n".join(str(item) for item in values)


def _base_template_editor(
    mode: dict[str, Any],
    *,
    template_catalog: dict[str, Any],
    template_dir: Path,
    runs_dir: str,
) -> None:
    product_key = str(mode.get("product_key") or "").strip()
    template_key = str(mode.get("template_key") or "").strip()
    if not product_key or not template_key:
        return
    catalog = copy.deepcopy(template_catalog)
    catalog.setdefault("product_key", product_key)
    templates = catalog.get("templates") if isinstance(catalog.get("templates"), dict) else {}
    template = dict(templates.get(template_key)) if isinstance(templates.get(template_key), dict) else {}
    if not template:
        return

    with st.expander("编辑产品专属基础模板", expanded=False):
        st.caption("这里编辑的是文案池、CTA（行动按钮）、产品卖点、抖音号等产品专属内容；只写本地 JSON，不执行真实创建。")
        cols = st.columns(3)
        project_template_name = cols[0].text_input(
            "项目模板名",
            value=str(template.get("project_template_name") or ""),
            key=f"base_project_name_{product_key}_{template_key}",
        )
        unit_template_name = cols[1].text_input(
            "单元模板名",
            value=str(template.get("unit_template_name") or ""),
            key=f"base_unit_name_{product_key}_{template_key}",
        )
        game_name = cols[2].text_input(
            "游戏名",
            value=str(template.get("game_name") or catalog.get("product") or ""),
            key=f"base_game_name_{product_key}_{template_key}",
        )
        cols = st.columns(3)
        copy_product_name = cols[0].text_input(
            "文案产品名",
            value=str(template.get("copy_product_name") or template.get("product_name") or ""),
            key=f"base_copy_product_{product_key}_{template_key}",
        )
        copy_source_name = cols[1].text_input(
            "文案来源名",
            value=str(template.get("copy_source_name") or template.get("source_name") or ""),
            key=f"base_copy_source_{product_key}_{template_key}",
        )
        copy_review_note = cols[2].text_input(
            "文案审核备注",
            value=str(template.get("copy_review_note") or ""),
            key=f"base_copy_note_{product_key}_{template_key}",
        )
        title_text = st.text_area(
            "文案池，每行一条",
            value=_list_to_text(template.get("title_pool")),
            height=220,
            key=f"base_titles_{product_key}_{template_key}",
        )
        cols = st.columns(3)
        cta_text = cols[0].text_area(
            "CTA（行动按钮）池，每行一条",
            value=_list_to_text(template.get("cta_pool")),
            height=140,
            key=f"base_cta_{product_key}_{template_key}",
        )
        selling_text = cols[1].text_area(
            "产品卖点池，每行一条",
            value=_list_to_text(template.get("product_selling_points")),
            height=140,
            key=f"base_selling_{product_key}_{template_key}",
        )
        aweme_text = cols[2].text_area(
            "抖音号池，每行一个",
            value=_list_to_text(template.get("aweme_ids")),
            height=140,
            key=f"base_aweme_{product_key}_{template_key}",
        )
        if st.button("保存产品专属基础模板", type="primary", key=f"save_base_template_{product_key}_{template_key}"):
            updated_template = dict(template)
            updated_template["project_template_name"] = project_template_name.strip()
            updated_template["unit_template_name"] = unit_template_name.strip()
            updated_template["game_name"] = game_name.strip()
            updated_template["source_name"] = game_name.strip()
            updated_template["product_name"] = game_name.strip()
            updated_template["copy_product_name"] = copy_product_name.strip()
            updated_template["copy_source_name"] = copy_source_name.strip()
            updated_template["copy_review_note"] = copy_review_note.strip()
            updated_template["title_pool"] = _lines_to_list(title_text)
            updated_template["cta_pool"] = _lines_to_list(cta_text)
            updated_template["product_selling_points"] = _lines_to_list(selling_text)
            updated_template["aweme_ids"] = _lines_to_list(aweme_text)
            templates[template_key] = updated_template
            catalog["templates"] = templates
            health = build_create_template_health(mode, catalog)
            blocking_reasons = health.get("blocking_reasons") if isinstance(health.get("blocking_reasons"), list) else []
            if blocking_reasons:
                st.error("保存已阻断：" + "；".join(str(item) for item in blocking_reasons))
                _show_json_with_summary("查看模板健康检查 JSON", health, expanded=False)
                return
            try:
                output = save_product_create_template_catalog(template_dir, catalog)
            except Exception as exc:
                st.error(f"保存失败：{exc}")
            else:
                operation_log = _record_simple_ui_operation(
                    runs_dir=runs_dir,
                    operation_type="create_template_update",
                    status="completed",
                    actor="",
                    request={
                        "product_key": product_key,
                        "template_key": template_key,
                        "output_path": str(output),
                    },
                    result={
                        "ok": True,
                        "artifact_path": str(output),
                        "status": "saved",
                        "health": health,
                    },
                    details={
                        "product": str(catalog.get("product") or mode.get("product") or ""),
                        "product_key": product_key,
                        "template_key": template_key,
                        "title_count": len(updated_template["title_pool"]),
                        "cta_count": len(updated_template["cta_pool"]),
                        "selling_point_count": len(updated_template["product_selling_points"]),
                        "health": health,
                    },
                )
                st.success(f"基础模板已保存：{output}")
                st.cache_data.clear()
                st.caption("后续生成创建计划会优先读取这个产品专属基础模板。")
                st.caption(f"前端操作日志：{operation_log.get('artifact_path')}")
                cols = st.columns(4)
                cols[0].metric("文案", str(len(updated_template["title_pool"])))
                cols[1].metric("CTA（行动按钮）", str(len(updated_template["cta_pool"])))
                cols[2].metric("卖点", str(len(updated_template["product_selling_points"])))
                cols[3].metric("健康检查", _format_status(health.get("status")))
                _show_json_with_summary("查看模板健康检查 JSON", health, expanded=False)
                _show_json_with_summary("查看保存后的基础模板 JSON", updated_template, expanded=False)


def _show_script_result(result) -> None:
    st.code(" ".join(result.command), language="bash")
    if result.ok:
        st.success(f"脚本完成，退出码={result.return_code}")
    else:
        st.error(f"脚本失败，退出码={result.return_code}")
    if result.parsed_stdout:
        _show_json_with_summary("查看脚本原始 JSON", result.parsed_stdout, expanded=False)
    elif result.stdout.strip():
        st.code(result.stdout, language="text")
    if result.stderr.strip():
        st.code(result.stderr, language="text")


def _show_next_command(title: str, command: list[str]) -> None:
    st.info(title)
    st.code(" ".join(command), language="bash")


def _run_confirmed_execution(
    *,
    title: str,
    command: list[str],
    project_root: Path,
    timeout_seconds: int,
    state_key: str,
    runs_dir: str = "",
    operation_type: str = "",
    request: dict[str, Any] | None = None,
    review: dict[str, Any] | None = None,
) -> None:
    with st.container(border=True):
        st.markdown(f"**{title}**")
        st.warning("这个按钮会调用固定脚本执行真实业务动作。执行前必须核对下面的中文摘要。")
        if isinstance(review, dict) and review:
            summary = review.get("summary") if isinstance(review.get("summary"), dict) else {}
            rows = review.get("rows") if isinstance(review.get("rows"), list) else []
            if summary:
                cols = st.columns(min(max(len(summary), 1), 4))
                for index, (label, value) in enumerate(summary.items()):
                    cols[index % len(cols)].metric(str(label), str(value))
            if rows:
                st.dataframe(rows, use_container_width=True, hide_index=True)
        st.code(_format_shell_command(command, cwd=project_root), language="bash")
        confirmed = st.checkbox("我已核对上方摘要，允许执行固定脚本", key=f"{state_key}_confirm")
        if st.button("确认执行", type="primary", disabled=not confirmed, key=f"{state_key}_execute"):
            result = run_fixed_script(command, cwd=project_root, timeout_seconds=timeout_seconds)
            st.session_state[f"{state_key}_result"] = result.parsed_stdout
            if runs_dir and operation_type:
                operation_log = _record_simple_ui_operation(
                    runs_dir=runs_dir,
                    operation_type=operation_type,
                    status="completed" if result.ok else "failed",
                    request={**(request or {}), "command": command, "confirmed": confirmed},
                    result={
                        "return_code": result.return_code,
                        "artifact_path": str(result.parsed_stdout.get("artifact_path") or "") if isinstance(result.parsed_stdout, dict) else "",
                        "status": result.parsed_stdout.get("status") if isinstance(result.parsed_stdout, dict) else "",
                        "ok": result.ok,
                    },
                )
                st.session_state[f"{state_key}_operation_log"] = operation_log
            st.cache_data.clear()
            _show_script_result(result)
            operation_log = st.session_state.get(f"{state_key}_operation_log")
            if isinstance(operation_log, dict) and operation_log:
                st.caption(f"前端操作日志：{operation_log.get('artifact_path')}")
        stored = st.session_state.get(f"{state_key}_result")
        if isinstance(stored, dict) and stored:
            _show_json_with_summary("查看最近执行结果 JSON", stored, expanded=False)
        operation_log = st.session_state.get(f"{state_key}_operation_log")
        if isinstance(operation_log, dict) and operation_log:
            st.caption(f"前端操作日志：{operation_log.get('artifact_path')}")


def _format_shell_command(command: list[str], *, cwd: Path | None = None) -> str:
    body = " \\\n  ".join(shlex.quote(str(part)) for part in command)
    if cwd is None:
        return body
    return f"cd {shlex.quote(str(cwd))}\n\n{body}"


def _load_json_path(project_root: Path, path_value: str) -> dict[str, Any]:
    text = str(path_value or "").strip()
    if not text:
        return {}
    path = Path(text)
    if not path.is_absolute():
        path = project_root / path
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _read_text_path(project_root: Path, path_value: str, *, max_chars: int = 20000) -> str:
    text = str(path_value or "").strip()
    if not text:
        return ""
    path = Path(text)
    if not path.is_absolute():
        path = project_root / text
    try:
        value = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""
    if len(value) <= max_chars:
        return value
    return value[-max_chars:]


def _load_frontend_task_record(runs_dir: str, task_id: str) -> dict[str, Any]:
    text = str(task_id or "").strip()
    if not text:
        return {}
    return _load_json_path(Path(runs_dir), f"frontend_tasks/{text}.json")


def _execution_payloads_from_task(project_root: Path, task: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    result = task.get("result") if isinstance(task.get("result"), dict) else {}
    execute_payload = _load_json_path(project_root, str(result.get("execute_artifact_path") or result.get("artifact_path") or ""))
    report_payload: dict[str, Any] = {}
    post_results = task.get("post_results") if isinstance(task.get("post_results"), list) else []
    for post_result in post_results:
        if not isinstance(post_result, dict):
            continue
        report_payload = _load_json_path(project_root, str(post_result.get("artifact_path") or ""))
        if not report_payload:
            report_payload = post_result
        break
    return execute_payload, report_payload


def _show_progress_snapshot(progress: dict[str, Any], *, title: str = "执行进度") -> None:
    current = progress.get("current") if isinstance(progress.get("current"), dict) else {}
    events = progress.get("events") if isinstance(progress.get("events"), list) else []
    percent = int(progress.get("percent") or 0)
    with st.container(border=True):
        st.subheader(title)
        if not current:
            st.caption("暂无执行进度。真实执行开始后，固定脚本会写入 current.json（当前进度）和 events.jsonl（事件日志）。")
            return
        cols = st.columns(5)
        cols[0].metric("状态", _format_status(current.get("status")))
        cols[1].metric("步骤", str(current.get("operation") or "-"))
        cols[2].metric("进度", f"{current.get('done', 0)}/{current.get('total', 0)}")
        cols[3].metric("接口调用", str(current.get("external_api_calls", 0)))
        cols[4].metric("账户", str(current.get("advertiser_id") or "-"))
        st.progress(percent)
        message = str(current.get("message") or "").strip()
        if message:
            st.error(message) if str(current.get("status") or "") == "failed" else st.caption(message)
        if events:
            with st.expander("查看最近进度事件", expanded=False):
                st.dataframe(
                    [
                        {
                            "时间": row.get("created_at") or row.get("updated_at") or "",
                            "状态": _format_status(row.get("status")),
                            "步骤": row.get("operation"),
                            "进度": f"{row.get('done', 0)}/{row.get('total', 0)}",
                            "账户": row.get("advertiser_id") or "",
                            "信息": row.get("message") or "",
                        }
                        for row in events
                        if isinstance(row, dict)
                    ],
                    use_container_width=True,
                    hide_index=True,
                )


def _create_plan_summary(project_root: Path, plan_path: str, fallback: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = _load_json_path(project_root, plan_path)
    summary = dict(fallback or {})
    if isinstance(payload.get("summary"), dict):
        summary = {**summary, **payload["summary"]}
    request = payload.get("create_request") if isinstance(payload.get("create_request"), dict) else {}
    target_accounts = request.get("target_accounts") if isinstance(request.get("target_accounts"), list) else []
    if target_accounts:
        summary["target_account_count"] = len(target_accounts)
    summary.setdefault("artifact_path", plan_path)
    return summary


def _show_create_plan_summary(summary: dict[str, Any]) -> None:
    with st.container(border=True):
        st.subheader("创建计划摘要")
        cols = st.columns(6)
        cols[0].metric("创建模式", str(summary.get("display_name") or summary.get("mode_key") or "-"))
        cols[1].metric("账户数", str(summary.get("target_account_count", "-")))
        cols[2].metric("项目数", str(summary.get("planned_project_count", "-")))
        cols[3].metric("单元数", str(summary.get("planned_unit_count", "-")))
        cols[4].metric("素材数", str(summary.get("planned_material_count", "-")))
        cols[5].metric("候选素材数", str(summary.get("source_material_count", "-")))
        st.caption(f"创建计划文件：{summary.get('artifact_path') or '-'}")
        if int(summary.get("violation_count") or 0) > 0:
            st.warning(f"规则异常数量：{summary.get('violation_count')}")


def _preview_account_options(preview: dict[str, Any]) -> list[str]:
    values: set[str] = set()
    for row in preview.get("accounts") or []:
        if isinstance(row, dict) and str(row.get("advertiser_id") or "").strip():
            values.add(str(row.get("advertiser_id")).strip())
    for row in preview.get("materials") or []:
        if not isinstance(row, dict):
            continue
        for account_id in row.get("covered_accounts") or []:
            if str(account_id or "").strip():
                values.add(str(account_id).strip())
    for row in preview.get("units") or []:
        if isinstance(row, dict) and str(row.get("advertiser_id") or "").strip():
            values.add(str(row.get("advertiser_id")).strip())
    return ["全部账户"] + sorted(values)


def _show_create_plan_preview_panel(
    preview: dict[str, Any],
    *,
    key_prefix: str,
    title: str = "执行前核对",
    use_expanders: bool = True,
) -> None:
    if not preview:
        st.warning("没有可展示的创建计划审查数据。")
        return
    summary = preview.get("summary") if isinstance(preview.get("summary"), dict) else {}
    blocking_reasons = preview.get("blocking_reasons") if isinstance(preview.get("blocking_reasons"), list) else []
    warnings = preview.get("warnings") if isinstance(preview.get("warnings"), list) else []

    st.subheader(title)
    cols = st.columns(7)
    cols[0].metric("审查状态", "可执行" if summary.get("can_execute") else "不可执行")
    cols[1].metric("账户", str(summary.get("target_account_count", 0)))
    cols[2].metric("项目", str(summary.get("planned_project_count", 0)))
    cols[3].metric("单元", str(summary.get("planned_unit_count", 0)))
    cols[4].metric("素材分配", str(summary.get("material_assignment_count", 0)))
    cols[5].metric("唯一素材", str(summary.get("unique_material_count", 0)))
    cols[6].metric("缺视频 ID", str(summary.get("missing_video_id_material_count", 0)))
    st.caption("这里展示生成计划已经选中的素材、文案、CTA（行动按钮）和卖点；素材消耗/转化按当前产品统计，不使用跨产品全局消耗。")

    if blocking_reasons:
        st.error("不能进入真实执行：" + "；".join(str(item) for item in blocking_reasons))
    else:
        st.success("执行前审查通过。")
    if warnings and use_expanders:
        with st.expander("查看风险提示", expanded=False):
            for item in warnings:
                st.warning(str(item))
    elif warnings:
        for item in warnings:
            st.warning(str(item))

    account_options = _preview_account_options(preview)
    filter_cols = st.columns([2, 1, 1, 2])
    material_query = filter_cols[0].text_input("筛选素材 ID / 视频 ID / 素材名", key=f"{key_prefix}_material_query")
    missing_video_only = filter_cols[1].checkbox("只看缺 video_id（视频 ID）", key=f"{key_prefix}_missing_video")
    min_usage_count = filter_cols[2].number_input("最小使用次数", min_value=0, value=0, step=1, key=f"{key_prefix}_min_usage")
    selected_account = filter_cols[3].selectbox("账户筛选", account_options, key=f"{key_prefix}_material_account")
    material_account_id = "" if selected_account == "全部账户" else selected_account
    material_rows = filter_preview_materials(
        preview.get("materials") or [],
        missing_video_only=missing_video_only,
        min_usage_count=int(min_usage_count or 0),
        account_id=material_account_id,
        query=material_query,
    )
    if material_rows:
        st.markdown("**已选素材（该产品维度数据）**")
        st.dataframe(
            [
                {
                    "缺 video_id": "是" if row.get("missing_video_id") else "",
                    "material_id（素材 ID）": row.get("material_id"),
                    "video_id（视频 ID）": row.get("video_id"),
                    "素材名": row.get("name"),
                    "产品": row.get("product"),
                    "源素材账户": row.get("source_advertiser_id"),
                    "该产品消耗": row.get("product_stat_cost"),
                    "该产品转化": row.get("product_convert_cnt"),
                    "使用次数": row.get("usage_count"),
                    "覆盖账户": row.get("covered_account_count"),
                    "覆盖单元": row.get("covered_unit_count"),
                    "有效创建日期": row.get("effective_create_date"),
                }
                for row in material_rows
                if isinstance(row, dict)
            ],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.warning("当前筛选下没有素材。")

    tabs = st.tabs(["文案", "CTA（行动按钮）", "卖点", "账户素材分布", "单元级明细"])
    with tabs[0]:
        st.dataframe(
            [
                {"文案": row.get("title"), "使用次数": row.get("usage_count"), "覆盖单元": row.get("covered_unit_count")}
                for row in preview.get("copywriting") or []
                if isinstance(row, dict)
            ],
            use_container_width=True,
            hide_index=True,
        )
    with tabs[1]:
        st.dataframe(
            [
                {"CTA（行动按钮）": row.get("cta"), "使用次数": row.get("usage_count"), "覆盖单元": row.get("covered_unit_count")}
                for row in preview.get("ctas") or []
                if isinstance(row, dict)
            ],
            use_container_width=True,
            hide_index=True,
        )
    with tabs[2]:
        st.dataframe(
            [
                {"卖点": row.get("selling_point"), "使用次数": row.get("usage_count"), "覆盖单元": row.get("covered_unit_count")}
                for row in preview.get("selling_points") or []
                if isinstance(row, dict)
            ],
            use_container_width=True,
            hide_index=True,
        )
    with tabs[3]:
        st.dataframe(
            [
                {
                    "账户": row.get("advertiser_id"),
                    "项目数": row.get("project_count"),
                    "单元数": row.get("unit_count"),
                    "素材分配": row.get("material_assignment_count"),
                    "唯一素材": row.get("unique_material_count"),
                }
                for row in preview.get("accounts") or []
                if isinstance(row, dict)
            ],
            use_container_width=True,
            hide_index=True,
        )
    with tabs[4]:
        unit_cols = st.columns([1, 2])
        selected_unit_account = unit_cols[0].selectbox("单元账户筛选", account_options, key=f"{key_prefix}_unit_account")
        project_query = unit_cols[1].text_input("筛选项目 / 单元", key=f"{key_prefix}_unit_query")
        unit_account_id = "" if selected_unit_account == "全部账户" else selected_unit_account
        unit_rows = filter_preview_units(
            preview.get("units") or [],
            account_id=unit_account_id,
            project_query=project_query,
        )
        st.dataframe(
            [
                {
                    "账户": row.get("advertiser_id"),
                    "项目": row.get("project_name"),
                    "单元": row.get("promotion_name"),
                    "素材数": row.get("material_count"),
                    "文案数": row.get("title_count"),
                    "CTA 数": row.get("cta_count"),
                    "卖点数": row.get("selling_point_count"),
                }
                for row in unit_rows
                if isinstance(row, dict)
            ],
            use_container_width=True,
            hide_index=True,
        )
        if use_expanders:
            _show_json_with_summary("查看单元级完整分配 JSON", {"units": unit_rows}, expanded=False)
        else:
            st.caption("完整单元分配 JSON 可在操作日志 JSON 中查看。")


def _show_create_plan_review(project_root: Path, plan_path: str) -> dict[str, Any]:
    plan_payload = _load_json_path(project_root, plan_path)
    if not plan_payload:
        return {}
    preview = build_create_plan_preview(plan_payload)
    with st.container(border=True):
        _show_create_plan_preview_panel(preview, key_prefix=f"create_plan_review_{Path(plan_path).stem}")
    return preview.get("review") if isinstance(preview.get("review"), dict) else {}


def _show_create_execute_report(report: dict[str, Any]) -> None:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    readable = report.get("readable_reference") if isinstance(report.get("readable_reference"), dict) else {}
    delivery = report.get("delivery") if isinstance(report.get("delivery"), dict) else {}
    issues = readable.get("execution_issues") if isinstance(readable.get("execution_issues"), dict) else {}
    with st.expander("执行汇报", expanded=False):
        cols = st.columns(5)
        cols[0].metric("状态", _format_status(report.get("status")))
        cols[1].metric("项目", str(summary.get("created_project_count", 0)))
        cols[2].metric("单元", str(summary.get("created_unit_count", 0)))
        cols[3].metric("绑定素材", str(summary.get("material_bind_count", 0)))
        cols[4].metric("接口调用", str(summary.get("source_external_api_calls", 0)))
        message = str(report.get("message") or "").strip()
        if message:
            st.write(message)
        if bool(issues.get("manual_review_required")):
            st.error(
                "存在需要处理的部分失败："
                f"{int(issues.get('affected_account_count') or 0)} 个账户受影响，"
                f"跳过 {int(issues.get('skipped_unit_count') or 0)} 个单元。"
            )
            accounts = issues.get("accounts") if isinstance(issues.get("accounts"), list) else []
            if accounts:
                st.table(
                    [
                        {
                            "账户": row.get("advertiser_id"),
                            "素材绑定异常": row.get("material_bind_failure_count"),
                            "跳过单元": row.get("skipped_unit_count"),
                            "错误码": "/".join(str(item) for item in row.get("codes") or []),
                            "原因": "；".join(str(item) for item in row.get("messages") or []),
                        }
                        for row in accounts
                        if isinstance(row, dict)
                    ]
                )
            rebuild = issues.get("rebuild_reference") if isinstance(issues.get("rebuild_reference"), list) else []
            if rebuild:
                with st.expander("查看补建参考", expanded=False):
                    st.table(rebuild)
        feishu = delivery.get("feishu") if isinstance(delivery.get("feishu"), dict) else {}
        if feishu:
            if bool(feishu.get("attempted")) and bool(feishu.get("ok", False)):
                st.success("飞书推送已完成。")
            elif bool(feishu.get("attempted")):
                st.error(f"飞书推送失败：{feishu.get('reason') or feishu.get('error') or 'unknown'}")
            else:
                st.info("飞书推送未启用。")
        selected = readable.get("selected_materials") if isinstance(readable.get("selected_materials"), dict) else {}
        if selected:
            st.markdown("**选材摘要**")
            cols = st.columns(3)
            cols[0].metric("素材分配", str(selected.get("assignment_count", 0)))
            cols[1].metric("唯一素材", str(selected.get("unique_material_count", 0)))
            cols[2].metric("覆盖账户", str(len(selected.get("by_account") or [])))
            by_account = selected.get("by_account") if isinstance(selected.get("by_account"), list) else []
            if by_account:
                with st.expander("查看账户选材分布", expanded=False):
                    st.table(
                        [
                            {
                                "账户": row.get("advertiser_id"),
                                "素材分配": row.get("assignment_count"),
                                "唯一素材": row.get("unique_material_count"),
                            }
                            for row in by_account[:20]
                            if isinstance(row, dict)
                        ]
                    )
            top_materials = selected.get("top_materials_by_cost") if isinstance(selected.get("top_materials_by_cost"), list) else []
            if top_materials:
                with st.expander("查看高消耗素材 Top", expanded=False):
                    st.table(top_materials[:20])
        artifact_path = str(report.get("artifact_path") or "")
        if artifact_path:
            st.caption(f"汇报结果文件：{artifact_path}")
        _show_json_with_summary("查看汇报 JSON", report, expanded=False)


def _show_create_execution_summary_card(
    *,
    task: dict[str, Any] | None = None,
    progress: dict[str, Any] | None = None,
    execute_payload: dict[str, Any] | None = None,
    report_payload: dict[str, Any] | None = None,
    expanded: bool = False,
) -> None:
    summary = build_task_status_summary(
        task=task or {},
        progress=progress or {},
        execute_payload=execute_payload or {},
        report_payload=report_payload or {},
    )
    if not any([summary.get("status"), summary.get("task_status"), summary.get("progress_operation"), execute_payload, report_payload]):
        return
    title = "任务状态与执行结果"
    with st.expander(title, expanded=expanded):
        level = str(summary.get("status_level") or "")
        message = str(summary.get("message") or "").strip()
        if level == "running":
            st.info(message or "任务正在执行，页面会自动刷新。")
        elif level == "error":
            st.error(message or "任务执行失败。")
        elif level == "warning":
            st.warning(message or "任务完成但存在需要处理的问题。")
        elif level == "success":
            st.success(message or "任务已完成。")
        elif message:
            st.write(message)

        cols = st.columns(7)
        cols[0].metric("状态", _format_status(summary.get("status")))
        cols[1].metric("任务", _format_status(summary.get("task_status")))
        cols[2].metric("进度", f"{summary.get('progress_done', 0)}/{summary.get('progress_total', 0)}")
        cols[3].metric("项目", str(summary.get("created_project_count", 0)))
        cols[4].metric("单元", str(summary.get("created_unit_count", 0)))
        cols[5].metric("绑定素材", str(summary.get("material_bind_count", 0)))
        cols[6].metric("飞书", _format_status(summary.get("feishu_status")))

        progress_percent = int(summary.get("progress_percent") or 0)
        if progress_percent or int(summary.get("progress_total") or 0) > 0:
            st.progress(progress_percent)
            progress_parts = [
                f"步骤：{summary.get('progress_operation') or '-'}",
                f"账户：{summary.get('progress_account') or '-'}",
                f"接口调用：{summary.get('external_api_calls') or 0}",
            ]
            st.caption("；".join(progress_parts))
        if summary.get("feishu_status") == "failed":
            st.error(f"飞书推送失败：{summary.get('feishu_reason') or 'unknown'}")
        if bool(summary.get("manual_review_required")):
            st.error(
                "存在需要处理的部分失败："
                f"{int(summary.get('affected_account_count') or 0)} 个账户受影响，"
                f"跳过 {int(summary.get('skipped_unit_count') or 0)} 个单元，"
                f"素材绑定异常 {int(summary.get('material_bind_failure_count') or 0)} 次。"
            )
            accounts = summary.get("issue_accounts") if isinstance(summary.get("issue_accounts"), list) else []
            if accounts:
                st.table(
                    [
                        {
                            "账户": row.get("advertiser_id"),
                            "跳过单元": row.get("skipped_unit_count"),
                            "错误码": "/".join(str(item) for item in row.get("codes") or []),
                            "原因": "；".join(str(item) for item in row.get("messages") or []),
                        }
                        for row in accounts
                        if isinstance(row, dict)
                    ]
                )
            rebuild = summary.get("rebuild_reference") if isinstance(summary.get("rebuild_reference"), list) else []
            if rebuild:
                with st.expander("查看补建参考", expanded=False):
                    st.table(rebuild)
        failure = summary.get("failure") if isinstance(summary.get("failure"), dict) else {}
        if failure:
            st.error("执行失败明细")
            st.table(
                [
                    {
                        "操作": failure.get("operation"),
                        "序号": failure.get("index"),
                        "错误码": failure.get("code"),
                        "原因": failure.get("message"),
                    }
                ]
            )
        recent_events = summary.get("recent_events") if isinstance(summary.get("recent_events"), list) else []
        if recent_events:
            with st.expander("查看最近进度事件", expanded=False):
                st.dataframe(
                    [
                        {
                            "时间": row.get("created_at") or row.get("updated_at") or "",
                            "状态": _format_status(row.get("status")),
                            "步骤": row.get("operation"),
                            "进度": f"{row.get('done', 0)}/{row.get('total', 0)}",
                            "账户": row.get("advertiser_id") or "",
                            "信息": row.get("message") or "",
                        }
                        for row in recent_events
                        if isinstance(row, dict)
                    ],
                    use_container_width=True,
                    hide_index=True,
                )


def _record_create_ui_operation(
    *,
    runs_dir: str,
    operation_type: str,
    status: str,
    actor: str,
    request: dict[str, Any],
    result: dict[str, Any],
    plan_payload: dict[str, Any] | None = None,
    extra_details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    details = create_operation_details_from_plan(plan_payload) if isinstance(plan_payload, dict) else {}
    if extra_details:
        details = {**details, **extra_details}
    return record_frontend_operation(
        runs_dir=runs_dir,
        operation_type=operation_type,
        status=status,
        actor=actor,
        request=request,
        result=result,
        details=details,
    )


def _record_simple_ui_operation(
    *,
    runs_dir: str,
    operation_type: str,
    status: str,
    actor: str = "",
    request: dict[str, Any] | None = None,
    result: dict[str, Any] | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return record_frontend_operation(
        runs_dir=runs_dir,
        operation_type=operation_type,
        status=status,
        actor=actor,
        request=request or {},
        result=result or {},
        details=details or {},
    )


def _show_create_execution_steps(
    project_root: Path,
    plan_path: str,
    timeout_seconds: int,
    runs_dir: str,
    *,
    plan_review: dict[str, Any] | None = None,
) -> None:
    st.subheader("下一步")
    st.caption("网页调用固定脚本完成检查和真实执行；真实创建前仍必须人工确认。")
    check_command = build_create_live_config_check_command(plan_path=plan_path)
    check_state_key = f"create_config_check_result_{plan_path}"
    check_return_key = f"create_config_check_return_code_{plan_path}"
    with st.container(border=True):
        st.markdown("**1. 检查真实执行配置**")
        st.caption("只检查配置、token（令牌）和账户准允许名单，不创建项目。")
        if st.button("检查真实执行配置", key=f"check_create_config_{plan_path}"):
            result = run_fixed_script(check_command, cwd=project_root, timeout_seconds=timeout_seconds)
            st.session_state[check_state_key] = result.parsed_stdout
            st.session_state[check_return_key] = result.return_code
            plan_payload = _load_json_path(project_root, plan_path)
            operation_log = _record_create_ui_operation(
                runs_dir=runs_dir,
                operation_type="create_live_config_check",
                status="completed"
                if result.ok and str(result.parsed_stdout.get("status") if isinstance(result.parsed_stdout, dict) else "") == "config_ready"
                else "failed",
                actor=str((plan_payload.get("create_request") or {}).get("owner") or ""),
                request={
                    "plan_path": plan_path,
                    "command": result.command,
                },
                result={
                    "return_code": result.return_code,
                    "artifact_path": str(result.parsed_stdout.get("artifact_path") or "") if isinstance(result.parsed_stdout, dict) else "",
                    "summary": result.parsed_stdout.get("summary") if isinstance(result.parsed_stdout, dict) else {},
                    "status": result.parsed_stdout.get("status") if isinstance(result.parsed_stdout, dict) else "",
                    "blocking_reasons": result.parsed_stdout.get("blocking_reasons") if isinstance(result.parsed_stdout, dict) else [],
                    "ok": result.ok,
                },
                plan_payload=plan_payload,
            )
            st.session_state[f"create_live_config_check_operation_log_{plan_path}"] = operation_log
            st.cache_data.clear()
        result_payload = st.session_state.get(check_state_key)
        ready = False
        if isinstance(result_payload, dict) and result_payload:
            ready = bool(result_payload.get("ok")) and str(result_payload.get("status") or "") == "config_ready"
            readiness = result_payload.get("local_config_readiness") if isinstance(result_payload.get("local_config_readiness"), dict) else {}
            if ready:
                st.success(str(readiness.get("plain_language") or "真实执行配置已就绪。"))
            else:
                reasons = result_payload.get("blocking_reasons") if isinstance(result_payload.get("blocking_reasons"), list) else []
                st.error("真实执行配置未通过。")
                if reasons:
                    st.write("阻断原因：" + "；".join(str(item) for item in reasons))
            _show_json_with_summary("查看检查结果 JSON", result_payload, expanded=False)
        operation_log = st.session_state.get(f"create_live_config_check_operation_log_{plan_path}")
        if isinstance(operation_log, dict) and operation_log:
            st.caption(f"配置检查操作日志：{operation_log.get('artifact_path')}")

    real_command = build_create_live_execute_command(plan_path=plan_path)
    progress_command = build_create_live_terminal_command(
        plan_path=plan_path,
        check_config_only=False,
        open_progress_window=True,
    )
    with st.container(border=True):
        st.markdown("**2. 真实执行**")
        st.caption("配置检查通过后，在这里确认并调用固定脚本。运行后会真实创建项目和单元。")
        _show_progress_snapshot(read_create_live_progress(runs_dir), title="最近真实执行进度")
        review_ready = bool(plan_review.get("can_execute")) if isinstance(plan_review, dict) else False
        if not review_ready:
            reasons = plan_review.get("blocking_reasons") if isinstance(plan_review, dict) and isinstance(plan_review.get("blocking_reasons"), list) else []
            st.error("执行前审查未通过，不能真实执行。" + ("阻断原因：" + "；".join(str(item) for item in reasons) if reasons else ""))
        resume_existing_plan = st.checkbox(
            "续跑已有计划（resume-existing-plan）",
            value=False,
            key=f"create_live_resume_existing_plan_{plan_path}",
            help="只在同一个计划已经部分创建、需要补齐剩余项目或单元时勾选；脚本会先按本地记录跳过已完成部分。",
        )
        confirm_text = st.text_input(
            "输入“确认执行”后解锁真实执行按钮",
            value="",
            key=f"create_live_confirm_text_{plan_path}",
        )
        confirmed = confirm_text.strip() == "确认执行"
        execute_disabled = not (ready and confirmed and review_ready)
        if not ready:
            st.info("请先完成并通过真实执行配置检查。")
        if not review_ready:
            st.info("请先修复执行前审查里的阻断原因。")
        if st.button(
            "确认执行并真实创建",
            type="primary",
            disabled=execute_disabled,
            key=f"create_live_execute_{plan_path}",
        ):
            real_command = build_create_live_execute_command(
                plan_path=plan_path,
                resume_existing_plan=resume_existing_plan,
            )
            plan_payload = _load_json_path(project_root, plan_path)
            report_command_template = build_create_live_execute_report_command(
                plan_path=plan_path,
                execute_artifact_path="{result.artifact_path}",
                push_feishu=True,
            )
            task_record = build_task_record(
                runs_dir=runs_dir,
                operation_type="create_live_execute",
                command=real_command,
                cwd=str(project_root),
                request={
                    "plan_path": plan_path,
                    "confirmed_text_matched": confirmed,
                    "resume_existing_plan": resume_existing_plan,
                },
                post_commands=[report_command_template],
            )
            task_path = write_task_record(runs_dir, task_record)
            runner_pid = start_runner(build_runner_command(task_path), cwd=project_root)
            operation_log = _record_create_ui_operation(
                runs_dir=runs_dir,
                operation_type="create_live_execute",
                status="running",
                actor=str((plan_payload.get("create_request") or {}).get("owner") or ""),
                request={
                    "plan_path": plan_path,
                    "command": real_command,
                    "post_commands": [report_command_template],
                    "confirmed_text_matched": confirmed,
                    "resume_existing_plan": resume_existing_plan,
                    "task_id": task_record["task_id"],
                    "runner_pid": runner_pid,
                },
                result={
                    "task_id": task_record["task_id"],
                    "task_artifact_path": task_record["artifact_path"],
                    "status": "running",
                    "ok": False,
                },
                plan_payload=plan_payload,
                extra_details={
                    "task_id": task_record["task_id"],
                    "task_artifact_path": task_record["artifact_path"],
                },
            )
            st.session_state[f"create_live_operation_log_{plan_path}"] = operation_log
            st.session_state[f"create_live_execute_task_{plan_path}"] = task_record
            st.cache_data.clear()
            st.success(f"真实执行任务已启动：{task_record['task_id']}。可在任务中心查看进度、stdout（标准输出）、stderr（标准错误）和结果。")
        task_record = st.session_state.get(f"create_live_execute_task_{plan_path}")
        if isinstance(task_record, dict) and task_record:
            latest_task = _load_frontend_task_record(runs_dir, str(task_record.get("task_id") or "")) or task_record
            if str(latest_task.get("status") or "").startswith("running"):
                components.html(
                    "<script>setTimeout(() => window.parent.location.reload(), 3000)</script>",
                    height=0,
                    width=0,
                )
            st.subheader("当前真实执行任务")
            _show_progress_snapshot(read_create_live_progress(runs_dir), title="当前执行进度")
            execute_payload, report_payload = _execution_payloads_from_task(project_root, latest_task)
            progress_payload = read_create_live_progress(runs_dir)
            _show_create_execution_summary_card(
                task=latest_task,
                progress=progress_payload,
                execute_payload=execute_payload,
                report_payload=report_payload,
                expanded=True,
            )
            _show_background_task_detail(project_root, runs_dir, latest_task)
        stored = st.session_state.get(f"create_live_execute_result_{plan_path}")
        if isinstance(stored, dict) and stored:
            status = str(stored.get("status") or "")
            if bool(stored.get("ok")):
                st.success(f"真实执行完成：{status or 'ok'}")
            else:
                st.error(f"真实执行未完成：{status or 'blocked'}")
            artifact_path = str(stored.get("artifact_path") or "")
            if artifact_path:
                st.caption(f"执行结果文件：{artifact_path}")
            _show_json_with_summary("查看真实执行结果 JSON", stored, expanded=False)
        raw_result = st.session_state.get(f"create_live_execute_raw_{plan_path}")
        if isinstance(raw_result, dict) and raw_result and not bool((stored or {}).get("ok") if isinstance(stored, dict) else False):
            with st.expander("查看真实执行原始输出", expanded=False):
                st.code(_format_shell_command(raw_result.get("command") or [], cwd=project_root), language="bash")
                if str(raw_result.get("stdout") or "").strip():
                    st.code(str(raw_result.get("stdout") or ""), language="text")
                if str(raw_result.get("stderr") or "").strip():
                    st.code(str(raw_result.get("stderr") or ""), language="text")
        stored_report = st.session_state.get(f"create_live_execute_report_result_{plan_path}")
        if isinstance(stored_report, dict) and stored_report:
            _show_create_execute_report(stored_report)
        operation_log = st.session_state.get(f"create_live_operation_log_{plan_path}")
        if isinstance(operation_log, dict) and operation_log:
            st.caption(f"前端操作日志：{operation_log.get('artifact_path')}")
            _show_json_with_summary("查看前端操作日志 JSON", operation_log, expanded=False)
        with st.expander("查看备用终端命令", expanded=False):
            st.caption("仅用于前端执行异常时排查；正常情况下不需要复制命令。")
            st.code(_format_shell_command(progress_command, cwd=project_root), language="bash")


def _dashboard(runs_dir: str) -> None:
    st.header("首页")
    st.caption("只读展示最近本地产物，不调用平台接口。")
    scheduler_payload = _latest(runs_dir, "scheduler_status")
    if scheduler_payload:
        _show_scheduler_status_panel(scheduler_payload, compact=True)
    workflows = [
        ("投放巡检", "delivery_patrol"),
        ("投放巡检建议", "delivery_patrol_suggestions"),
        ("创建执行", "create_live_execute_once"),
        ("前端操作日志", "frontend_operation_log"),
        ("AI 创建模板草稿", "ai_create_template_drafts"),
    ]
    for title, workflow in workflows:
        _show_summary(title, _latest(runs_dir, workflow))


def _scheduler_status_page(runs_dir: str) -> None:
    st.header("定时任务")
    st.caption("只读展示 scheduler_status（定时任务状态）最近结果；这里不触发任何真实业务执行。")
    payload = _latest(runs_dir, "scheduler_status")
    if not payload:
        st.info("还没有定时任务状态结果。")
        return
    _show_scheduler_status_panel(payload, compact=False)
    _show_json_with_summary("查看 scheduler_status JSON", payload, expanded=False)


def _delivery_patrol(project_root: Path, runs_dir: str, timeout_seconds: int) -> None:
    st.header("投放巡检")
    st.caption("运行固定只读巡检脚本，结果写入 data/runs（运行结果目录）。")
    if st.button("运行只读巡检脚本", type="primary"):
        command = build_delivery_patrol_command(readonly=True)
        result = run_fixed_script(command, cwd=project_root, timeout_seconds=timeout_seconds)
        operation_log = _record_simple_ui_operation(
            runs_dir=runs_dir,
            operation_type="delivery_patrol_run",
            status="completed" if result.ok else "failed",
            request={"command": command, "readonly": True},
            result={
                "return_code": result.return_code,
                "artifact_path": str(result.parsed_stdout.get("artifact_path") or "") if isinstance(result.parsed_stdout, dict) else "",
                "status": result.parsed_stdout.get("status") if isinstance(result.parsed_stdout, dict) else "",
                "ok": result.ok,
            },
        )
        st.cache_data.clear()
        _show_script_result(result)
        st.caption(f"前端操作日志：{operation_log.get('artifact_path')}")
    patrol = _latest(runs_dir, "delivery_patrol")
    _show_summary("最近巡检结果", patrol)
    message = str(patrol.get("message") or "")
    if message:
        st.text_area("飞书摘要", value=message, height=260)
    suggestions = patrol.get("delivery_patrol_suggestions")
    if isinstance(suggestions, dict):
        st.subheader("同频建议摘要")
        _show_json_with_summary("查看建议摘要 JSON", suggestions.get("summary") or suggestions, expanded=False)


def _create(project_root: Path, config: dict[str, Any], timeout_seconds: int) -> None:
    st.header("创建计划")
    st.caption("只生成创建计划，不执行真实创建。预算、出价、项目数、单元数、素材规则来自固定创建模式。")
    mode_dir = PROJECT_ROOT / str(config.get("create_modes_dir") or "configs/create-modes")
    drafts_dir = PROJECT_ROOT / str(config.get("create_mode_drafts_dir") or "configs/create-mode-drafts")
    modes = _modes(str(mode_dir))
    if not modes:
        st.warning("未找到创建模式配置。")
        return
    products = _products(str(PROJECT_ROOT / str(config.get("products_dir") or "configs/products")))
    product_labels = ["全部产品"]
    product_label_to_key = {"全部产品": ""}
    for product in products:
        label = product_label(product)
        product_labels.append(label)
        product_label_to_key[label] = product.get("product_key", "")
    selected_product_label = st.selectbox("产品", product_labels, key="create_product_filter")
    selected_product_key = product_label_to_key.get(selected_product_label, "")
    if selected_product_key:
        modes = [row for row in modes if str(row.get("product_key") or "").strip() == selected_product_key]
    if not modes:
        st.warning("当前产品没有可用创建模板。")
        return
    labels = [row.get("display_name") or mode_label(row) for row in modes]
    label_to_mode = {label: row for label, row in zip(labels, modes)}
    selected = st.selectbox("固定创建模式", labels)
    selected_mode = label_to_mode[selected]
    mode_detail = load_create_mode(mode_dir, selected_mode["mode_key"], selected_mode.get("product_key", ""))
    template_dir = PROJECT_ROOT / "configs/create-templates"
    template_catalog_path = _create_template_catalog_path_for_mode(mode_detail)
    template_catalog = _create_template_catalog(str(template_catalog_path))
    product_config = _product_config_for_mode(mode_detail, str(PROJECT_ROOT / "configs/products")) if mode_detail else {}
    if mode_detail:
        st.caption(f"当前基础模板文件：{template_catalog_path}")
        _show_mode_detail(mode_detail, template_catalog=template_catalog, product_config=product_config)
        _mode_draft_editor(
            mode_detail,
            drafts_dir=drafts_dir,
            mode_dir=mode_dir,
            template_catalog=template_catalog,
            runs_dir=str(config.get("runs_dir") or "data/runs"),
        )
        _base_template_editor(
            mode_detail,
            template_catalog=template_catalog,
            template_dir=template_dir,
            runs_dir=str(config.get("runs_dir") or "data/runs"),
        )
    accounts = st.text_area("账户 ID，多个账户用逗号或换行分隔", height=100, key="create_accounts")
    account_count = len(split_account_ids(accounts))
    if account_count:
        st.caption(f"当前识别到账户 {account_count} 个。")
    else:
        st.warning("请先填写至少一个账户 ID，再生成创建计划。")
    owner = st.text_input("负责人", value=str(config.get("default_owner") or "郭靖"), key="create_owner")
    target_date = st.text_input("目标日期，可空", value="", key="create_target_date")
    cols = st.columns(2)
    run_cpa_bid = cols[0].text_input("本次项目出价，空为不写", value="", key="create_run_cpa_bid")
    run_roi_coefficient = cols[1].text_input("本次 ROI 系数，空为不写", value="", key="create_run_roi")
    if st.button("生成创建计划", type="primary", disabled=account_count == 0):
        mode = selected_mode["mode_key"]
        try:
            command = build_create_plan_command(
                mode=mode,
                accounts=accounts,
                owner=owner,
                target_date=target_date,
                product_key=selected_mode.get("product_key", ""),
                template_catalog=str(template_catalog_path.relative_to(PROJECT_ROOT))
                if template_catalog_path.is_relative_to(PROJECT_ROOT)
                else str(template_catalog_path),
                cpa_bid=run_cpa_bid,
                roi_coefficient=run_roi_coefficient,
            )
        except ValueError as exc:
            st.error(str(exc))
            return
        result = run_fixed_script(command, cwd=project_root, timeout_seconds=timeout_seconds)
        st.cache_data.clear()
        if result.ok:
            st.success(f"创建计划已生成，退出码={result.return_code}")
        else:
            st.error(f"创建计划生成失败，退出码={result.return_code}")
            _show_script_result(result)
        artifact_path = result.parsed_stdout.get("artifact_path") if result.parsed_stdout else ""
        if artifact_path:
            plan_payload = _load_json_path(project_root, str(artifact_path))
            plan_review = build_create_plan_review(plan_payload) if plan_payload else {}
            operation_log = _record_create_ui_operation(
                runs_dir=str(config.get("runs_dir") or "data/runs"),
                operation_type="create_plan_generate",
                status="completed" if result.ok else "failed",
                actor=owner.strip() or str(config.get("default_owner") or ""),
                request={
                    "mode": mode,
                    "product_key": selected_mode.get("product_key", ""),
                    "accounts": split_account_ids(accounts),
                    "owner": owner,
                    "target_date": target_date,
                    "cpa_bid": run_cpa_bid,
                    "roi_coefficient": run_roi_coefficient,
                    "command": command,
                },
                result={
                    "return_code": result.return_code,
                    "artifact_path": str(artifact_path),
                    "summary": result.parsed_stdout.get("summary") if isinstance(result.parsed_stdout, dict) else {},
                    "status": result.parsed_stdout.get("status") if isinstance(result.parsed_stdout, dict) else "",
                    "ok": result.ok,
                },
                plan_payload=plan_payload,
                extra_details={
                    "review": {
                        "can_execute": bool(plan_review.get("can_execute")),
                        "summary": plan_review.get("summary") if isinstance(plan_review.get("summary"), dict) else {},
                        "blocking_reasons": plan_review.get("blocking_reasons") if isinstance(plan_review.get("blocking_reasons"), list) else [],
                        "warnings": plan_review.get("warnings") if isinstance(plan_review.get("warnings"), list) else [],
                    }
                },
            )
            st.session_state["create_plan_artifact_path"] = str(artifact_path)
            st.session_state["create_plan_summary"] = _create_plan_summary(
                project_root,
                str(artifact_path),
                result.parsed_stdout.get("summary") if isinstance(result.parsed_stdout.get("summary"), dict) else {},
            )
            st.session_state["create_plan_operation_log"] = operation_log
            st.session_state.pop("create_config_check_result", None)
            st.caption(f"前端操作日志：{operation_log.get('artifact_path')}")
            _show_json_with_summary("查看生成结果 JSON", result.parsed_stdout, expanded=False)
        else:
            operation_log = _record_create_ui_operation(
                runs_dir=str(config.get("runs_dir") or "data/runs"),
                operation_type="create_plan_generate",
                status="failed",
                actor=owner.strip() or str(config.get("default_owner") or ""),
                request={
                    "mode": mode,
                    "product_key": selected_mode.get("product_key", ""),
                    "accounts": split_account_ids(accounts),
                    "owner": owner,
                    "target_date": target_date,
                    "cpa_bid": run_cpa_bid,
                    "roi_coefficient": run_roi_coefficient,
                    "command": command,
                },
                result={
                    "return_code": result.return_code,
                    "stdout": result.stdout[-4000:],
                    "stderr": result.stderr[-4000:],
                    "ok": result.ok,
                },
            )
            st.session_state["create_plan_operation_log"] = operation_log
            st.caption(f"前端操作日志：{operation_log.get('artifact_path')}")
    plan_path = str(st.session_state.get("create_plan_artifact_path") or "")
    if plan_path:
        summary = st.session_state.get("create_plan_summary")
        if not isinstance(summary, dict) or not summary:
            summary = _create_plan_summary(project_root, plan_path)
        _show_create_plan_summary(summary)
        review = _show_create_plan_review(project_root, plan_path)
        _show_create_execution_steps(
            project_root,
            plan_path,
            timeout_seconds,
            str(config.get("runs_dir") or "data/runs"),
            plan_review=review,
        )


def _product_management(config: dict[str, Any]) -> None:
    st.header("产品管理")
    st.caption("只读展示产品配置，支持复制为草稿。草稿不会进入真实创建。")
    product_dir = PROJECT_ROOT / str(config.get("products_dir") or "configs/products")
    drafts_dir = PROJECT_ROOT / str(config.get("product_drafts_dir") or "configs/product-drafts")
    mode_dir = PROJECT_ROOT / str(config.get("create_modes_dir") or "configs/create-modes")
    products = _products(str(product_dir))
    if not products:
        st.warning("未找到产品配置。")
        return

    labels = [product_label(row) for row in products]
    selected_label = st.selectbox("产品", labels)
    selected_product = products[labels.index(selected_label)]
    product = load_product_config(product_dir, selected_product["product_key"])
    foundation = product.get("foundation") if isinstance(product.get("foundation"), dict) else {}
    automation = product.get("automation") if isinstance(product.get("automation"), dict) else {}
    account_discovery = automation.get("account_discovery") if isinstance(automation.get("account_discovery"), dict) else {}
    material_daily_sync = automation.get("material_daily_sync") if isinstance(automation.get("material_daily_sync"), dict) else {}
    source_material_auto_push = automation.get("source_material_auto_push") if isinstance(automation.get("source_material_auto_push"), dict) else {}
    source_material_preload = automation.get("source_material_preload") if isinstance(automation.get("source_material_preload"), dict) else {}
    delivery_patrol = automation.get("delivery_patrol") if isinstance(automation.get("delivery_patrol"), dict) else {}
    missing = product_config_missing_fields(product)

    with st.container(border=True):
        st.subheader("产品基础配置")
        cols = st.columns(4)
        cols[0].metric("产品键", str(product.get("product_key") or "-"))
        cols[1].metric("产品名", str(product.get("product") or "-"))
        cols[2].metric("平台", str(product.get("platform") or "-"))
        cols[3].metric("缺失字段", str(len(missing)))
        base_rows = [
            ("源素材账户", product.get("source_advertiser_id")),
            ("组织 ID", product.get("organization_id")),
            ("账户准允许名单", product.get("allowed_target_accounts_path")),
            ("账户备注规则", product.get("account_remark_pattern")),
            ("有效触点链接", foundation.get("effective_touch_url")),
            ("锚点", f"{foundation.get('anchor_id') or '-'} / {foundation.get('anchor_type') or '-'} / {foundation.get('anchor_related_type') or '-'}"),
            ("落地页", foundation.get("landing_url")),
            ("产品图", foundation.get("product_image_id")),
            ("固定封面", foundation.get("fixed_video_cover_id")),
            ("小程序实例", foundation.get("micro_app_instance_id")),
            ("小程序类型", foundation.get("micro_promotion_type")),
        ]
        st.table([{"配置项": key, "当前值": str(value or "-")} for key, value in base_rows])
        if missing:
            st.error("字段不完整：" + "；".join(missing))
        else:
            st.success("产品配置字段完整。")

    with st.container(border=True):
        st.subheader("自动化配置")
        automation_rows = [
            ("总开关", "启用" if automation.get("enabled", True) else "关闭"),
            ("账户名关键词", account_discovery.get("account_name_keyword")),
            ("账户备注匹配", account_discovery.get("account_remark_equals")),
            ("每日素材入库", "启用" if material_daily_sync.get("enabled") else "关闭"),
            ("源素材账户自动补材", "启用" if source_material_auto_push.get("enabled") else "关闭"),
            ("源素材预推送", "启用" if source_material_preload.get("enabled") else "关闭"),
            ("预推送目标范围", source_material_preload.get("target_scope")),
            ("投放巡检", "启用" if delivery_patrol.get("enabled") else "关闭"),
        ]
        st.table([{"配置项": key, "当前值": str(value or "-")} for key, value in automation_rows])

    referencing_modes = []
    for row in _modes(str(mode_dir)):
        mode = load_create_mode(mode_dir, row["mode_key"], row.get("product_key", ""))
        if str(mode.get("product_key") or "").strip() == str(product.get("product_key") or "").strip():
            referencing_modes.append(
                {
                    "创建模式": mode.get("display_name") or row["display_name"],
                    "模式键": mode.get("mode_key") or row["mode_key"],
                    "基础模板": mode.get("template_key") or "-",
                }
            )
    with st.container(border=True):
        st.subheader("引用该产品的创建模式")
        if referencing_modes:
            st.table(referencing_modes)
        else:
            st.caption("暂无创建模式引用该产品。")

    with st.expander("复制为产品草稿", expanded=False):
        draft_key = st.text_input("草稿产品键", value=f"{product.get('product_key')}_draft", key="product_draft_key")
        draft_name = st.text_input("产品名", value=str(product.get("product") or ""), key="product_draft_name")
        draft_platform = st.text_input("平台", value=str(product.get("platform") or "WECHAT_GAME"), key="product_draft_platform")
        source_advertiser_id = st.text_input("源素材账户", value=str(product.get("source_advertiser_id") or ""), key="product_draft_source")
        organization_id = st.text_input("组织 ID", value=str(product.get("organization_id") or ""), key="product_draft_org")
        allowed_path = st.text_input("账户准允许名单", value=str(product.get("allowed_target_accounts_path") or ""), key="product_draft_allowed")
        remark_pattern = st.text_input("账户备注规则", value=str(product.get("account_remark_pattern") or ""), key="product_draft_remark")
        st.markdown("**自动化**")
        automation_enabled = st.checkbox("启用该产品自动化", value=bool(automation.get("enabled", True)), key="product_draft_auto_enabled")
        account_name_keyword = st.text_input(
            "账户名关键词",
            value=str(account_discovery.get("account_name_keyword") or product.get("product") or ""),
            key="product_draft_account_keyword",
        )
        account_remark_equals = st.text_input(
            "账户备注匹配",
            value=str(account_discovery.get("account_remark_equals") or product.get("account_remark_pattern") or ""),
            key="product_draft_account_remark_equals",
        )
        cols = st.columns(4)
        enable_material_daily = cols[0].checkbox("每日素材入库", value=bool(material_daily_sync.get("enabled", True)), key="product_draft_enable_material_daily")
        enable_auto_push = cols[1].checkbox("源素材自动补材", value=bool(source_material_auto_push.get("enabled", True)), key="product_draft_enable_auto_push")
        enable_preload = cols[2].checkbox("源素材预推送", value=bool(source_material_preload.get("enabled", True)), key="product_draft_enable_preload")
        enable_patrol = cols[3].checkbox("投放巡检", value=bool(delivery_patrol.get("enabled", True)), key="product_draft_enable_patrol")
        preload_scope = st.selectbox(
            "预推送目标范围",
            ["allowed_accounts", "today_spent", "yesterday_spent"],
            index=["allowed_accounts", "today_spent", "yesterday_spent"].index(
                str(source_material_preload.get("target_scope") or "allowed_accounts")
                if str(source_material_preload.get("target_scope") or "allowed_accounts") in {"allowed_accounts", "today_spent", "yesterday_spent"}
                else "allowed_accounts"
            ),
            key="product_draft_preload_scope",
        )
        st.markdown("**基础资源**")
        effective_touch_url = st.text_area("有效触点链接", value=str(foundation.get("effective_touch_url") or ""), height=100, key="product_draft_touch")
        cols = st.columns(3)
        anchor_id = cols[0].text_input("锚点 ID", value=str(foundation.get("anchor_id") or ""), key="product_draft_anchor")
        anchor_type = cols[1].text_input("锚点类型", value=str(foundation.get("anchor_type") or ""), key="product_draft_anchor_type")
        anchor_related_type = cols[2].text_input("锚点关联类型", value=str(foundation.get("anchor_related_type") or ""), key="product_draft_anchor_related")
        landing_url = st.text_input("落地页", value=str(foundation.get("landing_url") or ""), key="product_draft_landing")
        product_image_id = st.text_input("产品图", value=str(foundation.get("product_image_id") or ""), key="product_draft_image")
        fixed_video_cover_id = st.text_input("固定封面", value=str(foundation.get("fixed_video_cover_id") or ""), key="product_draft_cover")
        cols = st.columns(2)
        micro_app_instance_id = cols[0].text_input("小程序实例", value=str(foundation.get("micro_app_instance_id") or ""), key="product_draft_micro_app")
        micro_promotion_type = cols[1].text_input("小程序类型", value=str(foundation.get("micro_promotion_type") or "WECHAT_GAME"), key="product_draft_micro_type")

        if st.button("保存产品草稿", type="primary"):
            draft = {
                "product_key": draft_key.strip(),
                "product": draft_name.strip(),
                "platform": draft_platform.strip(),
                "source_advertiser_id": source_advertiser_id.strip(),
                "organization_id": organization_id.strip(),
                "allowed_target_accounts_path": allowed_path.strip(),
                "account_remark_pattern": remark_pattern.strip(),
                "automation": {
                    "enabled": bool(automation_enabled),
                    "account_discovery": {
                        "account_name_keyword": account_name_keyword.strip(),
                        "account_remark_equals": account_remark_equals.strip(),
                    },
                    "material_daily_sync": {
                        "enabled": bool(enable_material_daily),
                        "source": "account_name_keyword",
                        "min_spend": 0,
                    },
                    "source_material_auto_push": {
                        "enabled": bool(enable_auto_push),
                        "from_spent_accounts": True,
                    },
                    "source_material_preload": {
                        "enabled": bool(enable_preload),
                        "target_scope": preload_scope,
                    },
                    "delivery_patrol": {
                        "enabled": bool(enable_patrol),
                        "account_scope": "account_remark",
                    },
                },
                "foundation": {
                    "effective_touch_url": effective_touch_url.strip(),
                    "anchor_id": anchor_id.strip(),
                    "anchor_type": anchor_type.strip(),
                    "anchor_related_type": anchor_related_type.strip(),
                    "landing_url": landing_url.strip(),
                    "product_image_id": product_image_id.strip(),
                    "fixed_video_cover_id": fixed_video_cover_id.strip(),
                    "micro_app_instance_id": micro_app_instance_id.strip(),
                    "micro_promotion_type": micro_promotion_type.strip(),
                },
            }
            draft_missing = product_config_missing_fields(draft)
            output = save_product_draft(drafts_dir, draft)
            st.success(f"产品草稿已保存：{output}")
            if draft_missing:
                st.warning("草稿仍缺字段：" + "；".join(draft_missing))
            else:
                st.caption("草稿字段完整；后续仍需通过固定发布脚本转成正式产品配置。")
                publish_command = build_product_config_publish_command(
                    draft_path=str(output.relative_to(PROJECT_ROOT)) if output.is_relative_to(PROJECT_ROOT) else str(output)
                )
                st.code(_format_shell_command(publish_command, cwd=PROJECT_ROOT), language="bash")
            _show_json_with_summary("查看产品草稿 JSON", draft, expanded=False)

    with st.expander("生成账户准允许名单", expanded=False):
        st.caption("用于新产品真实创建前限定可操作账户。只写本地 JSON，不调用平台接口。")
        allowed_product = st.text_input(
            "名单产品名",
            value=str(product.get("product") or "点点英雄"),
            key="allowed_product_name",
        )
        allowed_channel = st.text_input("渠道", value="wx", key="allowed_channel")
        allowed_prefix = st.text_input(
            "账户显示名前缀",
            value=f"{allowed_product}-微小-郭靖",
            key="allowed_account_prefix",
        )
        allowed_accounts_raw = st.text_area(
            "账户 ID，多个账户用逗号或换行分隔",
            height=160,
            key="allowed_accounts_raw",
        )
        allowed_output_path = st.text_input(
            "账户准允许名单输出路径",
            value=f"configs/allowed-create-accounts.{str(product.get('product_key') or 'new-product')}.local.json",
            key="allowed_output_path",
        )
        account_ids = split_account_ids(allowed_accounts_raw)
        st.caption(f"当前识别到账户 {len(account_ids)} 个。")
        if st.button("保存账户准允许名单", type="primary", key="save_allowed_accounts"):
            allowed_config = build_allowed_create_accounts_config(
                product=allowed_product,
                channel=allowed_channel,
                account_ids=account_ids,
                account_name_prefix=allowed_prefix,
            )
            try:
                output = save_allowed_create_accounts_config(PROJECT_ROOT / allowed_output_path, allowed_config)
            except Exception as exc:
                st.error(f"保存失败：{exc}")
            else:
                st.success(f"账户准允许名单已保存：{output}")
                _show_json_with_summary("查看账户准允许名单 JSON", allowed_config, expanded=False)


def _project_management(project_root: Path, timeout_seconds: int, runs_dir: str) -> None:
    st.header("项目管理配置")
    st.caption("按实时数据生成项目管理 JSON；账户备注也归入项目管理固定链路。真实执行仍需单独确认后调用固定执行脚本。")
    st.subheader("项目更新")
    advertiser_ids = st.text_area("账户 ID，多个账户用逗号或换行分隔", height=100, key="project_accounts")
    action_labels = {
        "删除项目": "delete_project",
        "开启/关闭项目": "status_update",
        "调整预算": "budget_update",
        "调整出价": "bid_update",
        "调整 ROI 系数": "roi_coeff_update",
    }
    action_label = st.selectbox("动作", list(action_labels))
    action_type = action_labels[action_label]
    project_update_id = st.text_input("配置 ID", value="ui-project-filter", key="project_update_id")
    name_contains = st.text_input("项目名包含，可空", key="project_name_contains")
    window_labels = {"今天": "today", "昨天": "yesterday", "近 3 天": "last_3_days"}
    spend_window = window_labels[st.selectbox("数据窗口", list(window_labels))]
    metric_labels = {
        "消耗": "stat_cost",
        "注册数": "active_register",
        "注册成本": "register_cost",
        "计费时间转化数": "billing_convert_cnt",
        "计费时间转化成本": "billing_conversion_cost",
        "计费当日付费 ROI": "billing_1day_pay_roi",
    }
    metric_field = metric_labels[st.selectbox(
        "筛选字段",
        list(metric_labels),
    )]
    op_labels = {"小于": "lt", "小于等于": "lte", "大于": "gt", "大于等于": "gte", "等于": "eq"}
    metric_op = op_labels[st.selectbox("比较符", list(op_labels))]
    metric_value = st.text_input("筛选值", value="100", key="project_metric_value")
    opt_status = ""
    budget = ""
    cpa_bid = ""
    roi_goal = ""
    if action_type == "status_update":
        status_labels = {"关闭": "DISABLE", "开启": "ENABLE"}
        opt_status = status_labels[st.selectbox("目标状态", list(status_labels))]
    elif action_type == "budget_update":
        budget = st.text_input("预算", value="", key="project_budget")
    elif action_type == "bid_update":
        cpa_bid = st.text_input("项目出价", value="", key="project_cpa_bid")
    elif action_type == "roi_coeff_update":
        roi_goal = st.text_input("ROI 系数", value="", key="project_roi_goal")
    output_path = st.text_input("输出 JSON 路径", value="configs/project-updates/ui-project-filter.local.json", key="project_output_path")
    if st.button("生成项目管理 JSON", type="primary"):
        command = build_project_filter_command(
            project_update_id=project_update_id,
            advertiser_ids=advertiser_ids,
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
        operation_log = _record_simple_ui_operation(
            runs_dir=runs_dir,
            operation_type="project_management_config_generate",
            status="completed" if result.ok else "failed",
            request={
                "command": command,
                "advertiser_ids": split_account_ids(advertiser_ids),
                "action_type": action_type,
                "spend_window": spend_window,
                "metric_field": metric_field,
                "metric_op": metric_op,
                "metric_value": metric_value,
            },
            result={
                "return_code": result.return_code,
                "artifact_path": str(result.parsed_stdout.get("artifact_path") or result.parsed_stdout.get("project_update_path") or "") if isinstance(result.parsed_stdout, dict) else "",
                "status": result.parsed_stdout.get("status") if isinstance(result.parsed_stdout, dict) else "",
                "ok": result.ok,
            },
            details={"accounts": [{"advertiser_id": item} for item in split_account_ids(advertiser_ids)]},
        )
        st.cache_data.clear()
        _show_script_result(result)
        st.caption(f"前端操作日志：{operation_log.get('artifact_path')}")
        project_update_path = result.parsed_stdout.get("project_update_path") if result.parsed_stdout else ""
        if project_update_path:
            remember_execution_path(st.session_state, "project_update_execute_path", str(project_update_path))

    project_update_execute_path = resolve_optional_execution_path(
        st.session_state,
        "project_update_execute_path",
        output_path,
        project_root=project_root,
    )
    if project_update_execute_path:
        project_update_payload = _load_json_path(project_root, project_update_execute_path)
        _run_confirmed_execution(
            title="项目管理真实执行",
            command=build_project_update_execute_command(project_update_path=project_update_execute_path, execute=True),
            project_root=project_root,
            timeout_seconds=timeout_seconds,
            state_key=f"project_update_{project_update_execute_path}",
            runs_dir=runs_dir,
            operation_type="project_management_execute",
            request={"project_update_path": project_update_execute_path},
            review=build_project_update_execution_review(project_update_payload),
        )

    st.divider()
    st.subheader("账户备注修改")
    st.caption("用于批量修改 account_remark（账户备注）。只生成 JSON 配置；真实执行仍需人工确认。")
    remark_accounts = st.text_area("备注账户 ID，多个账户用逗号或换行分隔", height=100, key="remark_accounts")
    remark_value = st.text_input("目标账户备注", value="点点英雄-微小-郭靖", key="remark_value")
    remark_update_id = st.text_input("备注配置 ID", value="ui-account-remark-update", key="remark_update_id")
    remark_output_path = st.text_input(
        "备注配置输出 JSON 路径",
        value="configs/account-updates/ui-account-remark-update.local.json",
        key="remark_output_path",
    )
    if st.button("生成账户备注 JSON", type="primary", key="build_account_remark_json"):
        command = build_account_remark_config_command(
            update_id=remark_update_id,
            remark=remark_value,
            accounts=remark_accounts,
            output_path=remark_output_path,
        )
        result = run_fixed_script(command, cwd=project_root, timeout_seconds=timeout_seconds)
        operation_log = _record_simple_ui_operation(
            runs_dir=runs_dir,
            operation_type="account_remark_config_generate",
            status="completed" if result.ok else "failed",
            request={
                "command": command,
                "accounts": split_account_ids(remark_accounts),
                "remark": remark_value,
            },
            result={
                "return_code": result.return_code,
                "artifact_path": str(result.parsed_stdout.get("artifact_path") or "") if isinstance(result.parsed_stdout, dict) else "",
                "status": result.parsed_stdout.get("status") if isinstance(result.parsed_stdout, dict) else "",
                "ok": result.ok,
            },
            details={"accounts": [{"advertiser_id": item} for item in split_account_ids(remark_accounts)]},
        )
        st.cache_data.clear()
        _show_script_result(result)
        st.caption(f"前端操作日志：{operation_log.get('artifact_path')}")
        account_remark_path = result.parsed_stdout.get("artifact_path") if result.parsed_stdout else ""
        if account_remark_path:
            remember_execution_path(st.session_state, "account_remark_update_path", str(account_remark_path))

    account_remark_update_path = resolve_optional_execution_path(
        st.session_state,
        "account_remark_update_path",
        remark_output_path,
        project_root=project_root,
    )
    if account_remark_update_path:
        check_command = build_account_remark_execute_command(
            account_remark_update_path=account_remark_update_path,
            execute=False,
        )
        execute_command = build_account_remark_execute_command(
            account_remark_update_path=account_remark_update_path,
            execute=True,
        )
        with st.container(border=True):
            st.markdown("**固定命令**")
            st.caption("第一条只检查并生成预览；第二条是真实执行命令，必须确认后再运行。")
            st.code(_format_shell_command(check_command, cwd=project_root), language="bash")
        _run_confirmed_execution(
            title="账户备注真实执行",
            command=execute_command,
            project_root=project_root,
            timeout_seconds=timeout_seconds,
            state_key=f"account_remark_{account_remark_update_path}",
            runs_dir=runs_dir,
            operation_type="account_remark_execute",
            request={"account_remark_update_path": account_remark_update_path},
            review=build_account_remark_execution_review(_load_json_path(project_root, account_remark_update_path)),
        )


def _ai_template_drafts(project_root: Path, runs_dir: str, timeout_seconds: int) -> None:
    st.header("AI 创建模板草稿")
    st.caption("只生成草稿，不写人工模板，不生成创建计划，不执行真实创建。")
    if st.button("生成 AI 创建模板草稿", type="primary"):
        command = build_ai_template_drafts_command()
        result = run_fixed_script(command, cwd=project_root, timeout_seconds=timeout_seconds)
        operation_log = _record_simple_ui_operation(
            runs_dir=runs_dir,
            operation_type="ai_template_drafts_generate",
            status="completed" if result.ok else "failed",
            request={"command": command},
            result={
                "return_code": result.return_code,
                "artifact_path": str(result.parsed_stdout.get("artifact_path") or "") if isinstance(result.parsed_stdout, dict) else "",
                "status": result.parsed_stdout.get("status") if isinstance(result.parsed_stdout, dict) else "",
                "ok": result.ok,
            },
        )
        st.cache_data.clear()
        _show_script_result(result)
        st.caption(f"前端操作日志：{operation_log.get('artifact_path')}")
    payload = _latest(runs_dir, "ai_create_template_drafts")
    _show_summary("最近 AI 草稿结果", payload)
    drafts = payload.get("drafts") if isinstance(payload.get("drafts"), list) else []
    for draft in drafts:
        name = str(draft.get("draft_name") or draft.get("draft_key") or "draft")
        with st.expander(name):
            _show_json_with_summary("查看 AI 草稿 JSON", draft, expanded=False)


def _task_center(project_root: Path, runs_dir: str) -> None:
    st.header("任务中心")
    st.caption("展示前端触发过的固定脚本任务。这里不调用平台接口，只读取本地操作日志和执行结果文件。")
    _show_progress_snapshot(read_create_live_progress(runs_dir), title="最近真实执行进度")
    background_rows = load_frontend_task_rows(runs_dir, limit=80)
    if background_rows:
        st.subheader("后台任务")
        running_count = sum(1 for row in background_rows if str(row.get("status") or "").startswith("running"))
        completed_count = sum(1 for row in background_rows if str(row.get("status") or "") == "completed")
        failed_count = sum(1 for row in background_rows if str(row.get("status") or "") == "failed")
        cols = st.columns(4)
        cols[0].metric("总任务", str(len(background_rows)))
        cols[1].metric("执行中", str(running_count))
        cols[2].metric("已完成", str(completed_count))
        cols[3].metric("失败", str(failed_count))
        if running_count:
            components.html(
                "<script>setTimeout(() => window.parent.location.reload(), 3000)</script>",
                height=0,
                width=0,
            )
        st.dataframe(
            [
                {
                    "任务ID": row.get("task_id"),
                    "操作": row.get("operation_type"),
                    "状态": _format_status(row.get("status")),
                    "退出码": row.get("return_code"),
                    "执行结果": row.get("execute_artifact_path"),
                    "汇报结果": row.get("report_artifact_path"),
                    "更新时间": row.get("updated_at"),
                }
                for row in background_rows
            ],
            use_container_width=True,
            hide_index=True,
        )
        labels = [
            f"{row.get('updated_at') or row.get('created_at') or '-'} | {row.get('operation_type') or '-'} | {row.get('status') or '-'} | {row.get('task_id')}"
            for row in background_rows
        ]
        selected_label = st.selectbox("查看后台任务详情", labels)
        selected_row = background_rows[labels.index(selected_label)]
        _show_background_task_detail(project_root, runs_dir, selected_row)

    rows = load_recent_task_runs(runs_dir, limit=80)
    if not rows:
        if not background_rows:
            st.info("还没有前端任务记录。生成创建计划、检查配置或真实执行后会出现在这里。")
        return
    st.subheader("最近任务")
    table_rows = [
        {
            "任务ID": row.get("task_id"),
            "操作": row.get("operation_type"),
            "状态": _format_status(row.get("status")),
            "结果状态": _format_status(row.get("result_status")),
            "审查": _format_status(row.get("review_status")),
            "阻断": row.get("review_blocking_reason_count"),
            "风险": row.get("review_warning_count"),
            "产品": row.get("product") or "-",
            "账户数": row.get("account_count"),
            "素材分配": row.get("material_assignment_count"),
            "时间": row.get("created_at"),
        }
        for row in rows
    ]
    st.dataframe(table_rows, use_container_width=True, hide_index=True)
    labels = [
        f"{row.get('created_at') or '-'} | {row.get('operation_type') or '-'} | {row.get('product') or '-'} | {row.get('task_id')}"
        for row in rows
    ]
    selected_label = st.selectbox("查看任务详情", labels)
    selected_index = labels.index(selected_label)
    selected_task_id = str(rows[selected_index].get("task_id") or "")
    detail = load_task_detail(runs_dir, selected_task_id)
    task = detail.get("task") if isinstance(detail.get("task"), dict) else {}
    artifact = detail.get("artifact") if isinstance(detail.get("artifact"), dict) else {}
    progress = detail.get("progress") if isinstance(detail.get("progress"), dict) else {}

    with st.container(border=True):
        st.subheader("任务详情")
        cols = st.columns(5)
        cols[0].metric("任务ID", str(task.get("task_id") or "-"))
        cols[1].metric("操作", str(task.get("operation_type") or "-"))
        cols[2].metric("状态", _format_status(task.get("status")))
        cols[3].metric("产品", str(task.get("product") or "-"))
        cols[4].metric("操作人", str(task.get("actor") or "-"))
        for label, path_value in [
            ("操作日志文件", task.get("artifact_path")),
            ("执行结果文件", task.get("execute_artifact_path")),
            ("汇报结果文件", task.get("report_artifact_path")),
        ]:
            text = str(path_value or "").strip()
            if text:
                st.caption(f"{label}：{text}")
        if progress:
            _show_progress_snapshot(progress, title="该类任务最近执行进度")
        execute_payload = _load_json_path(project_root, str(task.get("execute_artifact_path") or ""))
        report_payload = _load_json_path(project_root, str(task.get("report_artifact_path") or ""))
        if report_payload:
            _show_create_execute_report(report_payload)
        elif execute_payload:
            status = str(execute_payload.get("status") or "")
            if bool(execute_payload.get("ok")):
                st.success(f"执行结果：{_format_status(status)}")
            else:
                st.error(f"执行结果：{_format_status(status)}")
            failure = execute_payload.get("failure") if isinstance(execute_payload.get("failure"), dict) else {}
            if failure:
                st.table(
                    [
                        {
                            "操作": failure.get("operation"),
                            "序号": failure.get("index"),
                            "错误码": failure.get("code"),
                            "原因": failure.get("message"),
                        }
                    ]
                )
        _show_json_with_summary("查看任务操作日志 JSON", artifact, expanded=False)
        if execute_payload:
            _show_json_with_summary("查看执行结果 JSON", execute_payload, expanded=False)


def _show_background_task_detail(project_root: Path, runs_dir: str, row: dict[str, Any]) -> None:
    with st.container(border=True):
        st.subheader("后台任务详情")
        cols = st.columns(5)
        cols[0].metric("任务ID（任务 ID）", str(row.get("task_id") or "-"))
        cols[1].metric("操作", str(row.get("operation_type") or "-"))
        cols[2].metric("状态", _format_status(row.get("status")))
        cols[3].metric("退出码", str(row.get("return_code") if row.get("return_code") is not None else "-"))
        cols[4].metric("更新时间", str(row.get("updated_at") or "-"))
        command = row.get("command") if isinstance(row.get("command"), list) else []
        if command:
            with st.expander("查看固定执行命令", expanded=False):
                st.code(_format_shell_command(command, cwd=project_root), language="bash")
        for label, path_value in [
            ("任务 artifact（执行结果文件）", row.get("artifact_path")),
            ("执行结果 artifact（执行结果文件）", row.get("execute_artifact_path")),
            ("汇报 artifact（执行结果文件）", row.get("report_artifact_path")),
        ]:
            text = str(path_value or "").strip()
            if text:
                st.caption(f"{label}：{text}")
        stdout = _read_text_path(Path(runs_dir), str(row.get("stdout_path") or ""))
        stderr = _read_text_path(Path(runs_dir), str(row.get("stderr_path") or ""))
        execute_payload, report_payload = _execution_payloads_from_task(project_root, row)
        progress_payload = read_create_live_progress(runs_dir) if str(row.get("operation_type") or "") == "create_live_execute" else {}
        _show_create_execution_summary_card(
            task=row,
            progress=progress_payload,
            execute_payload=execute_payload,
            report_payload=report_payload,
            expanded=False,
        )
        if stdout:
            with st.expander("查看 stdout（标准输出）", expanded=False):
                st.code(stdout, language="text")
        if stderr:
            with st.expander("查看 stderr（标准错误）", expanded=False):
                st.code(stderr, language="text")
        result = row.get("result") if isinstance(row.get("result"), dict) else {}
        post_results = row.get("post_results") if isinstance(row.get("post_results"), list) else []
        if result:
            _show_json_with_summary("查看任务结果 JSON", result, expanded=False)
        if post_results:
            _show_json_with_summary("查看后续命令结果 JSON", {"post_results": post_results}, expanded=False)
            for index, post_result in enumerate(post_results, start=1):
                if not isinstance(post_result, dict):
                    continue
                post_stdout = _read_text_path(Path(runs_dir), str(post_result.get("stdout_path") or ""))
                post_stderr = _read_text_path(Path(runs_dir), str(post_result.get("stderr_path") or ""))
                if post_stdout:
                    with st.expander(f"查看后续命令 {index} stdout（标准输出）", expanded=False):
                        st.code(post_stdout, language="text")
                if post_stderr:
                    with st.expander(f"查看后续命令 {index} stderr（标准错误）", expanded=False):
                        st.code(post_stderr, language="text")


def _operation_logs(runs_dir: str) -> None:
    st.header("操作日志")
    st.caption("前端触发的创建、巡检、项目管理、真实执行都会在这里留痕。这里不调用平台接口，只读取本地日志和执行结果。")
    rows = load_operation_logs(runs_dir, limit=500)
    if not rows:
        st.info("还没有前端操作日志。")
        return

    products = sorted({str(row.get("product") or row.get("product_key") or "").strip() for row in rows if row.get("product") or row.get("product_key")})
    operations = sorted({str(row.get("operation_type") or "").strip() for row in rows if row.get("operation_type")})
    statuses = sorted({str(row.get("status") or "").strip() for row in rows if row.get("status")})
    cols = st.columns(3)
    product_filter = cols[0].selectbox("产品", ["全部产品", *products])
    operation_filter = cols[1].selectbox("操作类型", ["全部操作", *operations])
    status_filter = cols[2].selectbox("状态", ["全部状态", *statuses])
    filtered = filter_operation_logs(
        rows,
        product="" if product_filter == "全部产品" else product_filter,
        operation_type="" if operation_filter == "全部操作" else operation_filter,
        status="" if status_filter == "全部状态" else status_filter,
    )
    st.caption(f"当前显示 {len(filtered)} / {len(rows)} 条。")
    table_rows = [
        {
            "时间": row.get("created_at"),
            "操作": row.get("operation_type"),
            "状态": _format_status(row.get("status")),
            "审查": _format_status(row.get("review_status")),
            "产品": row.get("product") or row.get("product_key") or "-",
            "账户数": row.get("account_count"),
            "素材分配": row.get("material_assignment_count"),
            "阻断": row.get("review_blocking_reason_count"),
            "风险": row.get("review_warning_count"),
            "任务": _format_status(row.get("task_status")),
            "退出码": row.get("return_code"),
            "飞书": _format_status(row.get("feishu_status")),
            "任务ID": row.get("task_id"),
        }
        for row in filtered
    ]
    st.dataframe(table_rows, use_container_width=True, hide_index=True)

    labels = [
        f"{row.get('created_at') or '-'} | {row.get('operation_type') or '-'} | {row.get('product') or row.get('product_key') or '-'} | {row.get('task_id')}"
        for row in filtered
    ]
    if not labels:
        st.info("没有符合筛选条件的操作日志。")
        return
    selected_label = st.selectbox("查看操作详情", labels)
    selected_task_id = str(filtered[labels.index(selected_label)].get("task_id") or "")
    _show_operation_log_detail(runs_dir, selected_task_id)


def _show_operation_log_detail(runs_dir: str, task_id: str) -> None:
    detail = load_operation_log_detail(runs_dir, task_id)
    row = detail.get("row") if isinstance(detail.get("row"), dict) else {}
    artifact = detail.get("artifact") if isinstance(detail.get("artifact"), dict) else {}
    task = detail.get("task") if isinstance(detail.get("task"), dict) else {}
    create_review = detail.get("create_review") if isinstance(detail.get("create_review"), dict) else {}
    execute_payload = detail.get("execute_payload") if isinstance(detail.get("execute_payload"), dict) else {}
    report_payload = detail.get("report_payload") if isinstance(detail.get("report_payload"), dict) else {}
    failure = detail.get("failure") if isinstance(detail.get("failure"), dict) else {}
    feishu = detail.get("feishu") if isinstance(detail.get("feishu"), dict) else {}

    with st.container(border=True):
        st.subheader("操作详情")
        cols = st.columns(6)
        cols[0].metric("任务ID（任务 ID）", str(row.get("task_id") or "-"))
        cols[1].metric("操作", str(row.get("operation_type") or "-"))
        cols[2].metric("状态", _format_status(row.get("status")))
        cols[3].metric("产品", str(row.get("product") or row.get("product_key") or "-"))
        cols[4].metric("审查", _format_status(row.get("review_status")))
        cols[5].metric("飞书", _format_status(feishu.get("status") or row.get("feishu_status")))
        for label, path_value in [
            ("操作日志 artifact（执行结果文件）", row.get("artifact_path")),
            ("执行结果 artifact（执行结果文件）", row.get("execute_artifact_path")),
            ("汇报 artifact（执行结果文件）", row.get("report_artifact_path")),
        ]:
            text = str(path_value or "").strip()
            if text:
                st.caption(f"{label}：{text}")
        message = str(feishu.get("message") or "").strip()
        if message:
            st.info(message)
        _show_create_execution_summary_card(
            task=task,
            progress=read_create_live_progress(runs_dir) if str(row.get("operation_type") or "") == "create_live_execute" else {},
            execute_payload=execute_payload,
            report_payload=report_payload,
            expanded=False,
        )
        stdout = _read_text_path(Path(runs_dir), str(row.get("stdout_path") or ""))
        stderr = _read_text_path(Path(runs_dir), str(row.get("stderr_path") or ""))
        if stdout:
            with st.expander("查看 stdout（标准输出）", expanded=False):
                st.code(stdout, language="text")
        if stderr:
            with st.expander("查看 stderr（标准错误）", expanded=False):
                st.code(stderr, language="text")
        if failure:
            st.error("执行失败明细")
            st.table(
                [
                    {
                        "操作": failure.get("operation"),
                        "序号": failure.get("index"),
                        "错误码": failure.get("code"),
                        "原因": failure.get("message"),
                    }
                ]
            )
        if report_payload:
            _show_create_execute_report(report_payload)
        elif execute_payload:
            status = str(execute_payload.get("status") or "")
            if bool(execute_payload.get("ok")):
                st.success(f"执行结果：{_format_status(status)}")
            else:
                st.error(f"执行结果：{_format_status(status)}")
        _show_operation_create_review(create_review)
        _show_json_with_summary("查看操作日志 JSON", artifact, expanded=False)
        if execute_payload:
            _show_json_with_summary("查看真实执行结果 JSON", execute_payload, expanded=False)
        if report_payload:
            _show_json_with_summary("查看飞书汇报结果 JSON", report_payload, expanded=False)


def _show_operation_create_review(create_review: dict[str, Any]) -> None:
    preview = build_create_plan_preview_from_review(create_review)
    if not preview:
        return

    with st.expander("查看创建计划审查与选材明细", expanded=False):
        task_id = str((create_review.get("review") or {}).get("task_id") or id(create_review))
        _show_create_plan_preview_panel(
            preview,
            key_prefix=f"operation_create_review_{task_id}",
            title="创建计划审查与选材明细",
            use_expanders=False,
        )


def _results(runs_dir: str) -> None:
    st.header("执行结果")
    workflow_labels = {
        "创建计划": "create_mode",
        "创建执行": "create_live_execute_once",
        "创建执行报告": "create_live_execute_report",
        "项目实时筛选配置": "project_realtime_filter_config",
        "项目管理执行": "project_update_execute",
        "账户备注修改": "account_remark_update",
        "投放巡检": "delivery_patrol",
        "投放巡检建议": "delivery_patrol_suggestions",
        "定时任务状态": "scheduler_status",
        "AI 创建模板草稿": "ai_create_template_drafts",
    }
    workflow = workflow_labels[st.selectbox(
        "流程名",
        list(workflow_labels),
    )]
    payload = _latest(runs_dir, workflow)
    if workflow == "scheduler_status":
        _show_scheduler_status_panel(payload, compact=False)
    else:
        _show_summary("最近结果", payload)
    _show_json_with_summary("查看完整结果 JSON", payload, expanded=False)


def main() -> None:
    args = _args()
    config = load_ui_config(args.ui_config)
    project_root = (PROJECT_ROOT / str(config.get("project_root") or ".")).resolve()
    runs_dir = str(project_root / str(config.get("runs_dir") or "data/runs"))
    timeout_seconds = int(config.get("readonly_timeout_seconds") or 900)

    st.set_page_config(page_title=str(config.get("title") or "RoiBang-v2"), layout="wide")
    _disable_streamlit_cache_shortcut()
    st.markdown(
        """
        <style>
        [data-testid="stToolbar"] {visibility: hidden;}
        [data-testid="stDecoration"] {display: none;}
        #MainMenu {visibility: hidden;}
        header {visibility: hidden;}
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.title(str(config.get("title") or "RoiBang-v2 本地工作台"))
    st.caption("v0.1：只读展示、生成 JSON、调用固定脚本。前端不直接调用平台接口。")

    tabs = st.tabs(
        [
            "首页",
            "任务中心",
            "操作日志",
            "定时任务",
            "投放巡检",
            "产品管理",
            "创建",
            "项目管理",
            "AI 草稿",
            "执行结果",
        ]
    )
    with tabs[0]:
        _dashboard(runs_dir)
    with tabs[1]:
        _task_center(project_root, runs_dir)
    with tabs[2]:
        _operation_logs(runs_dir)
    with tabs[3]:
        _scheduler_status_page(runs_dir)
    with tabs[4]:
        _delivery_patrol(project_root, runs_dir, timeout_seconds)
    with tabs[5]:
        _product_management(config)
    with tabs[6]:
        _create(project_root, config, timeout_seconds)
    with tabs[7]:
        _project_management(project_root, timeout_seconds, runs_dir)
    with tabs[8]:
        _ai_template_drafts(project_root, runs_dir, timeout_seconds)
    with tabs[9]:
        _results(runs_dir)


if __name__ == "__main__":
    main()
