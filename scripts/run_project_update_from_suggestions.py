#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from roibang_v2.workflows.project_update_from_suggestions import run_project_update_from_suggestions_request


def _parse_account_names(values: list[str]) -> dict[str, str]:
    names: dict[str, str] = {}
    for value in values:
        account_id, separator, account_name = value.partition("=")
        account_id = account_id.strip()
        account_name = account_name.strip()
        if separator and account_id and account_name:
            names[account_id] = account_name
    return names


def run_from_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build project_update.json from readonly control suggestions.")
    parser.add_argument("--suggestions-artifact", required=True)
    parser.add_argument("--project-update-id", required=True)
    parser.add_argument("--operator", default="")
    parser.add_argument("--product-key", default="")
    parser.add_argument("--product-name", default="")
    parser.add_argument("--allowed-target-accounts-path", default="")
    parser.add_argument(
        "--suggestion-id",
        action="append",
        default=[],
        help="Only convert these suggestion_id values.",
    )
    parser.add_argument(
        "--suggested-action",
        action="append",
        default=[],
        help="Only convert these suggested_action values, for example suggest_delete_project.",
    )
    parser.add_argument(
        "--account-name",
        action="append",
        default=[],
        help="Account display name in advertiser_id=账户名 format. Used only for JSON summaries.",
    )
    parser.add_argument("--output", required=True)
    parser.add_argument("--runs-dir", default="data/runs")
    args = parser.parse_args(argv)

    result = run_project_update_from_suggestions_request(
        {
            "suggestions_artifact_path": args.suggestions_artifact,
            "project_update_id": args.project_update_id,
            "operator": args.operator,
            "product_key": args.product_key,
            "product_name": args.product_name,
            "allowed_target_accounts_path": args.allowed_target_accounts_path,
            "selected_suggestion_ids": args.suggestion_id,
            "suggested_actions": args.suggested_action,
            "account_names": _parse_account_names(args.account_name),
            "output_path": args.output,
        },
        runs_dir=args.runs_dir,
    )
    print(
        json.dumps(
            {
                "ok": result["ok"],
                "workflow": result["workflow"],
                "phase": result["phase"],
                "execution_enabled": result["execution_enabled"],
                "external_api_calls": result["external_api_calls"],
                "summary": result["summary"],
                "project_update_path": result["project_update_path"],
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
