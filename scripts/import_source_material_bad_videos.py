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
from roibang_v2.db.bootstrap import bootstrap_database
from roibang_v2.runs import write_run_artifact
from roibang_v2.workflows.source_material_preload_to_accounts import _record_bad_video_ids


def _load_json(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import bad source video_ids from a preload artifact into SQLite.")
    parser.add_argument("--config", default="configs/runtime.example.json")
    parser.add_argument("--artifact", required=True)
    args = parser.parse_args(argv)

    runtime = load_runtime_config(args.config)
    bootstrap_database(runtime.database_path)
    source = _load_json(args.artifact)
    plan = source.get("plan") if isinstance(source.get("plan"), dict) else {}
    product = str(plan.get("product") or "").strip()
    source_advertiser_id = str(plan.get("source_advertiser_id") or "").strip()
    if not product or not source_advertiser_id:
        raise ValueError("artifact plan requires product and source_advertiser_id")
    results = source.get("results") if isinstance(source.get("results"), list) else []
    rows = _record_bad_video_ids(
        db_path=runtime.database_path,
        product=product,
        source_advertiser_id=source_advertiser_id,
        results=[dict(row) for row in results if isinstance(row, dict)],
    )
    payload = {
        "ok": True,
        "workflow": "source_material_bad_video_import",
        "phase": "maintenance",
        "status": "completed",
        "execution_enabled": False,
        "external_api_calls": 0,
        "source_artifact_path": args.artifact,
        "summary": {
            "product": product,
            "source_advertiser_id": source_advertiser_id,
            "bad_video_rows_upserted": rows,
        },
    }
    artifact = write_run_artifact(runtime.runs_dir, "source_material_bad_video_import", payload)
    print(json.dumps({**payload, "artifact_path": str(artifact)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
