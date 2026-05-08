#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from roibang_v2.scheduler.jobs import load_job_registry
from roibang_v2.scheduler.render import render_scheduler_templates


def render_from_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render RoiBang-v2 scheduler templates without installing them.")
    parser.add_argument("--registry", default="configs/scheduler/roibang-v2.jobs.example.json")
    parser.add_argument("--output-dir", default="scheduler")
    parser.add_argument("--repo-root", default=str(Path.cwd()))
    args = parser.parse_args(argv)

    summary = render_scheduler_templates(
        load_job_registry(args.registry),
        output_dir=args.output_dir,
        repo_root=args.repo_root,
    )
    print(json.dumps({"ok": True, **summary, "output_dir": args.output_dir}, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    return render_from_args()


if __name__ == "__main__":
    raise SystemExit(main())
