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
from roibang_v2.workflows.account_remark_update import run_account_remark_update


def run_from_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run account remark update from JSON config.")
    parser.add_argument("--account-remark-update", required=True)
    parser.add_argument("--config", default="configs/project-update-execute.local.json")
    parser.add_argument("--runs-dir", default=None)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args(argv)

    if args.execute and not args.yes:
        raise RuntimeError("account remark update execute requires --yes")
    if args.execute:
        if not args.config:
            raise RuntimeError("account remark update execute requires --config")
        runtime = load_json(args.config)
        transport_config = runtime.get("create_http_transport") if isinstance(runtime.get("create_http_transport"), dict) else {}
        if not bool(transport_config.get("allow_mutation", False)):
            raise RuntimeError("account remark update execute requires create_http_transport.allow_mutation=true")
    request = load_json(args.account_remark_update)
    result = run_account_remark_update(
        request,
        runs_dir=args.runs_dir or "data/runs",
        execute=bool(args.execute),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if bool(result.get("ok", False)) else 1


def main() -> int:
    return run_from_args()


if __name__ == "__main__":
    raise SystemExit(main())
