from __future__ import annotations

import json
from datetime import datetime
from datetime import timezone
from pathlib import Path
from typing import Any

from roibang_v2.runs import write_latest_artifact
from roibang_v2.runs import write_run_artifact
from roibang_v2.workflows.delivery_business_report import build_delivery_business_report
from roibang_v2.workflows.create_batch_review import run_create_batch_review_request
from roibang_v2.workflows.delivery_business_report import run_delivery_business_report_request
from roibang_v2.workflows.delivery_suggestion_backtest import run_delivery_suggestion_backtest_request
from roibang_v2.workflows.scheduler_status import FeishuSender
from roibang_v2.workflows.scheduler_status import send_feishu_app_chat_text


def _text(value: Any) -> str:
    return str(value or "").strip()


def _rows(value: Any) -> list[dict[str, Any]]:
    return [dict(item) for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _load_json(path: str | Path) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _relative_or_absolute(path: Path) -> str:
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return str(path)


def _scope_title(scope: dict[str, Any]) -> str:
    title = _text(scope.get("title") or scope.get("name"))
    if title:
        return title
    if _text(scope.get("account_remark_equals")):
        return _text(scope.get("account_remark_equals"))
    if _text(scope.get("account_name_contains")):
        return f"账户名包含“{_text(scope.get('account_name_contains'))}”"
    return _text(scope.get("scope_id")) or "默认范围"


def _report_scopes(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    scopes = _rows(cfg.get("report_scopes"))
    if scopes:
        return scopes
    return [
        {
            "scope_id": "default",
            "title": _text(cfg.get("title")) or "默认范围",
            "patrol_artifact_path": _text(cfg.get("patrol_artifact_path") or "data/runs/delivery_patrol/latest.json"),
            "suggestions_artifact_path": _text(
                cfg.get("suggestions_artifact_path") or "data/runs/delivery_patrol_suggestions/latest.json"
            ),
        }
    ]


def _artifact_target_date(payload: dict[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    return _text(summary.get("target_date") or payload.get("target_date"))


def _artifact_account_scope(payload: dict[str, Any]) -> dict[str, Any]:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    scope = summary.get("account_scope") if isinstance(summary.get("account_scope"), dict) else {}
    return dict(scope)


def _matches_scope(payload: dict[str, Any], scope: dict[str, Any], *, target_date: str) -> bool:
    if target_date and _artifact_target_date(payload) != target_date:
        return False
    account_scope = _artifact_account_scope(payload)
    remark_equals = _text(scope.get("account_remark_equals"))
    if remark_equals:
        return _text(account_scope.get("account_remark_equals")) == remark_equals
    name_contains = _text(scope.get("account_name_contains"))
    if name_contains:
        scope_name_contains = _text(account_scope.get("account_name_contains"))
        product_keyword = _text(payload.get("product_keyword") or payload.get("summary", {}).get("product_keyword"))
        has_narrow_remark = bool(_text(account_scope.get("account_remark_equals")))
        if scope_name_contains:
            return scope_name_contains == name_contains
        if product_keyword == name_contains and not has_narrow_remark:
            return True
        if has_narrow_remark:
            return False
        accounts = _rows(payload.get("accounts"))
        return bool(accounts) and all(name_contains in _text(account.get("account_name")) for account in accounts)
    return True


def _find_scope_patrol_artifact(
    scope: dict[str, Any],
    *,
    runs_dir: str | Path,
    target_date: str,
) -> tuple[str, dict[str, Any], list[str]]:
    explicit = _text(scope.get("patrol_artifact_path") or scope.get("patrol_artifact"))
    if explicit:
        payload = _load_json(explicit)
        return explicit, payload, [] if payload else [f"巡检文件不可读取：{explicit}"]

    patrol_dir = Path(runs_dir) / "delivery_patrol"
    warnings: list[str] = []
    candidates = sorted(
        [path for path in patrol_dir.glob("*.json") if path.name != "latest.json"],
        reverse=True,
    )
    for path in candidates:
        payload = _load_json(path)
        if payload and _matches_scope(payload, scope, target_date=target_date):
            return _relative_or_absolute(path), payload, warnings
    warnings.append(f"未找到“{_scope_title(scope)}”对应的投放巡检结果。")
    return "", {}, warnings


def _scope_suggestions_path(scope: dict[str, Any], patrol: dict[str, Any]) -> str:
    explicit = _text(scope.get("suggestions_artifact_path") or scope.get("suggestions_artifact"))
    if explicit:
        return explicit
    summary = patrol.get("summary") if isinstance(patrol.get("summary"), dict) else {}
    return _text(summary.get("suggestion_artifact_path"))


def _message_without_title(report: dict[str, Any]) -> list[str]:
    lines = _text(report.get("message")).splitlines()
    if lines and lines[0].startswith("RoiBang-V2 投放运营日报"):
        lines = lines[1:]
    while lines and not lines[0].strip():
        lines = lines[1:]
    return lines


def _combined_multi_scope_message(
    *,
    target_date: str,
    scope_reports: list[dict[str, Any]],
    create_batch_review: dict[str, Any],
    warnings: list[str],
) -> str:
    lines = [f"RoiBang-V2 投放运营日报 {target_date}", ""]
    for index, scope_report in enumerate(scope_reports, start=1):
        lines.append(f"{index}、{scope_report['title']}")
        if scope_report.get("blocking_reasons"):
            for reason in scope_report["blocking_reasons"]:
                lines.append(f"- {reason}")
        else:
            lines.extend(_message_without_title(scope_report["business_report"]))
        lines.append("")
    if create_batch_review:
        summary = create_batch_review.get("summary") if isinstance(create_batch_review.get("summary"), dict) else {}
        modes = _rows(create_batch_review.get("mode_summary"))
        lines.append(f"{len(scope_reports) + 1}、创建批次复盘")
        lines.append(
            "- "
            + (
                f"批次 {int(float(summary.get('batch_count') or 0))} 个，"
                f"项目 {int(float(summary.get('project_count') or 0))} 个，"
                f"消耗 {float(summary.get('stat_cost') or 0):.2f}，"
                f"ROI {float(summary.get('roi_1day') or 0):.4f}".rstrip("0").rstrip(".")
            )
        )
        for item in modes[:3]:
            lines.append(
                f"  - {_text(item.get('mode_label') or item.get('key'))}："
                f"项目 {int(float(item.get('project_count') or 0))}，"
                f"消耗 {float(item.get('stat_cost') or 0):.2f}，"
                f"转化 {float(item.get('convert_cnt') or 0):.4f}".rstrip("0").rstrip(".")
                + f"，ROI {float(item.get('roi_1day') or 0):.4f}".rstrip("0").rstrip(".")
            )
    if warnings:
        lines.extend(["", "数据口径提示"])
        for warning in warnings:
            lines.append(f"- {warning}")
    return "\n".join(lines).strip()


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


def _run_single_scope_chain(
    scope: dict[str, Any],
    *,
    cfg: dict[str, Any],
    runs_dir: str | Path,
    db_path: str,
    target_date: str,
    lookahead_days: int,
) -> dict[str, Any]:
    title = _scope_title(scope)
    patrol_path, patrol, warnings = _find_scope_patrol_artifact(scope, runs_dir=runs_dir, target_date=target_date)
    suggestions_path = _scope_suggestions_path(scope, patrol)
    blocking_reasons = list(warnings)
    suggestions = _load_json(suggestions_path) if suggestions_path else {}
    if patrol and not suggestions_path:
        blocking_reasons.append(f"“{title}”巡检结果没有绑定建议结果。")
    if suggestions_path and not suggestions:
        blocking_reasons.append(f"“{title}”建议文件不可读取：{suggestions_path}")

    backtest: dict[str, Any] = {}
    business_report: dict[str, Any] = {}
    if not blocking_reasons:
        backtest = run_delivery_suggestion_backtest_request(
            {
                "suggestions_artifact_paths": [suggestions_path],
                "db_path": db_path,
                "lookahead_days": lookahead_days,
            },
            runs_dir=runs_dir,
        )
        business_report = build_delivery_business_report(
            patrol=patrol,
            suggestions=suggestions,
            backtest=backtest,
            create_batch_review=None,
        )

    return {
        "scope_id": _text(scope.get("scope_id")) or title,
        "title": title,
        "patrol_artifact_path": patrol_path,
        "suggestions_artifact_path": suggestions_path,
        "blocking_reasons": blocking_reasons,
        "backtest": backtest,
        "business_report": business_report,
    }


def run_delivery_readonly_report_chain_request(
    request: dict[str, Any] | None,
    *,
    runs_dir: str | Path,
    feishu_sender: FeishuSender | None = None,
) -> dict[str, Any]:
    cfg = dict(request or {})
    db_path = _text(cfg.get("db_path") or "data/roibang_v2.sqlite3")
    patrol_path = _text(cfg.get("patrol_artifact_path") or "data/runs/delivery_patrol/latest.json")
    suggestions_path = _text(cfg.get("suggestions_artifact_path") or "data/runs/delivery_patrol_suggestions/latest.json")
    target_date = _text(cfg.get("target_date"))
    lookahead_days = int(cfg.get("lookahead_days") or 1)
    recent_days = int(cfg.get("create_batch_recent_days") or cfg.get("recent_days") or 7)
    project_name_contains = _text(cfg.get("project_name_contains") or "郭靖")
    limit = int(cfg.get("limit") or 20)
    scopes = _report_scopes(cfg)

    if len(scopes) > 1 or _rows(cfg.get("report_scopes")):
        scope_reports = [
            _run_single_scope_chain(
                scope,
                cfg=cfg,
                runs_dir=runs_dir,
                db_path=db_path,
                target_date=target_date,
                lookahead_days=lookahead_days,
            )
            for scope in scopes
        ]
        create_batch_review = run_create_batch_review_request(
            {
                "db_path": db_path,
                "recent_days": recent_days,
                "project_name_contains": project_name_contains,
                "limit": limit,
            },
            runs_dir=runs_dir,
        )
        warnings = [
            reason
            for scope_report in scope_reports
            for reason in scope_report.get("blocking_reasons", [])
        ]
        resolved_target_date = target_date or next(
            (
                _text(report.get("business_report", {}).get("target_date"))
                for report in scope_reports
                if _text(report.get("business_report", {}).get("target_date"))
            ),
            _text(create_batch_review.get("summary", {}).get("end_date"))
            or datetime.now(timezone.utc).date().isoformat(),
        )
        message = _combined_multi_scope_message(
            target_date=resolved_target_date,
            scope_reports=scope_reports,
            create_batch_review=create_batch_review,
            warnings=warnings,
        )
        business_report_payload = {
            "ok": not warnings,
            "workflow": "delivery_business_report",
            "phase": "readonly_multi_scope_report",
            "execution_enabled": False,
            "external_api_calls": 0,
            "target_date": resolved_target_date,
            "summary": {
                "scope_count": len(scope_reports),
                "scopes": [
                    {
                        "scope_id": report["scope_id"],
                        "title": report["title"],
                        "business_report": report.get("business_report", {}).get("summary", {}),
                        "blocking_reasons": report.get("blocking_reasons", []),
                    }
                    for report in scope_reports
                ],
                "create_batch_review": create_batch_review.get("summary", {}),
            },
            "source": {
                "scopes": [
                    {
                        "scope_id": report["scope_id"],
                        "patrol_artifact_path": report.get("patrol_artifact_path", ""),
                        "suggestions_artifact_path": report.get("suggestions_artifact_path", ""),
                    }
                    for report in scope_reports
                ],
                "create_batch_review_artifact_path": create_batch_review["artifact_path"],
            },
            "scope_reports": scope_reports,
            "create_batch_review": create_batch_review,
            "warnings": warnings,
            "message": message,
        }
        business_report_payload["artifact_path"] = str(
            write_run_artifact(runs_dir, "delivery_business_report", business_report_payload)
        )
        business_report_payload["latest_artifact_path"] = str(Path(runs_dir) / "delivery_business_report" / "latest.json")
        write_latest_artifact(runs_dir, "delivery_business_report", business_report_payload)
        payload = {
            "ok": not warnings and all(bool(report.get("business_report", {}).get("ok", True)) for report in scope_reports),
            "workflow": "delivery_readonly_report_chain",
            "phase": "readonly_chain",
            "execution_enabled": False,
            "external_api_calls": 0,
            "summary": {
                "scope_count": len(scope_reports),
                "scopes": [
                    {
                        "scope_id": report["scope_id"],
                        "title": report["title"],
                        "business_report": report.get("business_report", {}).get("summary", {}),
                        "blocking_reasons": report.get("blocking_reasons", []),
                    }
                    for report in scope_reports
                ],
                "create_batch_review": create_batch_review.get("summary", {}),
            },
            "artifacts": {
                "scopes": [
                    {
                        "scope_id": report["scope_id"],
                        "patrol_artifact_path": report.get("patrol_artifact_path", ""),
                        "suggestions_artifact_path": report.get("suggestions_artifact_path", ""),
                        "backtest_artifact_path": report.get("backtest", {}).get("artifact_path", ""),
                    }
                    for report in scope_reports
                ],
                "create_batch_review_artifact_path": create_batch_review["artifact_path"],
                "create_batch_review_latest_artifact_path": create_batch_review["latest_artifact_path"],
                "business_report_artifact_path": business_report_payload["artifact_path"],
                "business_report_latest_artifact_path": business_report_payload["latest_artifact_path"],
            },
            "message": message,
        }
        payload["delivery"] = {
            "feishu": _deliver_feishu(
                cfg,
                payload["message"],
                feishu_sender=feishu_sender or send_feishu_app_chat_text,
            )
        }
        payload["artifact_path"] = str(write_run_artifact(runs_dir, "delivery_readonly_report_chain", payload))
        payload["latest_artifact_path"] = str(Path(runs_dir) / "delivery_readonly_report_chain" / "latest.json")
        write_latest_artifact(runs_dir, "delivery_readonly_report_chain", payload)
        return payload

    backtest = run_delivery_suggestion_backtest_request(
        {
            "suggestions_artifact_paths": [suggestions_path],
            "db_path": db_path,
            "lookahead_days": lookahead_days,
        },
        runs_dir=runs_dir,
    )
    create_batch_review = run_create_batch_review_request(
        {
            "db_path": db_path,
            "recent_days": recent_days,
            "project_name_contains": project_name_contains,
            "limit": limit,
        },
        runs_dir=runs_dir,
    )
    business_report = run_delivery_business_report_request(
        {
            "patrol_artifact_path": patrol_path,
            "suggestions_artifact_path": suggestions_path,
            "backtest_artifact_path": backtest["latest_artifact_path"],
            "create_batch_review_artifact_path": create_batch_review["latest_artifact_path"],
        },
        runs_dir=runs_dir,
    )
    payload = {
        "ok": bool(backtest.get("ok") and create_batch_review.get("ok") and business_report.get("ok")),
        "workflow": "delivery_readonly_report_chain",
        "phase": "readonly_chain",
        "execution_enabled": False,
        "external_api_calls": 0,
        "summary": {
            "backtest": backtest.get("summary", {}),
            "create_batch_review": create_batch_review.get("summary", {}),
            "business_report": business_report.get("summary", {}),
        },
        "artifacts": {
            "backtest_artifact_path": backtest["artifact_path"],
            "backtest_latest_artifact_path": backtest["latest_artifact_path"],
            "create_batch_review_artifact_path": create_batch_review["artifact_path"],
            "create_batch_review_latest_artifact_path": create_batch_review["latest_artifact_path"],
            "business_report_artifact_path": business_report["artifact_path"],
            "business_report_latest_artifact_path": business_report["latest_artifact_path"],
        },
        "message": business_report.get("message", ""),
    }
    payload["delivery"] = {
        "feishu": _deliver_feishu(
            cfg,
            payload["message"],
            feishu_sender=feishu_sender or send_feishu_app_chat_text,
        )
    }
    payload["artifact_path"] = str(write_run_artifact(runs_dir, "delivery_readonly_report_chain", payload))
    payload["latest_artifact_path"] = str(Path(runs_dir) / "delivery_readonly_report_chain" / "latest.json")
    write_latest_artifact(runs_dir, "delivery_readonly_report_chain", payload)
    return payload
