#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from _repo_bootstrap import bootstrap_project_root

bootstrap_project_root()

from roibang_v2.config import load_json
from roibang_v2.config import load_runtime_config
from roibang_v2.db.bootstrap import bootstrap_database
from roibang_v2.workflows.ai_create_template_drafts import run_ai_create_template_drafts_request


def run_from_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate AI create-template draft JSON from local data without changing manual templates."
    )
    parser.add_argument("--config", default="configs/runtime.example.json")
    parser.add_argument("--request", default="configs/ai-create-template-drafts/example.json")
    parser.add_argument("--db", default=None)
    parser.add_argument("--runs-dir", default=None)
    args = parser.parse_args(argv)

    config = load_runtime_config(args.config)
    if config.external_api_enabled or config.execution_enabled:
        raise RuntimeError("AI create-template drafts require external_api_enabled=false and execution_enabled=false")

    request = load_json(args.request)
    db_path = args.db or config.database_path
    runs_dir = args.runs_dir or config.runs_dir
    bootstrap_database(db_path)
    result = run_ai_create_template_drafts_request(request, db_path=db_path, runs_dir=runs_dir)
    output = {
        "ok": result["ok"],
        "workflow": result["workflow"],
        "phase": result["phase"],
        "execution_enabled": result["execution_enabled"],
        "external_api_calls": result["external_api_calls"],
        "status": result["status"],
        "summary": result["summary"],
        "blocking_reasons": result["blocking_reasons"],
        "artifact_path": result["artifact_path"],
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


def main() -> int:
    return run_from_args()


if __name__ == "__main__":
    raise SystemExit(main())
