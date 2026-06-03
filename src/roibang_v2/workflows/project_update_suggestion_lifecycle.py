from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


WORKFLOW = "project_update_suggestion_lifecycle"

ACTION_OPERATIONS = {
    "delete_project": "delete_project",
    "status_update": "update_project_status",
    "budget_update": "update_project_budget",
    "bid_update": "update_project_cpa_bid",
    "roi_coeff_update": "update_project_roi_goal",
}

SUGGESTION_ACTION_OPERATIONS = {
    "suggest_delete_project": "delete_project",
    "delete_project": "delete_project",
    "suggest_close_project": "update_project_status",
    "pause_project": "update_project_status",
    "close_project": "update_project_status",
    "suggest_lower_budget": "update_project_budget",
    "adjust_project_budget": "update_project_budget",
    "suggest_lower_bid": "update_project_cpa_bid",
    "adjust_project_bid": "update_project_cpa_bid",
}

STATUS_LABELS = {
    "unprocessed": "未处理",
    "config_generated": "已生成配置",
    "execution_submitted": "已提交执行",
    "execution_completed": "已执行",
    "execution_failed": "执行失败",
}

STATUS_RANK = {
    "unprocessed": 0,
    "config_generated": 10,
    "execution_failed": 20,
    "execution_submitted": 30,
    "execution_completed": 40,
}

LOCKED_STATUSES = {"execution_submitted", "execution_completed"}


@dataclass(frozen=True)
class LifecycleEvent:
    status: str
    event_type: str
    path: str
    occurred_at: str
    message: str
    project_update_path: str = ""
    execute_artifact_path: str = ""
    blocking_reasons: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


def build_project_update_suggestion_lifecycle(
    *,
    project_root: str | Path,
    runs_dir: str | Path,
    suggestions_artifact: dict[str, Any] | None = None,
    suggestions_artifact_path: str = "",
    product_key: str = "",
) -> dict[str, Any]:
    root = Path(project_root)
    runs = Path(runs_dir)
    suggestions = _source_suggestions(suggestions_artifact or {}, product_key=product_key)
    records: dict[str, dict[str, Any]] = {}
    suggestion_ids_by_key: dict[str, set[str]] = {}
    for suggestion in suggestions:
        suggestion_id = _text(suggestion.get("suggestion_id"))
        if not suggestion_id:
            continue
        records[suggestion_id] = _base_record(
            suggestion_id=suggestion_id,
            suggestion=suggestion,
            source_suggestion_path=suggestions_artifact_path,
        )
        key = _action_key_from_suggestion(suggestion)
        if key:
            suggestion_ids_by_key.setdefault(key, set()).add(suggestion_id)

    index = _build_project_update_execution_index(root=root, runs_dir=runs)
    _merge_config_events(records, index=index)
    _merge_execution_events(records, suggestion_ids_by_key=suggestion_ids_by_key, index=index)

    lifecycle = [_finalize_record(record) for record in records.values()]
    lifecycle.sort(key=lambda row: (_text(row.get("product_key")), _text(row.get("suggestion_id"))))
    status_counts: dict[str, int] = {}
    locked_count = 0
    for row in lifecycle:
        status = _text(row.get("lifecycle_status")) or "unprocessed"
        status_counts[status] = status_counts.get(status, 0) + 1
        if row.get("locked_for_project_update"):
            locked_count += 1
    return {
        "ok": True,
        "workflow": WORKFLOW,
        "phase": "readonly_analysis",
        "execution_enabled": False,
        "external_api_calls": 0,
        "generated_at": _now_iso(),
        "summary": {
            "suggestion_count": len(lifecycle),
            "locked_suggestion_count": locked_count,
            "status_counts": status_counts,
        },
        "lifecycle": lifecycle,
        "by_suggestion_id": {row["suggestion_id"]: row for row in lifecycle},
        "completed_action_keys": sorted(index["completed_action_keys"]),
        "source": {
            "runs_dir": str(runs),
            "suggestions_artifact_path": suggestions_artifact_path,
            "product_key": product_key,
        },
        "guardrails": [
            "项目管理建议生命周期只读取本地配置和执行产物，不调用外部接口。",
            "已执行或已提交执行的项目管理建议会被锁定，避免重复删除、暂停、调预算或调出价。",
        ],
    }


def project_update_config_duplicate_reasons(
    *,
    project_root: str | Path,
    runs_dir: str | Path,
    project_update: dict[str, Any],
) -> list[str]:
    root = Path(project_root)
    index = _build_project_update_execution_index(root=root, runs_dir=Path(runs_dir))
    action_keys = [_action_key_from_action(action) for action in _rows(project_update.get("actions"))]
    action_keys = [key for key in action_keys if key]
    if not action_keys:
        return []
    completed = [key for key in action_keys if key in index["completed_action_keys"]]
    if not completed:
        return []
    if len(set(completed)) >= len(set(action_keys)):
        return ["这份投放建议生成的项目管理配置已经执行完成，不能重复确认执行。"]
    return [
        f"这份投放建议生成的项目管理配置中已有 {len(set(completed))} 个动作执行完成，不能重复确认执行；"
        "请返回投放建议工作台刷新后重新生成未处理建议。"
    ]


def _build_project_update_execution_index(*, root: Path, runs_dir: Path) -> dict[str, Any]:
    config_refs_by_key: dict[str, list[dict[str, Any]]] = {}
    config_refs_by_path: dict[str, dict[str, list[dict[str, Any]]]] = {}
    suggestion_ids_by_key: dict[str, set[str]] = {}
    configs_dir = root / "configs" / "project-updates"
    for path in _recent_json_paths(configs_dir, limit=1000):
        payload = _load_json(path)
        if not payload:
            continue
        display_path = _display_path(root, path)
        per_path: dict[str, list[dict[str, Any]]] = {}
        for action in _rows(payload.get("actions")):
            key = _action_key_from_action(action)
            if not key:
                continue
            suggestion_id = _text(action.get("source_suggestion_id"))
            ref = {
                "suggestion_id": suggestion_id,
                "project_update_path": display_path,
                "project_update_id": _text(payload.get("project_update_id")),
                "action": action,
            }
            config_refs_by_key.setdefault(key, []).append(ref)
            per_path.setdefault(key, []).append(ref)
            if suggestion_id:
                suggestion_ids_by_key.setdefault(key, set()).add(suggestion_id)
        if per_path:
            config_refs_by_path[display_path] = per_path
            config_refs_by_path[str(path)] = per_path
            try:
                config_refs_by_path[str(path.resolve())] = per_path
            except OSError:
                pass

    completed_action_keys: set[str] = set()
    execution_events: list[dict[str, Any]] = []
    for path in _recent_json_paths(runs_dir / "project_update_execute", limit=1000):
        payload = _load_json(path)
        if not payload:
            continue
        execute_path = _display_path(root, path)
        project_update_path = _project_update_path_from_execution(root, payload)
        per_path_refs = config_refs_by_path.get(project_update_path, {})
        occurred_at = _artifact_time(path, payload)
        for result in _rows(payload.get("results")):
            operation = _text(result.get("operation"))
            advertiser_id = _text(result.get("advertiser_id"))
            for project_id in _texts(result.get("project_ids")):
                key = _action_key(operation, advertiser_id, project_id)
                if not key:
                    continue
                completed_action_keys.add(key)
                execution_events.append(
                    _execution_event(
                        key=key,
                        status="execution_completed",
                        event_type="project_update_execute",
                        path=execute_path,
                        occurred_at=occurred_at,
                        message="项目管理动作已执行完成。",
                        project_update_path=project_update_path,
                        execute_artifact_path=execute_path,
                        refs=_refs_for_key(key, per_path_refs, config_refs_by_key),
                    )
                )
            for error in _rows(result.get("error_list")):
                project_id = _text(error.get("project_id"))
                key = _action_key(operation, advertiser_id, project_id)
                if not key:
                    continue
                terminal_delete_failure = operation == "delete_project" and _is_deleted_or_missing_error(error)
                status = "execution_completed" if terminal_delete_failure else "execution_failed"
                if terminal_delete_failure:
                    completed_action_keys.add(key)
                execution_events.append(
                    _execution_event(
                        key=key,
                        status=status,
                        event_type="project_update_execute",
                        path=execute_path,
                        occurred_at=occurred_at,
                        message="项目已经不存在或已删除，无需重复执行。" if terminal_delete_failure else "项目管理动作执行失败。",
                        project_update_path=project_update_path,
                        execute_artifact_path=execute_path,
                        refs=_refs_for_key(key, per_path_refs, config_refs_by_key),
                        blocking_reasons=tuple([_error_text(error)] if _error_text(error) else []),
                    )
                )
    return {
        "config_refs_by_key": config_refs_by_key,
        "suggestion_ids_by_key": suggestion_ids_by_key,
        "execution_events": execution_events,
        "completed_action_keys": completed_action_keys,
    }


def _merge_config_events(records: dict[str, dict[str, Any]], *, index: dict[str, Any]) -> None:
    for refs in index["config_refs_by_key"].values():
        for ref in refs:
            suggestion_id = _text(ref.get("suggestion_id"))
            if not suggestion_id:
                continue
            record = records.setdefault(suggestion_id, _base_record(suggestion_id=suggestion_id))
            _append_event(
                record,
                LifecycleEvent(
                    status="config_generated",
                    event_type="project_update_from_suggestions",
                    path=_text(ref.get("project_update_path")),
                    occurred_at="",
                    message="投放建议已生成项目管理配置。",
                    project_update_path=_text(ref.get("project_update_path")),
                ),
            )


def _merge_execution_events(
    records: dict[str, dict[str, Any]],
    *,
    suggestion_ids_by_key: dict[str, set[str]],
    index: dict[str, Any],
) -> None:
    for event in index["execution_events"]:
        key = _text(event.get("action_key"))
        ids = set(_texts(event.get("source_suggestion_ids")))
        ids.update(index["suggestion_ids_by_key"].get(key, set()))
        ids.update(suggestion_ids_by_key.get(key, set()))
        for suggestion_id in sorted(ids):
            record = records.setdefault(suggestion_id, _base_record(suggestion_id=suggestion_id))
            _append_event(
                record,
                LifecycleEvent(
                    status=_text(event.get("status")),
                    event_type=_text(event.get("event_type")),
                    path=_text(event.get("path")),
                    occurred_at=_text(event.get("occurred_at")),
                    message=_text(event.get("message")),
                    project_update_path=_text(event.get("project_update_path")),
                    execute_artifact_path=_text(event.get("execute_artifact_path")),
                    blocking_reasons=tuple(_texts(event.get("blocking_reasons"))),
                ),
            )


def _execution_event(
    *,
    key: str,
    status: str,
    event_type: str,
    path: str,
    occurred_at: str,
    message: str,
    project_update_path: str,
    execute_artifact_path: str,
    refs: list[dict[str, Any]],
    blocking_reasons: tuple[str, ...] = (),
) -> dict[str, Any]:
    return {
        "action_key": key,
        "status": status,
        "event_type": event_type,
        "path": path,
        "occurred_at": occurred_at,
        "message": message,
        "project_update_path": project_update_path,
        "execute_artifact_path": execute_artifact_path,
        "source_suggestion_ids": _unique(_text(ref.get("suggestion_id")) for ref in refs),
        "blocking_reasons": list(blocking_reasons),
    }


def _refs_for_key(
    key: str,
    per_path_refs: dict[str, list[dict[str, Any]]],
    config_refs_by_key: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    refs = per_path_refs.get(key)
    if refs:
        return refs
    return config_refs_by_key.get(key, [])


def _base_record(
    *,
    suggestion_id: str,
    suggestion: dict[str, Any] | None = None,
    source_suggestion_path: str = "",
) -> dict[str, Any]:
    suggestion = suggestion or {}
    return {
        "suggestion_id": suggestion_id,
        "product_key": _text(suggestion.get("product_key")),
        "product_name": _text(suggestion.get("product_name") or suggestion.get("product")),
        "advertiser_id": _text(suggestion.get("advertiser_id")),
        "account_name": _text(suggestion.get("account_name") or suggestion.get("advertiser_name")),
        "project_id": _text(suggestion.get("project_id") or suggestion.get("entity_id")),
        "project_name": _text(suggestion.get("project_name") or suggestion.get("entity_name")),
        "suggested_action": _text(suggestion.get("suggested_action") or suggestion.get("suggestion_type") or suggestion.get("action")),
        "source_suggestion_path": source_suggestion_path,
        "events": [],
    }


def _append_event(record: dict[str, Any], event: LifecycleEvent) -> None:
    events = record.setdefault("events", [])
    if isinstance(events, list):
        events.append(
            {
                "status": event.status,
                "event_type": event.event_type,
                "path": event.path,
                "occurred_at": event.occurred_at,
                "message": event.message,
                "project_update_path": event.project_update_path,
                "execute_artifact_path": event.execute_artifact_path,
                "blocking_reasons": list(event.blocking_reasons),
                "warnings": list(event.warnings),
            }
        )


def _finalize_record(record: dict[str, Any]) -> dict[str, Any]:
    events = _rows(record.get("events"))
    selected = _latest_best_event(events)
    status = _text(selected.get("status")) if selected else "unprocessed"
    last_event_at = _text(selected.get("occurred_at")) if selected else ""
    locked = status in LOCKED_STATUSES
    return {
        **{key: value for key, value in record.items() if key != "events"},
        "lifecycle_status": status,
        "lifecycle_label": STATUS_LABELS.get(status, status or "未处理"),
        "locked_for_project_update": locked,
        "lock_reason": "该项目管理建议已经进入执行链路，不能重复生成配置。" if locked else "",
        "project_update_path": _latest_value(events, "project_update_path"),
        "execute_artifact_path": _latest_value(events, "execute_artifact_path"),
        "blocking_reasons": _event_texts(events, "blocking_reasons"),
        "warnings": _event_texts(events, "warnings"),
        "last_event_at": last_event_at,
        "last_event_type": _text(selected.get("event_type")) if selected else "",
        "events": sorted(events, key=lambda row: (_text(row.get("occurred_at")), _text(row.get("path")))),
    }


def _latest_best_event(events: list[dict[str, Any]]) -> dict[str, Any]:
    if not events:
        return {}
    return sorted(
        events,
        key=lambda row: (
            STATUS_RANK.get(_text(row.get("status")), 0),
            _text(row.get("occurred_at")),
            _text(row.get("path")),
        ),
    )[-1]


def _action_key_from_action(action: dict[str, Any]) -> str:
    operation = ACTION_OPERATIONS.get(_text(action.get("action_type")))
    return _action_key(operation or "", _text(action.get("advertiser_id")), _text(action.get("project_id")))


def _action_key_from_suggestion(suggestion: dict[str, Any]) -> str:
    action = _text(suggestion.get("suggested_action") or suggestion.get("suggestion_type") or suggestion.get("action")).lower()
    operation = SUGGESTION_ACTION_OPERATIONS.get(action)
    project_id = _text(suggestion.get("project_id") or suggestion.get("entity_id"))
    return _action_key(operation or "", _text(suggestion.get("advertiser_id")), project_id)


def _action_key(operation: str, advertiser_id: str, project_id: str) -> str:
    if not operation or not advertiser_id or not project_id:
        return ""
    return f"{operation}:{advertiser_id}:{project_id}"


def _project_update_path_from_execution(root: Path, payload: dict[str, Any]) -> str:
    path_text = _text(payload.get("project_update_path"))
    if not path_text:
        return ""
    path = Path(path_text)
    if path.is_absolute():
        return _display_path(root, path)
    return path_text


def _source_suggestions(payload: dict[str, Any], *, product_key: str) -> list[dict[str, Any]]:
    rows = _rows(payload.get("suggestions")) + _rows(payload.get("source_suggestions"))
    if not product_key:
        return rows
    return [row for row in rows if _text(row.get("product_key")) == product_key]


def _is_deleted_or_missing_error(error: dict[str, Any]) -> bool:
    text = _error_text(error).lower()
    return any(part in text for part in ["不存在", "已被删除", "not exist", "not found", "deleted"])


def _error_text(error: dict[str, Any]) -> str:
    for key in ["message", "reason", "error", "msg"]:
        text = _text(error.get(key))
        if text:
            return text
    return json.dumps(error, ensure_ascii=False, sort_keys=True) if error else ""


def _event_texts(events: list[dict[str, Any]], key: str) -> list[str]:
    output: list[str] = []
    for event in events:
        output.extend(_texts(event.get(key)))
    return _unique(output)


def _latest_value(events: list[dict[str, Any]], key: str) -> str:
    values = [
        (_text(event.get("occurred_at")), _text(event.get(key)))
        for event in events
        if _text(event.get(key))
    ]
    if not values:
        return ""
    return sorted(values)[-1][1]


def _recent_json_paths(directory: Path, *, limit: int) -> list[Path]:
    if not directory.exists():
        return []
    paths = [path for path in directory.glob("*.json") if path.name != "latest.json"]
    latest = directory / "latest.json"
    paths = sorted(paths, reverse=True)
    if latest.exists():
        paths.insert(0, latest)
    return paths[:limit]


def _artifact_time(path: Path, payload: dict[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    for value in [
        payload.get("generated_at"),
        payload.get("created_at"),
        summary.get("generated_at") if isinstance(summary, dict) else "",
        summary.get("created_at") if isinstance(summary, dict) else "",
    ]:
        text = _text(value)
        if text:
            return text
    try:
        return datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat(timespec="seconds")
    except OSError:
        return ""


def _display_path(root: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except (OSError, ValueError):
        return str(path)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _rows(value: Any) -> list[dict[str, Any]]:
    return [dict(item) for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _texts(value: Any) -> list[str]:
    if isinstance(value, list):
        return [_text(item) for item in value if _text(item)]
    text = _text(value)
    return [text] if text else []


def _unique(values: Any) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _text(value)
        if text and text not in seen:
            output.append(text)
            seen.add(text)
    return output


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _text(value: Any) -> str:
    return str(value or "").strip()
