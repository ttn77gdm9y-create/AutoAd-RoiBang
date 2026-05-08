# Phase 1 Scope

Closeout review: `docs/phase-1-closeout-review.md`.

## Included

- Local project skeleton.
- SQLite schema bootstrap.
- JSON config and policy examples.
- No-op script entrypoints for data sync, daily learning, material sync, and
  strategy planning.
- Local material cache import and supplement-plan generation.
- Product source material import and target-account provision planning.
- Local report snapshot import for projects, promotions, material bindings,
  promotion metrics, operation logs, and material summaries.
- Daily learning artifact generation from local SQLite.
- Strategy plan generation with preflight, dry-run, approval record, and execute
  hard-block artifacts only.
- Scheduler job registry for the Phase 1 fixed scripts.
- Run artifact layout under `data/runs/`.
- Documentation for AI boundaries and future execution chain.

## Excluded

- Real project creation.
- Real unit creation.
- Real pause, delete, budget, targeting, or schedule changes.
- Pulling live data from ad platforms.
- Uploading or binding material.
- Executable approval.
- Real execute implementation.

## Success Criteria

- A developer can understand where configs, policies, scripts, database schema,
  and generated artifacts belong.
- Running placeholder scripts cannot perform real business actions.
- Future implementation has clear boundaries for deterministic scripts and AI
  review.

## Material Sync Entry

Phase 1 material sync is local-only:

```bash
PYTHONPATH=src scripts/run_material_sync.py \
  --config configs/runtime.example.json \
  --request configs/material-sync.example.json
```

The script imports a local material cache fixture into SQLite and writes a
supplement plan artifact under `data/runs/material_sync/`. It refuses to run if
`external_api_enabled` or `execution_enabled` is true.

## Product Source Material Entry

Phase 1 source material planning is local-only:

```bash
PYTHONPATH=src scripts/run_material_source.py \
  --config configs/runtime.example.json \
  --request configs/material-source.example.json
```

The script imports source-account materials into `product_source_materials`,
checks which selected materials the target account already has, and writes a
provision plan artifact under `data/runs/material_source/`. It does not push,
bind, upload, create, or call external APIs.

The OpenAPI source-account material template is disabled by default and can be
preflighted without external calls:

```bash
PYTHONPATH=src scripts/run_material_source.py \
  --config configs/runtime.example.json \
  --request configs/material-source.openapi-http.disabled.example.json \
  --preflight
```

The only supported real sync shape for Phase 1 is read-only
`/open_api/2/file/video/get/`, driven by JSON config and redacted HTTP audit
logs. It must keep `execution_enabled=false`.

## Data Sync Entry

Phase 1 data sync is local-only:

The read-only report snapshot fetching design is documented in
`docs/api/report-snapshot-fetching.md`. Phase 1 starts with local snapshot files;
future OpenAPI fetching must stay behind explicit read-only config.

```bash
PYTHONPATH=src scripts/run_data_sync.py \
  --config configs/runtime.example.json \
  --request configs/data-sync.example.json
```

The script imports a local report snapshot fixture into SQLite, including
account/project/promotion operation logs, and writes an artifact under
`data/runs/data_sync/`. It refuses to run if
`external_api_enabled` or `execution_enabled` is true.

## Daily Learning Entry

Phase 1 daily learning is local-only:

```bash
PYTHONPATH=src scripts/run_daily_learning.py \
  --config configs/runtime.example.json \
  --request configs/daily-learning.example.json
```

The script reads SQLite and writes an artifact under
`data/runs/daily_learning/`. It emits account signals, material deltas,
operation log summaries, decision hints, and guardrails. It refuses to run if
`external_api_enabled` or `execution_enabled` is true.

## Strategy Plan Entry

Phase 1 strategy planning is local-only:

```bash
PYTHONPATH=src scripts/run_strategy_plan.py \
  --config configs/runtime.example.json \
  --request configs/requests/example.strategy-request.json \
  --policy policies/strategy.example.json
```

The script reads the latest daily learning artifact by default, stores the plan
in SQLite, and writes an artifact under `data/runs/strategy_plan/`. Executable
approval and real execute are disabled in Phase 1.

If `data/runs/material_source/` contains a latest artifact, the strategy plan
also includes plan-only material provision recommendations based on
`missing_materials`. It still writes no executable payloads and does not push,
bind, upload, create, pause, delete, or update live objects.

Phase 1 strategy preflight is also local-only:

```bash
PYTHONPATH=src scripts/run_strategy_preflight.py \
  --config configs/runtime.example.json
```

It reads the latest strategy plan artifact, validates phase and plan-only
guardrails, checks material provision recommendation structure, writes a
`strategy_preflight` artifact with source-plan lineage, and never approves
execution in Phase 1.

Phase 1 strategy dry-run is also local-only:

```bash
PYTHONPATH=src scripts/run_strategy_dry_run.py \
  --config configs/runtime.example.json \
  --policy policies/strategy.example.json
```

It reads the latest strategy plan and preflight artifacts, requires preflight to
pass, applies dry-run policy limits, and writes non-executable candidate tasks.
It emits no live API payloads and cannot approve or execute business actions.
It blocks if the plan and preflight do not carry matching `plan_id` and
`target_date` values.

Phase 1 strategy approval is local-only:

```bash
PYTHONPATH=src scripts/run_strategy_approval.py \
  --config configs/runtime.example.json \
  --policy policies/strategy.example.json
```

It reads the latest dry-run artifact and records the policy decision. Phase 1
keeps `approved=false` and `execute_allowed=false` even when policy would
approve the simulated candidate tasks. It requires dry-run lineage to include
matching plan and preflight references.

Phase 1 strategy execute is a local-only hard-block:

```bash
PYTHONPATH=src scripts/run_strategy_execute.py \
  --config configs/runtime.example.json \
  --policy policies/strategy.example.json
```

It reads the latest approval artifact and writes a `strategy_execute` artifact
with `status=blocked`, `reason=phase1_execute_disabled`,
`execution_enabled=false`, `external_api_calls=0`,
`approved_for_execute=false`, `executed_task_count=0`, and `actions=[]`. This
keeps the future execution chain shape complete while preventing real business
execution in Phase 1. It records lineage back to approval, dry-run, preflight,
and plan, and fails closed if required `plan_id` / `target_date` references are
missing or mismatched.

## Scheduler Registry

Phase 1 includes a job registry but does not install cron or launchd jobs:

```bash
PYTHONPATH=src scripts/validate_scheduler_jobs.py \
  --registry configs/scheduler/roibang-v2.jobs.example.json
```

The registry is intentionally script-driven. It does not contain AI prompts,
agent IDs, operator tasks, or ad hoc command instructions.

Scheduler templates can be rendered for review:

```bash
PYTHONPATH=src scripts/render_scheduler_templates.py \
  --registry configs/scheduler/roibang-v2.jobs.example.json \
  --output-dir scheduler
```

The renderer writes example cron and launchd files only. It does not call
`crontab`, `launchctl`, or any business workflow script.

Cron and launchd templates call the unified scheduler runner:

```bash
PYTHONPATH=src scripts/run_scheduler_job.py \
  --job-id roibang-material-sync
```

The runner executes only the foreground script configured in the registry,
captures stdout, stderr, exit code, validates the resulting artifact contract,
and writes a scheduler execution result JSON under
`data/runs/scheduler/<job-id>/`.

## Artifact Contract Validation

Each scheduler job declares a result contract. Validate the latest artifact for
a job with:

```bash
PYTHONPATH=src scripts/validate_run_artifact.py \
  --job-id roibang-daily-learning
```

The validator checks that the JSON file exists, has the expected workflow, and
contains all fields declared in `result_contract.must_include`. It is a read-only
check and does not run the scheduled job.
