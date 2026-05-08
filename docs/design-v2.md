# RoiBang-v2 Design

## Purpose

RoiBang-v2 is a deterministic automation system for mature ad operation
workflows. It separates business execution from AI review: fixed scripts and
schedulers perform repeatable work, while AI helps maintain code, inspect
results, and revise policy files.

The v2 repository is independent from the legacy RoiBang project. Legacy code
may be read for reference and copied only after review, but new development
happens here.

## Principles

1. Mature business operations run through fixed scripts scheduled by launchd,
   cron, or equivalent schedulers.
2. Scripts read JSON config, JSON policies, and SQLite state. Scripts do not
   ask AI to decide what to do during execution.
3. AI responsibilities are limited to writing or repairing scripts, reviewing
   result JSON, and editing strategy JSON.
4. Daily learning and automatic material supplement capabilities from the old
   project will be preserved and refactored into v2 modules.
5. Phase 1 includes only data sync, daily learning, material sync/supplement
   planning, and strategy plan generation.
6. Phase 1 excludes real creation, pause, deletion, schedule-emptying, and live
   execution actions.
7. Future creation workflows must preserve:
   `request -> strategy -> preflight -> dry-run -> approve -> execute`.

## Architecture

RoiBang-v2 is organized around small local units:

- `configs/`: environment-neutral runtime configuration.
- `policies/`: strategy and decision rules expressed as JSON.
- `data/`: local SQLite database and generated JSON artifacts.
- `scripts/`: stable CLI entrypoints for scheduled jobs.
- `src/roibang_v2/`: reusable Python package for loading config, accessing
  SQLite, writing artifacts, and running phase workflows.
- `docs/`: operating model, phase boundaries, and future workflow contracts.
- `tests/`: local tests for deterministic behavior.

Scripts are thin entrypoints. They load JSON and SQLite through package modules,
run a named workflow, and write machine-readable result JSON into `data/runs/`.

## Phase 1 Workflows

### Data Sync

The data sync workflow establishes the local contract for importing account,
project, unit, creative, cost, conversion, and material metrics into SQLite.
Initial implementation is allowed to use local fixtures or cached files only.
Live API sync must be added behind explicit configuration and tested in dry-run
mode first.

### Daily Learning

The daily learning workflow reads SQLite snapshots and policy JSON to produce a
daily review artifact. The output should summarize signals, anomalies,
candidate adjustments, and policy update suggestions. It must not mutate live
campaign state.

### Material Sync And Supplement Planning

The material workflow records known materials, recent performance, and reuse
constraints. It may generate supplement plans that say which projects or
strategy groups need more material, but it must not upload, bind, or create live
units in Phase 1.

Product source materials are modeled with `source_advertiser_id`. This is an
important future creation precondition: creation plans should choose deterministic
materials from the product source pool, compare them with the target account's
existing inventory, and produce a provision plan before any future dry-run or
execution. Phase 1 stores source materials and missing-material plans only; it
does not push, bind, upload, or execute.

### Strategy Plan Generation

The strategy planner reads requests, policies, and SQLite facts to generate
strategy plan JSON. Plans may include preflight requirements and dry-run
instructions, but Phase 1 stops before approval and execute.

## SQLite Role

SQLite is the local source of operational facts. It should hold imported account
state, project state, material metadata, metrics snapshots, generated plans, and
run history. JSON files remain the interface for human review, policy changes,
and scheduler inputs.

The initial schema lives in `src/roibang_v2/db/schema.sql`.

## JSON Contracts

Config JSON answers "where and how should this script run locally?"

Policy JSON answers "what deterministic rules should scripts apply?"

Request JSON answers "what does an operator want planned?"

Result JSON answers "what did this script observe or generate?"

The system should validate JSON before running a workflow. Invalid JSON should
produce a failed local run artifact and exit non-zero.

## AI Boundary

AI may:

- write and refactor scripts
- inspect generated JSON results
- propose policy changes
- edit strategy JSON after review
- summarize daily learning output

AI must not:

- choose live business actions during script execution
- bypass preflight, dry-run, or approval
- run real create, pause, delete, or schedule-emptying actions in Phase 1
- develop directly in `/Users/hongen/Codes/RoiBang`

## Scheduler Model

Scheduled jobs should call stable scripts in `scripts/`. Each script should:

1. load config and policy
2. open SQLite
3. run one workflow
4. write `data/runs/<workflow>/<timestamp>.json`
5. exit with a clear status code

The scheduler must not contain business logic. It only invokes scripts at fixed
times.

RoiBang-v2 keeps scheduled task definitions in a registry such as
`configs/scheduler/roibang-v2.jobs.example.json`. The registry must describe
fixed scripts, config/policy files, result contracts, schedules, and delivery
metadata. It must not contain `prompt`, `agentId`, `operator_task`, or ad hoc
shell command fields that ask AI to run business operations.

The validation entrypoint is:

```bash
PYTHONPATH=src scripts/validate_scheduler_jobs.py \
  --registry configs/scheduler/roibang-v2.jobs.example.json
```

The rendering entrypoint is:

```bash
PYTHONPATH=src scripts/render_scheduler_templates.py \
  --registry configs/scheduler/roibang-v2.jobs.example.json \
  --output-dir scheduler
```

It only writes reviewable cron and launchd examples. Installation remains a
separate manual step outside Phase 1.

Rendered scheduler entries should call the unified runner:

```bash
PYTHONPATH=src scripts/run_scheduler_job.py \
  --job-id roibang-material-sync
```

The runner is not a strategy engine. It reads the fixed registry entry, executes
the configured foreground script, records stdout, stderr, exit code, and then
checks the artifact contract.

After a scheduled script writes an artifact, the artifact should be checked
against the registry result contract:

```bash
PYTHONPATH=src scripts/validate_run_artifact.py \
  --job-id roibang-daily-learning
```

The validator reads JSON only. It verifies the expected `workflow` and required
top-level fields from `result_contract.must_include`.

## Future Execution Chain

Future creation or mutation workflows must use this chain:

1. `request`: operator-authored JSON request.
2. `strategy`: deterministic plan generated from policy and facts.
3. `preflight`: validation of account, budget, targeting, material, and limits.
4. `dry-run`: exact simulated API payloads and expected mutations.
5. `approve`: explicit human or configured approval record.
6. `execute`: live action script reads approved dry-run artifact.

Phase 1 may create request, strategy, preflight draft, and dry-run draft schemas,
but execute scripts should remain unavailable or hard-failed.

## Safety Defaults

- No script should call external ad APIs by default.
- No script should mutate live campaign state in Phase 1.
- Generated plans should include `phase: "phase1"` and `execution_enabled:
  false`.
- Any future live-capable script must require explicit config, approval input,
  and command-line flags.
