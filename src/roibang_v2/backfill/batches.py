from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from roibang_v2.config import load_json


def _find_batch(plan: dict[str, Any], batch_id: str) -> dict[str, Any]:
    batches = plan.get("batches")
    if not isinstance(batches, list):
        raise ValueError("backfill batch plan requires batches list")
    for batch in batches:
        if isinstance(batch, dict) and str(batch.get("batch_id") or "") == batch_id:
            return batch
    raise ValueError(f"batch not found: {batch_id}")


def _disabled_request(request: dict[str, Any]) -> dict[str, Any]:
    payload = deepcopy(request)
    cfg = payload.get("report_fetch") if isinstance(payload.get("report_fetch"), dict) else payload
    execution = cfg.setdefault("execution", {})
    execution["status"] = "planned_only"
    execution["external_api_enabled"] = False
    http = cfg.setdefault("openapi_http", {})
    http["enabled"] = False
    return payload


def export_batch_request(
    *,
    plan_path: str | Path,
    batch_id: str,
    output_dir: str | Path,
) -> dict[str, Any]:
    plan = load_json(plan_path)
    if str(plan.get("workflow") or "") != "report_backfill_batch_plan":
        raise ValueError("plan must be a report_backfill_batch_plan artifact")
    batch = _find_batch(plan, batch_id)
    request = batch.get("report_fetch_request")
    if not isinstance(request, dict):
        raise ValueError(f"batch {batch_id} does not contain report_fetch_request")
    payload = _disabled_request(request)
    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{batch_id}.report-fetch.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    cfg = payload["report_fetch"] if isinstance(payload.get("report_fetch"), dict) else payload
    account_ids = cfg.get("account_ids") if isinstance(cfg.get("account_ids"), list) else []
    date_range = cfg.get("date_range") if isinstance(cfg.get("date_range"), dict) else {}
    return {
        "ok": True,
        "workflow": "backfill_batch_request_export",
        "batch_id": batch_id,
        "execution_enabled": False,
        "external_api_calls": 0,
        "output_path": str(target),
        "summary": {
            "planned_request_count": int(batch.get("planned_request_count") or 0),
            "account_count": len(account_ids),
            "date_range": {
                "start": str(date_range.get("start") or ""),
                "end": str(date_range.get("end") or ""),
            },
        },
    }
