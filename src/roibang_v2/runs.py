from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def write_run_artifact(runs_dir: str | Path, workflow: str, payload: dict[str, Any]) -> Path:
    target_dir = Path(runs_dir) / workflow
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{utc_timestamp()}.json"
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return target
