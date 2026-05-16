from __future__ import annotations

import json
import re
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable

from roibang_v2.runs import write_run_artifact
from roibang_v2.workflows.source_material_account_auto_push import BIND_MATERIAL_ENDPOINT
from roibang_v2.workflows.source_material_account_auto_push import _api_code
from roibang_v2.workflows.source_material_account_auto_push import _response_message


MutationTransport = Callable[[dict[str, Any]], dict[str, Any]]
Sleeper = Callable[[float], None]
_VALID_SOURCE_VIDEO_ID = re.compile(r"^v[0-9A-Za-z]{12,}$")
_MAX_BIND_MATERIAL_VIDEO_IDS = 50


def _cfg(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("source_material_preload_to_accounts")
    return dict(value) if isinstance(value, dict) else dict(request)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _float(value: Any) -> float:
    try:
        return float(str(value or "0").replace(",", ""))
    except ValueError:
        return 0.0


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _target_date(cfg: dict[str, Any], *, today: date | None = None) -> str:
    value = _text(cfg.get("target_date"))
    if value == "today":
        return (today or date.today()).isoformat()
    if value == "yesterday":
        base = today or date.today()
        return date.fromordinal(base.toordinal() - 1).isoformat()
    if value:
        return value
    return (today or date.today()).isoformat()


def _load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _metric_for_window(account: dict[str, Any], window: str) -> dict[str, Any]:
    metrics = account.get("metrics") if isinstance(account.get("metrics"), dict) else {}
    value = metrics.get(window)
    return dict(value) if isinstance(value, dict) else {}


def _select_target_accounts(cfg: dict[str, Any], *, today: date | None = None) -> list[dict[str, Any]]:
    target_cfg = cfg.get("target_accounts") if isinstance(cfg.get("target_accounts"), dict) else {}
    explicit = target_cfg.get("accounts")
    if isinstance(explicit, list) and explicit:
        return [
            {
                "advertiser_id": _text(row.get("advertiser_id") if isinstance(row, dict) else row),
                "account_name": _text(row.get("account_name") if isinstance(row, dict) else ""),
                "account_remark": _text(row.get("account_remark") if isinstance(row, dict) else ""),
                "stat_cost": _float(row.get("stat_cost") if isinstance(row, dict) else 0),
            }
            for row in explicit
            if _text(row.get("advertiser_id") if isinstance(row, dict) else row)
        ]

    source = _text(target_cfg.get("source") or "delivery_patrol_artifact")
    if source != "delivery_patrol_artifact":
        raise ValueError(f"unsupported target account source: {source}")
    artifact_path = _text(target_cfg.get("artifact_path") or "data/runs/delivery_patrol/latest.json")
    payload = _load_json(artifact_path)
    accounts = payload.get("accounts") if isinstance(payload.get("accounts"), list) else []
    remark_equals = _text(target_cfg.get("account_remark_equals"))
    spend_window = _text(target_cfg.get("spend_window") or "today")
    min_spend = _float(target_cfg.get("min_spend"))
    selected: list[dict[str, Any]] = []
    for account in [row for row in accounts if isinstance(row, dict)]:
        account_remark = _text(account.get("account_remark") or account.get("advertiser_remark"))
        if remark_equals and account_remark != remark_equals:
            continue
        metric = _metric_for_window(account, spend_window)
        stat_cost = _float(metric.get("stat_cost"))
        if stat_cost <= min_spend:
            continue
        advertiser_id = _text(account.get("advertiser_id") or account.get("account_id"))
        if not advertiser_id:
            continue
        selected.append(
            {
                "advertiser_id": advertiser_id,
                "account_name": _text(account.get("account_name") or account.get("advertiser_name")),
                "account_remark": account_remark,
                "stat_cost": stat_cost,
                "spend_window": spend_window,
                "artifact_path": artifact_path,
                "target_date": _target_date(cfg, today=today),
            }
        )
    return selected


def _select_source_materials(*, db_path: str | Path, cfg: dict[str, Any]) -> list[dict[str, Any]]:
    material_cfg = cfg.get("material_source") if isinstance(cfg.get("material_source"), dict) else {}
    material_type = _text(material_cfg.get("material_type") or "video")
    limit = _int(material_cfg.get("limit"), 0)
    params: list[Any] = [_text(cfg.get("product")), _text(cfg.get("source_advertiser_id")), material_type]
    limit_sql = ""
    if limit > 0:
        limit_sql = "LIMIT ?"
        params.append(limit)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"""
            SELECT material_id, video_id, name, material_type, review_status, cost_lookback, score, source, synced_at
            FROM product_source_materials
            WHERE product = ?
              AND source_advertiser_id = ?
              AND material_type = ?
              AND is_active = 1
              AND COALESCE(video_id, '') <> ''
            ORDER BY COALESCE(cost_lookback, 0) DESC, COALESCE(score, 0) DESC, material_id ASC
            {limit_sql}
            """,
            tuple(params),
        ).fetchall()
    materials: list[dict[str, Any]] = []
    for row in rows:
        material_id = _text(row["material_id"])
        video_id = _text(row["video_id"])
        source = _text(row["source"])
        if not material_id.isdigit():
            continue
        if not _VALID_SOURCE_VIDEO_ID.fullmatch(video_id):
            continue
        if "fixtures" in source.lower().replace("\\", "/"):
            continue
        materials.append(
            {
                "material_id": material_id,
                "video_id": video_id,
                "name": _text(row["name"]),
                "material_type": _text(row["material_type"]),
                "review_status": _text(row["review_status"]),
                "cost_lookback": float(row["cost_lookback"] or 0),
                "score": float(row["score"] or 0),
                "synced_at": _text(row["synced_at"]),
            }
        )
    return materials


def _existing_target_material_ids(
    *,
    db_path: str | Path,
    product: str,
    source_advertiser_id: str,
    target_account_ids: list[str],
) -> dict[str, set[str]]:
    if not target_account_ids:
        return {}
    placeholders = ",".join("?" for _ in target_account_ids)
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            f"""
            SELECT advertiser_id, material_id
            FROM account_materials
            WHERE advertiser_id IN ({placeholders})
              AND material_type = 'video'
            UNION
            SELECT advertiser_id, material_id
            FROM material_bindings
            WHERE advertiser_id IN ({placeholders})
              AND material_kind = 'video'
            UNION
            SELECT target_advertiser_id AS advertiser_id, source_material_id AS material_id
            FROM source_material_preload_ledger
            WHERE product = ?
              AND source_advertiser_id = ?
              AND target_advertiser_id IN ({placeholders})
              AND status = 'completed'
            """,
            tuple([*target_account_ids, *target_account_ids, product, source_advertiser_id, *target_account_ids]),
        ).fetchall()
    existing: dict[str, set[str]] = {advertiser_id: set() for advertiser_id in target_account_ids}
    for advertiser_id, material_id in rows:
        existing.setdefault(_text(advertiser_id), set()).add(_text(material_id))
    return existing


def _chunks(items: list[Any], size: int) -> list[list[Any]]:
    chunk_size = max(size, 1)
    return [items[index : index + chunk_size] for index in range(0, len(items), chunk_size)]


def build_source_material_preload_plan(
    *,
    db_path: str | Path,
    cfg: dict[str, Any],
    today: date | None = None,
) -> dict[str, Any]:
    target_accounts = _select_target_accounts(cfg, today=today)
    source_materials = _select_source_materials(db_path=db_path, cfg=cfg)
    existing = _existing_target_material_ids(
        db_path=db_path,
        product=_text(cfg.get("product")),
        source_advertiser_id=_text(cfg.get("source_advertiser_id")),
        target_account_ids=[row["advertiser_id"] for row in target_accounts],
    )
    material_cfg = cfg.get("material_source") if isinstance(cfg.get("material_source"), dict) else {}
    max_bind_materials = _int(material_cfg.get("max_bind_materials"), 0)
    requested_batch_size = _int(material_cfg.get("batch_size"), _MAX_BIND_MATERIAL_VIDEO_IDS)
    batch_size = min(max(requested_batch_size, 1), _MAX_BIND_MATERIAL_VIDEO_IDS)
    already_exists_count = 0
    pairs_by_account: dict[str, list[dict[str, Any]]] = {}
    for account in target_accounts:
        advertiser_id = account["advertiser_id"]
        existing_ids = existing.get(advertiser_id, set())
        for material in source_materials:
            if material["material_id"] in existing_ids:
                already_exists_count += 1
                continue
            pairs_by_account.setdefault(advertiser_id, []).append({"account": account, "material": material})

    planned_pairs: list[dict[str, Any]] = []
    account_ids = [row["advertiser_id"] for row in target_accounts]
    if max_bind_materials > 0:
        offsets = {advertiser_id: 0 for advertiser_id in account_ids}
        while len(planned_pairs) < max_bind_materials:
            progressed = False
            for advertiser_id in account_ids:
                rows = pairs_by_account.get(advertiser_id, [])
                offset = offsets.get(advertiser_id, 0)
                if offset >= len(rows):
                    continue
                planned_pairs.append(rows[offset])
                offsets[advertiser_id] = offset + 1
                progressed = True
                if len(planned_pairs) >= max_bind_materials:
                    break
            if not progressed:
                break
    else:
        for advertiser_id in account_ids:
            planned_pairs.extend(pairs_by_account.get(advertiser_id, []))

    batches: list[dict[str, Any]] = []
    grouped: dict[str, list[dict[str, Any]]] = {}
    account_lookup = {row["advertiser_id"]: row for row in target_accounts}
    for pair in planned_pairs:
        grouped.setdefault(pair["account"]["advertiser_id"], []).append(pair["material"])
    for advertiser_id, materials in grouped.items():
        for index, chunk in enumerate(_chunks(materials, batch_size), start=1):
            batches.append(
                {
                    "batch_key": f"{_target_date(cfg, today=today)}_{advertiser_id}_{index}",
                    "source_advertiser_id": _text(cfg.get("source_advertiser_id")),
                    "target_advertiser_id": advertiser_id,
                    "target_account": account_lookup.get(advertiser_id, {}),
                    "video_ids": [row["video_id"] for row in chunk],
                    "material_ids": [row["material_id"] for row in chunk],
                    "material_count": len(chunk),
                }
            )
    return {
        "ok": True,
        "workflow": "source_material_preload_plan",
        "phase": "source_material_preload",
        "execution_enabled": False,
        "external_api_calls": 0,
        "product": _text(cfg.get("product")),
        "source_advertiser_id": _text(cfg.get("source_advertiser_id")),
        "target_date": _target_date(cfg, today=today),
        "summary": {
            "target_account_count": len(target_accounts),
            "source_material_count": len(source_materials),
            "already_exists_count": already_exists_count,
            "planned_bind_material_count": len(planned_pairs),
            "push_batch_count": len(batches),
            "batch_size": batch_size,
            "requested_batch_size": requested_batch_size,
            "max_bind_material_video_ids": _MAX_BIND_MATERIAL_VIDEO_IDS,
        },
        "target_accounts": target_accounts,
        "push_batches": batches,
    }


def _bind_request(batch: dict[str, Any]) -> dict[str, Any]:
    return {
        "operation": "bind_material",
        "endpoint": BIND_MATERIAL_ENDPOINT,
        "payload": {
            "advertiser_id": int(batch["source_advertiser_id"])
            if str(batch["source_advertiser_id"]).isdigit()
            else batch["source_advertiser_id"],
            "target_advertiser_ids": [
                int(batch["target_advertiser_id"])
                if str(batch["target_advertiser_id"]).isdigit()
                else batch["target_advertiser_id"]
            ],
            "video_ids": list(batch.get("video_ids") or []),
        },
    }


def _execute_batches(
    batches: list[dict[str, Any]],
    *,
    transport: MutationTransport,
    execute_cfg: dict[str, Any],
    sleeper: Sleeper,
) -> dict[str, Any]:
    retry_codes = {str(item) for item in execute_cfg.get("retry_api_codes", [])} if isinstance(execute_cfg.get("retry_api_codes"), list) else set()
    max_retries = _int(execute_cfg.get("max_api_retries"), 0)
    retry_sleep = _float(execute_cfg.get("retry_sleep_seconds") or 1)
    concurrency = max(_int(execute_cfg.get("concurrency"), 1), 1)

    def execute_one(batch: dict[str, Any]) -> dict[str, Any]:
        request = _bind_request(batch)
        response: dict[str, Any] = {}
        calls = 0
        start = time.monotonic()
        attempts = max_retries + 1
        for attempt in range(1, attempts + 1):
            try:
                response = transport(request)
            except Exception as exc:  # keep one bad batch from aborting the whole preload run
                calls += 1
                duration = round(time.monotonic() - start, 4)
                return {
                    "batch_key": batch["batch_key"],
                    "target_advertiser_id": batch["target_advertiser_id"],
                    "video_count": len(batch.get("video_ids") or []),
                    "status": "failed",
                    "api_code": "transport_error",
                    "message": str(exc),
                    "duration_seconds": duration,
                    "external_api_calls": calls,
                    "response": {"error_type": type(exc).__name__, "error": str(exc)},
                }
            calls += 1
            code = _api_code(response)
            if not code or code not in retry_codes or attempt == attempts:
                break
            sleeper(retry_sleep)
        duration = round(time.monotonic() - start, 4)
        code = _api_code(response)
        return {
            "batch_key": batch["batch_key"],
            "target_advertiser_id": batch["target_advertiser_id"],
            "video_count": len(batch.get("video_ids") or []),
            "status": "completed" if not code else "failed",
            "api_code": code,
            "message": _response_message(response),
            "duration_seconds": duration,
            "external_api_calls": calls,
            "response": response,
        }

    total_start = time.monotonic()
    if concurrency <= 1 or len(batches) <= 1:
        results = [execute_one(batch) for batch in batches]
    else:
        results = []
        with ThreadPoolExecutor(max_workers=min(concurrency, len(batches))) as pool:
            futures = {pool.submit(execute_one, batch): index for index, batch in enumerate(batches)}
            ordered: list[tuple[int, dict[str, Any]]] = []
            for future in as_completed(futures):
                ordered.append((futures[future], future.result()))
        results = [row for _index, row in sorted(ordered, key=lambda item: item[0])]
    durations = [float(row.get("duration_seconds") or 0) for row in results]
    total_duration = round(time.monotonic() - total_start, 4)
    return {
        "external_api_calls": sum(int(row.get("external_api_calls") or 0) for row in results),
        "results": results,
        "concurrency": concurrency,
        "total_duration_seconds": total_duration,
        "avg_seconds_per_batch": round(sum(durations) / len(durations), 4) if durations else 0,
        "max_seconds_per_batch": max(durations) if durations else 0,
    }


def _record_completed_preload_ledger(
    *,
    db_path: str | Path,
    product: str,
    source_advertiser_id: str,
    batches: list[dict[str, Any]],
    results: list[dict[str, Any]],
) -> int:
    completed_keys = {str(row.get("batch_key") or ""): row for row in results if row.get("status") == "completed"}
    if not completed_keys:
        return 0
    batch_lookup = {str(batch.get("batch_key") or ""): batch for batch in batches}
    now = _now_iso()
    rows: list[tuple[Any, ...]] = []
    for batch_key, result in completed_keys.items():
        batch = batch_lookup.get(batch_key)
        if not batch:
            continue
        material_ids = list(batch.get("material_ids") or [])
        video_ids = list(batch.get("video_ids") or [])
        response_json = json.dumps(result.get("response") or {}, ensure_ascii=False, sort_keys=True)
        for index, material_id in enumerate(material_ids):
            rows.append(
                (
                    product,
                    source_advertiser_id,
                    _text(batch.get("target_advertiser_id")),
                    _text(material_id),
                    _text(video_ids[index] if index < len(video_ids) else ""),
                    "completed",
                    batch_key,
                    response_json,
                    now,
                    now,
                )
            )
    if not rows:
        return 0
    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            """
            INSERT INTO source_material_preload_ledger (
              product, source_advertiser_id, target_advertiser_id, source_material_id,
              source_video_id, status, batch_key, response_payload_json, first_seen_at, last_seen_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(product, source_advertiser_id, target_advertiser_id, source_material_id)
            DO UPDATE SET
              source_video_id = excluded.source_video_id,
              status = excluded.status,
              batch_key = excluded.batch_key,
              response_payload_json = excluded.response_payload_json,
              last_seen_at = excluded.last_seen_at
            """,
            rows,
        )
    return len(rows)


def run_source_material_preload_to_accounts_request(
    request: dict[str, Any],
    *,
    db_path: str | Path,
    runs_dir: str | Path,
    mutation_transport: MutationTransport | None = None,
    today: date | None = None,
    sleeper: Sleeper | None = None,
) -> dict[str, Any]:
    cfg = _cfg(request)
    reasons: list[str] = []
    if not _text(cfg.get("product")):
        reasons.append("missing product")
    if not _text(cfg.get("source_advertiser_id")):
        reasons.append("missing source_advertiser_id")
    plan = build_source_material_preload_plan(db_path=db_path, cfg=cfg, today=today) if not reasons else {}
    execute_cfg = cfg.get("execute") if isinstance(cfg.get("execute"), dict) else {}
    execute_enabled = bool(execute_cfg.get("enabled", False))
    approved = bool(execute_cfg.get("approved", False))
    if not execute_enabled:
        payload = {
            "ok": not reasons,
            "workflow": "source_material_preload_to_accounts",
            "phase": "source_material_preload",
            "status": "preflight",
            "execution_enabled": False,
            "external_api_calls": 0,
            "summary": {
                **(plan.get("summary") if isinstance(plan.get("summary"), dict) else {}),
                "executed_bind_material_count": 0,
                "failed_batch_count": 0,
            },
            "blocking_reasons": reasons,
            "plan": plan,
            "results": [],
        }
        artifact = write_run_artifact(runs_dir, "source_material_preload_to_accounts", payload)
        return {**payload, "artifact_path": str(artifact)}

    if not approved:
        reasons.append("execute requires approved=true")
    if mutation_transport is None:
        reasons.append("execute requires mutation_transport")
    if not bool(execute_cfg.get("allow_mutation", False)):
        reasons.append("execute requires allow_mutation=true")
    if reasons:
        payload = {
            "ok": False,
            "workflow": "source_material_preload_to_accounts",
            "phase": "source_material_preload",
            "status": "blocked",
            "execution_enabled": False,
            "external_api_calls": 0,
            "summary": plan.get("summary") if isinstance(plan.get("summary"), dict) else {},
            "blocking_reasons": reasons,
            "plan": plan,
            "results": [],
        }
        artifact = write_run_artifact(runs_dir, "source_material_preload_to_accounts", payload)
        return {**payload, "artifact_path": str(artifact)}

    execution = _execute_batches(
        plan["push_batches"],
        transport=mutation_transport,
        execute_cfg=execute_cfg,
        sleeper=sleeper or time.sleep,
    )
    results = execution["results"]
    failed = [row for row in results if row["status"] != "completed"]
    completed = [row for row in results if row["status"] == "completed"]
    ledger_rows = _record_completed_preload_ledger(
        db_path=db_path,
        product=_text(cfg.get("product")),
        source_advertiser_id=_text(cfg.get("source_advertiser_id")),
        batches=plan["push_batches"],
        results=results,
    )
    payload = {
        "ok": not failed,
        "workflow": "source_material_preload_to_accounts",
        "phase": "source_material_preload",
        "status": "completed" if not failed else "completed_with_errors",
        "execution_enabled": True,
        "external_api_calls": int(execution["external_api_calls"]),
        "summary": {
            **plan["summary"],
            "executed_batch_count": len(completed),
            "executed_bind_material_count": sum(int(row.get("video_count") or 0) for row in completed),
            "failed_batch_count": len(failed),
            "ledger_rows_upserted": ledger_rows,
            "rate_limited_batch_count": sum(1 for row in results if str(row.get("api_code") or "") == "40100"),
            "concurrency": execution["concurrency"],
            "total_duration_seconds": execution["total_duration_seconds"],
            "avg_seconds_per_batch": execution["avg_seconds_per_batch"],
            "max_seconds_per_batch": execution["max_seconds_per_batch"],
        },
        "blocking_reasons": [],
        "plan": plan,
        "results": results,
        "completed_at": _now_iso(),
    }
    artifact = write_run_artifact(runs_dir, "source_material_preload_to_accounts", payload)
    return {**payload, "artifact_path": str(artifact)}
