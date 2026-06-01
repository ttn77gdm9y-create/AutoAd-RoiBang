from __future__ import annotations

import json
from datetime import datetime
from datetime import timezone
from pathlib import Path
from typing import Any

from roibang_v2.runs import write_run_artifact


WORKFLOW = "create_plan_from_suggestions"
CREATE_ACTION = "suggest_create_project"


def build_create_plan_from_suggestions(
    suggestions_artifact: dict[str, Any],
    cfg: dict[str, Any],
    *,
    project_root: str | Path = ".",
    template_dir: str | Path = "configs/create-templates",
) -> dict[str, Any]:
    selected_ids = _selected_suggestion_ids(cfg)
    suggestions = _rows(suggestions_artifact.get("suggestions"))
    selected, missing_ids = _select_suggestions(suggestions, selected_ids)
    blocking_reasons = _selection_blocking_reasons(selected_ids, selected, missing_ids, cfg)
    owner = _text(cfg.get("owner") or cfg.get("operator"))
    if not owner:
        blocking_reasons.append("必须填写负责人，不能从建议里猜负责人。")

    create_suggestions = [suggestion for suggestion in selected if _suggestion_action(suggestion) == CREATE_ACTION]
    suggestion_groups = _build_suggestion_groups(
        create_suggestions,
        cfg,
        project_root=project_root,
        template_dir=template_dir,
        owner=owner,
    )
    split_reasons = _split_reasons(suggestion_groups, create_suggestions)
    split_required = len([group for group in suggestion_groups if group["can_generate_single_plan"]]) > 1
    if not suggestion_groups and selected and not blocking_reasons:
        blocking_reasons.append("所选建议没有可生成创建计划预览的创建项目建议。")

    group_blocking_reasons = [
        f"批次 {group['group_id']}：{reason}"
        for group in suggestion_groups
        for reason in group.get("blocking_reasons", [])
    ]
    blocking_reasons.extend(group_blocking_reasons)

    single_group = suggestion_groups[0] if len(suggestion_groups) == 1 else {}
    create_plan_request = (
        single_group.get("create_plan_request") if isinstance(single_group.get("create_plan_request"), dict) else {}
    )
    product_key = _text(create_plan_request.get("product_key"))
    product_name = _text(create_plan_request.get("product_name"))
    mode_key = _text(create_plan_request.get("mode"))
    target_date = _text(create_plan_request.get("target_date"))
    template_catalog = _text(create_plan_request.get("template_catalog"))
    advertiser_ids = _split_accounts(create_plan_request.get("advertiser_ids"))
    total_account_count = len(advertiser_ids) or sum(int(group.get("account_count") or 0) for group in suggestion_groups)

    account_rows = [
        {
            "advertiser_id": advertiser_id,
            "account_name": _account_name_for(selected, advertiser_id),
        }
        for advertiser_id in advertiser_ids
    ]
    recommendation = _combined_recommendation(selected)
    if blocking_reasons:
        status = "blocked"
    elif split_required:
        status = "split_required"
    else:
        status = "preview_only"
    ok = status in {"preview_only", "split_required"}
    return {
        "ok": ok,
        "workflow": WORKFLOW,
        "phase": "create_plan_preview",
        "status": status,
        "execution_enabled": False,
        "external_api_calls": 0,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "summary": {
            "status": status,
            "source_suggestion_count": len(selected),
            "account_count": total_account_count,
            "suggestion_group_count": len(suggestion_groups),
            "can_generate_single_plan": status == "preview_only",
            "split_required": split_required,
            "product_key": product_key,
            "product_name": product_name,
            "mode_key": mode_key,
            "target_date": target_date,
            "template_catalog": template_catalog,
            "blocking_reason_count": len(blocking_reasons),
            "split_reason_count": len(split_reasons),
        },
        "blocking_reasons": blocking_reasons,
        "split_reasons": split_reasons,
        "create_plan_request": create_plan_request,
        "suggestion_groups": suggestion_groups,
        "source": {
            "suggestions_workflow": _text(suggestions_artifact.get("workflow")),
            "suggestions_artifact_path": _text(cfg.get("suggestions_artifact_path")),
            "source_suggestion_ids": [_text(suggestion.get("suggestion_id")) for suggestion in selected],
        },
        "accounts": account_rows,
        "source_suggestions": selected,
        "recommendation": recommendation,
        "guardrails": [
            "这里只把创建项目建议转换成创建计划请求预览。",
            "不会生成 data/runs/create_mode 下的创建计划。",
            "不会调用外部接口，也不会创建项目、单元或素材绑定。",
            "真实创建必须进入创建计划页人工核对并确认。",
        ],
    }


def run_create_plan_from_suggestions_request(request: dict[str, Any], *, runs_dir: str | Path) -> dict[str, Any]:
    suggestions_artifact = request.get("suggestions_artifact")
    if not isinstance(suggestions_artifact, dict):
        suggestions_path = _text(request.get("suggestions_artifact_path"))
        if not suggestions_path:
            raise ValueError("create_plan_from_suggestions requires suggestions_artifact_path")
        suggestions_artifact = _load_json(Path(suggestions_path))

    result = build_create_plan_from_suggestions(
        suggestions_artifact,
        request,
        project_root=request.get("project_root") or ".",
        template_dir=request.get("template_dir") or "configs/create-templates",
    )
    artifact_path = write_run_artifact(runs_dir, WORKFLOW, result)
    result["artifact_path"] = str(artifact_path)
    return result


def _selected_suggestion_ids(cfg: dict[str, Any]) -> list[str]:
    raw = cfg.get("selected_suggestion_ids", cfg.get("suggestion_ids", cfg.get("suggestion_id")))
    values: list[str]
    if isinstance(raw, list):
        values = [_text(item) for item in raw]
    elif isinstance(raw, str):
        values = [item.strip() for item in raw.split(",")]
    else:
        values = []
    return _unique_texts(values)


def _select_suggestions(
    suggestions: list[dict[str, Any]],
    selected_ids: list[str],
) -> tuple[list[dict[str, Any]], list[str]]:
    by_id = {_text(suggestion.get("suggestion_id")): suggestion for suggestion in suggestions if _text(suggestion.get("suggestion_id"))}
    selected = [by_id[suggestion_id] for suggestion_id in selected_ids if suggestion_id in by_id]
    missing = [suggestion_id for suggestion_id in selected_ids if suggestion_id not in by_id]
    return selected, missing


def _selection_blocking_reasons(
    selected_ids: list[str],
    selected: list[dict[str, Any]],
    missing_ids: list[str],
    cfg: dict[str, Any],
) -> list[str]:
    reasons: list[str] = []
    if not selected_ids:
        reasons.append("必须选择至少一条创建项目建议。")
    for suggestion_id in missing_ids:
        reasons.append(f"建议 {suggestion_id} 不存在。")
    requested_product_key = _text(cfg.get("product_key"))
    for suggestion in selected:
        suggestion_id = _text(suggestion.get("suggestion_id")) or "未命名建议"
        if requested_product_key and _text(suggestion.get("product_key")) and _text(suggestion.get("product_key")) != requested_product_key:
            reasons.append(f"建议 {suggestion_id} 不属于当前产品 {requested_product_key}。")
        if _suggestion_action(suggestion) != CREATE_ACTION:
            reasons.append(f"建议 {suggestion_id} 不是创建项目建议，不能生成创建计划预览。")
        if _text(suggestion.get("status")) == "blocked":
            reasons.append(f"建议 {suggestion_id} 当前处于阻断状态，不能生成创建计划预览。")
        blocking = [_text(item) for item in suggestion.get("blocking_reasons") or [] if _text(item)]
        if blocking:
            reasons.append(f"建议 {suggestion_id} 有阻断原因：{'；'.join(blocking)}。")
        if not _text(suggestion.get("advertiser_id")):
            reasons.append(f"建议 {suggestion_id} 缺少账户 ID。")
    return reasons


def _build_suggestion_groups(
    suggestions: list[dict[str, Any]],
    cfg: dict[str, Any],
    *,
    project_root: str | Path,
    template_dir: str | Path,
    owner: str,
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str, bool], list[dict[str, Any]]] = {}
    for suggestion in suggestions:
        product_key = _text(suggestion.get("product_key"))
        product_name = _text(suggestion.get("product_name") or suggestion.get("product"))
        mode_key = _text(suggestion.get("mode_key") or suggestion.get("recommended_mode_key"))
        template_catalog = _resolve_template_catalog(
            [suggestion],
            cfg,
            project_root=project_root,
            template_dir=template_dir,
            product_key=product_key,
            product_name=product_name,
        )
        grouped.setdefault((product_key, mode_key, template_catalog, _is_7r_mode(mode_key)), []).append(suggestion)

    groups: list[dict[str, Any]] = []
    for index, ((product_key, mode_key, template_catalog, is_7r), rows) in enumerate(sorted(grouped.items()), start=1):
        groups.append(
            _build_group(
                index,
                rows,
                cfg,
                owner=owner,
                product_key=product_key,
                mode_key=mode_key,
                template_catalog=template_catalog,
                is_7r=is_7r,
            )
        )
    return groups


def _build_group(
    index: int,
    selected: list[dict[str, Any]],
    cfg: dict[str, Any],
    *,
    owner: str,
    product_key: str,
    mode_key: str,
    template_catalog: str,
    is_7r: bool,
) -> dict[str, Any]:
    product_name = _resolve_single_value(selected, {}, "product_name", "product")
    target_date = _text(cfg.get("target_date")) or _resolve_single_value(selected, {}, "target_date")
    recommendation = _combined_recommendation(selected)
    advertiser_ids = _unique_texts(_text(suggestion.get("advertiser_id")) for suggestion in selected)
    create_plan_request = {
        "mode": mode_key,
        "advertiser_ids": "\n".join(advertiser_ids),
        "owner": owner,
        "product_key": product_key,
        "product_name": product_name,
        "target_date": target_date,
        "template_catalog": template_catalog,
        "cpa_bid": _text(cfg.get("cpa_bid")) or _text(recommendation.get("cpa_bid") or recommendation.get("target_cpa_bid")),
        "roi_coefficient": _text(cfg.get("roi_coefficient")) or _text(recommendation.get("roi_coefficient")),
    }
    blocking_reasons: list[str] = []
    if not product_key:
        blocking_reasons.append("所选创建建议缺少产品 Key。")
    if not product_name:
        blocking_reasons.append("所选创建建议缺少产品名称。")
    if not mode_key:
        blocking_reasons.append("所选创建建议缺少推荐创建模式。")
    if not target_date:
        blocking_reasons.append("所选创建建议缺少目标日期。")
    if not template_catalog:
        blocking_reasons.append("未找到匹配的创建模板 JSON，请手动指定 template_catalog。")
    if not advertiser_ids:
        blocking_reasons.append("所选创建建议缺少账户 ID。")

    group_id = f"create-plan-group-{index}"
    return {
        "group_id": group_id,
        "group_key": {
            "product_key": product_key,
            "mode_key": mode_key,
            "template_catalog": template_catalog,
            "is_7r": is_7r,
        },
        "group_reason": "同产品、同创建模式、同模板，建议作为一批进入创建计划页复核。",
        "can_generate_single_plan": not blocking_reasons,
        "split_required": False,
        "product_key": product_key,
        "product_name": product_name,
        "mode_key": mode_key,
        "template_catalog": template_catalog,
        "target_date": target_date,
        "is_7r": is_7r,
        "account_count": len(advertiser_ids),
        "source_suggestion_count": len(selected),
        "source_suggestion_ids": [_text(suggestion.get("suggestion_id")) for suggestion in selected],
        "strategy_ids": _unique_texts(_text(suggestion.get("strategy_id") or suggestion.get("rule_id")) for suggestion in selected),
        "evidence_summary": _evidence_summary(selected),
        "blocking_reasons": blocking_reasons,
        "create_plan_request": create_plan_request,
    }


def _split_reasons(groups: list[dict[str, Any]], selected: list[dict[str, Any]]) -> list[str]:
    if len(groups) <= 1:
        return []
    reasons: list[str] = []
    product_keys = _unique_texts(_text(suggestion.get("product_key")) for suggestion in selected)
    mode_keys = _unique_texts(_text(suggestion.get("mode_key") or suggestion.get("recommended_mode_key")) for suggestion in selected)
    template_catalogs = _unique_texts(_text(group.get("template_catalog")) for group in groups)
    is_7r_values = {bool(group.get("is_7r")) for group in groups}
    if len(product_keys) > 1:
        reasons.append("所选创建建议跨多个产品，需要按产品拆分。")
    if len(mode_keys) > 1:
        reasons.append("所选创建建议跨多个创建模式，需要按模式拆分。")
    if len(template_catalogs) > 1:
        reasons.append("所选创建建议跨多个创建模板，需要按模板拆分。")
    if len(is_7r_values) > 1:
        reasons.append("所选创建建议同时包含 7R 与非 7R 模式，需要拆分。")
    if not reasons:
        reasons.append("所选创建建议被拆成多个可复核批次。")
    return reasons


def _resolve_single_value(selected: list[dict[str, Any]], cfg: dict[str, Any], *keys: str) -> str:
    for key in keys:
        explicit = _text(cfg.get(key))
        if explicit:
            return explicit
    values: list[str] = []
    for suggestion in selected:
        for key in keys:
            value = _text(suggestion.get(key))
            if value:
                values.append(value)
                break
    unique = _unique_texts(values)
    return unique[0] if len(unique) == 1 else ""


def _resolve_template_catalog(
    selected: list[dict[str, Any]],
    cfg: dict[str, Any],
    *,
    project_root: str | Path,
    template_dir: str | Path,
    product_key: str,
    product_name: str,
) -> str:
    for key in ("template_catalog", "template_catalog_path", "template_path"):
        value = _text(cfg.get(key))
        if value:
            return value
    for suggestion in selected:
        value = _text(suggestion.get("template_catalog") or suggestion.get("template_catalog_path"))
        if value:
            return value
        evidence = suggestion.get("evidence") if isinstance(suggestion.get("evidence"), dict) else {}
        recommended = evidence.get("recommended_request") if isinstance(evidence.get("recommended_request"), dict) else {}
        value = _text(recommended.get("template_catalog") or recommended.get("template_catalog_path"))
        if value:
            return value
    return _find_template_catalog(project_root, template_dir, product_key=product_key, product_name=product_name)


def _find_template_catalog(
    project_root: str | Path,
    template_dir: str | Path,
    *,
    product_key: str,
    product_name: str,
) -> str:
    root = Path(project_root)
    template_root = Path(template_dir)
    if not template_root.is_absolute():
        template_root = root / template_root
    if not template_root.exists():
        return ""
    candidates = sorted(template_root.glob("*.json"))
    for path in candidates:
        payload = _load_json(path)
        if product_key and _text(payload.get("product_key")) == product_key:
            return _relative_path(root, path)
    for path in candidates:
        payload = _load_json(path)
        if product_name and _text(payload.get("product")) == product_name:
            return _relative_path(root, path)
    return ""


def _combined_recommendation(selected: list[dict[str, Any]]) -> dict[str, Any]:
    combined: dict[str, Any] = {}
    for suggestion in selected:
        evidence = suggestion.get("evidence") if isinstance(suggestion.get("evidence"), dict) else {}
        recommended = evidence.get("recommended_request") if isinstance(evidence.get("recommended_request"), dict) else {}
        for key, value in recommended.items():
            if value not in (None, "") and key not in combined:
                combined[key] = value
    return combined


def _account_name_for(selected: list[dict[str, Any]], advertiser_id: str) -> str:
    for suggestion in selected:
        if _text(suggestion.get("advertiser_id")) == advertiser_id:
            return _text(suggestion.get("account_name") or suggestion.get("advertiser_name")) or advertiser_id
    return advertiser_id


def _evidence_summary(selected: list[dict[str, Any]]) -> dict[str, Any]:
    project_capacities: list[float] = []
    qualified_material_counts: list[float] = []
    current_project_counts: list[float] = []
    for suggestion in selected:
        metrics = suggestion.get("metrics") if isinstance(suggestion.get("metrics"), dict) else {}
        evidence = suggestion.get("evidence") if isinstance(suggestion.get("evidence"), dict) else {}
        project_capacities.append(_number(metrics.get("project_capacity"), evidence.get("project_capacity")))
        qualified_material_counts.append(
            _number(metrics.get("qualified_material_count"), evidence.get("qualified_material_count"))
        )
        current_project_counts.append(_number(metrics.get("project_count"), evidence.get("current_project_count")))
    return {
        "min_project_capacity": min(project_capacities) if project_capacities else 0,
        "total_project_capacity": sum(project_capacities),
        "min_qualified_material_count": min(qualified_material_counts) if qualified_material_counts else 0,
        "max_current_project_count": max(current_project_counts) if current_project_counts else 0,
    }


def _split_accounts(value: Any) -> list[str]:
    if isinstance(value, list):
        raw_items = value
    else:
        raw_items = str(value or "").replace("\n", ",").split(",")
    return _unique_texts(raw_items)


def _is_7r_mode(mode_key: str) -> bool:
    return "7r" in mode_key.lower()


def _number(value: Any, fallback: Any = 0) -> float:
    try:
        if value in (None, ""):
            return float(fallback or 0)
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _suggestion_action(suggestion: dict[str, Any]) -> str:
    return _text(suggestion.get("suggested_action") or suggestion.get("suggestion_type") or suggestion.get("action"))


def _rows(value: Any) -> list[dict[str, Any]]:
    return [dict(item) for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _unique_texts(values: Any) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _text(value)
        if text and text not in seen:
            output.append(text)
            seen.add(text)
    return output


def _relative_path(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()
