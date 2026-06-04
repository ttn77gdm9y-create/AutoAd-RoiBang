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

from roibang_v2.config import load_runtime_config
from roibang_v2.workflows.gravity_token_refresh import run_gravity_token_refresh


def run_from_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Refresh Gravity Engine token with a fixed headless browser workflow.")
    parser.add_argument("--config", default="configs/runtime.example.json")
    parser.add_argument("--auth-file", default="data/gravity_token.json")
    parser.add_argument("--username-env", default="GRAVITY_USERNAME")
    parser.add_argument("--password-env", default="GRAVITY_PASSWORD")
    parser.add_argument("--login-url", default="")
    parser.add_argument("--capture-url", default="")
    args = parser.parse_args(argv)

    config = load_runtime_config(args.config)
    request = {
        "auth_file": args.auth_file,
        "username_env": args.username_env,
        "password_env": args.password_env,
        "login_url": args.login_url,
        "capture_url": args.capture_url,
    }
    result = run_gravity_token_refresh(request, runs_dir=config.runs_dir)
    print(
        json.dumps(
            {
                "ok": result["ok"],
                "workflow": result["workflow"],
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
