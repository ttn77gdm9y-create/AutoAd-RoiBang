#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os

from roibang_v2.integrations.oceanengine.tokens import refresh_access_token


def _arg_or_env(value: str | None, env_name: str) -> str:
    return str(value or os.environ.get(env_name, "")).strip()


def run_from_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Refresh RoiBang-v2 OceanEngine access token.")
    parser.add_argument("--store-file", default="data/secrets/oceanengine-tokens.local.json")
    parser.add_argument("--user-id", default="default")
    parser.add_argument("--app-id", default=None)
    parser.add_argument("--app-secret", default=None)
    parser.add_argument("--timeout-seconds", type=float, default=20)
    args = parser.parse_args(argv)

    app_id = _arg_or_env(args.app_id, "OCEANENGINE_APP_ID")
    app_secret = _arg_or_env(args.app_secret, "OCEANENGINE_APP_SECRET")
    if not app_id:
        raise RuntimeError("OceanEngine app id is required via --app-id or OCEANENGINE_APP_ID")
    if not app_secret:
        raise RuntimeError("OceanEngine app secret is required via --app-secret or OCEANENGINE_APP_SECRET")

    result = refresh_access_token(
        store_file=args.store_file,
        user_id=args.user_id,
        app_id=app_id,
        app_secret=app_secret,
        timeout_seconds=args.timeout_seconds,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    return run_from_args()


if __name__ == "__main__":
    raise SystemExit(main())
