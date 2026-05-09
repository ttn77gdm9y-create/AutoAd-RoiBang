from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from roibang_v2.runs import write_run_artifact


def _check_config(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("create_phase2_yzt_account_pool_check")
    return dict(value) if isinstance(value, dict) else dict(request)


def _accounts(preview_config: dict[str, Any]) -> list[dict[str, Any]]:
    rows = preview_config.get("accounts")
    return [dict(row) for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _catalog(policy: dict[str, Any]) -> dict[str, Any]:
    prep = policy.get("create_phase2_template_slot_prep")
    prep = prep if isinstance(prep, dict) else {}
    catalog = prep.get("product_template_catalog")
    return dict(catalog) if isinstance(catalog, dict) else {}


def _product(policy: dict[str, Any]) -> str:
    return str(_catalog(policy).get("product") or "勇者突进")


def _platform(policy: dict[str, Any]) -> str:
    return str(_catalog(policy).get("platform") or "WECHAT_GAME")


def _account_pool_rows(
    *,
    db_path: str | Path,
    product: str,
    platform: str,
) -> dict[str, str]:
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT advertiser_id, account_name
            FROM account_pool
            WHERE product = ?
              AND platform = ?
            """,
            (product, platform),
        ).fetchall()
    return {str(row[0]): str(row[1] or "") for row in rows}


def _account_checks(
    *,
    preview_config: dict[str, Any],
    db_path: str | Path,
    product: str,
    platform: str,
) -> list[dict[str, Any]]:
    pool = _account_pool_rows(db_path=db_path, product=product, platform=platform)
    checks: list[dict[str, Any]] = []
    for account in _accounts(preview_config):
        advertiser_id = str(account.get("advertiser_id") or "").strip()
        if not advertiser_id:
            continue
        account_name = pool.get(advertiser_id, "")
        checks.append(
            {
                "advertiser_id": advertiser_id,
                "status": "found" if advertiser_id in pool else "missing",
                "account_name": account_name,
            }
        )
    return checks


def build_create_phase2_yzt_account_pool_check(
    *,
    preview_config: dict[str, Any],
    policy: dict[str, Any],
    db_path: str | Path,
) -> dict[str, Any]:
    product = _product(policy)
    platform = _platform(policy)
    checks = _account_checks(
        preview_config=preview_config,
        db_path=db_path,
        product=product,
        platform=platform,
    )
    missing = [row for row in checks if row["status"] == "missing"]
    violations = [
        f"账户 {row['advertiser_id']} 不在本地账户池：{product}/{platform}"
        for row in missing
    ]
    ok = not violations
    return {
        "ok": ok,
        "workflow": "create_phase2_yzt_account_pool_check",
        "phase": "phase2_preparation",
        "execution_enabled": False,
        "external_api_calls": 0,
        "status": "passed" if ok else "needs_account_pool_sync",
        "summary": {
            "product": product,
            "platform": platform,
            "requested_account_count": len(checks),
            "found_account_count": len([row for row in checks if row["status"] == "found"]),
            "missing_account_count": len(missing),
            "ready_for_dry_chain": ok,
        },
        "account_checks": checks,
        "violations": violations,
        "human_next_steps": (
            ["配置账户都在本地账户池里；下一步可以跑完整预演。"]
            if ok
            else ["先同步账户池，或把配置里的账户ID改成本地账户池已有账户。"]
        ),
        "actions": [],
    }


def run_create_phase2_yzt_account_pool_check_request(
    request: dict[str, Any],
    *,
    db_path: str | Path,
    runs_dir: str | Path,
) -> dict[str, Any]:
    cfg = _check_config(request)
    payload = build_create_phase2_yzt_account_pool_check(
        preview_config=cfg.get("preview_config") if isinstance(cfg.get("preview_config"), dict) else {},
        policy=cfg.get("policy") if isinstance(cfg.get("policy"), dict) else {},
        db_path=db_path,
    )
    artifact_path = write_run_artifact(runs_dir, "create_phase2_yzt_account_pool_check", payload)
    return {**payload, "artifact_path": str(artifact_path)}
