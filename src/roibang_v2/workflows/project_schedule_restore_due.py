from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from roibang_v2.runs import write_run_artifact
from roibang_v2.workflows.project_update_execute import run_project_update_execute_request


Transport = Callable[[dict[str, Any]], dict[str, Any]]
LOCAL_TZ = timezone(timedelta(hours=8))


def _text(value: Any) -> str:
    return str(value or "").strip()


def _rows(value: Any) -> list[dict[str, Any]]:
    return [dict(item) for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _parse_dt(value: str) -> datetime:
    text = _text(value)
    if not text:
        raise ValueError("restore_at must not be empty")
    normalized = text.replace(" ", "T")
    dt = datetime.fromisoformat(normalized)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=LOCAL_TZ)
    return dt.astimezone(LOCAL_TZ)


def _now(value: Any) -> datetime:
    if value:
        return _parse_dt(_text(value))
    return datetime.now(LOCAL_TZ)


def _load_queue(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "source": "project_update_execute", "items": []}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {"version": 1, "source": "project_update_execute", "items": []}
    if not isinstance(payload.get("items"), list):
        payload["items"] = []
    return payload


def _save_queue(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _ledger_entries(path: str | Path) -> dict[tuple[str, str], dict[str, Any]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return {
        (_text(entry.get("advertiser_id")), _text(entry.get("project_id"))): dict(entry)
        for entry in _rows(payload.get("entries"))
        if entry.get("action_type") == "schedule_hollow"
    }


def _due_items(items: list[dict[str, Any]], now_dt: datetime) -> list[dict[str, Any]]:
    due: list[dict[str, Any]] = []
    for item in items:
        if _text(item.get("status")) != "pending":
            continue
        try:
            restore_at = _parse_dt(_text(item.get("restore_at")))
        except ValueError:
            continue
        if restore_at <= now_dt:
            due.append(item)
    return due


def _queue_counts(items: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "pending_item_count": sum(1 for item in items if _text(item.get("status")) == "pending"),
        "completed_item_count": sum(1 for item in items if _text(item.get("status")) == "completed"),
        "failed_status_item_count": sum(1 for item in items if _text(item.get("status")) == "failed"),
    }


def _item_brief(item: dict[str, Any], *, error: str = "") -> dict[str, Any]:
    return {
        "restore_id": _text(item.get("restore_id")),
        "advertiser_id": _text(item.get("advertiser_id")),
        "project_id": _text(item.get("project_id")),
        "project_name": _text(item.get("project_name")),
        "restore_at": _text(item.get("restore_at")),
        "error": error,
    }


def _mark_attempt_failed(items: list[dict[str, Any]], due: list[dict[str, Any]], *, now_dt: datetime, error: str) -> None:
    due_ids = {_text(item.get("restore_id")) for item in due}
    for item in items:
        if _text(item.get("restore_id")) not in due_ids:
            continue
        item["status"] = "pending"
        item["last_error"] = error
        item["last_attempt_at"] = now_dt.isoformat()
        try:
            item["attempt_count"] = int(item.get("attempt_count") or 0) + 1
        except (TypeError, ValueError):
            item["attempt_count"] = 1


def _restore_project_update(due_items: list[dict[str, Any]]) -> dict[str, Any]:
    actions: list[dict[str, Any]] = []
    ledgers: dict[str, dict[tuple[str, str], dict[str, Any]]] = {}
    for item in due_items:
        ledger_path = _text(item.get("ledger_path"))
        ledgers.setdefault(ledger_path, _ledger_entries(ledger_path))
        ledger_entry = ledgers[ledger_path].get((_text(item.get("advertiser_id")), _text(item.get("project_id"))))
        if ledger_entry is None:
            raise RuntimeError(f"restore ledger entry not found: {item.get('restore_id')}")
        actions.append(
            {
                "action_type": "schedule_restore",
                "advertiser_id": _text(item.get("advertiser_id")),
                "entity_type": "project",
                "project_id": _text(item.get("project_id")),
                "project_name": _text(item.get("project_name") or ledger_entry.get("project_name")),
                "target_date": _text(item.get("target_date")),
                "restore_date": _text(item.get("restore_date")),
                "restore_at": _text(item.get("restore_at")),
                "original_schedule_time": _text(ledger_entry.get("original_schedule_time")),
                "reason": "restore_due_queue",
            }
        )
    restore_ids = "-".join(_text(item.get("restore_id")).replace(":", "_") for item in due_items)
    return {
        "project_update_id": f"project-schedule-restore-due-{restore_ids}"[:120],
        "operator": "system",
        "source": {"workflow": "project_schedule_restore_due"},
        "execution": {"enabled": False, "status": "planned_only"},
        "actions": actions,
        "restore_actions": [],
    }


def _preflight(project_update: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": True,
        "workflow": "project_update_preflight",
        "phase": "control_preflight",
        "status": "passed",
        "execution_enabled": False,
        "external_api_calls": 0,
        "summary": {
            "project_update_id": _text(project_update.get("project_update_id")),
            "action_count": len(_rows(project_update.get("actions"))),
        },
        "violations": [],
    }


def run_project_schedule_restore_due_request(
    request: dict[str, Any] | None,
    *,
    runs_dir: str | Path,
    transport: Transport | None = None,
) -> dict[str, Any]:
    cfg = dict(request or {})
    queue_path = Path(_text(cfg.get("restore_queue_path")) or Path(runs_dir) / "project_schedule_restore_queue.json")
    queue = _load_queue(queue_path)
    now_dt = _now(cfg.get("now"))
    items = _rows(queue.get("items"))
    due = _due_items(items, now_dt)
    execute_enabled = bool(cfg.get("execute_enabled", False))
    approved = bool(cfg.get("approved", False))
    restore_result: dict[str, Any] | None = None
    blocking_reasons: list[str] = []
    completed_items: list[dict[str, Any]] = []
    failed_items: list[dict[str, Any]] = []

    if due and execute_enabled and approved:
        if transport is None:
            blocking_reasons.append("restore due requires explicit transport")
            failed_items = [_item_brief(item, error="restore due requires explicit transport") for item in due]
            _mark_attempt_failed(items, due, now_dt=now_dt, error="restore due requires explicit transport")
            queue["items"] = items
            _save_queue(queue_path, queue)
        else:
            try:
                project_update = _restore_project_update(due)
                restore_result = run_project_update_execute_request(
                    {
                        "project_update": project_update,
                        "preflight_artifact": _preflight(project_update),
                        "execute_enabled": True,
                        "approved": True,
                        "schedule_scene": _text(cfg.get("schedule_scene") or "REALTIME"),
                        "restore_queue_path": str(queue_path),
                    },
                    runs_dir=runs_dir,
                    transport=transport,
                )
            except Exception as exc:
                error = str(exc)
                blocking_reasons.append(error)
                failed_items = [_item_brief(item, error=error) for item in due]
                _mark_attempt_failed(items, due, now_dt=now_dt, error=error)
                queue["items"] = items
                _save_queue(queue_path, queue)
            else:
                if restore_result.get("ok"):
                    completed_ids = {_text(item.get("restore_id")) for item in due}
                    for item in items:
                        if _text(item.get("restore_id")) in completed_ids:
                            item["status"] = "completed"
                            item["completed_at"] = now_dt.isoformat()
                            item["restore_artifact_path"] = _text(restore_result.get("artifact_path"))
                    completed_items = [_item_brief(item) for item in due]
                    queue["items"] = items
                    _save_queue(queue_path, queue)
                else:
                    errors = [_text(item) for item in restore_result.get("blocking_reasons") or []]
                    error = "；".join(errors) or "restore execution failed"
                    blocking_reasons.extend(errors or [error])
                    failed_items = [_item_brief(item, error=error) for item in due]
                    _mark_attempt_failed(items, due, now_dt=now_dt, error=error)
                    queue["items"] = items
                    _save_queue(queue_path, queue)

    counts = _queue_counts(items)
    payload = {
        "ok": not blocking_reasons,
        "workflow": "project_schedule_restore_due",
        "phase": "control_restore",
        "status": (
            "failed"
            if blocking_reasons
            else "completed"
            if due and execute_enabled and approved
            else "checked"
        ),
        "execution_enabled": execute_enabled,
        "external_api_calls": int(restore_result.get("external_api_calls") or 0) if restore_result else 0,
        "restore_queue_path": str(queue_path),
        "summary": {
            "queue_item_count": len(items),
            **counts,
            "due_item_count": len(due),
            "restored_item_count": len(due) if restore_result and restore_result.get("ok") else 0,
            "failed_item_count": len(failed_items),
        },
        "blocking_reasons": blocking_reasons,
        "due_items": due,
        "restore_report": {
            "completed": completed_items,
            "failed": failed_items,
            "pending": [_item_brief(item, error=_text(item.get("last_error"))) for item in items if _text(item.get("status")) == "pending"],
        },
        "restore_result": restore_result or {},
    }
    payload["artifact_path"] = str(write_run_artifact(runs_dir, "project_schedule_restore_due", payload))
    return payload
