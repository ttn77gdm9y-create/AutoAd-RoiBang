from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


WORKFLOW = "create_suggestion_lifecycle"


@dataclass(frozen=True)
class LifecycleEvent:
    status: str
    event_type: str
    path: str
    occurred_at: str
    message: str = ""
    plan_preview_path: str = ""
    execution_review_path: str = ""
    execution_task_id: str = ""
    execution_status: str = ""
    blocking_reasons: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


STATUS_LABELS = {
    "unprocessed": "未处理",
    "plan_previewed": "已生成计划预览",
    "plan_split_required": "需拆分计划批次",
    "reviewed_ready": "复核通过",
    "reviewed_warning": "复核有警告",
    "reviewed_blocked": "复核阻断",
    "execution_submitted": "已提交执行",
    "execution_completed": "执行完成",
    "execution_failed": "执行失败",
}

STATUS_RANK = {
    "unprocessed": 0,
    "plan_split_required": 8,
    "plan_previewed": 10,
    "reviewed_blocked": 18,
    "reviewed_ready": 20,
    "reviewed_warning": 20,
    "execution_submitted": 30,
    "execution_failed": 40,
    "execution_completed": 45,
}

LOCKED_STATUSES = {"execution_submitted", "execution_completed", "execution_failed"}


def build_create_suggestion_lifecycle(
    *,
    runs_dir: str | Path,
    project_root: str | Path = ".",
    suggestions_artifact: dict[str, Any] | None = None,
    suggestions_artifact_path: str = "",
    product_key: str = "",
) -> dict[str, Any]:
    root = Path(project_root)
    runs = Path(runs_dir)
    suggestions = _source_suggestions(suggestions_artifact or {}, product_key=product_key)
    records: dict[str, dict[str, Any]] = {}
    for suggestion in suggestions:
        suggestion_id = _text(suggestion.get("suggestion_id"))
        if not suggestion_id:
            continue
        records[suggestion_id] = _base_record(
            suggestion_id=suggestion_id,
            suggestion=suggestion,
            source_suggestion_path=suggestions_artifact_path,
        )

    plan_ids_to_suggestion_ids: dict[str, set[str]] = {}
    _merge_plan_preview_events(records, plan_ids_to_suggestion_ids, root=root, runs_dir=runs)
    _merge_execution_review_events(records, plan_ids_to_suggestion_ids, root=root, runs_dir=runs)
    _merge_frontend_operation_events(records, plan_ids_to_suggestion_ids, root=root, runs_dir=runs)
    _merge_create_live_execute_events(records, plan_ids_to_suggestion_ids, root=root, runs_dir=runs)

    lifecycle = [_finalize_record(record) for record in records.values()]
    lifecycle.sort(key=lambda row: (_text(row.get("product_key")), _text(row.get("suggestion_id"))))
    status_counts: dict[str, int] = {}
    locked_count = 0
    for row in lifecycle:
        status = _text(row.get("lifecycle_status")) or "unprocessed"
        status_counts[status] = status_counts.get(status, 0) + 1
        if row.get("locked_for_create_plan"):
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
        "source": {
            "runs_dir": str(runs),
            "suggestions_artifact_path": suggestions_artifact_path,
            "product_key": product_key,
        },
        "guardrails": [
            "生命周期索引只读取本地 artifact，不调用外部接口。",
            "进入真实执行或已有执行结果的创建建议会被锁定，避免重复创建。",
        ],
    }


def _merge_plan_preview_events(
    records: dict[str, dict[str, Any]],
    plan_ids_to_suggestion_ids: dict[str, set[str]],
    *,
    root: Path,
    runs_dir: Path,
) -> None:
    for path in _recent_json_paths(runs_dir / "create_plan_from_suggestions", limit=300):
        payload = _load_json(path)
        if not payload:
            continue
        source_ids = _unique(_text(item) for item in _source_ids_from_create_plan_preview(payload))
        if not source_ids:
            continue
        display_path = _display_path(root, path)
        status = _text(payload.get("status"))
        lifecycle_status = "plan_split_required" if status == "split_required" else "plan_previewed"
        occurred_at = _artifact_time(path, payload)
        blocking = _texts(payload.get("blocking_reasons"))
        warnings = [*_texts(payload.get("warnings")), *_texts(payload.get("split_reasons"))]
        plan_id = _plan_id_from_path_or_payload(path, payload)
        if plan_id:
            plan_ids_to_suggestion_ids.setdefault(plan_id, set()).update(source_ids)
        for suggestion_id in source_ids:
            record = records.setdefault(suggestion_id, _base_record(suggestion_id=suggestion_id))
            _append_event(
                record,
                LifecycleEvent(
                    status=lifecycle_status,
                    event_type="create_plan_from_suggestions",
                    path=display_path,
                    occurred_at=occurred_at,
                    message="创建建议已转换为创建计划预览。",
                    plan_preview_path=display_path,
                    blocking_reasons=tuple(blocking),
                    warnings=tuple(warnings),
                ),
            )


def _merge_execution_review_events(
    records: dict[str, dict[str, Any]],
    plan_ids_to_suggestion_ids: dict[str, set[str]],
    *,
    root: Path,
    runs_dir: Path,
) -> None:
    for path in _recent_json_paths(runs_dir / "create_plan_execution_review", limit=300):
        payload = _load_json(path)
        if not payload:
            continue
        source_ids = _unique(_text(item) for item in _source_ids_from_execution_review(payload))
        if not source_ids:
            continue
        display_path = _display_path(root, path)
        status = _review_lifecycle_status(_text(payload.get("status")))
        occurred_at = _artifact_time(path, payload)
        blocking = _texts(payload.get("blocking_reasons"))
        warnings = _texts(payload.get("warnings"))
        summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
        plan_id = _text(summary.get("plan_id") or _operation_record(payload).get("plan_id"))
        if plan_id:
            plan_ids_to_suggestion_ids.setdefault(plan_id, set()).update(source_ids)
        for suggestion_id in source_ids:
            record = records.setdefault(suggestion_id, _base_record(suggestion_id=suggestion_id))
            _append_event(
                record,
                LifecycleEvent(
                    status=status,
                    event_type="create_plan_execution_review",
                    path=display_path,
                    occurred_at=occurred_at,
                    message="创建计划已完成执行前复核。",
                    execution_review_path=display_path,
                    blocking_reasons=tuple(blocking),
                    warnings=tuple(warnings),
                ),
            )


def _merge_frontend_operation_events(
    records: dict[str, dict[str, Any]],
    plan_ids_to_suggestion_ids: dict[str, set[str]],
    *,
    root: Path,
    runs_dir: Path,
) -> None:
    for path in _recent_json_paths(runs_dir / "frontend_operation_log", limit=500):
        payload = _load_json(path)
        if _text(payload.get("operation_type")) != "create_live_execute":
            continue
        source_ids = _unique(_source_ids_from_frontend_operation(payload, root=root))
        if not source_ids:
            plan_id = _plan_id_from_frontend_operation(payload)
            source_ids = sorted(plan_ids_to_suggestion_ids.get(plan_id, set())) if plan_id else []
        if not source_ids:
            continue
        display_path = _display_path(root, path)
        occurred_at = _artifact_time(path, payload)
        lifecycle_status = _execution_lifecycle_status(_text(payload.get("status")))
        request = payload.get("request") if isinstance(payload.get("request"), dict) else {}
        task_id = _text(payload.get("task_id") or request.get("task_id"))
        plan_id = _plan_id_from_frontend_operation(payload)
        if plan_id:
            plan_ids_to_suggestion_ids.setdefault(plan_id, set()).update(source_ids)
        for suggestion_id in source_ids:
            record = records.setdefault(suggestion_id, _base_record(suggestion_id=suggestion_id))
            _append_event(
                record,
                LifecycleEvent(
                    status=lifecycle_status,
                    event_type="frontend_operation_log",
                    path=display_path,
                    occurred_at=occurred_at,
                    message="创建计划已进入真实执行任务链路。",
                    execution_task_id=task_id,
                    execution_status=_text(payload.get("status")),
                ),
            )


def _merge_create_live_execute_events(
    records: dict[str, dict[str, Any]],
    plan_ids_to_suggestion_ids: dict[str, set[str]],
    *,
    root: Path,
    runs_dir: Path,
) -> None:
    for path in _recent_json_paths(runs_dir / "create_live_execute_once", limit=500):
        payload = _load_json(path)
        plan_id = _plan_id_from_create_live_execute(payload)
        source_ids = sorted(plan_ids_to_suggestion_ids.get(plan_id, set())) if plan_id else []
        if not source_ids:
            continue
        display_path = _display_path(root, path)
        occurred_at = _artifact_time(path, payload)
        lifecycle_status = _execution_lifecycle_status(_text(payload.get("status")))
        blocking = _texts(payload.get("blocking_reasons") or payload.get("errors"))
        for suggestion_id in source_ids:
            record = records.setdefault(suggestion_id, _base_record(suggestion_id=suggestion_id))
            _append_event(
                record,
                LifecycleEvent(
                    status=lifecycle_status,
                    event_type="create_live_execute_once",
                    path=display_path,
                    occurred_at=occurred_at,
                    message="真实创建执行产物已生成。",
                    execution_status=_text(payload.get("status")),
                    blocking_reasons=tuple(blocking),
                ),
            )


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
        "suggested_action": _text(suggestion.get("suggested_action") or suggestion.get("suggestion_type") or suggestion.get("action")),
        "strategy_ids": _unique([_text(suggestion.get("strategy_id") or suggestion.get("rule_id"))]),
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
                "plan_preview_path": event.plan_preview_path,
                "execution_review_path": event.execution_review_path,
                "execution_task_id": event.execution_task_id,
                "execution_status": event.execution_status,
                "blocking_reasons": list(event.blocking_reasons),
                "warnings": list(event.warnings),
            }
        )


def _finalize_record(record: dict[str, Any]) -> dict[str, Any]:
    events = _rows(record.get("events"))
    selected = _latest_best_event(events)
    status = _text(selected.get("status")) if selected else "unprocessed"
    blocking_reasons = _event_texts(events, "blocking_reasons")
    warnings = _event_texts(events, "warnings")
    plan_preview_path = _latest_value(events, "plan_preview_path")
    execution_review_path = _latest_value(events, "execution_review_path")
    execution_task_id = _latest_value(events, "execution_task_id")
    execution_status = _latest_value(events, "execution_status")
    last_event_at = _text(selected.get("occurred_at")) if selected else ""
    return {
        **{key: value for key, value in record.items() if key != "events"},
        "lifecycle_status": status,
        "lifecycle_label": STATUS_LABELS.get(status, status or "未处理"),
        "locked_for_create_plan": status in LOCKED_STATUSES,
        "lock_reason": "该创建建议已经进入真实执行链路，不能重复生成创建计划。" if status in LOCKED_STATUSES else "",
        "plan_preview_path": plan_preview_path,
        "execution_review_path": execution_review_path,
        "execution_task_id": execution_task_id,
        "execution_status": execution_status,
        "blocking_reasons": blocking_reasons,
        "warnings": warnings,
        "last_event_at": last_event_at,
        "last_event_type": _text(selected.get("event_type")) if selected else "",
        "events": sorted(events, key=lambda row: _text(row.get("occurred_at"))),
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


def _source_suggestions(payload: dict[str, Any], *, product_key: str) -> list[dict[str, Any]]:
    rows = _rows(payload.get("suggestions")) + _rows(payload.get("source_suggestions"))
    if not product_key:
        return rows
    return [row for row in rows if _text(row.get("product_key")) == product_key]


def _source_ids_from_create_plan_preview(payload: dict[str, Any]) -> list[str]:
    source = payload.get("source") if isinstance(payload.get("source"), dict) else {}
    ids = _texts(source.get("source_suggestion_ids"))
    if ids:
        return ids
    ids = []
    for group in _rows(payload.get("suggestion_groups")):
        ids.extend(_texts(group.get("source_suggestion_ids")))
    if ids:
        return ids
    return [_text(row.get("suggestion_id")) for row in _rows(payload.get("source_suggestions")) if _text(row.get("suggestion_id"))]


def _source_ids_from_execution_review(payload: dict[str, Any]) -> list[str]:
    record = _operation_record(payload)
    ids = _texts(record.get("source_suggestion_ids"))
    if ids:
        return ids
    manifest = payload.get("execution_manifest") if isinstance(payload.get("execution_manifest"), dict) else {}
    return [_text(row.get("suggestion_id")) for row in _rows(manifest.get("source_suggestions")) if _text(row.get("suggestion_id"))]


def _source_ids_from_frontend_operation(payload: dict[str, Any], *, root: Path) -> list[str]:
    details = payload.get("details") if isinstance(payload.get("details"), dict) else {}
    ids = _texts(details.get("source_suggestion_ids"))
    if ids:
        return ids
    request = payload.get("request") if isinstance(payload.get("request"), dict) else {}
    review_path = _text(request.get("execution_review_artifact_path"))
    if review_path:
        review = _load_json(_resolve_path(root, review_path))
        ids = _source_ids_from_execution_review(review)
        if ids:
            return ids
    review = details.get("execution_review") if isinstance(details.get("execution_review"), dict) else {}
    return _source_ids_from_execution_review(review)


def _operation_record(payload: dict[str, Any]) -> dict[str, Any]:
    return payload.get("operation_record") if isinstance(payload.get("operation_record"), dict) else {}


def _review_lifecycle_status(status: str) -> str:
    if status == "ready_for_confirmation":
        return "reviewed_ready"
    if status == "warning_only":
        return "reviewed_warning"
    if status == "blocked":
        return "reviewed_blocked"
    return "reviewed_warning" if status else "reviewed_ready"


def _execution_lifecycle_status(status: str) -> str:
    normalized = status.strip().lower()
    if normalized in {"completed", "success", "succeeded", "executed", "create_http_completed"}:
        return "execution_completed"
    if normalized in {"failed", "partial_failed", "create_http_failed"}:
        return "execution_failed"
    return "execution_submitted"


def _plan_id_from_path_or_payload(path: Path, payload: dict[str, Any]) -> str:
    request = payload.get("create_plan_request") if isinstance(payload.get("create_plan_request"), dict) else {}
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    return _text(summary.get("plan_id") or request.get("plan_id") or path.stem)


def _plan_id_from_frontend_operation(payload: dict[str, Any]) -> str:
    result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
    details = payload.get("details") if isinstance(payload.get("details"), dict) else {}
    return _text(result.get("plan_id") or details.get("plan_id"))


def _plan_id_from_create_live_execute(payload: dict[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    return _text(payload.get("plan_id") or summary.get("plan_id"))


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
    except ValueError:
        return str(path)


def _resolve_path(root: Path, path_text: str) -> Path:
    path = Path(path_text)
    return path if path.is_absolute() else root / path


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
