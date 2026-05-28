from __future__ import annotations

import os

import uvicorn


if __name__ == "__main__":
    reload_enabled = os.environ.get("ROIBANG_API_RELOAD", "1") != "0"
    uvicorn.run("backend.app.main:app", host="127.0.0.1", port=8000, reload=reload_enabled)
