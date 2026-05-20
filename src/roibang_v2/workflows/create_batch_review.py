from __future__ import annotations

import sqlite3
from datetime import date
from datetime import datetime
from datetime import timedelta
from pathlib import Path
from typing import Any

from roibang_v2.runs import write_latest_artifact
from roibang_v2.runs import write_run_artifact


def _text(value: Any) -> str:
    return str(value or "").strip()


def _number(value: Any) -> float:
    try:
        if value in (None, ""):
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _round(value: float) -> float:
    return round(value, 4)


def parse_create_project_name(project_name: str) -> dict[str, Any]:
    parts = [part.strip() for part in _text(project_name).split("_") if part.strip()]
    parsed = {
        "parsed": False,
        "batch_date_code": "",
        "mode_label": "",
        "batch_id": "",
        "project_seq": "",
        "batch_key": "",
    }
    if len(parts) < 5:
        return parsed
    date_code = parts[0]
    project_seq = parts[-1]
    batch_id = parts[-2]
    mode_label = parts[-3]
    if not (date_code.isdigit() and len(date_code) == 4 and project_seq.isdigit() and batch_id):
        return parsed
    parsed.update(
        {
            "parsed": True,
            "batch_date_code": date_code,
            "mode_label": mode_label,
            "batch_id": batch_id,
            "project_seq": project_seq,
            "batch_key": f"{date_code}:{mode_label}:{batch_id}",
        }
    )
    return parsed


def _weighted_roi(cost: float, weighted_roi_cost: float) -> float | None:
    if cost <= 0:
        return None
    return _round(weighted_roi_cost / cost)


def _rate(numerator: float, denominator: float) -> float | None:
    if denominator <= 0:
        return None
    return _round(numerator / denominator)


def _empty_group(key: str, parsed: dict[str, Any]) -> dict[str, Any]:
    return {
        "key": key,
        "batch_date_code": parsed.get("batch_date_code", ""),
        "mode_label": parsed.get("mode_label", ""),
        "batch_id": parsed.get("batch_id", ""),
        "metric_dates": set(),
        "advertiser_ids": set(),
        "project_ids": set(),
        "promotion_ids": set(),
        "material_ids": set(),
        "stat_cost": 0.0,
        "show_cnt": 0.0,
        "click_cnt": 0.0,
        "convert_cnt": 0.0,
        "active_register": 0.0,
        "weighted_roi_1day_cost": 0.0,
    }


def _add_metrics(group: dict[str, Any], row: sqlite3.Row) -> None:
    group["metric_dates"].add(_text(row["metric_date"]))
    group["advertiser_ids"].add(_text(row["advertiser_id"]))
    group["project_ids"].add(_text(row["project_id"]))
    group["promotion_ids"].add(_text(row["promotion_id"]))
    group["material_ids"].add(_text(row["material_id"]))
    cost = _number(row["stat_cost"])
    group["stat_cost"] += cost
    group["show_cnt"] += _number(row["show_cnt"])
    group["click_cnt"] += _number(row["click_cnt"])
    group["convert_cnt"] += _number(row["convert_cnt"])
    group["active_register"] += _number(row["active_register"])
    group["weighted_roi_1day_cost"] += _number(row["roi_1day"]) * cost


def _finalize_group(group: dict[str, Any]) -> dict[str, Any]:
    stat_cost = _number(group["stat_cost"])
    convert_cnt = _number(group["convert_cnt"])
    active_register = _number(group["active_register"])
    show_cnt = _number(group["show_cnt"])
    click_cnt = _number(group["click_cnt"])
    metric_dates = sorted(group["metric_dates"])
    return {
        "key": group["key"],
        "batch_date_code": group.get("batch_date_code", ""),
        "mode_label": group.get("mode_label", ""),
        "batch_id": group.get("batch_id", ""),
        "first_metric_date": metric_dates[0] if metric_dates else "",
        "last_metric_date": metric_dates[-1] if metric_dates else "",
        "account_count": len({item for item in group["advertiser_ids"] if item}),
        "project_count": len({item for item in group["project_ids"] if item}),
        "promotion_count": len({item for item in group["promotion_ids"] if item}),
        "material_count": len({item for item in group["material_ids"] if item}),
        "stat_cost": _round(stat_cost),
        "show_cnt": _round(show_cnt),
        "click_cnt": _round(click_cnt),
        "ctr": _rate(click_cnt, show_cnt),
        "convert_cnt": _round(convert_cnt),
        "active_register": _round(active_register),
        "conversion_cost": _rate(stat_cost, convert_cnt),
        "register_cost": _rate(stat_cost, active_register),
        "roi_1day": _weighted_roi(stat_cost, _number(group["weighted_roi_1day_cost"])),
    }


def _fetch_metric_rows(
    conn: sqlite3.Connection,
    *,
    start_date: str,
    end_date: str,
    project_name_contains: str,
) -> list[sqlite3.Row]:
    clauses = ["metric_date BETWEEN ? AND ?", "project_name != ''"]
    params: list[Any] = [start_date, end_date]
    if project_name_contains:
        clauses.append("project_name LIKE ?")
        params.append(f"%{project_name_contains}%")
    sql = f"""
        SELECT
          metric_date,
          advertiser_id,
          project_id,
          project_name,
          promotion_id,
          promotion_name,
          material_id,
          stat_cost,
          show_cnt,
          click_cnt,
          convert_cnt,
          active_register,
          roi_1day
        FROM material_daily_metrics
        WHERE {" AND ".join(clauses)}
    """
    return list(conn.execute(sql, params).fetchall())


def _resolve_date_window(conn: sqlite3.Connection, cfg: dict[str, Any]) -> dict[str, Any]:
    max_date = _text(conn.execute("SELECT MAX(metric_date) FROM material_daily_metrics").fetchone()[0])
    if not max_date:
        raise ValueError("material_daily_metrics has no metric_date data")
    end_date = _text(cfg.get("end_date")) or max_date
    start_date = _text(cfg.get("start_date"))
    recent_days = int(cfg.get("recent_days") or 7)
    if not start_date:
        start_date = (_date(end_date) - timedelta(days=max(recent_days, 1) - 1)).isoformat()
    return {
        "start_date": start_date,
        "end_date": end_date,
        "max_metric_date": max_date,
        "recent_days": recent_days,
    }


def build_create_batch_review(
    *,
    db_path: str | Path,
    start_date: str = "",
    end_date: str = "",
    recent_days: int = 7,
    project_name_contains: str = "郭靖",
    limit: int = 20,
) -> dict[str, Any]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        window = _resolve_date_window(
            conn,
            {
                "start_date": start_date,
                "end_date": end_date,
                "recent_days": recent_days,
            },
        )
        rows = _fetch_metric_rows(
            conn,
            start_date=window["start_date"],
            end_date=window["end_date"],
            project_name_contains=project_name_contains,
        )
    finally:
        conn.close()

    batch_groups: dict[str, dict[str, Any]] = {}
    mode_groups: dict[str, dict[str, Any]] = {}
    project_groups: dict[str, dict[str, Any]] = {}
    unparsed_count = 0
    for row in rows:
        parsed = parse_create_project_name(_text(row["project_name"]))
        if not parsed["parsed"]:
            unparsed_count += 1
            continue
        batch_key = _text(parsed["batch_key"])
        mode_key = _text(parsed["mode_label"])
        project_key = f"{row['advertiser_id']}:{row['project_id']}"
        if batch_key not in batch_groups:
            batch_groups[batch_key] = _empty_group(batch_key, parsed)
        if mode_key not in mode_groups:
            mode_groups[mode_key] = _empty_group(mode_key, {"mode_label": mode_key})
        if project_key not in project_groups:
            project_groups[project_key] = {
                **_empty_group(project_key, parsed),
                "advertiser_id": _text(row["advertiser_id"]),
                "project_id": _text(row["project_id"]),
                "project_name": _text(row["project_name"]),
            }
        _add_metrics(batch_groups[batch_key], row)
        _add_metrics(mode_groups[mode_key], row)
        _add_metrics(project_groups[project_key], row)

    batches = sorted(
        (_finalize_group(group) for group in batch_groups.values()),
        key=lambda item: (-_number(item["stat_cost"]), item["key"]),
    )
    mode_summary = sorted(
        (_finalize_group(group) for group in mode_groups.values()),
        key=lambda item: (-_number(item["stat_cost"]), item["key"]),
    )
    projects = []
    for group in project_groups.values():
        item = _finalize_group(group)
        item.update(
            {
                "advertiser_id": group["advertiser_id"],
                "project_id": group["project_id"],
                "project_name": group["project_name"],
            }
        )
        projects.append(item)
    top_projects = sorted(projects, key=lambda item: (-_number(item["stat_cost"]), item["project_id"]))[:limit]

    total_cost = sum(_number(item["stat_cost"]) for item in batches)
    total_convert = sum(_number(item["convert_cnt"]) for item in batches)
    total_register = sum(_number(item["active_register"]) for item in batches)
    total_weighted_roi = sum(_number(item["roi_1day"]) * _number(item["stat_cost"]) for item in batches if item["roi_1day"] is not None)
    summary = {
        "start_date": window["start_date"],
        "end_date": window["end_date"],
        "max_metric_date": window["max_metric_date"],
        "project_name_contains": project_name_contains,
        "metric_row_count": len(rows),
        "parsed_metric_row_count": len(rows) - unparsed_count,
        "unparsed_metric_row_count": unparsed_count,
        "batch_count": len(batches),
        "mode_count": len(mode_summary),
        "project_count": len(projects),
        "account_count": len({project["advertiser_id"] for project in projects if project.get("advertiser_id")}),
        "stat_cost": _round(total_cost),
        "convert_cnt": _round(total_convert),
        "active_register": _round(total_register),
        "conversion_cost": _rate(total_cost, total_convert),
        "register_cost": _rate(total_cost, total_register),
        "roi_1day": _weighted_roi(total_cost, total_weighted_roi),
    }
    payload = {
        "ok": True,
        "workflow": "create_batch_review",
        "phase": "readonly_analysis",
        "execution_enabled": False,
        "external_api_calls": 0,
        "summary": summary,
        "batches": batches[:limit],
        "mode_summary": mode_summary,
        "top_projects": top_projects,
        "message": _message(summary, batches, mode_summary),
    }
    return payload


def _message(summary: dict[str, Any], batches: list[dict[str, Any]], mode_summary: list[dict[str, Any]]) -> str:
    lines = [
        f"RoiBang-V2 创建批次复盘 {summary['start_date']}~{summary['end_date']}",
        "",
        (
            f"整体：批次 {summary['batch_count']} 个，项目 {summary['project_count']} 个，"
            f"账户 {summary['account_count']} 个，消耗 {summary['stat_cost']:.2f}，"
            f"转化 {summary['convert_cnt']:.0f}，ROI {summary['roi_1day'] if summary['roi_1day'] is not None else '无'}"
        ),
    ]
    if mode_summary:
        lines.append("")
        lines.append("模式表现")
        for item in mode_summary[:5]:
            lines.append(
                f"- {item['mode_label'] or item['key']}：消耗 {item['stat_cost']:.2f}，"
                f"转化 {item['convert_cnt']:.0f}，ROI {item['roi_1day'] if item['roi_1day'] is not None else '无'}，"
                f"项目 {item['project_count']}"
            )
    if batches:
        lines.append("")
        lines.append("重点批次")
        for item in batches[:5]:
            lines.append(
                f"- {item['batch_date_code']} {item['mode_label']} {item['batch_id']}："
                f"消耗 {item['stat_cost']:.2f}，转化 {item['convert_cnt']:.0f}，"
                f"ROI {item['roi_1day'] if item['roi_1day'] is not None else '无'}，项目 {item['project_count']}"
            )
    return "\n".join(lines)


def run_create_batch_review_request(
    request: dict[str, Any] | None,
    *,
    runs_dir: str | Path,
) -> dict[str, Any]:
    cfg = dict(request or {})
    db_path = _text(cfg.get("db_path") or "data/roibang_v2.sqlite3")
    payload = build_create_batch_review(
        db_path=db_path,
        start_date=_text(cfg.get("start_date")),
        end_date=_text(cfg.get("end_date")),
        recent_days=int(cfg.get("recent_days") or 7),
        project_name_contains=_text(cfg.get("project_name_contains") or "郭靖"),
        limit=int(cfg.get("limit") or 20),
    )
    payload["source"] = {
        "db_path": db_path,
        "data_source": "material_daily_metrics",
    }
    payload["artifact_path"] = str(write_run_artifact(runs_dir, "create_batch_review", payload))
    payload["latest_artifact_path"] = str(Path(runs_dir) / "create_batch_review" / "latest.json")
    write_latest_artifact(runs_dir, "create_batch_review", payload)
    return payload
