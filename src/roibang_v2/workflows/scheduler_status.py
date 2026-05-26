from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

from roibang_v2.artifacts.contract import validate_artifact_contract
from roibang_v2.runs import write_run_artifact


LaunchctlStatusReader = Callable[[str], dict[str, Any]]
FeishuSender = Callable[[dict[str, Any], str], dict[str, Any]]
FEISHU_API_HOST = "https://open.feishu.cn"


def _config(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("scheduler_status")
    return dict(value) if isinstance(value, dict) else dict(request)


def _timezone(cfg: dict[str, Any]) -> ZoneInfo:
    return ZoneInfo(str(cfg.get("timezone") or "Asia/Shanghai"))


def _expected_data_date(cfg: dict[str, Any], *, now: datetime) -> str:
    value = cfg.get("expected_data_date") if isinstance(cfg.get("expected_data_date"), dict) else {}
    if str(value.get("mode") or "yesterday") == "yesterday":
        return (now.date() - timedelta(days=1)).isoformat()
    explicit = str(value.get("date") or "").strip()
    if explicit:
        return explicit
    return (now.date() - timedelta(days=1)).isoformat()


def _launchctl_print(job_id: str) -> dict[str, Any]:
    label = f"com.roibang.v2.{job_id}"
    domain = f"gui/{os.getuid()}/{label}"
    completed = subprocess.run(["launchctl", "print", domain], text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        return {
            "loaded": False,
            "runs": 0,
            "last_exit_code": "",
            "raw": completed.stderr.strip() or completed.stdout.strip(),
        }
    runs = 0
    last_exit_code = ""
    for line in completed.stdout.splitlines():
        stripped = line.strip()
        if stripped.startswith("runs ="):
            try:
                runs = int(stripped.split("=", 1)[1].strip())
            except ValueError:
                runs = 0
        if stripped.startswith("last exit code ="):
            last_exit_code = stripped.split("=", 1)[1].strip()
    return {"loaded": True, "runs": runs, "last_exit_code": last_exit_code, "raw": completed.stdout}


def _latest_scheduler_result(repo_root: Path, job_id: str) -> dict[str, Any]:
    result_dir = repo_root / "data" / "runs" / "scheduler" / job_id
    candidates = sorted(result_dir.glob("*.json"))
    if not candidates:
        return {"exists": False, "path": "", "ok": False, "violations": ["no scheduler result artifact"]}
    path = candidates[-1]
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {"exists": True, "path": str(path), "ok": False, "violations": [f"invalid scheduler JSON: {exc.msg}"]}
    script = payload.get("script") if isinstance(payload.get("script"), dict) else {}
    command = script.get("command") if isinstance(script.get("command"), list) else []
    return {
        "exists": True,
        "path": str(path),
        "ok": bool(payload.get("ok")),
        "started_at": str(payload.get("started_at") or ""),
        "finished_at": str(payload.get("finished_at") or ""),
        "script_command": [str(item) for item in command],
        "violations": [str(item) for item in payload.get("violations", [])],
    }


def _registry_script_command(registry: dict[str, Any], job_id: str) -> list[str]:
    job = _find_registry_job(registry, job_id)
    script = job.get("script") if isinstance(job.get("script"), dict) else {}
    command = script.get("command") if isinstance(script.get("command"), list) else []
    return [str(item) for item in command]


def _scalar(conn: sqlite3.Connection, query: str, params: tuple[Any, ...] = ()) -> Any:
    row = conn.execute(query, params).fetchone()
    return row[0] if row else None


def _material_daily_check(conn: sqlite3.Connection, expected_date: str) -> dict[str, Any]:
    max_date = str(_scalar(conn, "SELECT MAX(metric_date) FROM material_daily_metrics") or "")
    row_count = int(_scalar(conn, "SELECT COUNT(*) FROM material_daily_metrics WHERE metric_date = ?", (expected_date,)) or 0)
    status = "ok" if max_date >= expected_date and row_count > 0 else "stale"
    return {
        "type": "material_daily_metrics",
        "status": status,
        "expected_date": expected_date,
        "latest_date": max_date,
        "expected_date_row_count": row_count,
    }


def _daily_report_check(conn: sqlite3.Connection, expected_date: str) -> dict[str, Any]:
    max_date = str(_scalar(conn, "SELECT MAX(metric_date) FROM metric_snapshots") or "")
    row_count = int(_scalar(conn, "SELECT COUNT(*) FROM metric_snapshots WHERE metric_date = ?", (expected_date,)) or 0)
    status = "ok" if max_date >= expected_date and row_count > 0 else "stale"
    return {
        "type": "metric_snapshots",
        "status": status,
        "expected_date": expected_date,
        "latest_date": max_date,
        "expected_date_row_count": row_count,
    }


def _source_material_account_check(conn: sqlite3.Connection, check: dict[str, Any]) -> dict[str, Any]:
    product = str(check.get("product") or "勇者突进")
    source_advertiser_id = str(check.get("source_advertiser_id") or "")
    row = conn.execute(
        """
        SELECT COUNT(*), MAX(synced_at)
        FROM product_source_materials
        WHERE product = ?
          AND source_advertiser_id = ?
          AND is_active = 1
        """,
        (product, source_advertiser_id),
    ).fetchone()
    material_count = int(row[0] or 0) if row else 0
    latest_synced_at = str(row[1] or "") if row else ""
    status = "ok" if source_advertiser_id and material_count > 0 else "stale"
    return {
        "type": "source_material_account",
        "status": status,
        "product": product,
        "source_advertiser_id": source_advertiser_id,
        "source_account_material_count": material_count,
        "latest_synced_at": latest_synced_at,
    }


def _source_material_preload_check(conn: sqlite3.Connection, check: dict[str, Any]) -> dict[str, Any]:
    product = str(check.get("product") or "勇者突进")
    source_advertiser_id = str(check.get("source_advertiser_id") or "")
    row = conn.execute(
        """
        SELECT COUNT(*), COUNT(DISTINCT target_advertiser_id), MAX(last_seen_at)
        FROM source_material_preload_ledger
        WHERE product = ?
          AND source_advertiser_id = ?
          AND status = 'completed'
        """,
        (product, source_advertiser_id),
    ).fetchone()
    preload_count = int(row[0] or 0) if row else 0
    target_account_count = int(row[1] or 0) if row else 0
    latest_seen_at = str(row[2] or "") if row else ""
    return {
        "type": "source_material_preload",
        "status": "ok",
        "product": product,
        "source_advertiser_id": source_advertiser_id,
        "preload_count": preload_count,
        "target_account_count": target_account_count,
        "latest_seen_at": latest_seen_at,
    }


def _material_kind_reconcile_check(conn: sqlite3.Connection, expected_date: str) -> dict[str, Any]:
    max_date = str(_scalar(conn, "SELECT MAX(metric_date) FROM material_daily_metrics") or "")
    rows = conn.execute(
        """
        SELECT material_kind, COUNT(DISTINCT material_id), COUNT(*), COALESCE(SUM(stat_cost), 0)
        FROM material_daily_metrics
        GROUP BY material_kind
        """
    ).fetchall()
    by_kind = {
        str(kind or "unknown"): {
            "material_count": int(material_count or 0),
            "row_count": int(row_count or 0),
            "stat_cost": round(float(stat_cost or 0), 2),
        }
        for kind, material_count, row_count, stat_cost in rows
    }
    total_rows = sum(int(value["row_count"]) for value in by_kind.values())
    status = "ok" if max_date >= expected_date and total_rows > 0 else "stale"
    return {
        "type": "material_kind_reconcile",
        "status": status,
        "expected_date": expected_date,
        "latest_date": max_date,
        "row_count": total_rows,
        "by_kind": by_kind,
    }


def _source_material_rollup_check(conn: sqlite3.Connection, check: dict[str, Any], expected_date: str) -> dict[str, Any]:
    product = str(check.get("product") or "勇者突进")
    source_advertiser_id = str(check.get("source_advertiser_id") or "")
    latest_period_end = str(
        _scalar(
            conn,
            """
            SELECT MAX(period_end)
            FROM product_source_material_metric_rollups
            WHERE product = ?
              AND source_advertiser_id = ?
              AND window_key = 'all_history'
            """,
            (product, source_advertiser_id),
        )
        or ""
    )
    row = conn.execute(
        """
        SELECT COUNT(*), COALESCE(SUM(stat_cost), 0)
        FROM product_source_material_metric_rollups
        WHERE product = ?
          AND source_advertiser_id = ?
          AND window_key = 'all_history'
          AND period_end = ?
        """,
        (product, source_advertiser_id, latest_period_end),
    ).fetchone()
    row_count = int(row[0] or 0) if row else 0
    stat_cost = round(float(row[1] or 0), 2) if row else 0.0
    status = "ok" if source_advertiser_id and latest_period_end >= expected_date and row_count > 0 else "stale"
    return {
        "type": "source_material_rollup",
        "status": status,
        "product": product,
        "source_advertiser_id": source_advertiser_id,
        "latest_date": latest_period_end,
        "row_count": row_count,
        "stat_cost": stat_cost,
    }


def _operation_logs_check(conn: sqlite3.Connection, expected_date: str) -> dict[str, Any]:
    max_date = str(_scalar(conn, "SELECT MAX(substr(occurred_at, 1, 10)) FROM operation_logs") or "")
    row_count = int(
        _scalar(conn, "SELECT COUNT(*) FROM operation_logs WHERE substr(occurred_at, 1, 10) = ?", (expected_date,))
        or 0
    )
    status = "ok" if max_date >= expected_date and row_count > 0 else "stale"
    return {
        "type": "operation_logs",
        "status": status,
        "expected_date": expected_date,
        "latest_date": max_date,
        "expected_date_row_count": row_count,
    }


def _restore_queue_check(check: dict[str, Any], *, repo_root: Path, now: datetime) -> dict[str, Any]:
    path = repo_root / str(check.get("path") or "data/runs/project_schedule_restore_queue.json")
    if not path.exists():
        return {
            "type": "project_schedule_restore_queue",
            "status": "ok",
            "path": str(path),
            "queue_item_count": 0,
            "pending_item_count": 0,
            "completed_item_count": 0,
            "failed_status_item_count": 0,
            "retry_pending_item_count": 0,
            "due_pending_item_count": 0,
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {"type": "project_schedule_restore_queue", "status": "attention", "path": str(path), "error": exc.msg}
    items = payload.get("items") if isinstance(payload, dict) and isinstance(payload.get("items"), list) else []
    pending = [item for item in items if isinstance(item, dict) and str(item.get("status") or "") == "pending"]
    completed = [item for item in items if isinstance(item, dict) and str(item.get("status") or "") == "completed"]
    failed_status = [item for item in items if isinstance(item, dict) and str(item.get("status") or "") == "failed"]
    retry_pending = [item for item in pending if str(item.get("last_error") or "").strip()]
    due_pending = []
    for item in pending:
        restore_at = str(item.get("restore_at") or "").strip()
        if not restore_at:
            continue
        try:
            restore_dt = datetime.fromisoformat(restore_at.replace(" ", "T"))
        except ValueError:
            retry_pending.append(item)
            continue
        if restore_dt.tzinfo is None:
            restore_dt = restore_dt.replace(tzinfo=now.tzinfo)
        if restore_dt <= now:
            due_pending.append(item)
    needs_attention = bool(failed_status or retry_pending)
    return {
        "type": "project_schedule_restore_queue",
        "status": "attention" if needs_attention else "ok",
        "path": str(path),
        "queue_item_count": len([item for item in items if isinstance(item, dict)]),
        "pending_item_count": len(pending),
        "completed_item_count": len(completed),
        "failed_status_item_count": len(failed_status),
        "retry_pending_item_count": len(retry_pending),
        "due_pending_item_count": len(due_pending),
    }


def _data_check(
    conn: sqlite3.Connection,
    check: dict[str, Any],
    expected_date: str,
    *,
    repo_root: Path,
    now: datetime,
) -> dict[str, Any]:
    check_type = str(check.get("type") or "")
    if check_type == "material_daily_metrics":
        return _material_daily_check(conn, expected_date)
    if check_type == "metric_snapshots":
        return _daily_report_check(conn, expected_date)
    if check_type == "source_material_account":
        return _source_material_account_check(conn, check)
    if check_type == "source_material_preload":
        return _source_material_preload_check(conn, check)
    if check_type == "material_kind_reconcile":
        return _material_kind_reconcile_check(conn, expected_date)
    if check_type == "source_material_rollup":
        return _source_material_rollup_check(conn, check, expected_date)
    if check_type == "operation_logs":
        return _operation_logs_check(conn, expected_date)
    if check_type == "project_schedule_restore_queue":
        return _restore_queue_check(check, repo_root=repo_root, now=now)
    return {"type": check_type, "status": "unknown", "expected_date": expected_date}


def _job_contract(registry: dict[str, Any], job_id: str, repo_root: Path) -> dict[str, Any]:
    try:
        result = validate_artifact_contract(registry, job_id=job_id, repo_root=repo_root)
    except Exception as exc:  # status report must report, not crash, on missing stale jobs
        legacy = _legacy_product_automation_contract(registry, job_id, repo_root)
        if legacy:
            return legacy
        return {"ok": False, "job_id": job_id, "artifact_path": "", "violations": [str(exc)], "missing_fields": []}
    if not bool(result.get("ok")):
        legacy = _legacy_product_automation_contract(registry, job_id, repo_root)
        if legacy:
            return legacy
    return result


def _find_registry_job(registry: dict[str, Any], job_id: str) -> dict[str, Any]:
    for job in registry.get("jobs", []):
        if isinstance(job, dict) and str(job.get("id") or "") == job_id:
            return job
    return {}


def _legacy_product_automation_contract(registry: dict[str, Any], job_id: str, repo_root: Path) -> dict[str, Any]:
    job = _find_registry_job(registry, job_id)
    contract = job.get("result_contract") if isinstance(job.get("result_contract"), dict) else {}
    workflow = str(contract.get("workflow") or "")
    prefix = "product_automation_job_"
    if not workflow.startswith(prefix):
        return {}
    expected_job = workflow.removeprefix(prefix)
    legacy_dir = repo_root / "data/runs/product_automation_job"
    for path in sorted(legacy_dir.glob("*.json"), reverse=True):
        artifact = _load_artifact(str(path))
        summary = artifact.get("summary") if isinstance(artifact.get("summary"), dict) else {}
        if str(summary.get("job") or "") != expected_job:
            continue
        required = [str(field) for field in contract.get("must_include", []) if str(field) != "workflow"]
        missing_fields = [field for field in required if field not in artifact]
        violations = []
        if missing_fields:
            violations.append(f"missing required fields: {', '.join(missing_fields)}")
        must_equal = contract.get("must_equal") if isinstance(contract.get("must_equal"), dict) else {}
        for field, expected in must_equal.items():
            if str(field) == "workflow":
                continue
            actual = artifact.get(str(field))
            if actual != expected:
                violations.append(f"field {field} must equal {expected!r}, got {actual!r}")
        return {
            "ok": not violations,
            "job_id": job_id,
            "workflow": workflow,
            "artifact_path": str(path),
            "missing_fields": missing_fields,
            "violations": violations,
            "legacy_product_automation_artifact": True,
        }
    return {}


def _load_artifact(path_text: str) -> dict[str, Any]:
    if not path_text:
        return {}
    path = Path(path_text)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _product_results_from_artifact(artifact: dict[str, Any]) -> list[dict[str, Any]]:
    workflow = str(artifact.get("workflow") or "")
    summary_root = artifact.get("summary") if isinstance(artifact.get("summary"), dict) else {}
    if not workflow.startswith("product_automation_job_") and workflow != "product_automation_job":
        return []
    rows = artifact.get("results") if isinstance(artifact.get("results"), list) else []
    product_results: list[dict[str, Any]] = []
    for row in [item for item in rows if isinstance(item, dict)]:
        parsed = row.get("parsed_stdout") if isinstance(row.get("parsed_stdout"), dict) else {}
        summary = parsed.get("summary") if isinstance(parsed.get("summary"), dict) else {}
        if not summary and isinstance(row.get("summary"), dict):
            summary = dict(row["summary"])
        product_results.append(
            {
                "product": str(row.get("product") or row.get("product_key") or "未知产品"),
                "product_key": str(row.get("product_key") or ""),
                "job": str(row.get("job") or summary_root.get("job") or ""),
                "ok": bool(row.get("ok", True)),
                "return_code": row.get("return_code", ""),
                "status": str(parsed.get("status") or ""),
                "summary": summary,
                "artifact_path": str(parsed.get("artifact_path") or ""),
            }
        )
    return product_results


def _job_status(
    *,
    job_cfg: dict[str, Any],
    registry: dict[str, Any],
    conn: sqlite3.Connection,
    expected_date: str,
    repo_root: Path,
    now: datetime,
    launchctl_status_reader: LaunchctlStatusReader,
) -> dict[str, Any]:
    job_id = str(job_cfg["job_id"])
    launchctl = launchctl_status_reader(job_id)
    artifact_contract = _job_contract(registry, job_id, repo_root)
    contract_artifact = _load_artifact(str(artifact_contract.get("artifact_path") or ""))
    scheduler_result = _latest_scheduler_result(repo_root, job_id)
    data_check = _data_check(
        conn,
        job_cfg.get("data_check") if isinstance(job_cfg.get("data_check"), dict) else {},
        expected_date,
        repo_root=repo_root,
        now=now,
    )
    issues: list[str] = []
    if not bool(launchctl.get("loaded")):
        issues.append("launchd 未加载")
    if str(launchctl.get("last_exit_code") or "") not in {"", "0", "(never exited)"}:
        issues.append(f"launchd 上次退出码 {launchctl.get('last_exit_code')}")
    expected_command = _registry_script_command(registry, job_id)
    actual_command = scheduler_result.get("script_command") if isinstance(scheduler_result.get("script_command"), list) else []
    if expected_command and actual_command and [str(item) for item in actual_command] != expected_command:
        issues.append("定时任务命令与注册表不一致")
    if not bool(artifact_contract.get("ok")):
        issues.extend(str(item) for item in artifact_contract.get("violations", []))
    if str(data_check.get("status")) != "ok":
        issues.append("恢复队列需要处理" if str(data_check.get("type")) == "project_schedule_restore_queue" else f"缺数据：{expected_date}")
    return {
        "job_id": job_id,
        "display_name": str(job_cfg.get("display_name") or job_id),
        "status": "ok" if not issues else "attention",
        "issues": issues,
        "launchd": launchctl,
        "scheduler_result": scheduler_result,
        "artifact_contract": artifact_contract,
        "data_check": data_check,
        "product_results": _product_results_from_artifact(contract_artifact),
    }


def _format_data_line(data_check: dict[str, Any]) -> str:
    check_type = str(data_check.get("type") or "")
    if check_type == "source_material_account":
        return (
            f"源素材账户 {data_check.get('source_advertiser_id') or '无'}，"
            f"素材 {data_check.get('source_account_material_count', 0)} 个，"
            f"同步到 {data_check.get('latest_synced_at') or '无'}"
        )
    if check_type == "source_material_rollup":
        return (
            f"汇总到 {data_check.get('latest_date') or '无'}，"
            f"视频素材 {data_check.get('row_count', 0)} 个，"
            f"全历史消耗 {data_check.get('stat_cost', 0)}"
        )
    if check_type == "source_material_preload":
        return (
            f"已记录预推送 {data_check.get('preload_count', 0)} 条，"
            f"目标账户 {data_check.get('target_account_count', 0)} 个，"
            f"最近更新 {data_check.get('latest_seen_at') or '无'}"
        )
    if check_type == "material_kind_reconcile":
        by_kind = data_check.get("by_kind") if isinstance(data_check.get("by_kind"), dict) else {}
        video_count = (by_kind.get("video") or {}).get("material_count", 0) if isinstance(by_kind.get("video"), dict) else 0
        title_count = (by_kind.get("title") or {}).get("material_count", 0) if isinstance(by_kind.get("title"), dict) else 0
        unknown_count = (by_kind.get("unknown") or {}).get("material_count", 0) if isinstance(by_kind.get("unknown"), dict) else 0
        return (
            f"数据到 {data_check.get('latest_date') or '无'}，"
            f"视频 {video_count}，文案 {title_count}，未知 {unknown_count}"
        )
    if check_type == "project_schedule_restore_queue":
        return (
            f"待恢复 {data_check.get('pending_item_count', 0)}，"
            f"已恢复 {data_check.get('completed_item_count', 0)}，"
            f"失败待处理 {data_check.get('retry_pending_item_count', 0) or data_check.get('failed_status_item_count', 0)}"
        )
    return f"数据到 {data_check.get('latest_date') or '无'}"


def _format_product_result_line(result: dict[str, Any]) -> str:
    product = str(result.get("product") or "未知产品")
    job = str(result.get("job") or "")
    summary = result.get("summary") if isinstance(result.get("summary"), dict) else {}
    status = "完成" if bool(result.get("ok", True)) else "需要处理"
    if job == "material_daily_sync":
        return (
            f"{product}：{status}素材入库，活跃账户 {summary.get('active_account_count', 0)} 个，"
            f"导入素材行 {summary.get('material_rows_imported', 0)}，"
            f"接口调用 {summary.get('material_fetch_transport_calls', 0)} 次"
        )
    if job == "operation_log_sync":
        return (
            f"{product}：{status}操作日志同步，计划账户 {summary.get('planned_request_count', 0)} 个，"
            f"导入日志 {summary.get('operation_logs_imported', 0)} 条，"
            f"接口调用 {summary.get('transport_calls', summary.get('external_api_calls', 0))} 次"
        )
    if job == "daily_report_sync":
        return (
            f"{product}：{status}每日报表同步，发现账户 {summary.get('active_accounts_discovered', 0)} 个，"
            f"写入快照 {summary.get('snapshots_written', 0)} 条，"
            f"接口调用 {summary.get('transport_calls', summary.get('external_api_calls', 0))} 次"
        )
    if job == "source_material_auto_push":
        return (
            f"{product}：{status}源素材自动补材，源素材账户 {summary.get('source_advertiser_id') or '无'}，"
            f"新增素材 {summary.get('new_material_count', 0)} 个，"
            f"已推视频 {summary.get('pushed_video_count', 0)} 个，"
            f"失败批次 {summary.get('failed_batch_count', 0)}"
        )
    if job == "source_material_preload":
        return (
            f"{product}：{status}源素材预推送，目标账户 {summary.get('target_account_count', 0)} 个，"
            f"计划推送 {summary.get('planned_bind_material_count', 0)} 条，"
            f"已推 {summary.get('executed_bind_material_count', 0)} 条，"
            f"失败批次 {summary.get('failed_batch_count', 0)}"
        )
    if job == "delivery_patrol":
        return (
            f"{product}：{status}投放巡检，账户 {summary.get('account_count', summary.get('accounts', 0))} 个，"
            f"项目 {summary.get('project_count', summary.get('projects', 0))} 个，"
            f"单元 {summary.get('promotion_count', summary.get('promotions', 0))} 个"
        )
    return f"{product}：{status}，任务 {job or '未知'}"


def _format_message(project_name: str, report_date: str, expected_date: str, jobs: list[dict[str, Any]]) -> str:
    ok_count = sum(1 for job in jobs if job["status"] == "ok")
    overall = "正常" if ok_count == len(jobs) else "需要处理"
    lines = [
        f"{project_name} 定时任务日报 {report_date}",
        "",
        f"总体：{overall}",
        f"数据应到：{expected_date}",
        "",
    ]
    for job in jobs:
        status_text = "正常" if job["status"] == "ok" else "需要处理"
        lines.append(f"{job['display_name']}：{status_text}")
        lines.append(f"- {_format_data_line(job['data_check'])}")
        product_results = job.get("product_results") if isinstance(job.get("product_results"), list) else []
        for product_result in [item for item in product_results if isinstance(item, dict)]:
            lines.append(f"- {_format_product_result_line(product_result)}")
        issues = job.get("issues") or []
        if issues:
            lines.append(f"- 问题：{'；'.join(str(item) for item in issues[:3])}")
        contract_path = str((job.get("artifact_contract") or {}).get("artifact_path") or "")
        if contract_path:
            lines.append(f"- 产物：{contract_path}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def build_scheduler_status_report(
    request: dict[str, Any],
    *,
    registry: dict[str, Any],
    db_path: str | Path,
    runs_dir: str | Path,
    repo_root: str | Path,
    now: datetime | None = None,
    launchctl_status_reader: LaunchctlStatusReader | None = None,
) -> dict[str, Any]:
    cfg = _config(request)
    tz = _timezone(cfg)
    current = now.astimezone(tz) if now else datetime.now(tz)
    expected_date = _expected_data_date(cfg, now=current)
    reader = launchctl_status_reader or _launchctl_print
    job_configs = cfg.get("jobs") if isinstance(cfg.get("jobs"), list) else []
    root = Path(repo_root)
    with sqlite3.connect(db_path) as conn:
        jobs = [
            _job_status(
                job_cfg=dict(job_cfg),
                registry=registry,
                conn=conn,
                expected_date=expected_date,
                repo_root=root,
                now=current,
                launchctl_status_reader=reader,
            )
            for job_cfg in job_configs
            if isinstance(job_cfg, dict)
        ]
    message = _format_message(str(cfg.get("project_name") or "RoiBang-V2"), current.date().isoformat(), expected_date, jobs)
    return {
        "ok": all(job["status"] == "ok" for job in jobs),
        "workflow": "scheduler_status",
        "phase": "phase1",
        "execution_enabled": False,
        "external_api_calls": 0,
        "summary": {
            "report_date": current.date().isoformat(),
            "expected_data_date": expected_date,
            "job_count": len(jobs),
            "ok_count": sum(1 for job in jobs if job["status"] == "ok"),
            "attention_count": sum(1 for job in jobs if job["status"] != "ok"),
        },
        "jobs": jobs,
        "message": message,
        "runs_dir": str(runs_dir),
    }


def _load_local_json(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    if not source.exists():
        return {}
    value = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{source} must contain a JSON object")
    return value


def _resolve_feishu_app_config(feishu: dict[str, Any]) -> dict[str, str]:
    runtime_file = str(feishu.get("runtime_file") or "").strip()
    runtime = _load_local_json(runtime_file) if runtime_file else {}
    app_id = str(os.environ.get("FEISHU_APP_ID") or runtime.get("app_id") or feishu.get("app_id") or "").strip()
    app_secret = str(
        os.environ.get("FEISHU_APP_SECRET") or runtime.get("app_secret") or feishu.get("app_secret") or ""
    ).strip()
    chat_id = str(
        os.environ.get("FEISHU_CHAT_ID")
        or runtime.get("default_chat_id")
        or runtime.get("chat_id")
        or feishu.get("chat_id")
        or ""
    ).strip()
    missing = [
        name
        for name, value in [("app_id", app_id), ("app_secret", app_secret), ("chat_id", chat_id)]
        if not value
    ]
    if missing:
        raise ValueError(f"missing Feishu app config: {', '.join(missing)}")
    return {"app_id": app_id, "app_secret": app_secret, "chat_id": chat_id}


def _post_json(url: str, payload: dict[str, Any], *, headers: dict[str, str] | None = None) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request_headers = {"Content-Type": "application/json; charset=utf-8"}
    if headers:
        request_headers.update(headers)
    request = urllib.request.Request(url, data=body, headers=request_headers, method="POST")
    with urllib.request.urlopen(request, timeout=20) as response:
        raw = response.read().decode("utf-8", "ignore")
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        result = {"raw": raw}
    return {"ok": 200 <= response.status < 300, "status_code": response.status, "response": result}


def send_feishu_app_chat_text(feishu: dict[str, Any], text: str) -> dict[str, Any]:
    config = _resolve_feishu_app_config(feishu)
    token_response = _post_json(
        f"{FEISHU_API_HOST}/open-apis/auth/v3/tenant_access_token/internal",
        {"app_id": config["app_id"], "app_secret": config["app_secret"]},
    )
    token_body = token_response.get("response") if isinstance(token_response.get("response"), dict) else {}
    token = str(token_body.get("tenant_access_token") or "")
    if token_body.get("code") != 0 or not token:
        return {"ok": False, "stage": "tenant_access_token", "response": token_body}
    message_response = _post_json(
        f"{FEISHU_API_HOST}/open-apis/im/v1/messages?receive_id_type=chat_id",
        {
            "receive_id": config["chat_id"],
            "msg_type": "text",
            "content": json.dumps({"text": text}, ensure_ascii=False),
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    body = message_response.get("response") if isinstance(message_response.get("response"), dict) else {}
    return {
        "ok": bool(message_response.get("ok")) and body.get("code") in (None, 0),
        "stage": "message",
        "status_code": message_response.get("status_code"),
        "response": body,
    }


def _deliver_feishu(
    cfg: dict[str, Any],
    message: str,
    *,
    feishu_sender: FeishuSender,
) -> dict[str, Any]:
    delivery = cfg.get("delivery") if isinstance(cfg.get("delivery"), dict) else {}
    feishu = delivery.get("feishu") if isinstance(delivery.get("feishu"), dict) else {}
    if not bool(feishu.get("enabled", False)):
        return {"enabled": False, "attempted": False, "ok": True, "reason": "disabled"}
    try:
        result = feishu_sender(feishu, message)
    except Exception as exc:
        return {"enabled": True, "attempted": True, "ok": False, "reason": str(exc)}
    return {"enabled": True, "attempted": True, **result}


def run_scheduler_status_request(
    request: dict[str, Any],
    *,
    registry: dict[str, Any],
    db_path: str | Path,
    runs_dir: str | Path,
    repo_root: str | Path,
    now: datetime | None = None,
    launchctl_status_reader: LaunchctlStatusReader | None = None,
    feishu_sender: FeishuSender | None = None,
) -> dict[str, Any]:
    cfg = _config(request)
    result = build_scheduler_status_report(
        request,
        registry=registry,
        db_path=db_path,
        runs_dir=runs_dir,
        repo_root=repo_root,
        now=now,
        launchctl_status_reader=launchctl_status_reader,
    )
    status_dir = Path(runs_dir) / "scheduler_status"
    status_dir.mkdir(parents=True, exist_ok=True)
    (status_dir / "latest.md").write_text(result["message"], encoding="utf-8")
    delivery = {
        "feishu": _deliver_feishu(cfg, result["message"], feishu_sender=feishu_sender or send_feishu_app_chat_text),
    }
    payload = {**result, "delivery": delivery}
    artifact_path = write_run_artifact(runs_dir, "scheduler_status", payload)
    payload["artifact_path"] = str(artifact_path)
    return payload
