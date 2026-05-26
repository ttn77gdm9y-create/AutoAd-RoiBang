#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from roibang_v2.config import load_json
from roibang_v2.workflows.artifact_feishu_delivery import deliver_artifact_to_feishu, format_artifact_feishu_message


def run_from_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Push a RoiBang JSON artifact summary to Feishu.")
    parser.add_argument("--artifact", required=True, help="JSON artifact path.")
    parser.add_argument("--feishu-runtime-file", default="data/secrets/feishu.runtime.local.json")
    parser.add_argument("--print-message-only", action="store_true")
    args = parser.parse_args(argv)

    artifact_path = Path(args.artifact)
    artifact = load_json(artifact_path)
    if args.print_message_only:
        print(format_artifact_feishu_message(artifact, artifact_path=str(artifact_path)))
        return 0
    delivery = deliver_artifact_to_feishu(
        artifact,
        artifact_path=artifact_path,
        runtime_file=args.feishu_runtime_file,
    )
    print(json.dumps({"ok": bool(delivery.get("ok", False)), "delivery": {"feishu": delivery}}, ensure_ascii=False, indent=2))
    return 0 if bool(delivery.get("ok", False)) else 1


def main() -> int:
    return run_from_args()


if __name__ == "__main__":
    raise SystemExit(main())
