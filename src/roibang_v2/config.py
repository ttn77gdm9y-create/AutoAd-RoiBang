from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RuntimeConfig:
    environment: str
    phase: str
    database_path: Path
    runs_dir: Path
    fixtures_dir: Path
    external_api_enabled: bool
    execution_enabled: bool


def load_json(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    with source.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{source} must contain a JSON object")
    return data


def load_runtime_config(path: str | Path) -> RuntimeConfig:
    data = load_json(path)
    return RuntimeConfig(
        environment=str(data["environment"]),
        phase=str(data["phase"]),
        database_path=Path(data["database_path"]),
        runs_dir=Path(data["runs_dir"]),
        fixtures_dir=Path(data["fixtures_dir"]),
        external_api_enabled=bool(data.get("external_api_enabled", False)),
        execution_enabled=bool(data.get("execution_enabled", False)),
    )
