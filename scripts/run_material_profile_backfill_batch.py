#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path

from roibang_v2.config import load_json
from roibang_v2.config import load_runtime_config
from roibang_v2.db.bootstrap import bootstrap_database
from roibang_v2.fetch.openapi_http import build_http_transport
from roibang_v2.workflows.material_profile_backfill_batch import run_material_profile_backfill_batch_request


def _enable_readonly(request: dict) -> dict:
    updated = deepcopy(request)
    cfg = updated.setdefault("material_profile_backfill_batch", {})
    if not isinstance(cfg, dict):
        raise RuntimeError("material_profile_backfill_batch must be a JSON object")
    profile_cfg = cfg.setdefault("material_profile_sync", {})
    if not isinstance(profile_cfg, dict):
        raise RuntimeError("material_profile_backfill_batch.material_profile_sync must be a JSON object")
    if str(profile_cfg.get("kind") or "") != "openapi_video_materials":
        raise RuntimeError("--enable-readonly only supports kind=openapi_video_materials")
    profile_cfg["enabled"] = True
    openapi_http = profile_cfg.setdefault("openapi_http", {})
    if not isinstance(openapi_http, dict):
        raise RuntimeError("material_profile_sync.openapi_http must be a JSON object")
    openapi_http["enabled"] = True
    return updated


def run_from_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run material profile sync in small resumable readonly batches.")
    parser.add_argument("--config", default="configs/runtime.example.json")
    parser.add_argument("--request", default="configs/material-profile-backfill-batch.disabled.example.json")
    parser.add_argument("--db", default=None)
    parser.add_argument("--runs-dir", default=None)
    parser.add_argument(
        "--enable-readonly",
        action="store_true",
        help="Temporarily enable readonly OpenAPI requests for this run.",
    )
    args = parser.parse_args(argv)

    config = load_runtime_config(args.config)
    request = load_json(args.request)
    if args.enable_readonly:
        request = _enable_readonly(request)

    cfg = request.get("material_profile_backfill_batch") if isinstance(request.get("material_profile_backfill_batch"), dict) else request
    profile_cfg = cfg.get("material_profile_sync") if isinstance(cfg.get("material_profile_sync"), dict) else {}
    openapi_execute = bool(profile_cfg.get("enabled", False))
    if config.execution_enabled:
        raise RuntimeError("material profile backfill batch requires execution_enabled=false")
    if openapi_execute:
        if not config.external_api_enabled:
            raise RuntimeError("enabled material profile backfill batch requires runtime external_api_enabled=true")
    elif config.external_api_enabled:
        raise RuntimeError("disabled material profile backfill batch requires external_api_enabled=false")

    db_path = args.db or config.database_path
    runs_dir = args.runs_dir or config.runs_dir
    bootstrap_database(db_path)
    transport = None
    if openapi_execute:
        openapi_http = profile_cfg.get("openapi_http") if isinstance(profile_cfg.get("openapi_http"), dict) else {}
        transport = build_http_transport(
            openapi_http,
            response_dir=Path(runs_dir) / "openapi_http" / "material_profile_backfill_batch",
        )

    result = run_material_profile_backfill_batch_request(
        request,
        db_path=db_path,
        runs_dir=runs_dir,
        transport=transport,
    )
    output = {
        "ok": result["ok"],
        "workflow": result["workflow"],
        "phase": result["phase"],
        "execution_enabled": result["execution_enabled"],
        "external_api_calls": result["external_api_calls"],
        "summary": result["summary"],
        "artifact_path": result["artifact_path"],
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


def main() -> int:
    return run_from_args()


if __name__ == "__main__":
    raise SystemExit(main())
