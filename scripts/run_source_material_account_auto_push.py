#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from roibang_v2.config import load_json, load_runtime_config
from roibang_v2.db.bootstrap import bootstrap_database
from roibang_v2.fetch.openapi_http import build_http_transport
from roibang_v2.workflows.create_http_transport import build_create_http_transport
from roibang_v2.workflows.source_material_account_auto_push import run_source_material_account_auto_push_request


def _root_config(request: dict) -> dict:
    value = request.get("source_material_account_auto_push")
    return dict(value) if isinstance(value, dict) else dict(request)


def run_from_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Push yesterday's new spent materials into the product source material account.")
    parser.add_argument("--config", default="configs/runtime.openapi-execute.local.example.json")
    parser.add_argument("--request", default="configs/source-material-account-auto-push.daily.example.json")
    parser.add_argument("--db", default=None)
    parser.add_argument("--runs-dir", default=None)
    parser.add_argument("--enable-readonly", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args(argv)

    runtime = load_runtime_config(args.config)
    request = load_json(args.request)
    cfg = _root_config(request)
    db_path = args.db or runtime.database_path
    runs_dir = args.runs_dir or runtime.runs_dir
    bootstrap_database(db_path)

    readonly_transport = None
    source_sync = cfg.get("source_account_sync") if isinstance(cfg.get("source_account_sync"), dict) else {}
    detail_fetch = cfg.get("material_detail_fetch") if isinstance(cfg.get("material_detail_fetch"), dict) else {}
    needs_readonly = bool(source_sync.get("enabled", False)) or bool(detail_fetch.get("enabled", False))
    if needs_readonly:
        if not args.enable_readonly:
            raise RuntimeError("readonly source account sync/detail fetch requires --enable-readonly")
        if not runtime.external_api_enabled:
            raise RuntimeError("readonly source account sync/detail fetch requires runtime external_api_enabled=true")
        readonly_http = cfg.get("openapi_http") if isinstance(cfg.get("openapi_http"), dict) else {}
        readonly_transport = build_http_transport(
            readonly_http,
            response_dir=Path(runs_dir) / "openapi_http" / "source-material-account-auto-push-readonly",
        )

    mutation_transport = None
    execute_cfg = cfg.get("execute") if isinstance(cfg.get("execute"), dict) else {}
    if args.execute:
        if not args.yes:
            raise RuntimeError("real source material account auto-push requires --yes")
        transport_cfg = execute_cfg.get("create_http_transport") if isinstance(execute_cfg.get("create_http_transport"), dict) else {}
        mutation_transport = build_create_http_transport(
            transport_cfg,
            response_dir=Path(runs_dir) / "openapi_http" / "source-material-account-auto-push-execute",
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

    result = run_source_material_account_auto_push_request(
        {"source_material_account_auto_push": cfg},
        db_path=db_path,
        runs_dir=runs_dir,
        readonly_transport=readonly_transport,
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
