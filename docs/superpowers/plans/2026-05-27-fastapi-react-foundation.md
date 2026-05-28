# FastAPI React Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立 FastAPI + React 新系统第一阶段基础框架，使日常入口不再依赖 Streamlit：能打开 React 页面、读取最新 artifact、用中文摘要展示 JSON、查看任务中心，并通过后端 allowlist 启动固定脚本 dry-run 任务。

**Architecture:** React 前端只调用 `/api/*`；FastAPI 后端只做本地编排、读取文件、生成中文摘要、启动固定脚本。真实业务动作仍然只能通过固定脚本和 `data/runs/frontend_tasks/` task artifact 执行。第一阶段不改现有业务脚本语义，不删除 Streamlit，不把 token 或平台 API 暴露给前端。

**Tech Stack:** Python 3.11, FastAPI, Pydantic, Uvicorn, pytest, React, TypeScript, Vite, Ant Design, TanStack Query, existing `src/roibang_v2` workflows and `scripts/run_frontend_task.py`.

---

## File Structure

- Create: `backend/app/main.py`
- Create: `backend/app/api/health.py`
- Create: `backend/app/api/workflows.py`
- Create: `backend/app/api/tasks.py`
- Create: `backend/app/api/actions.py`
- Create: `backend/app/api/accounts.py`
- Create: `backend/app/schemas/common.py`
- Create: `backend/app/services/settings.py`
- Create: `backend/app/services/artifacts.py`
- Create: `backend/app/services/tasks.py`
- Create: `backend/app/services/script_registry.py`
- Create: `backend/app/services/summary_builder.py`
- Create: `backend/tests/test_api_foundation.py`
- Create: `backend/tests/test_script_registry.py`
- Modify: `requirements-ui.txt`
- Create: `frontend/package.json`
- Create: `frontend/index.html`
- Create: `frontend/vite.config.ts`
- Create: `frontend/tsconfig.json`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/app/App.tsx`
- Create: `frontend/src/app/routes.tsx`
- Create: `frontend/src/api/client.ts`
- Create: `frontend/src/types/api.ts`
- Create: `frontend/src/components/SummaryPanel.tsx`
- Create: `frontend/src/components/RawJsonDrawer.tsx`
- Create: `frontend/src/components/ConfirmExecutePanel.tsx`
- Create: `frontend/src/pages/DashboardPage.tsx`
- Create: `frontend/src/pages/AccountsPage.tsx`
- Create: `frontend/src/pages/TasksPage.tsx`
- Create: `frontend/src/pages/ResultsPage.tsx`
- Create: `frontend/src/pages/SystemSettingsPage.tsx`
- Create: `frontend/src/styles.css`
- Create: `scripts/run_fastapi_backend.py`
- Create: `scripts/run_react_frontend.sh`
- Create: `scripts/run_new_ui_dev.sh`

---

## Task 1: FastAPI App Shell

**Files:**
- Create: `backend/app/main.py`
- Create: `backend/app/api/health.py`
- Create: `backend/app/api/workflows.py`
- Create: `backend/app/api/tasks.py`
- Create: `backend/app/api/actions.py`
- Create: `backend/app/api/accounts.py`
- Create: `backend/app/services/settings.py`
- Create: `backend/tests/test_api_foundation.py`
- Modify: `requirements-ui.txt`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_api_foundation.py`:

```python
from fastapi.testclient import TestClient

from backend.app.main import create_app


def test_health_endpoint_returns_ok(tmp_path):
    app = create_app(project_root=tmp_path)
    client = TestClient(app)

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_settings_endpoint_exposes_local_paths(tmp_path):
    app = create_app(project_root=tmp_path)
    client = TestClient(app)

    response = client.get("/api/settings")

    assert response.status_code == 200
    payload = response.json()
    assert payload["project_root"] == str(tmp_path)
    assert payload["runs_dir"].endswith("data/runs")
    assert payload["streamlit_status"] == "legacy_retained"
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
PYTHONPATH=.:src python3 -m pytest backend/tests/test_api_foundation.py -q
```

Expected: FAIL because `backend.app.main` does not exist.

- [ ] **Step 3: Add dependencies**

Append to `requirements-ui.txt`:

```text
fastapi>=0.111,<1
uvicorn[standard]>=0.30,<1
python-multipart>=0.0.9,<1
```

- [ ] **Step 4: Implement app factory and settings service**

Implement `backend/app/services/settings.py`:

```python
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
```

Implement `backend/app/main.py`:

```python
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api import accounts, actions, health, tasks, workflows
from backend.app.services.settings import build_settings


def create_app(project_root: str | Path | None = None) -> FastAPI:
    settings = build_settings(project_root)
    app = FastAPI(title="RoiBang Local API", version="0.1.0")
    app.state.settings = settings
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router, prefix="/api")
    app.include_router(workflows.router, prefix="/api")
    app.include_router(tasks.router, prefix="/api")
    app.include_router(actions.router, prefix="/api")
    app.include_router(accounts.router, prefix="/api")
    return app


app = create_app()
```

Implement `backend/app/api/health.py`:

```python
from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/settings")
def settings(request: Request) -> dict[str, str]:
    value = request.app.state.settings
    return {
        "project_root": str(value.project_root),
        "runs_dir": str(value.runs_dir),
        "configs_dir": str(value.configs_dir),
        "streamlit_status": value.streamlit_status,
    }
```

Create empty router placeholders with `router = APIRouter()` in:
- `backend/app/api/workflows.py`
- `backend/app/api/tasks.py`
- `backend/app/api/actions.py`
- `backend/app/api/accounts.py`

- [ ] **Step 5: Run tests to verify GREEN**

Run:

```bash
PYTHONPATH=.:src python3 -m pytest backend/tests/test_api_foundation.py -q
```

Expected: PASS.

---

## Task 2: Chinese Summary Builder

**Files:**
- Create: `backend/app/schemas/common.py`
- Create: `backend/app/services/summary_builder.py`
- Modify: `backend/tests/test_api_foundation.py`

- [ ] **Step 1: Add failing tests**

Append to `backend/tests/test_api_foundation.py`:

```python
from backend.app.services.summary_builder import build_json_summary


def test_build_json_summary_prefers_chinese_business_fields():
    payload = {
        "workflow": "site_status_update",
        "status": "completed",
        "ok": True,
        "summary": {"target_site_count": 1, "success_count": 1, "failure_count": 0},
        "actions": [
            {"advertiser_id": "1866125088740552", "site_id": "7644466520214601766", "status": "DELETED"}
        ],
    }

    result = build_json_summary("落地页删除结果", payload)

    assert result["summary"]["title"] == "落地页删除结果"
    assert result["summary"]["status"] == "completed"
    assert {"label": "成功数", "value": 1} in result["summary"]["items"]
    assert result["table"]["columns"] == ["账户 ID", "落地页 ID", "状态"]
    assert result["table"]["rows"][0]["落地页 ID"] == "7644466520214601766"
    assert result["raw"] == payload
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
PYTHONPATH=.:src python3 -m pytest backend/tests/test_api_foundation.py -q
```

Expected: FAIL because `summary_builder.py` does not exist.

- [ ] **Step 3: Implement summary schema and builder**

Implement `backend/app/schemas/common.py`:

```python
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SummaryItem(BaseModel):
    label: str
    value: Any


class ChineseSummary(BaseModel):
    title: str
    status: str = "unknown"
    risk_level: str = "low"
    execution_enabled: bool = False
    items: list[SummaryItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    blocking_reasons: list[str] = Field(default_factory=list)


class ChineseTable(BaseModel):
    columns: list[str] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)


class ChineseResult(BaseModel):
    summary: ChineseSummary
    table: ChineseTable
    artifact_path: str = ""
    raw: dict[str, Any] = Field(default_factory=dict)
```

Implement `backend/app/services/summary_builder.py`:

```python
from __future__ import annotations

from typing import Any


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def build_json_summary(title: str, payload: dict[str, Any], *, artifact_path: str = "") -> dict[str, Any]:
    summary = _dict(payload.get("summary"))
    status = str(payload.get("status") or summary.get("status") or "unknown")
    items = []
    mapping = [
        ("目标数", "target_site_count"),
        ("成功数", "success_count"),
        ("失败数", "failure_count"),
        ("账户数", "account_count"),
        ("项目数", "project_count"),
        ("任务数", "task_count"),
    ]
    for label, key in mapping:
        if key in summary:
            items.append({"label": label, "value": summary[key]})
    actions = _list(payload.get("actions"))
    rows = []
    for action in actions[:200]:
        row = _dict(action)
        if row:
            rows.append({
                "账户 ID": str(row.get("advertiser_id") or ""),
                "落地页 ID": str(row.get("site_id") or row.get("orange_site_id") or ""),
                "状态": str(row.get("status") or row.get("target_status") or ""),
            })
    table = {"columns": ["账户 ID", "落地页 ID", "状态"] if rows else [], "rows": rows}
    warnings = [str(item) for item in _list(payload.get("warnings") or summary.get("warnings"))]
    blocking = [str(item) for item in _list(payload.get("blocking_reasons") or summary.get("blocking_reasons"))]
    return {
        "summary": {
            "title": title,
            "status": status,
            "risk_level": "high" if blocking else "low",
            "execution_enabled": False,
            "items": items,
            "warnings": warnings,
            "blocking_reasons": blocking,
        },
        "table": table,
        "artifact_path": artifact_path or str(payload.get("artifact_path") or ""),
        "raw": payload,
    }
```

- [ ] **Step 4: Run tests to verify GREEN**

Run:

```bash
PYTHONPATH=.:src python3 -m pytest backend/tests/test_api_foundation.py -q
```

Expected: PASS.

---

## Task 3: Workflow Latest Artifact API

**Files:**
- Create: `backend/app/services/artifacts.py`
- Modify: `backend/app/api/workflows.py`
- Modify: `backend/tests/test_api_foundation.py`

- [ ] **Step 1: Add failing tests**

Append to `backend/tests/test_api_foundation.py`:

```python
import json


def test_latest_workflow_endpoint_returns_chinese_summary(tmp_path):
    artifact_dir = tmp_path / "data" / "runs" / "site_status_update"
    artifact_dir.mkdir(parents=True)
    artifact = artifact_dir / "20260527T124459Z.json"
    artifact.write_text(
        json.dumps(
            {
                "workflow": "site_status_update",
                "status": "completed",
                "summary": {"target_site_count": 1, "success_count": 1, "failure_count": 0},
                "actions": [{"advertiser_id": "1866125088740552", "site_id": "7644466520214601766", "status": "DELETED"}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    app = create_app(project_root=tmp_path)
    client = TestClient(app)

    response = client.get("/api/workflows/latest", params={"workflow": "site_status_update"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "site_status_update 最新结果"
    assert payload["summary"]["items"][1] == {"label": "成功数", "value": 1}
    assert payload["table"]["rows"][0]["账户 ID"] == "1866125088740552"
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
PYTHONPATH=.:src python3 -m pytest backend/tests/test_api_foundation.py -q
```

Expected: FAIL because endpoint is missing.

- [ ] **Step 3: Implement artifact lookup**

Implement `backend/app/services/artifacts.py`:

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def find_latest_artifact(runs_dir: str | Path, workflow: str) -> Path | None:
    base = Path(runs_dir) / workflow
    if not base.exists():
        return None
    candidates = sorted(path for path in base.glob("*.json") if path.name != "latest.json")
    if not candidates:
        latest = base / "latest.json"
        return latest if latest.exists() else None
    return candidates[-1]


def read_json(path: str | Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}
```

Implement `backend/app/api/workflows.py`:

```python
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from backend.app.services.artifacts import find_latest_artifact, read_json
from backend.app.services.summary_builder import build_json_summary

router = APIRouter()


@router.get("/workflows/latest")
def latest_workflow(request: Request, workflow: str) -> dict:
    settings = request.app.state.settings
    path = find_latest_artifact(settings.runs_dir, workflow)
    if path is None:
        raise HTTPException(status_code=404, detail=f"未找到 workflow: {workflow}")
    payload = read_json(path)
    return build_json_summary(f"{workflow} 最新结果", payload, artifact_path=str(path))
```

- [ ] **Step 4: Run tests to verify GREEN**

Run:

```bash
PYTHONPATH=.:src python3 -m pytest backend/tests/test_api_foundation.py -q
```

Expected: PASS.

---

## Task 4: Task Center API

**Files:**
- Create: `backend/app/services/tasks.py`
- Modify: `backend/app/api/tasks.py`
- Modify: `backend/tests/test_api_foundation.py`

- [ ] **Step 1: Add failing tests**

Append to `backend/tests/test_api_foundation.py`:

```python
def test_tasks_endpoint_lists_frontend_tasks(tmp_path):
    task_dir = tmp_path / "data" / "runs" / "frontend_tasks"
    task_dir.mkdir(parents=True)
    task = task_dir / "frontend-1.json"
    task.write_text(
        json.dumps(
            {
                "task_id": "frontend-1",
                "operation_type": "dry_run_probe",
                "status": "completed",
                "created_at": "2026-05-27T12:00:00+08:00",
                "updated_at": "2026-05-27T12:01:00+08:00",
                "return_code": 0,
                "stdout_path": "frontend_tasks/frontend-1.stdout.log",
                "stderr_path": "frontend_tasks/frontend-1.stderr.log",
                "result": {"ok": True},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    app = create_app(project_root=tmp_path)
    client = TestClient(app)

    response = client.get("/api/tasks")

    assert response.status_code == 200
    rows = response.json()["items"]
    assert rows[0]["task_id"] == "frontend-1"
    assert rows[0]["operation_type"] == "dry_run_probe"


def test_task_detail_endpoint_returns_stdout_stderr_paths(tmp_path):
    task_dir = tmp_path / "data" / "runs" / "frontend_tasks"
    task_dir.mkdir(parents=True)
    (task_dir / "frontend-1.stdout.log").write_text("hello", encoding="utf-8")
    (task_dir / "frontend-1.stderr.log").write_text("", encoding="utf-8")
    (task_dir / "frontend-1.json").write_text(
        json.dumps({"task_id": "frontend-1", "status": "completed", "stdout_path": "frontend_tasks/frontend-1.stdout.log", "stderr_path": "frontend_tasks/frontend-1.stderr.log"}),
        encoding="utf-8",
    )
    app = create_app(project_root=tmp_path)
    client = TestClient(app)

    response = client.get("/api/tasks/frontend-1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["task"]["task_id"] == "frontend-1"
    assert payload["stdout"] == "hello"
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
PYTHONPATH=.:src python3 -m pytest backend/tests/test_api_foundation.py -q
```

Expected: FAIL because endpoints are missing.

- [ ] **Step 3: Implement task service and API**

Implement `backend/app/services/tasks.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.app.services.artifacts import read_json


def list_tasks(runs_dir: str | Path) -> list[dict[str, Any]]:
    task_dir = Path(runs_dir) / "frontend_tasks"
    rows = []
    for path in sorted(task_dir.glob("frontend-*.json"), reverse=True):
        payload = read_json(path)
        if payload:
            rows.append({
                "task_id": str(payload.get("task_id") or path.stem),
                "operation_type": str(payload.get("operation_type") or ""),
                "status": str(payload.get("status") or ""),
                "created_at": str(payload.get("created_at") or ""),
                "updated_at": str(payload.get("updated_at") or ""),
                "return_code": payload.get("return_code"),
                "artifact_path": str(payload.get("artifact_path") or path),
            })
    return rows


def load_task_detail(runs_dir: str | Path, task_id: str) -> dict[str, Any]:
    base = Path(runs_dir)
    payload = read_json(base / "frontend_tasks" / f"{task_id}.json")
    if not payload:
        return {}
    stdout = _read_text(base / str(payload.get("stdout_path") or ""))
    stderr = _read_text(base / str(payload.get("stderr_path") or ""))
    return {"task": payload, "stdout": stdout, "stderr": stderr}


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""
```

Implement `backend/app/api/tasks.py`:

```python
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from backend.app.services.tasks import list_tasks, load_task_detail

router = APIRouter()


@router.get("/tasks")
def tasks(request: Request) -> dict:
    return {"items": list_tasks(request.app.state.settings.runs_dir)}


@router.get("/tasks/{task_id}")
def task_detail(request: Request, task_id: str) -> dict:
    detail = load_task_detail(request.app.state.settings.runs_dir, task_id)
    if not detail:
        raise HTTPException(status_code=404, detail=f"未找到任务: {task_id}")
    return detail
```

- [ ] **Step 4: Run tests to verify GREEN**

Run:

```bash
PYTHONPATH=.:src python3 -m pytest backend/tests/test_api_foundation.py -q
```

Expected: PASS.

---

## Task 5: Fixed Script Registry And Dry-Run Action

**Files:**
- Create: `backend/app/services/script_registry.py`
- Modify: `backend/app/api/actions.py`
- Create: `backend/tests/test_script_registry.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_script_registry.py`:

```python
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.services.script_registry import build_action_task


def test_build_action_task_rejects_unknown_action(tmp_path):
    result = build_action_task("unknown", {}, project_root=tmp_path)

    assert result["ok"] is False
    assert "不在固定脚本白名单" in result["summary"]["blocking_reasons"][0]


def test_build_action_task_creates_probe_task_without_shell_string(tmp_path):
    result = build_action_task("dry_run_probe", {"message": "hello"}, project_root=tmp_path)

    assert result["ok"] is True
    assert result["task"]["operation_type"] == "dry_run_probe"
    assert result["task"]["command"][:2] == ["python3", "-c"]
    assert isinstance(result["task"]["command"], list)


def test_action_execute_requires_confirmation(tmp_path):
    app = create_app(project_root=tmp_path)
    client = TestClient(app)

    response = client.post("/api/actions/dry_run_probe/execute", json={"confirmation": "错了", "request": {"message": "hello"}})

    assert response.status_code == 400
    assert "确认执行" in response.json()["detail"]
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
PYTHONPATH=.:src python3 -m pytest backend/tests/test_script_registry.py -q
```

Expected: FAIL because `script_registry.py` does not exist.

- [ ] **Step 3: Implement allowlist builder**

Implement `backend/app/services/script_registry.py`:

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from roibang_v2.ui.background_tasks import build_task_record, build_runner_command, start_runner, write_task_record


def build_action_task(action: str, request: dict[str, Any], *, project_root: str | Path) -> dict[str, Any]:
    root = Path(project_root)
    runs_dir = root / "data" / "runs"
    if action != "dry_run_probe":
        return {
            "ok": False,
            "summary": {
                "title": "固定脚本执行预览",
                "status": "blocked",
                "risk_level": "high",
                "execution_enabled": False,
                "items": [{"label": "动作", "value": action}],
                "warnings": [],
                "blocking_reasons": [f"动作 {action} 不在固定脚本白名单中"],
            },
            "table": {"columns": [], "rows": []},
            "raw": {"action": action, "request": request},
        }
    message = str(request.get("message") or "dry-run-ok")
    code = "import json,sys; print(json.dumps({'ok': True, 'status': 'completed', 'message': sys.argv[1]}, ensure_ascii=False))"
    task = build_task_record(
        runs_dir=runs_dir,
        operation_type="dry_run_probe",
        command=["python3", "-c", code, message],
        cwd=str(root),
        request=request,
    )
    return {
        "ok": True,
        "summary": {
            "title": "固定脚本 dry-run 预览",
            "status": "planned",
            "risk_level": "low",
            "execution_enabled": True,
            "items": [{"label": "动作", "value": "dry_run_probe"}, {"label": "消息", "value": message}],
            "warnings": [],
            "blocking_reasons": [],
        },
        "table": {"columns": ["动作", "消息"], "rows": [{"动作": "dry_run_probe", "消息": message}]},
        "task": task,
        "raw": {"action": action, "request": request},
    }


def start_action_task(project_root: str | Path, task: dict[str, Any]) -> dict[str, Any]:
    runs_dir = Path(project_root) / "data" / "runs"
    task_path = write_task_record(runs_dir, task)
    pid = start_runner(build_runner_command(task_path), cwd=project_root)
    task["pid"] = pid
    write_task_record(runs_dir, task)
    return {"task_id": task["task_id"], "pid": pid, "artifact_path": str(task_path)}
```

Implement `backend/app/api/actions.py`:

```python
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.app.services.script_registry import build_action_task, start_action_task

router = APIRouter()


class ActionPreviewRequest(BaseModel):
    request: dict[str, Any] = Field(default_factory=dict)


class ActionExecuteRequest(BaseModel):
    confirmation: str
    request: dict[str, Any] = Field(default_factory=dict)


@router.post("/actions/{action}/preview")
def action_preview(request: Request, action: str, body: ActionPreviewRequest) -> dict:
    return build_action_task(action, body.request, project_root=request.app.state.settings.project_root)


@router.post("/actions/{action}/execute")
def action_execute(request: Request, action: str, body: ActionExecuteRequest) -> dict:
    if body.confirmation != "确认执行":
        raise HTTPException(status_code=400, detail="真实执行前必须输入：确认执行")
    preview = build_action_task(action, body.request, project_root=request.app.state.settings.project_root)
    if not preview.get("ok"):
        raise HTTPException(status_code=400, detail=preview["summary"]["blocking_reasons"][0])
    started = start_action_task(request.app.state.settings.project_root, preview["task"])
    return {
        "summary": preview["summary"],
        "table": preview["table"],
        "task": started,
        "raw": {"preview": preview, "started": started},
    }
```

- [ ] **Step 4: Run registry tests**

Run:

```bash
PYTHONPATH=.:src python3 -m pytest backend/tests/test_script_registry.py -q
```

Expected: PASS.

---

## Task 6: Account Store Skeleton

**Files:**
- Modify: `backend/app/api/accounts.py`
- Modify: `backend/tests/test_api_foundation.py`
- Create directory/file on demand: `configs/accounts/product-accounts.local.json`

- [ ] **Step 1: Add failing tests**

Append to `backend/tests/test_api_foundation.py`:

```python
def test_accounts_endpoint_reads_product_account_store(tmp_path):
    account_dir = tmp_path / "configs" / "accounts"
    account_dir.mkdir(parents=True)
    (account_dir / "product-accounts.local.json").write_text(
        json.dumps(
            {
                "accounts": [
                    {
                        "product_key": "diandian-hero",
                        "product_name": "点点英雄",
                        "advertiser_id": "1866125088740552",
                        "advertiser_name": "黑旗游戏",
                        "channel": "微信",
                        "owner": "运营A",
                        "account_remark": "点点英雄-黑旗",
                        "status": "active",
                        "notes": "",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    app = create_app(project_root=tmp_path)
    client = TestClient(app)

    response = client.get("/api/accounts")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["items"][0] == {"label": "账户数", "value": 1}
    assert payload["table"]["rows"][0]["产品"] == "点点英雄"
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
PYTHONPATH=.:src python3 -m pytest backend/tests/test_api_foundation.py -q
```

Expected: FAIL because `/api/accounts` has no implementation.

- [ ] **Step 3: Implement read-only account list**

Implement `backend/app/api/accounts.py`:

```python
from __future__ import annotations

from fastapi import APIRouter, Request

from backend.app.services.artifacts import read_json

router = APIRouter()


@router.get("/accounts")
def accounts(request: Request) -> dict:
    path = request.app.state.settings.configs_dir / "accounts" / "product-accounts.local.json"
    payload = read_json(path)
    accounts_list = payload.get("accounts") if isinstance(payload.get("accounts"), list) else []
    rows = [
        {
            "产品": str(row.get("product_name") or ""),
            "产品 Key": str(row.get("product_key") or ""),
            "账户 ID": str(row.get("advertiser_id") or ""),
            "账户名": str(row.get("advertiser_name") or ""),
            "渠道": str(row.get("channel") or ""),
            "负责人": str(row.get("owner") or ""),
            "状态": str(row.get("status") or ""),
            "备注": str(row.get("account_remark") or ""),
        }
        for row in accounts_list
        if isinstance(row, dict)
    ]
    return {
        "summary": {
            "title": "产品账户库",
            "status": "loaded",
            "risk_level": "low",
            "execution_enabled": False,
            "items": [{"label": "账户数", "value": len(rows)}],
            "warnings": [],
            "blocking_reasons": [],
        },
        "table": {
            "columns": ["产品", "产品 Key", "账户 ID", "账户名", "渠道", "负责人", "状态", "备注"],
            "rows": rows,
        },
        "artifact_path": str(path),
        "raw": payload,
    }
```

- [ ] **Step 4: Run tests to verify GREEN**

Run:

```bash
PYTHONPATH=.:src python3 -m pytest backend/tests/test_api_foundation.py -q
```

Expected: PASS.

---

## Task 7: React Frontend Shell

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/index.html`
- Create: `frontend/vite.config.ts`
- Create: `frontend/tsconfig.json`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/app/App.tsx`
- Create: `frontend/src/app/routes.tsx`
- Create: `frontend/src/api/client.ts`
- Create: `frontend/src/types/api.ts`
- Create: `frontend/src/components/SummaryPanel.tsx`
- Create: `frontend/src/components/RawJsonDrawer.tsx`
- Create: `frontend/src/pages/DashboardPage.tsx`
- Create: `frontend/src/pages/AccountsPage.tsx`
- Create: `frontend/src/pages/TasksPage.tsx`
- Create: `frontend/src/pages/ResultsPage.tsx`
- Create: `frontend/src/pages/SystemSettingsPage.tsx`
- Create: `frontend/src/styles.css`

- [ ] **Step 1: Create Vite app files manually**

Create `frontend/package.json`:

```json
{
  "scripts": {
    "dev": "vite --host 127.0.0.1",
    "build": "tsc -b && vite build",
    "lint": "tsc --noEmit"
  },
  "dependencies": {
    "@ant-design/icons": "^5.3.0",
    "@tanstack/react-query": "^5.45.0",
    "antd": "^5.19.0",
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-router-dom": "^6.24.0"
  },
  "devDependencies": {
    "@types/react": "^18.3.3",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.1",
    "typescript": "^5.5.3",
    "vite": "^5.3.3"
  }
}
```

Create the React app with routes:
- `/` 首页数据看板骨架
- `/accounts` 产品账户库
- `/tasks` 任务中心
- `/results` 结果中心
- `/settings` 系统设置

All pages must render Chinese titles and use `SummaryPanel` for any JSON-backed response.

- [ ] **Step 2: Implement shared API client**

`frontend/src/api/client.ts` must expose:

```ts
export async function apiGet<T>(path: string): Promise<T>
export async function apiPost<T>(path: string, body: unknown): Promise<T>
```

Default base URL: `http://127.0.0.1:8000/api`, overridable by `VITE_API_BASE_URL`.

- [ ] **Step 3: Implement `SummaryPanel`**

`SummaryPanel` must render:
- Chinese title
- Status/risk/execution enabled
- Summary items
- Warnings
- Blocking reasons
- Table
- Raw JSON hidden behind a user-clicked drawer

It must not show raw JSON as the primary content.

- [ ] **Step 4: Implement first pages**

`AccountsPage`:
- Calls `GET /api/accounts`
- Shows summary and table
- Has disabled placeholders for upload and paste import marked "第二阶段启用"

`TasksPage`:
- Calls `GET /api/tasks`
- Shows task table
- Clicking a task loads `GET /api/tasks/{task_id}` and shows stdout/stderr in tabs or panels

`ResultsPage`:
- Lets user choose workflow from a fixed dropdown:
  - `site_status_update`
  - `delivery_patrol`
  - `project_update_execute`
  - `create_live_execute_once`
- Calls `GET /api/workflows/latest?workflow=...`
- Shows summary and table first, raw JSON drawer second

`SystemSettingsPage`:
- Calls `GET /api/settings`
- Shows project root, runs dir, configs dir, Streamlit legacy status

`DashboardPage`:
- Static first-page shell with cards for 今日消耗、转化、成本、ROI、活跃账户、活跃项目、异常项目、建议事项.
- Mark data source as "第一阶段框架，第三周接入真实看板数据" in a small secondary text.

- [ ] **Step 5: Type-check frontend**

Run:

```bash
cd frontend
npm install
npm run lint
npm run build
```

Expected: install succeeds, TypeScript passes, production build succeeds.

If network blocks `npm install`, request escalation and retry with the same command.

---

## Task 8: Dev Server Scripts

**Files:**
- Create: `scripts/run_fastapi_backend.py`
- Create: `scripts/run_react_frontend.sh`
- Create: `scripts/run_new_ui_dev.sh`

- [ ] **Step 1: Create backend runner**

`scripts/run_fastapi_backend.py`:

```python
from __future__ import annotations

import uvicorn


if __name__ == "__main__":
    uvicorn.run("backend.app.main:app", host="127.0.0.1", port=8000, reload=True)
```

- [ ] **Step 2: Create frontend runner**

`scripts/run_react_frontend.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../frontend"
npm run dev -- --port 5173
```

- [ ] **Step 3: Create combined local runner**

`scripts/run_new_ui_dev.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PYTHONPATH=.:src python3 scripts/run_fastapi_backend.py &
BACKEND_PID="$!"
trap 'kill "$BACKEND_PID" 2>/dev/null || true' EXIT
cd "$ROOT/frontend"
npm run dev -- --port 5173
```

- [ ] **Step 4: Make shell scripts executable**

Run:

```bash
chmod +x scripts/run_react_frontend.sh scripts/run_new_ui_dev.sh
```

Expected: exit code 0.

---

## Task 9: Verification

**Files:**
- All files above

- [ ] **Step 1: Python tests**

Run:

```bash
PYTHONPATH=.:src python3 -m pytest backend/tests/test_api_foundation.py backend/tests/test_script_registry.py tests/test_ui_background_tasks.py -q
```

Expected: PASS.

- [ ] **Step 2: Backend smoke**

Run:

```bash
PYTHONPATH=.:src python3 scripts/run_fastapi_backend.py
```

Expected: server starts on `http://127.0.0.1:8000`.

Then request:

```bash
python3 -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=5).read().decode())"
```

Expected contains:

```json
{"status":"ok"}
```

- [ ] **Step 3: Frontend build**

Run:

```bash
cd frontend
npm run lint
npm run build
```

Expected: both commands PASS.

- [ ] **Step 4: Browser verification**

Start backend and frontend, then open:

```text
http://127.0.0.1:5173
```

Verify:
- 首页数据看板 renders.
- 产品账户库 renders and does not expose raw JSON first.
- 任务中心 renders.
- 结果中心 can load latest workflow or show a Chinese 404 error.
- 系统设置 shows local paths.

---

## Boundaries For This Phase

- Do not delete or rename `app/streamlit_app.py`.
- Do not modify existing real business scripts unless a test proves the new API cannot call them through the fixed task layer.
- Do not expose arbitrary command execution from React or FastAPI.
- Do not add any frontend path that accepts raw shell commands.
- Do not make React read local files directly.
- Do not make FastAPI call platform business APIs directly.
- Do not show raw JSON as the primary UI.
- Do not implement account upload commit, real dashboard metrics, project delete execution, site delete execution, account remark execution, or create-project execution in this phase.

## Handoff Notes

After this plan is complete, the next implementation plan should cover Week 2:
- account upload preview and commit,
- paste import,
- duplicate detection,
- product/channel/owner filtering,
- export,
- Chinese summary for every import result.
