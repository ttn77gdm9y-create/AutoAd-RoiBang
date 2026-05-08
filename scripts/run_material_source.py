#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from roibang_v2.config import load_json, load_runtime_config
from roibang_v2.db.bootstrap import bootstrap_database
from roibang_v2.fetch.openapi_http import build_http_transport
from roibang_v2.workflows.material_source import run_material_source_request


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Phase 1 product source material planning.")
    parser.add_argument("--config", default="configs/runtime.example.json")
    parser.add_argument("--request", default="configs/material-source.example.json")
    parser.add_argument("--db", default=None)
    parser.add_argument("--runs-dir", default=None)
    parser.add_argument("--preflight", action="store_true")
    args = parser.parse_args()

    config = load_runtime_config(args.config)
    request = load_json(args.request)
    cfg = request.get("material_source") if isinstance(request.get("material_source"), dict) else request
    kind = str(cfg.get("kind") or "local_product_source")
    openapi_enabled = kind == "openapi_source_materials" and bool(cfg.get("enabled", False))
    openapi_execute = openapi_enabled and not args.preflight
    if config.execution_enabled:
        raise RuntimeError("Phase 1 material source requires execution_enabled=false")
    if openapi_execute and not config.external_api_enabled:
        raise RuntimeError("openapi_source_materials enabled requires runtime external_api_enabled=true")
    if not openapi_execute and not args.preflight and config.external_api_enabled:
        raise RuntimeError("disabled/local Phase 1 material source requires external_api_enabled=false")

    db_path = args.db or config.database_path
    runs_dir = args.runs_dir or config.runs_dir
    bootstrap_database(db_path)
    transport = None
    if openapi_execute:
        openapi_http = cfg.get("openapi_http") if isinstance(cfg.get("openapi_http"), dict) else {}
        transport = build_http_transport(openapi_http, response_dir=Path(runs_dir) / "openapi_http" / "material_source")
    result = run_material_source_request(
        {**request, "material_source": {**cfg, "enabled": False}} if args.preflight and kind == "openapi_source_materials" else request,
        db_path=db_path,
        runs_dir=runs_dir,
        transport=transport,
    )
    print(
        json.dumps(
            {
                "ok": result["ok"],
                "workflow": result["workflow"],
                "phase": result["phase"],
                "execution_enabled": result["execution_enabled"],
                "external_api_calls": result["external_api_calls"],
                "summary": result.get("summary") or result.get("preflight", {}).get("summary") or {},
                "artifact_path": result["artifact_path"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
