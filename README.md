# RoiBang-v2

RoiBang-v2 is a script-first automation system for ad operation workflows.

This repository starts from a clean v2 architecture. The old project at
`/Users/hongen/Codes/RoiBang` is reference-only and must not be used as the
active development target.

## Current Phase

Phase 1 only builds safe local capabilities:

- data sync framework
- daily learning review
- material history backfill and rollups
- source material library sync and candidate planning
- strategy plan generation

Phase 1 does not perform real create, pause, delete, schedule-emptying, or
budget-changing actions.

## Core Rule

Business actions must be deterministic script executions. Scripts read only
JSON config, JSON policy, and SQLite state. AI may write scripts, review result
JSON, and update strategy JSON, but AI must not make live operational decisions
at execution time.

## Safety Chain

Future creation workflows must keep this chain:

`request -> strategy -> preflight -> dry-run -> approve -> execute`

Only the first planning parts are represented in this initial skeleton.

## Legacy Migration

Legacy migration notes live in `docs/legacy-migration-inventory.md`. The short
version: migrate local utility, material library, report normalization, daily
learning, and strategy planning logic first; keep all live execution scripts as
reference-only during Phase 1.

## Local Material Sync

Run the current local-only material sync with:

```bash
PYTHONPATH=src scripts/run_material_sync.py \
  --config configs/runtime.example.json \
  --request configs/material-sync.example.json
```

It imports `data/fixtures/material-cache.sample.json`, writes SQLite rows, and
emits a supplement plan. It does not call external APIs.

## Product Source Materials

Run the current local-only source material planning with:

```bash
PYTHONPATH=src scripts/run_material_source.py \
  --config configs/runtime.example.json \
  --request configs/material-source.example.json
```

It imports a local source material fixture for `source_advertiser_id`, compares
selected source materials with a target account's existing material inventory,
and emits a provision plan. It does not push, bind, upload, or create anything.

There is also a disabled real read-only template for syncing source-account
video materials through the OpenAPI allowlist:

```bash
PYTHONPATH=src scripts/run_material_source.py \
  --config configs/runtime.example.json \
  --request configs/material-source.openapi-http.disabled.example.json \
  --preflight
```

This only writes a preflight artifact by default. To perform an actual read-only
sync later, the request must explicitly set `material_source.enabled=true` and
`openapi_http.enabled=true`, and the runtime must keep
`execution_enabled=false` while setting `external_api_enabled=true`.

## Local Data Sync

Report snapshot fetching notes live in `docs/api/report-snapshot-fetching.md`.
The first fetcher should produce a local JSON snapshot before `run_data_sync.py`
imports it into SQLite.

Import the account pool CSV with:

```bash
PYTHONPATH=src scripts/import_accounts_csv.py \
  --csv data/sources/accounts/roibangv2yztj.csv
```

Build a dry-run historical backfill plan with:

```bash
PYTHONPATH=src scripts/plan_report_backfill.py \
  --product 勇者突进 \
  --platform WECHAT_GAME \
  --start-date 2026-02-10 \
  --end-date 2026-05-05
```

This only plans read-only fetch tasks and writes an artifact under
`data/runs/report_backfill_plan/`.

Build a dry-run batched historical backfill plan with:

```bash
PYTHONPATH=src scripts/plan_report_backfill_batches.py \
  --product 勇者突进 \
  --platform WECHAT_GAME \
  --start-date 2026-02-10 \
  --end-date 2026-05-06 \
  --endpoint report_custom \
  --endpoint operation_log_search \
  --report-preset promotion_daily \
  --max-accounts-per-batch 20 \
  --max-dates-per-batch 3 \
  --max-requests-per-batch 120
```

This writes `data/runs/report_backfill_batch_plan/<timestamp>.json`. Every
batch contains an `openapi_http_execute` request draft, but each draft remains
`planned_only`, `external_api_enabled=false`, and `openapi_http.enabled=false`.

Export one disabled batch request from a batch plan with:

```bash
PYTHONPATH=src scripts/export_backfill_batch_request.py \
  --plan data/runs/report_backfill_batch_plan/20260506T150241Z.json \
  --batch-id batch_0001
```

This writes `data/requests/backfill/batch_0001.report-fetch.json`. The exported
request is still disabled and planned-only.

Run the backfill batch runner in dry-run mode with:

```bash
PYTHONPATH=src scripts/run_backfill_batches.py \
  --request configs/backfill-runner.disabled.example.json
```

For the one-time historical pull, use the same runner script with a reviewed
runner config that sets `execution.status=execute`,
`execution.external_api_enabled=true`, and `openapi_http.enabled=true`, plus the
OpenAPI runtime config:

```bash
PYTHONPATH=src scripts/run_backfill_batches.py \
  --config configs/runtime.openapi-execute.local.example.json \
  --request configs/backfill-runner.execute.local.json
```

That avoids editing every batch request by hand. The runner reads the batch plan
and activates each selected batch in memory.

Run the daily report pipeline with:

```bash
PYTHONPATH=src scripts/run_daily_report_pipeline.py \
  --config configs/runtime.example.json \
  --request configs/daily-report-pipeline.example.json
```

The default example uses `mock_openapi` for local verification and targets
yesterday. In production-style read-only fetching, the same script should use
`source=openapi_http_execute` plus `configs/runtime.openapi-execute.local.example.json`.
The disabled draft is `configs/daily-report-pipeline.openapi-http.disabled.example.json`;
it keeps `openapi_http.enabled=false` and `execution.external_api_enabled=false`.
Here `openapi_http` means the script-to-Giant-Engine network reader, and
`execution.external_api_enabled` is the explicit switch that allows read-only
network requests. When that draft is explicitly enabled later, the pipeline
first runs account discovery, meaning it finds which accounts spent money that
day, filters `stat_cost > 0`, where `stat_cost` means spend, and only then
fetches project, unit, and operation-log details for spending accounts. It does
not include `material_daily`, which means素材明细日报, in the daily main path
because that report can require many pages. The pipeline performs fetch -> data
sync -> optional material source preflight/sync -> daily learning and writes one
`daily_report_pipeline` artifact. `artifact` means the result JSON file left by
a script run. The default material source step is disabled, so it only records
the planned source-account material read through `/open_api/2/file/video/get/`
and makes zero external API calls.

For faster account discovery, use the disabled workbench draft:
`configs/daily-report-pipeline.workbench-discovery.disabled.example.json`.
It can call the business workbench account-list endpoint sorted by `stat_cost`,
stop after sorted rows reach zero spend, then pass only `spend > 0` advertiser
IDs into the same OpenAPI detail fetch. Workbench credentials must live in
`data/secrets/oceanengine-workbench-session.local.json`; copy the shape from
`configs/oceanengine-workbench-session.local.example.json`. The audit file
redacts `Cookie` and `x-csrftoken`, and the adapter falls back to the OpenAPI
account discovery path if the workbench request fails.

To validate only the workbench account discovery layer without fetching account
details, run:

```bash
PYTHONPATH=src scripts/run_workbench_account_discovery.py \
  --preflight \
  --config configs/runtime.example.json \
  --request configs/workbench-account-discovery.disabled.example.json
```

For a real read-only validation, keep `execution_enabled=false`, use the
read-only runtime gate, and enable only `workbench.enabled=true` in a local
request copy. This writes a `workbench_account_discovery` artifact containing
the `spend > 0` advertiser IDs and no project/unit/material detail data.

Check whether OceanEngine still accepts the report fields used by RoiBang-v2
with:

```bash
PYTHONPATH=src scripts/run_report_field_catalog.py \
  --preflight \
  --config configs/runtime.example.json \
  --request configs/report-field-catalog.disabled.example.json
```

This is a field health check: it asks OceanEngine for the current report field
list, saves it as a local artifact, and compares it with RoiBang-v2's built-in
report presets. It does not create, pause, delete, upload, or bind anything.

Material detail reports are split into a separate disabled draft:
`configs/report-fetch.material-daily.disabled.example.json`. Material detail
means per-material spend/click/conversion rows. Keep it out of the daily main
path unless a reviewed material workflow explicitly needs it.

Before enabling any real read-only HTTP fetch, write a local preflight plan:

```bash
PYTHONPATH=src scripts/run_daily_report_pipeline.py \
  --preflight \
  --config configs/runtime.example.json \
  --request configs/daily-report-pipeline.openapi-http.single-account.disabled.example.json
```

The single-account draft is intentionally disabled and fail-closed for normal
runs. `--preflight` only reads the local account pool and writes a
`daily_report_pipeline_preflight` artifact with candidate account count,
discovery request count, detail endpoint/preset list, and worst-case initial
request count. If a `material_source` block is present, it also includes the
planned source-account material request count. It makes zero external API calls.

Manage OceanEngine tokens inside RoiBang-v2 with the local token store:

```bash
PYTHONPATH=src scripts/exchange_oceanengine_auth_code.py \
  --store-file data/secrets/oceanengine-tokens.local.json
```

Provide `OCEANENGINE_APP_ID`, `OCEANENGINE_APP_SECRET`, and
`OCEANENGINE_AUTH_CODE` in the command environment. The script writes access and
refresh tokens to `data/secrets/`, which is ignored by git, and prints only
redacted metadata. Refresh and health check use:

```bash
PYTHONPATH=src scripts/refresh_oceanengine_token.py \
  --store-file data/secrets/oceanengine-tokens.local.json

PYTHONPATH=src scripts/check_oceanengine_token.py \
  --store-file data/secrets/oceanengine-tokens.local.json
```

HTTP fetch configs can use `openapi_http.token_store` with `auto_refresh=true`.
The disabled single-account example is
`configs/daily-report-pipeline.openapi-http.single-account.token-store.disabled.example.json`.

Generate a tiny local/mock report snapshot sample with:

```bash
PYTHONPATH=src scripts/fetch_report_snapshot.py \
  --request configs/report-fetch.mock-sample.example.json
```

This writes `data/snapshots/report/mock/<date>.json` using deterministic mock
rows from the account pool. It does not call OpenAPI.

Generate an OpenAPI read-only request plan with:

```bash
PYTHONPATH=src scripts/fetch_report_snapshot.py \
  --request configs/report-fetch.openapi-readonly.example.json
```

This writes `data/runs/report_fetch/<timestamp>.json` containing the allowed
GET request plan, redacted headers, report presets, and pagination starting
points. It does not fetch data, write snapshot files, or call external APIs.

Run the same OpenAPI-shaped path against a local fixture transport with:

```bash
PYTHONPATH=src scripts/fetch_report_snapshot.py \
  --request configs/report-fetch.openapi-mock-execute.example.json
```

This reads `data/fixtures/openapi-report-responses.sample.json`, follows the
same readonly plan/pagination executor, and writes a normalized snapshot under
`data/snapshots/report/openapi-mock/`. The fixture includes both promotion
report rows and operation logs. It still does not call external APIs.

The real HTTP transport shell is present but disabled by default. Its example
config is:

```text
configs/openapi-http.disabled.example.json
configs/report-fetch.openapi-http-execute.disabled.example.json
configs/material-source.openapi-http.disabled.example.json
```

It requires an explicit `enabled=true` plus a token source, writes redacted
JSONL audit records, and only accepts allowlisted GET requests. No scheduler job
or default report fetch config uses real HTTP yet. The CLI also requires runtime
`external_api_enabled=true` for `source=openapi_http_execute`; the default
runtime config keeps this off.

For a small real read-only trial, use the OpenAPI runtime example:

```text
configs/runtime.openapi-execute.local.example.json
```

It sets `external_api_enabled=true` but keeps `execution_enabled=false`, so it is
only suitable for read-only fetching. Before running, a batch request must be
manually reviewed and changed from planned-only to execute:

```json
"openapi_http": {
  "enabled": true,
  "token_env": "OCEANENGINE_ACCESS_TOKEN"
},
"execution": {
  "status": "execute",
  "external_api_enabled": true
}
```

Then run the fixed script:

```bash
PYTHONPATH=src scripts/fetch_report_snapshot.py \
  --config configs/runtime.openapi-execute.local.example.json \
  --request data/requests/backfill/batch_0001.report-fetch.json
```

This path is still limited to allowlisted GET endpoints and writes redacted HTTP
audit JSONL plus normalized snapshot files.

Run the current local report snapshot import with:

```bash
PYTHONPATH=src scripts/run_data_sync.py \
  --config configs/runtime.example.json \
  --request configs/data-sync.example.json
```

It imports `data/fixtures/report-snapshot.sample.json` into SQLite and emits a
run artifact. The snapshot can include account, project, and promotion operation
logs, which are stored for daily learning context. It does not call external
APIs.

## Material History And Rollups

Material daily metrics are stored in `material_daily_metrics`. This means the
per-day material report table: every row records one material's spend,
impressions, clicks, conversions, and related metrics for a date, account,
project, and unit. It uses `material_id` as the stable material identifier.

Run the disabled material history backfill preflight with:

```bash
PYTHONPATH=src scripts/run_material_history_backfill_batch.py \
  --preflight \
  --config configs/runtime.example.json \
  --request configs/material-history-backfill-batch.disabled.example.json
```

For reviewed read-only historical pulls, use the OpenAPI runtime gate and keep
`execution_enabled=false`. The batch runner first discovers spending accounts,
meaning accounts whose `stat_cost` is greater than 0 for the date. It then
fetches material daily details only for those accounts. It does not create,
pause, delete, change budgets, push materials, or run clean tasks.

After material daily rows exist in SQLite, build local material rollups with:

```bash
PYTHONPATH=src scripts/run_material_quality_rollup.py \
  --config configs/runtime.example.json \
  --request configs/material-quality-rollup.example.json
```

`material_metric_rollups` is the material summary table. It precomputes 1-day,
3-day, 7-day, 15-day, 30-day, and all-history windows from
`material_daily_metrics`, so later scripts can read summary rows directly
instead of asking AI to calculate them.

## Source Material Performance

The source material account is the project's material library account. It does
not spend by itself. RoiBang-v2 therefore calculates source-material
performance by matching `product_source_materials.material_id` against
`material_daily_metrics.material_id` from target accounts.

Run the source material performance rollup with:

```bash
PYTHONPATH=src scripts/run_product_source_material_rollup.py \
  --config configs/runtime.example.json \
  --request configs/product-source-material-rollup.example.json
```

`product_source_material_metric_rollups` is the source-material performance
summary table. It answers: which source-account materials actually spent money
after being pushed to target accounts, how much they spent, how many accounts
used them, and how many conversions they produced. It is local-only and makes
zero external API calls.

Build the source material acceptance report and candidate pool with:

```bash
PYTHONPATH=src scripts/run_source_material_candidate_pool.py \
  --config configs/runtime.example.json \
  --request configs/source-material-candidate-pool.example.json
```

`product_source_material_candidates` is the candidate pool table. It is the
ranked source-material list that future project-creation planning will read.
The default example only selects video materials from the all-history source
rollup and writes a run artifact. It does not call external APIs or perform any
business action.

## Daily Learning

After local data sync has populated SQLite, run:

```bash
PYTHONPATH=src scripts/run_daily_learning.py \
  --config configs/runtime.example.json \
  --request configs/daily-learning.example.json
```

It reads SQLite and emits account signals, material deltas, decision hints, and
operation log summaries, plus guardrails. It does not call external APIs or
produce executable actions.

## Strategy Plan

After daily learning has produced an artifact, run:

```bash
PYTHONPATH=src scripts/run_strategy_plan.py \
  --config configs/runtime.example.json \
  --request configs/requests/example.strategy-request.json \
  --policy policies/strategy.example.json
```

It writes a Phase 1 strategy plan with preflight and dry-run drafts, while
approval and execute remain disabled. By default it reads the latest
`daily_learning` artifact; if a latest `material_source` artifact exists, it
also converts missing-material evidence into `plan_material_provision`
recommendations. These are plan-only recommendations and do not produce live
push, bind, upload, create, pause, delete, or update payloads.

Run the Phase 1 strategy preflight with:

```bash
PYTHONPATH=src scripts/run_strategy_preflight.py \
  --config configs/runtime.example.json
```

It reads the latest `strategy_plan` artifact by default and checks that the plan
is still Phase 1, plan-only, has no actions, has no dry-run payloads, and has
complete material provision recommendation fields. It writes a
`strategy_preflight` artifact with lineage back to the source plan and never
approves execution in Phase 1.

Run the Phase 1 strategy dry-run with:

```bash
PYTHONPATH=src scripts/run_strategy_dry_run.py \
  --config configs/runtime.example.json \
  --policy policies/strategy.example.json
```

It reads the latest `strategy_plan` and `strategy_preflight` artifacts, requires
preflight to have passed, and converts plan-only material provision
recommendations into non-executable candidate tasks. Candidate tasks have
`executable=false` and `live_api_payloads=[]`; this step still cannot execute
or approve any business action. It blocks if the plan and preflight artifacts
do not share the same `plan_id` and `target_date`.

Run the Phase 1 strategy approval record with:

```bash
PYTHONPATH=src scripts/run_strategy_approval.py \
  --config configs/runtime.example.json \
  --policy policies/strategy.example.json
```

It reads the latest `strategy_dry_run` artifact and records the policy decision.
In Phase 1 the approval mode is `phase1_record_only`: even when the policy would
approve the dry-run, the artifact still has `approved=false` and
`execute_allowed=false`. It also requires dry-run lineage to include matching
plan, preflight, and target-date references.

Run the Phase 1 strategy execute hard-block with:

```bash
PYTHONPATH=src scripts/run_strategy_execute.py \
  --config configs/runtime.example.json \
  --policy policies/strategy.example.json
```

It reads the latest `strategy_approval` artifact and writes a
`strategy_execute` artifact with `status=blocked`,
`reason=phase1_execute_disabled`, `execution_enabled=false`,
`external_api_calls=0`, `approved_for_execute=false`, and no actions. This keeps
the future `request -> strategy -> preflight -> dry-run -> approve -> execute`
chain complete while still making real execution impossible in Phase 1. The
artifact records lineage back to approval, dry-run, preflight, and plan; missing
or mismatched `plan_id` / `target_date` references fail closed.

## Scheduler Registry

Validate the Phase 1 scheduled job registry with:

```bash
PYTHONPATH=src scripts/validate_scheduler_jobs.py \
  --registry configs/scheduler/roibang-v2.jobs.example.json
```

The registry describes fixed scripts and result contracts. It does not ask AI to
run commands.

Render cron and launchd examples with:

```bash
PYTHONPATH=src scripts/render_scheduler_templates.py \
  --registry configs/scheduler/roibang-v2.jobs.example.json \
  --output-dir scheduler
```

This writes example files under `scheduler/cron/` and `scheduler/launchd/`.
Rendering templates does not install, load, or execute any scheduled job.

Run one fixed scheduler job through the unified runner with:

```bash
PYTHONPATH=src scripts/run_scheduler_job.py \
  --job-id roibang-material-sync
```

The runner reads the registry, executes only the configured foreground script,
captures stdout/stderr/exit code, validates the resulting artifact contract,
and writes a scheduler execution result under `data/runs/scheduler/<job-id>/`.

Validate the latest artifact for a scheduled job with:

```bash
PYTHONPATH=src scripts/validate_run_artifact.py \
  --job-id roibang-daily-report-pipeline
```

This reads the job's `result_contract` from the scheduler registry and checks
the latest JSON artifact. It does not run the job.
