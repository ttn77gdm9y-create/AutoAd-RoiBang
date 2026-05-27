from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, IsADirectoryError, OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _float(value: Any) -> float:
    try:
        return round(float(value or 0), 2)
    except (TypeError, ValueError):
        return 0.0


def _legacy_task_id(path: Path, payload: dict[str, Any]) -> str:
    task_id = _text(payload.get("task_id"))
    if task_id:
        return task_id
    created_at = _text(payload.get("created_at")).replace(":", "").replace("+", "-")
    return f"legacy-{created_at or path.stem}"


def operation_log_row_from_artifact(payload: dict[str, Any], artifact_path: str | Path) -> dict[str, Any]:
    path = Path(artifact_path)
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
    return {
        "task_id": _legacy_task_id(path, payload),
        "operation_type": _text(payload.get("operation_type") or summary.get("operation_type")),
        "status": _text(payload.get("status") or summary.get("status")),
        "product": _text(summary.get("product")),
        "product_key": _text(summary.get("product_key")),
        "actor": _text(payload.get("actor")),
        "created_at": _text(payload.get("created_at")),
        "account_count": _int(summary.get("account_count")),
        "material_assignment_count": _int(summary.get("material_assignment_count")),
        "unique_material_count": _int(summary.get("unique_material_count")),
        "review_status": _text(summary.get("review_status")),
        "review_blocking_reason_count": _int(summary.get("review_blocking_reason_count")),
        "review_warning_count": _int(summary.get("review_warning_count")),
        "feishu_status": _text(summary.get("feishu_status")),
        "result_status": _text(result.get("status")),
        "execute_artifact_path": _text(result.get("execute_artifact_path")),
        "report_artifact_path": _text(result.get("report_artifact_path")),
        "artifact_path": str(path),
    }


def _frontend_task_path(runs_dir: Path, task_id: str) -> Path:
    return runs_dir / "frontend_tasks" / f"{task_id}.json"


def _load_frontend_task(runs_dir: Path, task_id: str) -> dict[str, Any]:
    if not task_id:
        return {}
    return _read_json(_frontend_task_path(runs_dir, task_id))


def _task_report_artifact_path(task: dict[str, Any]) -> str:
    post_results = task.get("post_results") if isinstance(task.get("post_results"), list) else []
    for row in post_results:
        if isinstance(row, dict) and _text(row.get("artifact_path")):
            return _text(row.get("artifact_path"))
    return ""


def _task_feishu_status(task: dict[str, Any]) -> str:
    post_results = task.get("post_results") if isinstance(task.get("post_results"), list) else []
    for row in post_results:
        if not isinstance(row, dict):
            continue
        delivery = row.get("delivery") if isinstance(row.get("delivery"), dict) else {}
        feishu = delivery.get("feishu") if isinstance(delivery.get("feishu"), dict) else {}
        if not feishu:
            continue
        if not bool(feishu.get("attempted")):
            return "not_attempted"
        return "sent" if bool(feishu.get("ok")) else "failed"
    return ""


def merge_frontend_task_row(row: dict[str, Any], task: dict[str, Any]) -> dict[str, Any]:
    if not task:
        return row
    result = task.get("result") if isinstance(task.get("result"), dict) else {}
    merged = dict(row)
    task_status = _text(task.get("status"))
    execute_artifact_path = _text(result.get("execute_artifact_path") or result.get("artifact_path"))
    report_artifact_path = _task_report_artifact_path(task)
    feishu_status = _task_feishu_status(task)
    merged.update(
        {
            "status": task_status or _text(row.get("status")),
            "task_status": task_status,
            "return_code": task.get("return_code"),
            "result_status": _text(result.get("status")) or _text(row.get("result_status")),
            "execute_artifact_path": execute_artifact_path or _text(row.get("execute_artifact_path")),
            "report_artifact_path": report_artifact_path or _text(row.get("report_artifact_path")),
            "feishu_status": feishu_status or _text(row.get("feishu_status")),
            "stdout_path": _text(task.get("stdout_path")),
            "stderr_path": _text(task.get("stderr_path")),
            "task_artifact_path": _text(task.get("artifact_path")),
            "task_updated_at": _text(task.get("updated_at")),
        }
    )
    return merged


def load_operation_logs(runs_dir: str | Path, *, limit: int = 200) -> list[dict[str, Any]]:
    runs_path = Path(runs_dir)
    log_dir = runs_path / "frontend_operation_log"
    paths = sorted(log_dir.glob("*.json"), key=lambda path: path.name, reverse=True)
    rows: list[dict[str, Any]] = []
    for path in paths:
        payload = _read_json(path)
        if not payload:
            continue
        row = operation_log_row_from_artifact(payload, path)
        task = _load_frontend_task(runs_path, _text(row.get("task_id")))
        rows.append(merge_frontend_task_row(row, task))
        if len(rows) >= limit:
            break
    return rows


def filter_operation_logs(
    rows: list[dict[str, Any]],
    *,
    product: str = "",
    operation_type: str = "",
    status: str = "",
) -> list[dict[str, Any]]:
    product_text = _text(product)
    operation_text = _text(operation_type)
    status_text = _text(status)
    result: list[dict[str, Any]] = []
    for row in rows:
        if product_text and _text(row.get("product")) != product_text and _text(row.get("product_key")) != product_text:
            continue
        if operation_text and _text(row.get("operation_type")) != operation_text:
            continue
        if status_text and _text(row.get("status")) != status_text:
            continue
        result.append(row)
    return result


def _resolve_artifact_path(runs_dir: Path, value: Any) -> Path:
    text = _text(value)
    if not text:
        return Path("")
    path = Path(text)
    if path.is_absolute():
        return path
    return runs_dir.parent / path if str(text).startswith("data/runs/") else runs_dir / path


def _create_review_from_details(details: dict[str, Any]) -> dict[str, Any]:
    review = details.get("review") if isinstance(details.get("review"), dict) else {}
    material_rows = details.get("materials") if isinstance(details.get("materials"), list) else []
    creative_usage = details.get("creative_usage") if isinstance(details.get("creative_usage"), dict) else {}
    unit_assignments = details.get("unit_assignments") if isinstance(details.get("unit_assignments"), list) else []
    if not material_rows and isinstance(details.get("material_assignments"), list):
        material_rows = _material_rows_from_operation_details(details)
    if not creative_usage and isinstance(details.get("unit_copywriting"), list):
        creative_usage = _creative_usage_from_operation_details(details)
    if not unit_assignments and (
        isinstance(details.get("unit_copywriting"), list) or isinstance(details.get("material_assignments"), list)
    ):
        unit_assignments = _unit_assignments_from_operation_details(details)
    return {
        "review": review,
        "accounts": details.get("accounts") if isinstance(details.get("accounts"), list) else [],
        "materials": material_rows,
        "creative_usage": creative_usage,
        "unit_assignments": unit_assignments,
    }


def _material_rows_from_operation_details(details: dict[str, Any]) -> list[dict[str, Any]]:
    product = _text(details.get("product"))
    product_key = _text(details.get("product_key"))
    source_advertiser_id = _text(details.get("source_advertiser_id"))
    rows: dict[str, dict[str, Any]] = {}
    accounts: dict[str, set[str]] = defaultdict(set)
    units: dict[str, set[str]] = defaultdict(set)
    for assignment in details.get("material_assignments") or []:
        if not isinstance(assignment, dict):
            continue
        key = _text(assignment.get("material_id")) or _text(assignment.get("source_video_id"))
        if not key:
            continue
        row = rows.setdefault(
            key,
            {
                "material_id": _text(assignment.get("material_id")),
                "video_id": _text(assignment.get("source_video_id")),
                "name": _text(assignment.get("name")),
                "product": product,
                "product_key": product_key,
                "source_advertiser_id": source_advertiser_id,
                "product_stat_cost": _float(assignment.get("product_stat_cost") if assignment.get("product_stat_cost") is not None else assignment.get("stat_cost")),
                "product_convert_cnt": _float(assignment.get("product_convert_cnt") if assignment.get("product_convert_cnt") is not None else assignment.get("convert_cnt")),
                "usage_count": 0,
                "covered_account_count": 0,
                "covered_unit_count": 0,
            },
        )
        row["usage_count"] = int(row["usage_count"]) + 1
        account_id = _text(assignment.get("advertiser_id"))
        unit_key = _text(assignment.get("unit_key"))
        if account_id:
            accounts[key].add(account_id)
        if unit_key:
            units[key].add(unit_key)
    for key, row in rows.items():
        row["covered_account_count"] = len(accounts[key])
        row["covered_unit_count"] = len(units[key])
    return sorted(rows.values(), key=lambda row: (-int(row.get("usage_count") or 0), _text(row.get("material_id"))))


def _creative_usage_from_operation_details(details: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    titles: Counter[str] = Counter()
    ctas: Counter[str] = Counter()
    selling_points: Counter[str] = Counter()
    for unit in details.get("unit_copywriting") or []:
        if not isinstance(unit, dict):
            continue
        for item in unit.get("title_material_list") or []:
            title = _text(item.get("title") if isinstance(item, dict) else item)
            if title:
                titles[title] += 1
        for item in unit.get("call_to_action_buttons") or []:
            cta = _text(item)
            if cta:
                ctas[cta] += 1
        product_info = unit.get("product_info") if isinstance(unit.get("product_info"), dict) else {}
        for item in product_info.get("selling_points") or []:
            selling = _text(item)
            if selling:
                selling_points[selling] += 1
    return {
        "titles": [{"title": key, "usage_count": count} for key, count in titles.most_common()],
        "ctas": [{"cta": key, "usage_count": count} for key, count in ctas.most_common()],
        "selling_points": [{"selling_point": key, "usage_count": count} for key, count in selling_points.most_common()],
    }


def _unit_assignments_from_operation_details(details: dict[str, Any]) -> list[dict[str, Any]]:
    materials_by_unit: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for assignment in details.get("material_assignments") or []:
        if not isinstance(assignment, dict):
            continue
        materials_by_unit[_text(assignment.get("unit_key"))].append(
            {
                "material_id": _text(assignment.get("material_id")),
                "video_id": _text(assignment.get("source_video_id")),
                "name": _text(assignment.get("name")),
            }
        )
    rows: list[dict[str, Any]] = []
    for unit in details.get("unit_copywriting") or []:
        if not isinstance(unit, dict):
            continue
        unit_key = _text(unit.get("unit_key"))
        product_info = unit.get("product_info") if isinstance(unit.get("product_info"), dict) else {}
        rows.append(
            {
                "advertiser_id": _text(unit.get("advertiser_id")),
                "project_name": _text(unit.get("project_name")),
                "unit_key": unit_key,
                "promotion_name": _text(unit.get("promotion_name")),
                "materials": materials_by_unit.get(unit_key, []),
                "titles": [
                    _text(item.get("title") if isinstance(item, dict) else item)
                    for item in unit.get("title_material_list") or []
                    if _text(item.get("title") if isinstance(item, dict) else item)
                ],
                "ctas": [_text(item) for item in unit.get("call_to_action_buttons") or [] if _text(item)],
                "selling_points": [_text(item) for item in product_info.get("selling_points") or [] if _text(item)],
            }
        )
    return rows


def _feishu_status(report_payload: dict[str, Any]) -> dict[str, Any]:
    delivery = report_payload.get("delivery") if isinstance(report_payload.get("delivery"), dict) else {}
    feishu = delivery.get("feishu") if isinstance(delivery.get("feishu"), dict) else {}
    if not feishu:
        return {"status": "", "reason": "", "message": _text(report_payload.get("message"))}
    if not bool(feishu.get("attempted")):
        status = "not_attempted"
    elif bool(feishu.get("ok")):
        status = "sent"
    else:
        status = "failed"
    return {
        "status": status,
        "reason": _text(feishu.get("reason") or feishu.get("error")),
        "message": _text(report_payload.get("message")),
    }


def load_operation_log_detail(runs_dir: str | Path, task_id: str) -> dict[str, Any]:
    runs_path = Path(runs_dir)
    for row in load_operation_logs(runs_path, limit=1000):
        if row.get("task_id") != task_id:
            continue
        artifact = _read_json(Path(str(row.get("artifact_path") or "")))
        details = artifact.get("details") if isinstance(artifact.get("details"), dict) else {}
        task = _load_frontend_task(runs_path, _text(row.get("task_id")))
        execute_payload = _read_json(_resolve_artifact_path(runs_path, row.get("execute_artifact_path")))
        report_payload = _read_json(_resolve_artifact_path(runs_path, row.get("report_artifact_path")))
        if not report_payload and isinstance(task.get("post_results"), list):
            for post_result in task["post_results"]:
                if isinstance(post_result, dict) and post_result:
                    report_payload = post_result
                    break
        failure = execute_payload.get("failure") if isinstance(execute_payload.get("failure"), dict) else {}
        return {
            "row": row,
            "artifact": artifact,
            "task": task,
            "create_review": _create_review_from_details(details),
            "execute_payload": execute_payload,
            "report_payload": report_payload,
            "failure": failure,
            "feishu": _feishu_status(report_payload),
        }
    return {
        "row": {},
        "artifact": {},
        "task": {},
        "create_review": {},
        "execute_payload": {},
        "report_payload": {},
        "failure": {},
        "feishu": {},
    }
