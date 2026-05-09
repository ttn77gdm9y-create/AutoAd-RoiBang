#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from roibang_v2.workflows.create_phase2_yzt_local_config_prepare import (
    DEFAULT_EXAMPLE_CONFIG,
    DEFAULT_LOCAL_CONFIG,
    prepare_yzt_local_preview_config,
)


def run_from_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare local-only Phase 2 勇者突进 preview config.")
    parser.add_argument("--example-config", default=str(DEFAULT_EXAMPLE_CONFIG))
    parser.add_argument("--local-config", default=str(DEFAULT_LOCAL_CONFIG))
    args = parser.parse_args(argv)

    result = prepare_yzt_local_preview_config(
        example_path=args.example_config,
        local_path=args.local_config,
    )
    print(
        json.dumps(
            {
                "ok": result["ok"],
                "workflow": result["workflow"],
                "phase": result["phase"],
                "execution_enabled": result["execution_enabled"],
                "external_api_calls": result["external_api_calls"],
                "status": result["status"],
                "summary": result["summary"],
                "safety_notes": result["safety_notes"],
                "operator_guide": result["operator_guide"],
                "violations": result["violations"],
                "human_next_steps": result["human_next_steps"],
                "actions": result["actions"],
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
