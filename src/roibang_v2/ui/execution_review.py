from __future__ import annotations

from pathlib import Path
from typing import Any, MutableMapping


ACTION_LABELS = {
    "delete_project": "删除项目",
    "status_update": "开启/关闭项目",
    "budget_update": "调整预算",
    "bid_update": "调整出价",
    "roi_coeff_update": "调整 ROI 系数",
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _rows(value: Any) -> list[dict[str, Any]]:
    return [dict(item) for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def remember_execution_path(state: MutableMapping[str, Any], key: str, new_path: str) -> str:
    path = _text(new_path)
    if path:
        state[key] = path
        return path
    return _text(state.get(key))


def resolve_optional_execution_path(
    state: MutableMapping[str, Any],
    key: str,
    fallback_path: str,
    *,
    project_root: str | Path,
) -> str:
    stored = _text(state.get(key))
    if stored:
        return stored
    fallback = _text(fallback_path)
    if not fallback:
        return ""
    candidate = Path(fallback)
    if not candidate.is_absolute():
        candidate = Path(project_root) / candidate
    return fallback if candidate.exists() else ""


def _action_target_value(action: dict[str, Any]) -> str:
    action_type = _text(action.get("action_type"))
    if action_type == "status_update":
        return _text(action.get("opt_status"))
    if action_type == "budget_update":
        return _text(action.get("budget"))
    if action_type == "bid_update":
        return _text(action.get("cpa_bid"))
    if action_type == "roi_coeff_update":
        return _text(action.get("roi_goal"))
    return ""


def build_project_update_execution_review(project_update: dict[str, Any]) -> dict[str, Any]:
    actions = _rows(project_update.get("actions"))
    action_types = {_text(action.get("action_type")) for action in actions if _text(action.get("action_type"))}
    action_label = ACTION_LABELS.get(next(iter(action_types), ""), "项目管理")
    if len(action_types) > 1:
        action_label = "混合项目管理"
    rows = [
        {
            "动作": ACTION_LABELS.get(_text(action.get("action_type")), _text(action.get("action_type"))),
            "账户 ID": _text(action.get("advertiser_id")),
            "项目 ID": _text(action.get("project_id")),
            "项目名称": _text(action.get("project_name")),
            "消耗": action.get("stat_cost", ""),
            "目标值": _action_target_value(action),
        }
        for action in actions
    ]
    return {
        "summary": {
            "配置 ID": _text(project_update.get("project_update_id")),
            "动作": action_label,
            "账户数": len({row["账户 ID"] for row in rows if row["账户 ID"]}),
            "项目数": len(rows),
        },
        "rows": rows,
    }


def build_payload_chinese_rows(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    actions = _rows(payload.get("actions"))
    if actions:
        return build_project_update_execution_review(payload)["rows"]
    project_update = payload.get("project_update") if isinstance(payload.get("project_update"), dict) else {}
    if project_update:
        return build_project_update_execution_review(project_update)["rows"]
    account_update = payload.get("account_remark_update") if isinstance(payload.get("account_remark_update"), dict) else {}
    if account_update:
        return build_account_remark_execution_review(payload)["rows"]
    success_list = payload.get("success_list") if isinstance(payload.get("success_list"), list) else []
    error_list = payload.get("error_list") if isinstance(payload.get("error_list"), list) else []
    rows: list[dict[str, Any]] = []
    for item in success_list[:100]:
        if isinstance(item, dict):
            rows.append(
                {
                    "结果": "成功",
                    "账户 ID": _text(item.get("advertiser_id") or item.get("target_advertiser_id")),
                    "项目 ID": _text(item.get("project_id")),
                    "站点 ID": _text(item.get("site_id")),
                    "说明": _text(item.get("status") or item.get("message")),
                }
            )
    for item in error_list[:100]:
        if isinstance(item, dict):
            rows.append(
                {
                    "结果": "失败",
                    "账户 ID": _text(item.get("advertiser_id") or item.get("target_advertiser_id")),
                    "项目 ID": _text(item.get("project_id")),
                    "站点 ID": _text(item.get("site_id")),
                    "说明": _text(item.get("message") or item.get("error_reason") or item.get("reason")),
                }
            )
    return rows


def build_payload_chinese_summary(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    if isinstance(payload.get("account_remark_update"), dict):
        return build_account_remark_execution_review(payload)["summary"]
    actions = _rows(payload.get("actions"))
    if actions:
        return build_project_update_execution_review(payload)["summary"]
    project_update = payload.get("project_update") if isinstance(payload.get("project_update"), dict) else {}
    if project_update:
        return build_project_update_execution_review(project_update)["summary"]

    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    result: dict[str, Any] = {}
    if "ok" in payload:
        result["结果"] = "成功" if bool(payload.get("ok")) else "失败"
    workflow = _text(payload.get("workflow"))
    if workflow:
        result["流程"] = workflow
    status = _text(payload.get("status"))
    if status:
        result["状态"] = status
    if "execution_enabled" in payload:
        result["真实执行"] = "是" if bool(payload.get("execution_enabled")) else "否"
    if "external_api_calls" in payload:
        result["接口调用"] = payload.get("external_api_calls")
    action_count = summary.get("action_count") or summary.get("request_count")
    if action_count not in (None, ""):
        result["动作数"] = action_count
    project_count = (
        summary.get("updated_project_count")
        or summary.get("project_count")
        or summary.get("site_count")
        or summary.get("success_count")
    )
    if project_count not in (None, ""):
        result["项目数"] = project_count
    account_count = summary.get("advertiser_count") or summary.get("account_count")
    if account_count not in (None, ""):
        result["账户数"] = account_count
    blocking = payload.get("blocking_reasons") if isinstance(payload.get("blocking_reasons"), list) else []
    if blocking:
        result["阻断原因"] = "；".join(_text(item) for item in blocking if _text(item))
    artifact_path = _text(payload.get("artifact_path") or summary.get("artifact_path"))
    if artifact_path:
        result["结果文件"] = artifact_path
    return result


def build_account_remark_execution_review(account_update: dict[str, Any]) -> dict[str, Any]:
    cfg = account_update.get("account_remark_update") if isinstance(account_update.get("account_remark_update"), dict) else account_update
    advertiser_ids = [_text(item) for item in cfg.get("advertiser_ids", []) if _text(item)] if isinstance(cfg.get("advertiser_ids"), list) else []
    remark = _text(cfg.get("remark"))
    rows = [{"动作": "修改账户备注", "账户 ID": advertiser_id, "目标备注": remark} for advertiser_id in advertiser_ids]
    return {
        "summary": {"动作": "修改账户备注", "账户数": len(rows), "目标备注": remark},
        "rows": rows,
    }
