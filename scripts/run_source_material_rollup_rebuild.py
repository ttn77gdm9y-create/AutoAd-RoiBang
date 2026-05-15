#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from roibang_v2.config import load_json
from roibang_v2.config import load_runtime_config
from roibang_v2.db.bootstrap import bootstrap_database
from roibang_v2.workflows.product_source_material_rollup import run_product_source_material_rollup_request


def run_from_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Rebuild source-material video performance rollups from local material_daily_metrics."
    )
    parser.add_argument("--config", default="configs/runtime.example.json")
    parser.add_argument("--request", default="configs/product-source-material-rollup.example.json")
    parser.add_argument("--db", default=None)
    parser.add_argument("--runs-dir", default=None)
    args = parser.parse_args(argv)

    config = load_runtime_config(args.config)
    if config.external_api_enabled or config.execution_enabled:
        raise RuntimeError("source material rollup rebuild requires external_api_enabled=false and execution_enabled=false")

    request = load_json(args.request)
    db_path = args.db or config.database_path
    runs_dir = args.runs_dir or config.runs_dir
    bootstrap_database(db_path)
    result = run_product_source_material_rollup_request(request, db_path=db_path, runs_dir=runs_dir)
    output = {
        "ok": result["ok"],
        "workflow": "source_material_rollup_rebuild",
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
