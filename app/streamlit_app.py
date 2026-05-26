from __future__ import annotations

import argparse
import copy
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

from roibang_v2.create_mode_rules import normalize_create_mode_config
from roibang_v2.ui.artifact_reader import compact_summary
from roibang_v2.ui.artifact_reader import load_latest_artifact
from roibang_v2.ui.script_runner import build_account_remark_config_command
from roibang_v2.ui.script_runner import build_account_remark_execute_command
from roibang_v2.ui.script_runner import build_ai_template_drafts_command
from roibang_v2.ui.script_runner import build_create_live_config_check_command
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
            with st.expander("查看执行摘要 JSON", expanded=False):
                st.json(details)


def _format_bool(value: Any) -> str:
    return "是" if bool(value) else "否"


def _format_status(value: Any) -> str:
    raw = str(value or "").strip()
    labels = {
        "completed": "已完成",
        "blocked": "已阻断",
        "control_analysis": "分析完成",
        "control_config": "配置生成",
        "control_execute": "执行完成",
        "phase1": "正常",
        "missing": "未找到",
        "failed": "失败",
        "planned_only": "仅生成计划",
        "drafted": "草稿已生成",
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

    with st.expander("当前模板内容", expanded=False):
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
        with st.expander("查看 CTA（行动按钮）和产品卖点", expanded=False):
            st.json(
                {
                    "cta_pool": cta_pool,
                    "product_selling_points": selling_points,
                    "aweme_ids": aweme_ids,
                }
            )
        st.caption(f"命名后缀：{mode.get('template_name_suffix') or '-'}")
        with st.expander("查看模板原始 JSON", expanded=False):
            st.json(mode)


def _mode_draft_editor(mode: dict[str, Any], *, drafts_dir: Path, mode_dir: Path) -> None:
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

            try:
                if can_save_official:
                    output = save_product_create_mode_config(mode_dir, draft)
                else:
                    output = save_create_mode_draft(drafts_dir, draft)
            except Exception as exc:
                st.error(f"保存失败：{exc}")
            else:
                st.success(f"已保存：{output}")
                if can_save_official:
                    st.caption("已保存为该产品正式创建模板；后续生成计划会读取这个 .local.json。")
                else:
                    st.caption("这只是草稿；正式模板仍需后续转正脚本处理。")
                st.json(draft)


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


def _base_template_editor(mode: dict[str, Any], *, template_catalog: dict[str, Any], template_dir: Path) -> None:
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
            updated_template["title_pool"] = _lines_to_list(title_text)
            updated_template["cta_pool"] = _lines_to_list(cta_text)
            updated_template["product_selling_points"] = _lines_to_list(selling_text)
            updated_template["aweme_ids"] = _lines_to_list(aweme_text)
            templates[template_key] = updated_template
            catalog["templates"] = templates
            try:
                output = save_product_create_template_catalog(template_dir, catalog)
            except Exception as exc:
                st.error(f"保存失败：{exc}")
            else:
                st.success(f"基础模板已保存：{output}")
                st.cache_data.clear()
                st.caption("后续生成创建计划会优先读取这个产品专属基础模板。")
                st.json(updated_template)


def _show_script_result(result) -> None:
    st.code(" ".join(result.command), language="bash")
    if result.ok:
        st.success(f"脚本完成，退出码={result.return_code}")
    else:
        st.error(f"脚本失败，退出码={result.return_code}")
    if result.parsed_stdout:
        st.json(result.parsed_stdout)
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
) -> None:
    with st.container(border=True):
        st.markdown(f"**{title}**")
        st.warning("这个按钮会调用固定脚本执行真实业务动作。执行前必须确认 JSON 内容正确。")
        st.code(_format_shell_command(command, cwd=project_root), language="bash")
        confirmed = st.checkbox("我已确认 JSON 内容正确，允许执行固定脚本", key=f"{state_key}_confirm")
        if st.button("确认执行", type="primary", disabled=not confirmed, key=f"{state_key}_execute"):
            result = run_fixed_script(command, cwd=project_root, timeout_seconds=timeout_seconds)
            st.session_state[f"{state_key}_result"] = result.parsed_stdout
            st.cache_data.clear()
            _show_script_result(result)
        stored = st.session_state.get(f"{state_key}_result")
        if isinstance(stored, dict) and stored:
            with st.expander("查看最近执行结果 JSON", expanded=False):
                st.json(stored)


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


def _show_create_execution_steps(project_root: Path, plan_path: str, timeout_seconds: int) -> None:
    st.subheader("下一步")
    st.caption("网页只做检查和生成命令，不直接执行真实创建。")
    check_command = build_create_live_config_check_command(plan_path=plan_path)
    with st.container(border=True):
        st.markdown("**1. 检查真实执行配置**")
        st.caption("只检查配置、token（令牌）和账户准允许名单，不创建项目。")
        if st.button("检查真实执行配置", key=f"check_create_config_{plan_path}"):
            result = run_fixed_script(check_command, cwd=project_root, timeout_seconds=timeout_seconds)
            st.session_state["create_config_check_result"] = result.parsed_stdout
            st.session_state["create_config_check_return_code"] = result.return_code
            st.cache_data.clear()
        result_payload = st.session_state.get("create_config_check_result")
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
            with st.expander("查看检查结果 JSON", expanded=False):
                st.json(result_payload)

    real_command = build_create_live_terminal_command(
        plan_path=plan_path,
        check_config_only=False,
        open_progress_window=True,
    )
    with st.container(border=True):
        st.markdown("**2. 真实执行命令**")
        st.caption("配置检查通过后，复制下面命令到终端运行。运行后会真实创建项目和单元。")
        st.code(_format_shell_command(real_command, cwd=project_root), language="bash")


def _dashboard(runs_dir: str) -> None:
    st.header("首页")
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
    st.header("投放巡检")
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
        with st.expander("查看建议摘要 JSON", expanded=False):
            st.json(suggestions.get("summary") or suggestions)


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
        _mode_draft_editor(mode_detail, drafts_dir=drafts_dir, mode_dir=mode_dir)
        _base_template_editor(mode_detail, template_catalog=template_catalog, template_dir=template_dir)
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
            st.session_state["create_plan_artifact_path"] = str(artifact_path)
            st.session_state["create_plan_summary"] = _create_plan_summary(
                project_root,
                str(artifact_path),
                result.parsed_stdout.get("summary") if isinstance(result.parsed_stdout.get("summary"), dict) else {},
            )
            st.session_state.pop("create_config_check_result", None)
            with st.expander("查看生成结果 JSON", expanded=False):
                st.json(result.parsed_stdout)
    plan_path = str(st.session_state.get("create_plan_artifact_path") or "")
    if plan_path:
        summary = st.session_state.get("create_plan_summary")
        if not isinstance(summary, dict) or not summary:
            summary = _create_plan_summary(project_root, plan_path)
        _show_create_plan_summary(summary)
        _show_create_execution_steps(project_root, plan_path, timeout_seconds)


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
            st.json(draft)

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
                st.json(allowed_config)


def _project_management(project_root: Path, timeout_seconds: int) -> None:
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
        st.cache_data.clear()
        _show_script_result(result)
        project_update_path = result.parsed_stdout.get("project_update_path") if result.parsed_stdout else ""
        if project_update_path:
            _run_confirmed_execution(
                title="项目管理真实执行",
                command=build_project_update_execute_command(project_update_path=str(project_update_path), execute=True),
                project_root=project_root,
                timeout_seconds=timeout_seconds,
                state_key=f"project_update_{project_update_path}",
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
        st.cache_data.clear()
        _show_script_result(result)
        account_remark_path = result.parsed_stdout.get("artifact_path") if result.parsed_stdout else ""
        if account_remark_path:
            st.session_state["account_remark_update_path"] = str(account_remark_path)

    account_remark_update_path = str(st.session_state.get("account_remark_update_path") or remark_output_path or "")
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
        )


def _ai_template_drafts(project_root: Path, runs_dir: str, timeout_seconds: int) -> None:
    st.header("AI 创建模板草稿")
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
    _show_summary("最近结果", payload)
    with st.expander("查看完整结果 JSON", expanded=False):
        st.json(payload)


def main() -> None:
    args = _args()
    config = load_ui_config(args.ui_config)
    project_root = (PROJECT_ROOT / str(config.get("project_root") or ".")).resolve()
    runs_dir = str(project_root / str(config.get("runs_dir") or "data/runs"))
    timeout_seconds = int(config.get("readonly_timeout_seconds") or 900)

    st.set_page_config(page_title=str(config.get("title") or "RoiBang-v2"), layout="wide")
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
        _delivery_patrol(project_root, runs_dir, timeout_seconds)
    with tabs[2]:
        _product_management(config)
    with tabs[3]:
        _create(project_root, config, timeout_seconds)
    with tabs[4]:
        _project_management(project_root, timeout_seconds)
    with tabs[5]:
        _ai_template_drafts(project_root, runs_dir, timeout_seconds)
    with tabs[6]:
        _results(runs_dir)


if __name__ == "__main__":
    main()
