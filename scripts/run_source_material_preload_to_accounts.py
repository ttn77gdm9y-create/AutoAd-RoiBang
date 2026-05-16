#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from roibang_v2.config import load_json, load_runtime_config
from roibang_v2.db.bootstrap import bootstrap_database
from roibang_v2.workflows.create_http_transport import build_create_http_transport
from roibang_v2.workflows.source_material_preload_to_accounts import run_source_material_preload_to_accounts_request


def _root_config(request: dict) -> dict:
    value = request.get("source_material_preload_to_accounts")
    return dict(value) if isinstance(value, dict) else dict(request)


def _account_rows(accounts_text: str) -> list[dict[str, str]]:
    return [
        {"advertiser_id": account_id.strip()}
        for account_id in accounts_text.split(",")
        if account_id.strip()
    ]


def run_from_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Preload product source account materials into target advertiser accounts.")
    parser.add_argument("--config", default="configs/runtime.openapi-execute.local.example.json")
    parser.add_argument("--request", default="configs/source-material-preload-to-accounts.today-guojing.example.json")
    parser.add_argument("--db", default=None)
    parser.add_argument("--runs-dir", default=None)
    parser.add_argument("--accounts", default="", help="Comma-separated target advertiser IDs for manual new-account preload.")
    parser.add_argument("--target-date", default="", help="Override target_date used in batch keys and artifacts.")
    parser.add_argument("--full-source", action="store_true", help="Use all source materials for the selected target accounts.")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args(argv)

    runtime = load_runtime_config(args.config)
    request = load_json(args.request)
    cfg = _root_config(request)
    if args.target_date:
        cfg = {**cfg, "target_date": args.target_date}
    if args.accounts:
        cfg = {**cfg, "target_accounts": {"accounts": _account_rows(args.accounts)}}
    if args.full_source:
        material_source = cfg.get("material_source") if isinstance(cfg.get("material_source"), dict) else {}
        cfg = {
            **cfg,
            "material_source": {
                **material_source,
                "limit": 0,
                "max_bind_materials": 0,
            },
        }
    db_path = args.db or runtime.database_path
    runs_dir = args.runs_dir or runtime.runs_dir
    bootstrap_database(db_path)

    mutation_transport = None
    execute_cfg = cfg.get("execute") if isinstance(cfg.get("execute"), dict) else {}
    if args.execute:
        if not args.yes:
            raise RuntimeError("real source material preload requires --yes")
        transport_cfg = execute_cfg.get("create_http_transport") if isinstance(execute_cfg.get("create_http_transport"), dict) else {}
        mutation_transport = build_create_http_transport(
            transport_cfg,
            response_dir=Path(runs_dir) / "openapi_http" / "source-material-preload-to-accounts-execute",
        )
        cfg = {
            **cfg,
            "execute": {
                **execute_cfg,
                "enabled": True,
                "approved": True,
                "allow_mutation": True,
            },
        }
    else:
        cfg = {
            **cfg,
            "execute": {
                **execute_cfg,
                "enabled": False,
                "approved": False,
                "allow_mutation": False,
            },
        }

    result = run_source_material_preload_to_accounts_request(
        {"source_material_preload_to_accounts": cfg},
        db_path=db_path,
        runs_dir=runs_dir,
        mutation_transport=mutation_transport,
    )
    print(
        json.dumps(
            {
                "ok": result["ok"],
                "workflow": result["workflow"],
                "phase": result["phase"],
                "status": result["status"],
                "execution_enabled": result["execution_enabled"],
                "external_api_calls": result["external_api_calls"],
                "summary": result["summary"],
                "blocking_reasons": result["blocking_reasons"],
                "artifact_path": result["artifact_path"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if result["ok"] else 1


def main() -> int:
    return run_from_args()


if __name__ == "__main__":
    raise SystemExit(main())
