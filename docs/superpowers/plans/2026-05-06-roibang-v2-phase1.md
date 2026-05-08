# RoiBang-v2 Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first safe phase of RoiBang-v2: local data contracts, SQLite state, daily learning artifacts, material supplement planning, and strategy plan generation without live business execution.

**Architecture:** Use deterministic Python scripts as scheduler entrypoints. Scripts read JSON config, JSON policy, and SQLite, then write result JSON artifacts. AI reviews outputs and edits code or policy files outside runtime execution.

**Tech Stack:** Python, JSON, SQLite, launchd/cron-compatible scripts, pytest.

---

## File Structure

- `configs/runtime.example.json`: local runtime defaults with external APIs and execution disabled.
- `policies/strategy.example.json`: phase policy defaults for learning, materials, and planning.
- `docs/legacy-migration-inventory.md`: read-only inventory of useful old RoiBang code and migration risks.
- `src/roibang_v2/config.py`: JSON and runtime config loading.
- `src/roibang_v2/db/schema.sql`: SQLite tables for imported facts, metrics, plans, and run history.
- `src/roibang_v2/db/bootstrap.py`: schema initialization helper.
- `src/roibang_v2/runs.py`: result artifact writer.
- `src/roibang_v2/workflows/`: one module per phase workflow.
- `scripts/`: stable command-line entrypoints for schedulers.
- `data/`: local SQLite, fixtures, and generated run artifacts.
- `tests/`: local tests proving deterministic and safe behavior.

## Task 1: Lock Phase 1 Safety Contract

**Files:**
- Modify: `src/roibang_v2/config.py`
- Modify: `scripts/run_phase1_workflow.py`
- Test: `tests/test_phase1_safety.py`

- [ ] **Step 1: Add tests for refusing execution-enabled config**

```python
import pytest

from roibang_v2.workflows.placeholders import phase1_noop_result


def test_phase1_placeholder_cannot_execute_business_actions():
    result = phase1_noop_result("strategy_plan", {"policy_version": "test"})

    assert result["phase"] == "phase1"
    assert result["status"] == "noop"
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 0
```

- [ ] **Step 2: Run the test**

Run: `PYTHONPATH=src pytest tests/test_phase1_safety.py -q`

Expected: PASS.

- [ ] **Step 3: Keep scripts hard-failed when execution is enabled**

Ensure `scripts/run_phase1_workflow.py` raises `RuntimeError` when config or
policy contains `"execution_enabled": true`.

- [ ] **Step 4: Commit**

```bash
git add configs policies scripts src tests docs README.md data
git commit -m "chore: establish roibang v2 phase1 skeleton"
```

## Task 2: Implement Local Data Sync Contract

**Files:**
- Create: `src/roibang_v2/reports/snapshot.py`
- Create: `src/roibang_v2/workflows/data_sync.py`
- Create: `scripts/run_data_sync.py`
- Create: `configs/data-sync.example.json`
- Create: `data/fixtures/report-snapshot.sample.json`
- Create: `tests/test_report_snapshot.py`
- Modify: `src/roibang_v2/db/schema.sql`
- Reference: `docs/legacy-migration-inventory.md`

- [ ] **Step 1: Define fixture-to-SQLite sync tests**

Use local JSON fixtures only. Assert accounts, projects, materials, and metric
snapshots insert deterministically.

- [ ] **Step 2: Implement idempotent inserts**

Use SQLite upserts for stable entity tables and append-only rows for metric
snapshots.

- [ ] **Step 3: Write result artifact**

Return counts for inserted or updated records and include
`external_api_calls: 0`.

- [ ] **Step 4: Run tests**

Run: `PYTHONPATH=src pytest tests/test_data_sync.py -q`

Expected: PASS.

## Task 3: Implement Daily Learning Artifact

**Files:**
- Create: `src/roibang_v2/workflows/daily_learning.py`
- Create: `scripts/run_daily_learning.py`
- Create: `configs/daily-learning.example.json`
- Create: `tests/test_daily_learning.py`
- Modify: `policies/strategy.example.json`
- Reference: `docs/legacy-migration-inventory.md`

- [ ] **Step 1: Test policy-threshold signal generation**

Seed SQLite metrics and assert the workflow emits deterministic signals based
on `lookback_days`, `min_cost_for_signal`, and
`min_conversions_for_signal`.

- [ ] **Step 2: Implement read-only learning query**

Read SQLite snapshots and policy JSON. Do not write operational mutations.

- [ ] **Step 3: Write result JSON shape**

Include `signals`, `anomalies`, `policy_suggestions`, and
`execution_enabled: false`.

- [ ] **Step 4: Run tests**

Run: `PYTHONPATH=src pytest tests/test_daily_learning.py -q`

Expected: PASS.

## Task 4: Implement Material Supplement Planning

**Files:**
- Create: `src/roibang_v2/materials/library.py`
- Create: `src/roibang_v2/materials/product_source.py`
- Create: `src/roibang_v2/workflows/material_sync.py`
- Create: `src/roibang_v2/workflows/material_source.py`
- Create: `scripts/run_material_sync.py`
- Create: `scripts/run_material_source.py`
- Create: `configs/material-sync.example.json`
- Create: `configs/material-source.example.json`
- Create: `data/fixtures/material-cache.sample.json`
- Create: `data/fixtures/product-source-materials.sample.json`
- Create: `tests/test_material_sync.py`
- Create: `tests/test_material_source.py`
- Modify: `src/roibang_v2/db/schema.sql`
- Reference: `docs/legacy-migration-inventory.md`

- [ ] **Step 1: Test supplement threshold logic**

Seed materials and project usage facts. Assert the workflow emits supplement
needs when available material count is below policy threshold.

- [ ] **Step 2: Implement local material inventory query**

Read material rows and usage records from SQLite.

- [ ] **Step 3: Emit plan-only output**

Output recommended supplement quantities and reasons. Do not upload or bind
materials.

- [ ] **Step 4: Run tests**

Run: `PYTHONPATH=src pytest tests/test_material_sync.py -q`

Expected: PASS.

## Task 5: Implement Strategy Plan Generation

**Files:**
- Create: `src/roibang_v2/workflows/strategy_plan.py`
- Create: `configs/requests/example.strategy-request.json`
- Create: `scripts/run_strategy_plan.py`
- Create: `tests/test_strategy_plan.py`
- Reference: `docs/legacy-migration-inventory.md`

- [ ] **Step 1: Test request-to-plan conversion**

Given a request JSON, policy JSON, and SQLite facts, assert a plan JSON is
created with `phase: "phase1"`, `execution_enabled: false`, preflight
requirements, and dry-run placeholders.

- [ ] **Step 2: Implement plan generation**

Convert operator request into deterministic strategy plan records. Store plan
JSON in SQLite and write a run artifact.

- [ ] **Step 3: Preserve future chain**

Ensure output sections are named `request`, `strategy`, `preflight`, `dry_run`,
`approval`, and `execute`, with approval and execute disabled in Phase 1.

- [ ] **Step 4: Run tests**

Run: `PYTHONPATH=src pytest tests/test_strategy_plan.py -q`

Expected: PASS.

## Self-Review

- The plan covers Phase 1 only.
- All live business execution remains explicitly excluded.
- JSON config, policy, SQLite, scripts, and AI boundaries are represented.
- Future creation chain is preserved as a contract, not implemented as live
  execution.
