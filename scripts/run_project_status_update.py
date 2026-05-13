#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_shared_run_from_args():
    script_path = Path(__file__).with_name("run_project_update_execute.py")
    spec = importlib.util.spec_from_file_location("run_project_update_execute", script_path)
    module = importlib.util.module_from_spec(spec)
    if spec is None or spec.loader is None:
        raise RuntimeError("failed to load run_project_update_execute.py")
    spec.loader.exec_module(module)
    return module.run_from_args


run_from_args = _load_shared_run_from_args()


def main() -> int:
    return run_from_args()


if __name__ == "__main__":
    raise SystemExit(main())
