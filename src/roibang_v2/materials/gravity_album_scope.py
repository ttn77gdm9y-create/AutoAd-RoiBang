from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEFAULT_TARGET_ALBUM_NAMES = [
    "黑旗-奇门（塔防）",
    "魔兽开箱子",
    "黑旗-6480咸鱼-微小合集",
]


def normalize_album_name(value: Any) -> str:
    text = str(value or "").strip()
    text = text.replace("（", "(").replace("）", ")")
    return "".join(text.split())


def load_target_album_names(project_root: str | Path | None = None, *, fallback: list[str] | None = None) -> list[str]:
    default_names = list(fallback or DEFAULT_TARGET_ALBUM_NAMES)
    if project_root is None:
        return default_names
    root = Path(project_root)
    for path in [
        root / "configs" / "gravity-material-target-albums.local.json",
        root / "configs" / "gravity-material-target-albums.json",
    ]:
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return default_names
        names = _target_names_from_payload(payload)
        return names or default_names
    return default_names


def target_album_match_rows(nodes: list[dict[str, Any]], target_names: list[str]) -> list[dict[str, Any]]:
    rows = []
    for target_name in target_names:
        matches = [node for node in nodes if _node_matches_target(node, target_name)]
        selected = matches[0] if len(matches) == 1 else {}
        rows.append(
            {
                "目标专辑": target_name,
                "匹配状态": _match_status(len(matches)),
                "匹配数量": len(matches),
                "专辑/文件夹 ID": _text(selected.get("专辑/文件夹 ID")),
                "名称": _text(selected.get("名称")),
                "层级": int(selected.get("层级") or 0),
                "album_id": _text(selected.get("album_id")),
                "album_name": _text(selected.get("album_name")),
                "folder_id": _text(selected.get("folder_id")),
                "folder_name": _text(selected.get("folder_name")),
                "可自动绑定": "是" if len(matches) == 1 else "否",
                "候选": matches,
            }
        )
    return rows


def binding_in_target_scope(binding: dict[str, Any], target_names: list[str]) -> bool:
    binding_names = {
        normalize_album_name(binding.get("album_name")),
        normalize_album_name(binding.get("folder_name")),
    }
    target_set = {normalize_album_name(name) for name in target_names}
    return bool(binding_names & target_set)


def binding_scope_blocking_reasons(bindings: list[dict[str, Any]], target_names: list[str]) -> list[str]:
    allowed = "、".join(target_names)
    reasons = []
    for binding in bindings:
        if binding_in_target_scope(binding, target_names):
            continue
        name = _binding_display_name(binding)
        reasons.append(f"引力绑定不在允许同步的引力专辑范围内：{name}。允许范围：{allowed}")
    return reasons


def _target_names_from_payload(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return []
    raw = payload.get("target_albums") or payload.get("allowed_album_names") or payload.get("albums")
    if not isinstance(raw, list):
        return []
    names = []
    for item in raw:
        if isinstance(item, dict):
            value = item.get("album_name") or item.get("name") or item.get("target_album")
        else:
            value = item
        text = _text(value)
        if text:
            names.append(text)
    return names


def _node_matches_target(node: dict[str, Any], target_name: str) -> bool:
    target = normalize_album_name(target_name)
    candidates = {
        normalize_album_name(node.get("名称")),
        normalize_album_name(node.get("album_name")),
        normalize_album_name(node.get("folder_name")),
    }
    return target in candidates


def _match_status(count: int) -> str:
    if count == 1:
        return "已匹配"
    if count > 1:
        return "多个匹配"
    return "未匹配"


def _binding_display_name(binding: dict[str, Any]) -> str:
    folder_name = _text(binding.get("folder_name"))
    album_name = _text(binding.get("album_name"))
    if folder_name and album_name:
        return f"{album_name} / {folder_name}"
    return folder_name or album_name or _text(binding.get("album_id")) or "未命名绑定"


def _text(value: Any) -> str:
    return str(value or "").strip()
