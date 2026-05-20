from __future__ import annotations

from pathlib import Path
from typing import Any

from roibang_v2.runs import write_latest_artifact
from roibang_v2.runs import write_run_artifact
from roibang_v2.workflows.create_batch_review import run_create_batch_review_request
from roibang_v2.workflows.delivery_business_report import run_delivery_business_report_request
from roibang_v2.workflows.delivery_suggestion_backtest import run_delivery_suggestion_backtest_request
from roibang_v2.workflows.scheduler_status import FeishuSender
from roibang_v2.workflows.scheduler_status import send_feishu_app_chat_text


def _text(value: Any) -> str:
    return str(value or "").strip()


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


def run_delivery_readonly_report_chain_request(
    request: dict[str, Any] | None,
    *,
    runs_dir: str | Path,
    feishu_sender: FeishuSender | None = None,
) -> dict[str, Any]:
    cfg = dict(request or {})
    db_path = _text(cfg.get("db_path") or "data/roibang_v2.sqlite3")
    patrol_path = _text(cfg.get("patrol_artifact_path") or "data/runs/delivery_patrol/latest.json")
    suggestions_path = _text(
        cfg.get("suggestions_artifact_path") or "data/runs/delivery_patrol_suggestions/latest.json"
    )
    lookahead_days = int(cfg.get("lookahead_days") or 1)
    recent_days = int(cfg.get("create_batch_recent_days") or cfg.get("recent_days") or 7)
    project_name_contains = _text(cfg.get("project_name_contains") or "郭靖")
    limit = int(cfg.get("limit") or 20)

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
