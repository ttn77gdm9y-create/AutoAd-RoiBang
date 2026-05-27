# Frontend Observability And Product Create Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让前端真实执行任务可观察、可追踪、可复盘，并继续完善点点英雄创建模板和多产品创建审查。

**Architecture:** 前端仍然只调用固定脚本，不直接调用平台接口。新增一个本地 background task（后台任务）层负责启动固定脚本、记录 `task_id`（任务 ID）、stdout/stderr（标准输出/标准错误）、progress（进度）和 artifact（执行结果文件）；Streamlit 只读取这些本地 JSON 文件并展示。创建计划审查继续复用产品维度选材数据，保证素材消耗/转化只按当前产品统计。

**Tech Stack:** Python 3.11, Streamlit, pytest, JSON artifacts（执行结果文件）, existing fixed scripts under `scripts/`.

---

## File Structure

- Create: `src/roibang_v2/ui/background_tasks.py`
  - 负责启动、读取、更新本地 background task（后台任务）。
  - 不做平台 API 调用，只执行传入的固定命令数组。
- Create: `scripts/run_frontend_task.py`
  - 固定入口脚本，接收 task JSON，执行 command/post_commands，写 task 状态和输出文件。
  - 用于 Streamlit 启动后即使页面刷新也能继续记录结果。
- Modify: `app/streamlit_app.py`
  - 真实执行按钮改为创建 background task（后台任务）。
  - 任务中心和操作日志页展示实时状态、进度、stdout/stderr、执行结果和飞书推送状态。
  - 创建计划页在真实执行前展示素材、文案、CTA（行动按钮）、卖点使用次数和产品维度消耗/转化。
- Modify: `src/roibang_v2/ui/task_runs.py`
  - 读取 `data/runs/frontend_tasks/*.json`，合并操作日志、执行结果、progress（进度）。
- Modify: `src/roibang_v2/workflows/frontend_operation_log.py`
  - 增强操作日志 summary，记录 task file、stdout/stderr、report artifact（汇报结果文件）。
- Modify: point hero product/template files after task observability is stable:
  - `configs/products/diandian-hero.local.json`
  - product-specific create template catalog under existing config path
- Tests:
  - Create: `tests/test_ui_background_tasks.py`
  - Modify: `tests/test_ui_task_runs.py`
  - Modify: `tests/test_frontend_operation_log.py`
  - Modify: `tests/test_create_plan_review.py`

---

## Task 1: Local Background Task Store

**Files:**
- Create: `src/roibang_v2/ui/background_tasks.py`
- Test: `tests/test_ui_background_tasks.py`

- [ ] **Step 1: Write failing tests**

```python
from pathlib import Path

from roibang_v2.ui.background_tasks import build_task_record
from roibang_v2.ui.background_tasks import load_task_record
from roibang_v2.ui.background_tasks import task_paths
from roibang_v2.ui.background_tasks import write_task_record


def test_build_task_record_contains_stable_paths(tmp_path: Path):
    runs_dir = tmp_path / "runs"
    record = build_task_record(
        runs_dir=runs_dir,
        operation_type="create_live_execute",
        command=["python3", "scripts/run_create_live_execute_terminal.py"],
        cwd="/repo",
        request={"plan_path": "data/runs/create_mode/plan.json"},
    )

    assert record["task_id"].startswith("frontend-")
    assert record["status"] == "queued"
    assert record["operation_type"] == "create_live_execute"
    assert record["command"] == ["python3", "scripts/run_create_live_execute_terminal.py"]
    assert record["stdout_path"].startswith("frontend_tasks/")
    assert record["stderr_path"].startswith("frontend_tasks/")
    assert record["artifact_path"].startswith("frontend_tasks/")


def test_write_and_load_task_record_roundtrip(tmp_path: Path):
    runs_dir = tmp_path / "runs"
    record = build_task_record(
        runs_dir=runs_dir,
        operation_type="project_update_execute",
        command=["python3", "scripts/run_project_update.py"],
        cwd="/repo",
        request={"config_path": "data/runs/project_update/config.json"},
    )

    path = write_task_record(runs_dir, record)
    loaded = load_task_record(path)

    assert loaded["task_id"] == record["task_id"]
    assert loaded["status"] == "queued"
    assert task_paths(runs_dir, record["task_id"])["task"].name.endswith(".json")
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
PYTHONPATH=src python3 -m pytest tests/test_ui_background_tasks.py -q
```

Expected: FAIL because `roibang_v2.ui.background_tasks` does not exist.

- [ ] **Step 3: Implement minimal task store**

Create `src/roibang_v2/ui/background_tasks.py` with:

```python
from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def task_paths(runs_dir: str | Path, task_id: str) -> dict[str, Path]:
    base = Path(runs_dir) / "frontend_tasks"
    return {
        "dir": base,
        "task": base / f"{task_id}.json",
        "stdout": base / f"{task_id}.stdout.log",
        "stderr": base / f"{task_id}.stderr.log",
    }


def build_task_record(
    *,
    runs_dir: str | Path,
    operation_type: str,
    command: list[str],
    cwd: str,
    request: dict[str, Any] | None = None,
    post_commands: list[list[str]] | None = None,
) -> dict[str, Any]:
    task_id = f"frontend-{datetime.now().strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:8]}"
    paths = task_paths(runs_dir, task_id)
    return {
        "task_id": task_id,
        "operation_type": operation_type,
        "status": "queued",
        "created_at": _now(),
        "updated_at": _now(),
        "cwd": cwd,
        "command": command,
        "post_commands": post_commands or [],
        "request": request or {},
        "return_code": None,
        "stdout_path": str(paths["stdout"].relative_to(Path(runs_dir))),
        "stderr_path": str(paths["stderr"].relative_to(Path(runs_dir))),
        "artifact_path": str(paths["task"].relative_to(Path(runs_dir))),
        "result": {},
    }


def write_task_record(runs_dir: str | Path, record: dict[str, Any]) -> Path:
    task_id = str(record["task_id"])
    paths = task_paths(runs_dir, task_id)
    paths["dir"].mkdir(parents=True, exist_ok=True)
    paths["task"].write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return paths["task"]


def load_task_record(path: str | Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}
```

- [ ] **Step 4: Run tests to verify GREEN**

Run:

```bash
PYTHONPATH=src python3 -m pytest tests/test_ui_background_tasks.py -q
```

Expected: PASS.

---

## Task 2: Fixed Frontend Task Runner

**Files:**
- Create: `scripts/run_frontend_task.py`
- Modify: `src/roibang_v2/ui/background_tasks.py`
- Test: `tests/test_ui_background_tasks.py`

- [ ] **Step 1: Add failing runner tests**

Append to `tests/test_ui_background_tasks.py`:

```python
import json
import subprocess


def test_run_frontend_task_records_completed_result(tmp_path: Path):
    runs_dir = tmp_path / "runs"
    script = tmp_path / "ok.py"
    script.write_text("import json; print(json.dumps({'ok': True, 'artifact_path': 'x.json'}))", encoding="utf-8")
    record = build_task_record(
        runs_dir=runs_dir,
        operation_type="test_ok",
        command=["python3", str(script)],
        cwd=str(tmp_path),
        request={},
    )
    task_path = write_task_record(runs_dir, record)

    completed = subprocess.run(
        ["python3", "scripts/run_frontend_task.py", "--task", str(task_path)],
        cwd=Path.cwd(),
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0
    loaded = load_task_record(task_path)
    assert loaded["status"] == "completed"
    assert loaded["return_code"] == 0
    assert loaded["result"]["ok"] is True


def test_run_frontend_task_records_failed_result(tmp_path: Path):
    runs_dir = tmp_path / "runs"
    script = tmp_path / "fail.py"
    script.write_text("import sys; print('bad', file=sys.stderr); sys.exit(7)", encoding="utf-8")
    record = build_task_record(
        runs_dir=runs_dir,
        operation_type="test_fail",
        command=["python3", str(script)],
        cwd=str(tmp_path),
        request={},
    )
    task_path = write_task_record(runs_dir, record)

    completed = subprocess.run(
        ["python3", "scripts/run_frontend_task.py", "--task", str(task_path)],
        cwd=Path.cwd(),
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 7
    loaded = load_task_record(task_path)
    assert loaded["status"] == "failed"
    assert loaded["return_code"] == 7
    assert "bad" in (runs_dir / loaded["stderr_path"]).read_text(encoding="utf-8")
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
PYTHONPATH=src python3 -m pytest tests/test_ui_background_tasks.py -q
```

Expected: FAIL because `scripts/run_frontend_task.py` does not exist.

- [ ] **Step 3: Implement fixed runner**

Create `scripts/run_frontend_task.py`:

```python
from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _parse_stdout(stdout: str) -> dict[str, Any]:
    for line in reversed(stdout.splitlines()):
        text = line.strip()
        if not text.startswith("{"):
            continue
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return {}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", required=True)
    args = parser.parse_args()
    task_path = Path(args.task)
    runs_dir = task_path.parent.parent
    task = _read_json(task_path)
    task["status"] = "running"
    task["started_at"] = _now()
    task["updated_at"] = _now()
    _write_json(task_path, task)

    stdout_path = runs_dir / str(task["stdout_path"])
    stderr_path = runs_dir / str(task["stderr_path"])
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    command = [str(part) for part in task.get("command") or []]
    completed = subprocess.run(
        command,
        cwd=str(task.get("cwd") or "."),
        text=True,
        capture_output=True,
        check=False,
    )
    stdout_path.write_text(completed.stdout or "", encoding="utf-8")
    stderr_path.write_text(completed.stderr or "", encoding="utf-8")
    parsed = _parse_stdout(completed.stdout or "")
    task["status"] = "completed" if completed.returncode == 0 else "failed"
    task["return_code"] = completed.returncode
    task["result"] = parsed
    task["finished_at"] = _now()
    task["updated_at"] = _now()
    _write_json(task_path, task)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests to verify GREEN**

Run:

```bash
PYTHONPATH=src python3 -m pytest tests/test_ui_background_tasks.py -q
```

Expected: PASS.

---

## Task 3: Streamlit Start Task Instead Of Blocking On Real Execution

**Files:**
- Modify: `src/roibang_v2/ui/background_tasks.py`
- Modify: `app/streamlit_app.py`
- Modify: `src/roibang_v2/workflows/frontend_operation_log.py`
- Test: `tests/test_ui_background_tasks.py`
- Test: `tests/test_frontend_operation_log.py`

- [ ] **Step 1: Add test for start command construction**

Append to `tests/test_ui_background_tasks.py`:

```python
from roibang_v2.ui.background_tasks import build_runner_command


def test_build_runner_command_uses_fixed_entrypoint(tmp_path: Path):
    task_path = tmp_path / "runs" / "frontend_tasks" / "frontend-x.json"

    command = build_runner_command(task_path)

    assert command[:2] == ["python3", "scripts/run_frontend_task.py"]
    assert command[-2:] == ["--task", str(task_path)]
```

- [ ] **Step 2: Run test to verify RED**

Run:

```bash
PYTHONPATH=src python3 -m pytest tests/test_ui_background_tasks.py::test_build_runner_command_uses_fixed_entrypoint -q
```

Expected: FAIL because `build_runner_command` does not exist.

- [ ] **Step 3: Implement command builder**

Add to `src/roibang_v2/ui/background_tasks.py`:

```python
def build_runner_command(task_path: str | Path) -> list[str]:
    return ["python3", "scripts/run_frontend_task.py", "--task", str(task_path)]
```

- [ ] **Step 4: Wire Streamlit real-execute buttons**

In `app/streamlit_app.py`, update real execution handlers:

```python
from roibang_v2.ui.background_tasks import build_runner_command
from roibang_v2.ui.background_tasks import build_task_record
from roibang_v2.ui.background_tasks import write_task_record
```

For `_run_confirmed_execution`, replace blocking `run_fixed_script(command, ...)` with:

```python
record = build_task_record(
    runs_dir=runs_dir,
    operation_type=operation_type,
    command=command,
    cwd=str(project_root),
    request={**(request or {}), "confirmed": confirmed},
)
task_path = write_task_record(runs_dir, record)
runner_result = run_fixed_script(
    build_runner_command(task_path),
    cwd=project_root,
    timeout_seconds=1,
)
st.session_state[f"{state_key}_task_id"] = record["task_id"]
st.cache_data.clear()
st.success(f"任务已启动：{record['task_id']}")
```

If `timeout_seconds=1` is too short for process spawn on local machine, use `timeout_seconds=5`. Do not wait for real execution completion in the click handler.

- [ ] **Step 5: Run focused tests and py_compile**

Run:

```bash
PYTHONPATH=src python3 -m pytest tests/test_ui_background_tasks.py tests/test_frontend_operation_log.py -q
PYTHONPATH=src python3 -m py_compile app/streamlit_app.py src/roibang_v2/ui/background_tasks.py scripts/run_frontend_task.py
```

Expected: PASS.

---

## Task 4: Task Center Real-Time Status And Logs

**Files:**
- Modify: `src/roibang_v2/ui/task_runs.py`
- Modify: `app/streamlit_app.py`
- Test: `tests/test_ui_task_runs.py`

- [ ] **Step 1: Add failing test for frontend task rows**

Append to `tests/test_ui_task_runs.py`:

```python
import json
from pathlib import Path

from roibang_v2.ui.task_runs import load_frontend_task_rows


def test_load_frontend_task_rows_sorts_recent_first(tmp_path: Path):
    runs_dir = tmp_path / "runs"
    task_dir = runs_dir / "frontend_tasks"
    task_dir.mkdir(parents=True)
    (task_dir / "a.json").write_text(json.dumps({
        "task_id": "a",
        "operation_type": "create_live_execute",
        "status": "completed",
        "created_at": "2026-05-26T01:00:00+08:00",
        "updated_at": "2026-05-26T01:02:00+08:00",
        "return_code": 0,
        "result": {"artifact_path": "data/runs/x/a.json"},
    }), encoding="utf-8")
    (task_dir / "b.json").write_text(json.dumps({
        "task_id": "b",
        "operation_type": "create_live_execute",
        "status": "running",
        "created_at": "2026-05-26T02:00:00+08:00",
        "updated_at": "2026-05-26T02:01:00+08:00",
        "return_code": None,
        "result": {},
    }), encoding="utf-8")

    rows = load_frontend_task_rows(runs_dir, limit=10)

    assert [row["task_id"] for row in rows] == ["b", "a"]
    assert rows[0]["status"] == "running"
    assert rows[1]["execute_artifact_path"] == "data/runs/x/a.json"
```

- [ ] **Step 2: Run test to verify RED**

Run:

```bash
PYTHONPATH=src python3 -m pytest tests/test_ui_task_runs.py::test_load_frontend_task_rows_sorts_recent_first -q
```

Expected: FAIL because `load_frontend_task_rows` does not exist.

- [ ] **Step 3: Implement task row reader**

Add to `src/roibang_v2/ui/task_runs.py`:

```python
def load_frontend_task_rows(runs_dir: str | Path, *, limit: int = 100) -> list[dict[str, Any]]:
    task_dir = Path(runs_dir) / "frontend_tasks"
    rows: list[dict[str, Any]] = []
    for path in sorted(task_dir.glob("*.json"), key=lambda item: item.name, reverse=True):
        payload = _read_json(path)
        if not payload:
            continue
        result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
        rows.append({
            "task_id": str(payload.get("task_id") or path.stem),
            "operation_type": str(payload.get("operation_type") or ""),
            "status": str(payload.get("status") or ""),
            "created_at": str(payload.get("created_at") or ""),
            "updated_at": str(payload.get("updated_at") or ""),
            "return_code": payload.get("return_code"),
            "execute_artifact_path": str(result.get("execute_artifact_path") or result.get("artifact_path") or ""),
            "stdout_path": str(payload.get("stdout_path") or ""),
            "stderr_path": str(payload.get("stderr_path") or ""),
            "artifact_path": str(payload.get("artifact_path") or ""),
        })
        if len(rows) >= limit:
            break
    return rows
```

- [ ] **Step 4: Update task center UI**

In `app/streamlit_app.py`:
- Add a “后台任务” section above operation-log tasks.
- Show status cards: running/completed/failed counts.
- For selected task, show:
  - `task_id`（任务 ID）
  - command（固定命令）
  - stdout/stderr（标准输出/标准错误） collapsed expanders
  - artifact（执行结果文件）
  - progress（进度） from existing `read_create_live_progress`
- Add a small auto-refresh component only while any task is running:

```python
components.html(
    "<script>setTimeout(() => window.parent.location.reload(), 3000)</script>",
    height=0,
    width=0,
)
```

- [ ] **Step 5: Verify**

Run:

```bash
PYTHONPATH=src python3 -m pytest tests/test_ui_task_runs.py -q
PYTHONPATH=src python3 -m py_compile app/streamlit_app.py src/roibang_v2/ui/task_runs.py
```

Expected: PASS.

---

## Task 5: Create Plan Pre-Execution Review Completeness

**Files:**
- Modify: `src/roibang_v2/ui/create_plan_review.py`
- Modify: `app/streamlit_app.py`
- Test: `tests/test_create_plan_review.py`

- [ ] **Step 1: Add tests for product-scoped material metrics and creative usage**

Append to `tests/test_create_plan_review.py`:

```python
def test_review_uses_product_metrics_not_global_metrics():
    plan = {
        "summary": {"planned_project_count": 1, "planned_unit_count": 1, "planned_material_count": 1, "source_material_count": 1},
        "create_request": {"product_key": "diandian-hero", "target_accounts": ["186"]},
        "details": {
            "material_assignments": [{
                "advertiser_id": "186",
                "unit_key": "u1",
                "material_id": "m1",
                "source_video_id": "v1",
                "name": "素材 A",
                "product_stat_cost": 123.45,
                "product_convert_cnt": 6,
                "cost_lookback": 9999,
            }],
            "unit_copywriting": [{
                "advertiser_id": "186",
                "unit_key": "u1",
                "title_material_list": [{"title": "文案 A"}],
                "call_to_action_buttons": ["立即下载"],
                "product_info": {"selling_points": ["爆率高"]},
            }],
        },
    }

    review = build_create_plan_review(plan)

    assert review["materials"][0]["product_stat_cost"] == 123.45
    assert review["materials"][0]["product_convert_cnt"] == 6
    assert review["materials"][0].get("cost_lookback") is None
    assert review["creative_usage"]["titles"][0]["title"] == "文案 A"
    assert review["creative_usage"]["ctas"][0]["cta"] == "立即下载"
    assert review["creative_usage"]["selling_points"][0]["selling_point"] == "爆率高"
```

- [ ] **Step 2: Run test**

Run:

```bash
PYTHONPATH=src python3 -m pytest tests/test_create_plan_review.py -q
```

Expected: PASS if current implementation already satisfies it; otherwise FAIL and implement only the missing fields.

- [ ] **Step 3: Update UI labels**

In `app/streamlit_app.py`, make sure all material tables use:
- `material_id（素材 ID）`
- `video_id（视频 ID）`
- `该产品消耗`
- `该产品转化`
- `使用次数`

Do not show global cost as a substitute for product cost.

- [ ] **Step 4: Verify**

Run:

```bash
PYTHONPATH=src python3 -m pytest tests/test_create_plan_review.py -q
PYTHONPATH=src python3 -m py_compile app/streamlit_app.py src/roibang_v2/ui/create_plan_review.py
```

Expected: PASS.

---

## Task 6: Point Hero Template Hardening

**Files:**
- Modify: `configs/products/diandian-hero.local.json`
- Modify: product-specific create template catalog path resolved by `product_create_template_catalog_path`
- Modify: `src/roibang_v2/create_mode_rules.py` only if validation currently requires lookback days for random materials.
- Test: existing create mode tests plus focused new tests if config loader has tests.

- [ ] **Step 1: Inspect current point hero product config and template path**

Run:

```bash
PYTHONPATH=src python3 - <<'PY'
from pathlib import Path
from roibang_v2.ui.streamlit_shell import load_product_config, product_create_template_catalog_path
product = load_product_config("configs/products/diandian-hero.local.json")
print(product.get("product_key"), product.get("display_name"))
print(product_create_template_catalog_path(product))
PY
```

Expected: print point hero product key and product-specific template path.

- [ ] **Step 2: Verify template independence**

Run:

```bash
rg -n "yzt|勇者|wechat|template" configs/products configs/create_modes configs -g '*.json'
```

Expected: point hero template file must not reference 勇者突进 template keys unless it is an intentional copied-and-renamed independent file.

- [ ] **Step 3: Update point hero template values**

Required config behavior:
- `project bid` and `ROI coefficient` are not hard-coded in the point hero template.
- `selection_type=random_materials（随机素材）` does not require lookback days.
- title pool, CTA（行动按钮） pool, and selling points are fixed in the point hero product template.
- Random assignment is done when generating the plan, not during real execution.

- [ ] **Step 4: Verify plan generation only**

Run a dry-run（预演） plan generation for point hero:

```bash
PYTHONPATH=src python3 scripts/run_create_mode.py --config configs/runtime.example.json --mode wx_pay_male_random_materials --accounts 1866125088740552 --dry-run
```

Expected:
- No real execution.
- JSON artifact（执行结果文件） contains point hero title/CTA/selling point assignments.
- Material lookback days is not required for unlimited/random material mode.

---

## Task 7: Verification And Local UI Restart

**Files:**
- No new files.

- [ ] **Step 1: Run focused tests**

Run:

```bash
PYTHONPATH=src python3 -m pytest \
  tests/test_ui_background_tasks.py \
  tests/test_ui_task_runs.py \
  tests/test_operation_logs.py \
  tests/test_frontend_operation_log.py \
  tests/test_create_plan_review.py \
  tests/test_create_live_execute_report.py \
  tests/test_create_live_execute_once.py \
  -q
```

Expected: PASS.

- [ ] **Step 2: Compile changed modules**

Run:

```bash
PYTHONPATH=src python3 -m py_compile \
  app/streamlit_app.py \
  src/roibang_v2/ui/background_tasks.py \
  src/roibang_v2/ui/task_runs.py \
  src/roibang_v2/ui/operation_logs.py \
  src/roibang_v2/ui/create_plan_review.py \
  src/roibang_v2/workflows/frontend_operation_log.py \
  scripts/run_frontend_task.py
```

Expected: no output.

- [ ] **Step 3: Restart Streamlit**

Run:

```bash
python3 scripts/restart_streamlit_ui.py --host 127.0.0.1 --port 8502
```

Expected: JSON output with `"ok": true` and URL `http://127.0.0.1:8502`.

- [ ] **Step 4: Verify frontend loads**

Run:

```bash
python3 - <<'PY'
import urllib.request
with urllib.request.urlopen("http://127.0.0.1:8502/", timeout=5) as response:
    body = response.read(5000).decode("utf-8", "ignore")
print({"status": response.status, "has_streamlit": "streamlit" in body.lower()})
PY
```

Expected: `{"status": 200, "has_streamlit": True}`.

---

## Scope Guardrails

- Do not change existing Yongzhe Tujin material push/create logic unless a test proves a shared bug.
- Do not introduce approval pack / execution pack.
- Do not commit tokens, sessions, local secrets, or real account private artifacts.
- Do not call real platform execution during development verification.
- Real execution remains behind explicit “确认执行”.
- If a fixed script currently lacks progress output, show stdout/stderr and final artifact first; add script-level progress only after the fixed script behavior is stable.

## Completion Criteria

- Frontend can start real fixed-script tasks without blocking page rendering.
- Task center shows running/completed/failed status, stdout/stderr, result artifact（执行结果文件）, and progress（进度） where available.
- Operation logs show each frontend action and detailed create material/copy/CTA/selling point usage.
- Create plan review blocks obvious bad plans before real execution.
- Product material metrics are product-scoped.
- Point hero template is independent and random-material mode does not require lookback days.
