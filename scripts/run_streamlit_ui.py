#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from _repo_bootstrap import bootstrap_project_root

PROJECT_ROOT = bootstrap_project_root()


def _streamlit_available() -> bool:
    return importlib.util.find_spec("streamlit") is not None


def run_from_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Start RoiBang-v2 Streamlit local UI.")
    parser.add_argument("--ui-config", default="configs/ui/streamlit-v0.example.json")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default="8501")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    if not _streamlit_available():
        print("Streamlit（网页面板依赖）未安装。安装后再运行：python3 -m pip install streamlit")
        return 1
    if args.check:
        print("ok: Streamlit（网页面板依赖）可用")
        return 0

    command = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        "app/streamlit_app.py",
        "--server.address",
        str(args.host),
        "--server.port",
        str(args.port),
        "--server.headless",
        "true",
        "--browser.gatherUsageStats",
        "false",
        "--",
        "--ui-config",
        str(args.ui_config),
    ]
    print(f"starting Streamlit（网页面板）: http://{args.host}:{args.port}")
    return subprocess.call(command, cwd=str(PROJECT_ROOT))


def main() -> int:
    return run_from_args()


if __name__ == "__main__":
    raise SystemExit(main())
