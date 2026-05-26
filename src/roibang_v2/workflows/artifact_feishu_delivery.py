from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from roibang_v2.workflows.scheduler_status import send_feishu_app_chat_text

FeishuSender = Callable[[dict[str, Any], str], dict[str, Any]]


def _format_number(value: Any, *, digits: int = 2) -> str:
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        return "0"
    if number.is_integer():
        return str(int(number))
    return f"{number:.{digits}f}".rstrip("0").rstrip(".")


def _status_line(artifact: dict[str, Any]) -> str:
    workflow = str(artifact.get("workflow") or "unknown")
    status = str(artifact.get("status") or "unknown")
    ok = "成功" if bool(artifact.get("ok", False)) else "需要处理"
    return f"{workflow}：{ok}，状态 {status}"


def _summary_lines(summary: dict[str, Any]) -> list[str]:
    fields = [
        ("created_project_count", "创建项目"),
        ("created_unit_count", "创建单元"),
        ("material_bind_count", "素材推送"),
        ("source_external_api_calls", "外部接口调用"),
        ("external_api_calls", "外部接口调用"),
        ("account_count", "账户"),
        ("project_count", "项目"),
        ("promotion_count", "单元"),
        ("unit_count", "单元"),
    ]
    lines: list[str] = []
    for key, label in fields:
        if key in summary:
            lines.append(f"- {label}：{_format_number(summary.get(key))}")
    return lines[:8]


def _selected_material_lines(artifact: dict[str, Any]) -> list[str]:
    selected = artifact.get("readable_reference", {}).get("selected_materials", {})
    if not isinstance(selected, dict) or not selected:
        return []
    lines = [
        "选材摘要",
        f"- 素材分配：{int(selected.get('assignment_count') or 0)} 次",
        f"- 唯一素材：{int(selected.get('unique_material_count') or 0)} 个",
    ]
    top_materials = selected.get("top_materials_by_cost") if isinstance(selected.get("top_materials_by_cost"), list) else []
    if top_materials:
        lines.append("高消耗素材 Top 5")
        for row in top_materials[:5]:
            if not isinstance(row, dict):
                continue
            lines.append(
                "- "
                f"{row.get('name') or '未命名素材'}（{row.get('material_id') or ''}）："
                f"消耗 {_format_number(row.get('stat_cost'))}，"
                f"转化 {_format_number(row.get('convert_cnt'))}，"
                f"使用 {int(row.get('assigned_count') or 0)} 次"
            )
    return lines


def format_artifact_feishu_message(artifact: dict[str, Any], *, artifact_path: str = "") -> str:
    lines = ["RoiBang-V2 任务执行报告", "", _status_line(artifact)]
    message = str(artifact.get("message") or "").strip()
    if message:
        lines.extend(["", message])
    summary = artifact.get("summary") if isinstance(artifact.get("summary"), dict) else {}
    summary_lines = _summary_lines(summary)
    if summary_lines:
        lines.extend(["", "关键数据", *summary_lines])
    selected_lines = _selected_material_lines(artifact)
    if selected_lines:
        lines.extend(["", *selected_lines])
    path = str(artifact_path or artifact.get("artifact_path") or "")
    if path:
        lines.extend(["", f"完整 JSON：{path}"])
    return "\n".join(lines)


def deliver_artifact_to_feishu(
    artifact: dict[str, Any],
    *,
    artifact_path: str | Path = "",
    runtime_file: str = "data/secrets/feishu.runtime.local.json",
    feishu_sender: FeishuSender | None = None,
) -> dict[str, Any]:
    if not str(runtime_file or "").strip():
        return {"enabled": False, "attempted": False, "ok": True, "reason": "missing_runtime_file"}
    message = format_artifact_feishu_message(artifact, artifact_path=str(artifact_path or ""))
    try:
        delivery = (feishu_sender or send_feishu_app_chat_text)({"enabled": True, "runtime_file": runtime_file}, message)
    except Exception as exc:
        return {"enabled": True, "attempted": True, "ok": False, "reason": str(exc)}
    return {"enabled": True, "attempted": True, **delivery}
