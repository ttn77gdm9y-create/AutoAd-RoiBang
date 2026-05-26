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

from roibang_v2.workflows.account_remark_update import build_account_remark_update_config


def _split_accounts(value: str) -> list[str]:
    accounts: list[str] = []
    for part in str(value or "").replace("\n", ",").split(","):
        text = part.strip()
        if text:
            accounts.append(text)
    return accounts


def run_from_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build account remark update JSON config.")
    parser.add_argument("--update-id", required=True)
    parser.add_argument("--remark", required=True)
    parser.add_argument("--account", action="append", default=[])
    parser.add_argument("--accounts", default="")
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)

    advertiser_ids = [str(item).strip() for item in args.account if str(item).strip()]
    advertiser_ids.extend(_split_accounts(args.accounts))
    config = build_account_remark_update_config(
        update_id=args.update_id,
        advertiser_ids=advertiser_ids,
        remark=args.remark,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = {
        "ok": True,
        "workflow": "account_remark_update_config",
        "status": "created",
        "summary": {
            "update_id": args.update_id,
            "remark": args.remark,
            "account_count": len(config["account_remark_update"]["advertiser_ids"]),
            "output": str(output),
        },
        "artifact_path": str(output),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    return run_from_args()


if __name__ == "__main__":
    raise SystemExit(main())
