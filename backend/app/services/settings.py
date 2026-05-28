from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppSettings:
    project_root: Path
    runs_dir: Path
    configs_dir: Path
    streamlit_status: str = "legacy_retained"


def build_settings(project_root: str | Path | None = None) -> AppSettings:
    root = Path(project_root or Path(__file__).resolve().parents[3]).resolve()
    return AppSettings(
        project_root=root,
        runs_dir=root / "data" / "runs",
        configs_dir=root / "configs",
    )
