# RoiBang-v2

RoiBang-v2 is a script-first automation system for ad operation workflows.

This repository starts from a clean v2 architecture. The old project at
`/Users/hongen/Codes/RoiBang` is reference-only and must not be used as the
active development target.

## Current Phase

Phase 2 preparation has started. This stage is still review-only: it can add
field mapping prep artifacts, template slot review artifacts, project naming
rule checks, scripts, and tests, but it must not perform real creation or call
creation APIs.

Current Phase 2 preparation closeout notes live in
`docs/phase-2-preparation-closeout.md`.

Run the current provider field mapping preparation pack with:

```bash
PYTHONPATH=src scripts/run_create_phase2_provider_mapping_prep.py \
  --config configs/runtime.example.json \
  --policy policies/strategy.example.json
```

It writes a local `create_phase2_provider_mapping_prep` artifact with
`execution_enabled=false`, `external_api_calls=0`, and `actions=[]`. More notes
live in `docs/phase-2-preparation.md`.

Run the current template slot preparation pack with:

```bash
PYTHONPATH=src scripts/run_create_phase2_template_slot_prep.py \
  --config configs/runtime.example.json \
  --request configs/requests/example.create-request.json \
  --policy policies/strategy.example.json
```

It checks future create defaults, such as project type, budget, pricing,
inventory, unit count, and material count, while still writing only a local
review artifact. It also writes `product_template_catalog`, meaning the current
勇者突进微信小游戏 template list has four project templates: `微小每付男`,
`微小每付通投`, `微小每付7R男`, and `微小每付7R通投`. All four fix the
optimization goal to 付费. The two `微小每付` templates do not choose a deep
target and do not fill ROI, meaning 回本目标; the two `微小每付7R` templates
choose 7日ROI and require an ROI value. 男 templates fix gender to 男; 通投
templates fix gender to 不限. All four currently fix age to 不限. The front-end
field named 深度优化方式 is recorded as `deep_optimization_method`, and its
provider field is `deep_bid_type`, meaning the platform API field name. It also writes
`template_confirmation_groups`, meaning the 12 template items are grouped into
fixed defaults, per-account values, and fixed-strategy selections, so the next
manual review is easier to read. It also writes `template_confirmation_draft`,
meaning a 12-row confirmation draft with the current value, source, pending
confirmation status, and suggested decision for each template item. It also
writes `template_confirmation_checklist`, meaning the same 12 items in plain
Chinese labels for manual review.

Run the template confirmation record pack with:

```bash
PYTHONPATH=src scripts/run_create_phase2_template_confirmation_pack.py \
  --config configs/runtime.example.json
```

It reads the latest template slot preparation artifact and writes
`create_phase2_template_confirmation_pack`, meaning a local pending-confirmation
record for the same 12 items. This pack sets `required_user_input_now=true`,
meaning it is ready for manual confirmation, but it still keeps
`execution_enabled=false`, `external_api_calls=0`, and `actions=[]`.

Run the 勇者突进 manual create preview with:

```bash
PYTHONPATH=src python3 scripts/run_create_phase2_yzt_config_check.py \
  --config configs/runtime.example.json \
  --preview-config configs/create/yzt-wx-mini-game.preview.example.json \
  --policy policies/strategy.example.json
```

This checks the manual config before preview. It catches missing accounts,
placeholder accounts, budget outside the policy range, zero project or unit
count, unknown templates, and missing ROI coefficient for 7R templates. It
writes only a local
`create_phase2_yzt_config_check` artifact with `execution_enabled=false`,
`external_api_calls=0`, and `actions=[]`.
The example config uses a safe local budget of `1000` so the quick check can
pass the budget rule under the current policy. The quick check still stops on
the placeholder accounts until they are replaced with real advertiser IDs.
Full rehearsal may still stop later if the local material pool has not been
synced.

Check the configured accounts against the local account pool with:

```bash
PYTHONPATH=src python3 scripts/run_create_phase2_yzt_account_pool_check.py \
  --config configs/runtime.example.json \
  --preview-config configs/create/yzt-wx-mini-game.preview.example.json \
  --policy policies/strategy.example.json
```

This reads only local SQLite and writes `create_phase2_yzt_account_pool_check`.
It tells which configured accounts are found or missing for 勇者突进/WECHAT_GAME,
and still keeps `execution_enabled=false`, `external_api_calls=0`, and
`actions=[]`.

Check the local material pool capacity with:

```bash
PYTHONPATH=src python3 scripts/run_create_phase2_yzt_material_pool_check.py \
  --config configs/runtime.example.json \
  --preview-config configs/create/yzt-wx-mini-game.preview.example.json \
  --policy policies/strategy.example.json
```

This reads only local SQLite and writes `create_phase2_yzt_material_pool_check`.
It compares required materials for the current config with usable local
candidate materials, and still keeps `execution_enabled=false`,
`external_api_calls=0`, and `actions=[]`.

Run all preparation checks with one command:

```bash
PYTHONPATH=src python3 scripts/run_create_phase2_yzt_preparation_check.py \
  --config configs/runtime.example.json \
  --preview-config configs/create/yzt-wx-mini-game.preview.example.json \
  --policy policies/strategy.example.json
```

This runs config check, account-pool check, and material-pool check in order. It
writes `create_phase2_yzt_preparation_check`, keeps every sub-check local, and
still has `execution_enabled=false`, `external_api_calls=0`, and `actions=[]`.
It also writes `operator_guide`, meaning a direct operation guide: if checks
fail, it lists the fix order; if checks pass, it prints the full dry-chain
command to run next.

For real operator use, prepare a private local config with the helper script:

```bash
PYTHONPATH=src python3 scripts/run_create_phase2_yzt_local_config_prepare.py
```

The helper copies the safe `example` config to
`configs/create/yzt-wx-mini-game.preview.local.json` only when the local file
does not already exist. `example` means 示例配置; `local` means 本地私有配置.
It prints `operator_guide`, meaning 操作员填写指南, including field meanings and
the next preparation, preview, and dry-chain commands.

Then edit `configs/create/yzt-wx-mini-game.preview.local.json` and replace the
placeholder accounts with real account IDs. This `*.local.json` path is ignored
by git, meaning it is not meant to be committed. 不要提交真实账户.

```bash
PYTHONPATH=src python3 scripts/run_create_phase2_yzt_create_preview.py \
  --config configs/runtime.example.json \
  --preview-config configs/create/yzt-wx-mini-game.preview.example.json \
  --policy policies/strategy.example.json
```

The preview config is the file a human can edit before live create development.
It only keeps the fields that should be filled each time: project template,
owner, target date, batch generated time, default budget, default project count,
default unit count, ROI coefficient when the chosen template needs it, and
target accounts. The script keeps the fixed 勇者突进 fields inside the preview
result, including product, platform, source advertiser, material pool, material
requirements, field defaults, marketing scene, optimization goal, age, and
effective-touch URL source. It also writes `manual_config_contract`, meaning a
Chinese field guide for the manual config, and `preview_checks`, meaning local
checks for safety, template selection, target accounts, budget, ROI coefficient,
unique project names, and fixed effective-touch URL. It also writes
`standard_create_request`, meaning the normal create-request shape that can
enter the fixed create chain, and `chain_handoff`, meaning the next safe steps:
create request, strategy plan, preflight, and dry-run. It still writes only a
local `create_phase2_yzt_create_preview` artifact with `execution_enabled=false`,
`external_api_calls=0`, and `actions=[]`.

Run the 勇者突进 full dry create chain with:

```bash
PYTHONPATH=src python3 scripts/run_create_phase2_yzt_dry_chain.py \
  --config configs/runtime.example.json \
  --preview-config configs/create/yzt-wx-mini-game.preview.example.json \
  --policy policies/strategy.example.json
```

This is a complete local rehearsal, not real creation. It runs preview,
create-request recording, strategy plan, preflight, provider field-map check,
and dry-run in order. It writes `create_phase2_yzt_dry_chain`, including
`chain_steps` for the step list, `artifacts` for the generated JSON files,
`blocking_summary` for the plain blocked reason, and `human_next_steps` for the
next manual fixes in Chinese. It still keeps `execution_enabled=false`,
`external_api_calls=0`, `approved_for_execute=false`, and `actions=[]`.

Run the current project naming preparation pack with:

```bash
PYTHONPATH=src scripts/run_create_phase2_project_naming_prep.py \
  --config configs/runtime.example.json \
  --request configs/requests/example.create-request.json \
  --policy policies/strategy.example.json
```

It generates sample project names and compares the current v2 rule with the old
project naming reference. It still writes only a local review artifact.

Run the Phase 2 preparation summary with:

```bash
PYTHONPATH=src scripts/run_create_phase2_preparation_summary.py \
  --config configs/runtime.example.json
```

It combines field mapping, template slots, and project naming into one local
summary. It also writes `remaining_review_groups`, meaning the remaining items
are split into “needs provider evidence”, which means platform field evidence
still needs to be checked, and “needs human decision”, which means fixed rules
or defaults still need manual confirmation. The summary still keeps real
creation closed.

Phase 1 only builds safe local capabilities:

- data sync framework
- daily learning review
- material history backfill and rollups
- source material library sync and candidate planning
- strategy plan generation
- create request, create strategy plan, create preflight, create field mapping
  review pack, create template slot review pack, create dry-run, create
  approval record, create plan snapshot, and create execute hard-block

Phase 1 does not perform real create, pause, delete, schedule-emptying, or
budget-changing actions.

## Core Rule

Business actions must be deterministic script executions. Scripts read only
JSON config, JSON policy, and SQLite state. AI may write scripts, review result
JSON, and update strategy JSON, but AI must not make live operational decisions
at execution time.

## AI Boundary

AI participates only in code development and requirement discussion, data review
that outputs strategy JSON, and next-day review that summarizes the prior
strategy JSON effect and updates strategy JSON. Scheduled business workflows are
fixed script executions. If a fixed script fails, treat it as a bug in code,
config, policy, or data, then fix it with tests; do not let AI make runtime
business decisions.

## Safety Chain

Future creation workflows must keep this chain:

`request -> strategy -> preflight -> dry-run -> approve -> execute`

Phase 1 represents the full chain with local artifacts, while execute remains a
hard block.

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

## Create Project Safety Chain

The project-creation chain starts with local artifacts only:

`create_request -> create_strategy_plan -> create_preflight -> create_dry_run -> create_approval -> create_plan_snapshot -> create_execute`

These steps do not call external APIs and do not produce live create payloads.
The strategy plan reads
`product_source_material_candidates` by `pool_key` and assigns video
`material_id` rows to planned project/unit combinations. `material_id` remains
the material identity; `source_video_id` is carried only as source-account
context.
Project names are generated by `create_strategy_plan.project_naming`, meaning
the project-name rule in `policies/strategy.example.json`, and preflight can
enforce `create_preflight.project_name_pattern`, meaning the required project
name format. The current rule is:

```text
月日_归属_游戏名_项目模板名_批次码_序号
```

The batch code is generated once from request id, create date, product, project
type, account list, and second-level generated time. It uses a hash, meaning a
fixed short code made from those fields, and then reuses that code through
preflight, dry-run, approval, and execute. This keeps naming deterministic,
meaning the same input always produces the same name, inside fixed scripts
instead of relying on runtime AI choices, meaning AI decisions made while a
business script is running.

Record a create request with:

```bash
PYTHONPATH=src scripts/run_create_request.py \
  --config configs/runtime.example.json \
  --request configs/requests/example.create-request.json
```

Build the create strategy plan from the latest create request:

```bash
PYTHONPATH=src scripts/run_create_strategy_plan.py \
  --config configs/runtime.example.json \
  --policy policies/strategy.example.json
```

Run create preflight checks:

```bash
PYTHONPATH=src scripts/run_create_preflight.py \
  --config configs/runtime.example.json \
  --policy policies/strategy.example.json
```

The preflight checks account-pool membership, material counts, budget limits,
project names, required field defaults, and Phase 1 plan-only guardrails.

Run the provider field map check:

```bash
PYTHONPATH=src scripts/run_create_provider_field_map_check.py \
  --config configs/runtime.example.json \
  --policy policies/strategy.example.json
```

This step reads `provider_field_map_path`, meaning the configured channel field
map JSON path, and writes `create_provider_field_map_check`, meaning a local
field-mapping review artifact. It reports `missing_provider_fields`, meaning
internal fields that still do not have an official channel field name, and
`unverified_fields`, meaning fields that have not been manually checked. It
also reports `missing_required_fields`, meaning required internal fields that
are absent from the configured mapping entirely; for example `material_id`,
meaning the material's primary identity, must appear in material binding. It
reports `duplicate_internal_fields`, meaning repeated internal fields in the
same operation, `duplicate_provider_fields`, meaning two internal fields map to
the same channel field inside one operation, and `unknown_internal_fields`,
meaning fields that are not part of the Phase 1 create schema. These catch
common JSON editing mistakes before dry-run reads the mapping. Duplicate channel
fields are blocked because one value would overwrite another when the provider
payload draft is shaped.
It also reports provider and version mismatches, meaning the field map's
`provider` and `field_mapping_version` must match
`create_dry_run.provider_adapter` in `policies/strategy.example.json`. This
prevents a fixed script from using a field map for the wrong channel or wrong
mapping version.
It also writes `provider_field_map_digest`, meaning a SHA-256 fingerprint of
the entire field map JSON; SHA-256 is a standard one-way checksum used here to
prove two artifacts looked at the same field map content.
This check keeps `execution_enabled=false`, `external_api_calls=0`, and
`actions=[]`, meaning it cannot create or change anything.

Run the create field mapping review pack:

```bash
PYTHONPATH=src scripts/run_create_field_mapping_review_pack.py \
  --config configs/runtime.example.json \
  --policy policies/strategy.example.json
```

This step writes `create_field_mapping_review_pack`, meaning a local review
package for future create API fields. A review package is a checklist-style JSON
file: it groups fields by operation, meaning project creation, unit creation,
and material binding, and shows each internal RoiBang-v2 field, its provider
field, meaning the official channel API field name, its source, and its review
status. It does not require the user to fill anything now:
`required_user_input_now=false`, meaning the current step only builds the
framework. Empty provider fields are reported as `needs_provider_field`, meaning
the official channel field still needs to be confirmed later. Rows with a
provider field but `verified=false` are reported as `needs_verification`,
meaning the field still needs human confirmation before live execution can be
considered.
The artifact also carries `review_contract`, meaning the count summary for
fields that need provider names or verification, and
`provider_readiness_contract`, meaning the live-execution readiness gate. This
step keeps `execution_enabled=false`, `external_api_calls=0`, and `actions=[]`,
meaning it cannot create projects or call external APIs.

Run the create template slot review pack:

```bash
PYTHONPATH=src scripts/run_create_template_slot_review_pack.py \
  --config configs/runtime.example.json \
  --request configs/requests/example.create-request.json \
  --policy policies/strategy.example.json
```

This step writes `create_template_slot_review_pack`, meaning a local review
package for fixed create-template slots. A slot is one position in a future
hardcoded template, such as project name template, project type, daily budget,
field defaults, units per project, material type, materials per unit, and
`material_id` selection. It records each slot's source, meaning whether the
value comes from create request, policy, or the candidate table, and a
`value_preview`, meaning a safe local preview such as `<per-target-account>` or
`<selected-by-create-strategy-plan>`.
This is still only a framework: `required_user_input_now=false`, meaning the
user does not need to fill template values at this step. Slots are marked
`needs_review`, meaning they should be reviewed before live creation work is
opened, but they do not grant execution permission. The artifact also carries
`template_contract`, meaning the slot-count and missing-value summary. It keeps
`execution_enabled=false`, `external_api_calls=0`, and `actions=[]`, meaning it
cannot create projects or call external APIs.

Run the create dry-run:

```bash
PYTHONPATH=src scripts/run_create_dry_run.py \
  --config configs/runtime.example.json \
  --policy policies/strategy.example.json
```

The fixed dry-run script reads the latest `create_provider_field_map_check`
artifact, meaning the most recent field-mapping check output, and records it in
lineage. It also checks that `provider_field_map_contract`, meaning the field
mapping summary, and `provider_readiness_contract`, meaning the channel
execution-readiness result, match what dry-run reads from the configured JSON.
It also checks `provider_field_map_digest`, meaning the exact field-map content
fingerprint. If any of these do not match, dry-run is blocked.

The dry-run emits non-executable project/unit/material candidate tasks with
`executable=false`, `live_api_payloads=[]`, `execution_enabled=false`, and
`external_api_calls=0`. It also emits `payload_schema`, meaning the internal
request-field structure draft for future project, unit, and material-binding
payloads. This schema is `schema_only`, meaning it records required fields and
field sources but does not generate real API request bodies. Dry-run also
writes `payload_contract`, meaning the required-field check result for the
future create payload. If a required project, unit, or material-binding field is
missing, dry-run is blocked. It also writes `idempotency_contract`, meaning the
duplicate-check result for idempotency keys. An idempotency key is a stable
fingerprint for one planned create operation, used later to avoid repeating the
same project, unit, or material-binding action if a script is retried. It fails
closed unless create preflight passed and the lineage matches the create
strategy plan. When run through the fixed script, dry-run also records
`idempotency_ledger`, meaning the local SQLite ledger of these planned keys.
The ledger status is `planned`, meaning no create action has happened.
Dry-run now emits `redacted_payload_drafts`, meaning non-executable and
sanitized request-body drafts for review, plus `payload_draft_contract`, meaning
the count and safety check for those drafts. These drafts use the internal
Phase 1 schema only; they are not a provider adapter, meaning they are not yet
the final Giant Engine API field mapping.
Dry-run also emits `provider_payload_drafts`, meaning provider-shaped request
drafts, through `provider_adapter`, meaning the disabled mapping layer for a
specific ad platform. This adapter is marked `mapping_verified=false`, meaning
the mapping has not yet been confirmed against the provider's official create
API fields, and `executable=false`, meaning it cannot be sent to the provider.
Each provider draft also records `field_mapping_applied`, meaning whether the
internal RoiBang-v2 payload fields were actually converted to provider field
names. Field mapping is applied only when both the provider adapter and
`provider_field_map_contract`, meaning the field-map verification result, are
verified. If either side is not verified, dry-run keeps the internal field names
in the provider draft and leaves `field_mapping_applied=false`, meaning the
draft is still useful for review but must not be mistaken for a final API
request body.
When field mapping is requested, dry-run also records
`unmapped_payload_fields`, meaning internal payload fields that do not have a
provider-field mapping. `provider_adapter_contract`, meaning the adapter safety
summary, counts these fields, and `provider_readiness_contract`, meaning the
future execution-readiness gate, stays not ready until every provider payload
draft is fully mapped. This prevents a newly added internal field from slipping
into a provider-shaped draft under its internal name.
Dry-run also writes `provider_payload_draft_digest`, meaning a SHA-256
fingerprint of the emitted provider payload drafts. This proves later approval,
snapshot, and execute hard-block artifacts are referring to the same dry-run
request-shape preview. It does not grant execution permission; it is only a
traceability check.
It also emits `provider_field_map`, meaning a placeholder field map from
RoiBang-v2 internal fields to provider fields. All provider fields are blank and
`verified=false`, meaning no official field mapping has been confirmed yet. Its
source is `phase1_placeholder_no_legacy_reference`, meaning it does not use the
old project templates.
When `create_dry_run.provider_field_map_path` is configured in
`policies/strategy.example.json`, the fixed script reads that JSON file instead
of generating the built-in placeholder. The example file is
`configs/provider-field-maps/oceanengine.create.phase1.example.json`, meaning a
reviewable configuration scaffold for Giant Engine create fields. It is still
unverified by default: every `provider_field` is blank and every
`verified=false`, meaning no official create API field has been confirmed. If
the configured JSON file is missing or malformed, the script falls back to an
unverified placeholder, meaning the chain stays blocked rather than guessing.
The field map is considered verified only when every required row has a
provider field, every row has `verified=true`, meaning that single field has
been checked, and the top-level `mapping_verified=true`, meaning the whole
mapping file has been manually approved as one complete set. This prevents a
half-reviewed mapping file from becoming ready just because individual rows were
filled in.
Dry-run also emits `provider_readiness_contract`, meaning the provider
execution-readiness gate. It summarizes whether the provider adapter, meaning
the disabled channel-specific payload mapping layer, and provider field map,
meaning the internal-field to official-field checklist, are verified enough for
future live execution. In Phase 1 it reports `ready_for_live_execute=false`,
meaning real creation is still not allowed. Even if the field map is fully
verified later, `create_execute` remains hard-blocked in Phase 1 until the phase
policy changes.

Run the create approval record:

```bash
PYTHONPATH=src scripts/run_create_approval.py \
  --config configs/runtime.example.json \
  --policy policies/strategy.example.json
```

In Phase 1 the approval mode is `phase1_record_only`. The script may record
that policy would approve the dry-run, but it still writes `approved=false` and
`execute_allowed=false`. It also records `candidate_task_digest`, meaning a
SHA-256 fingerprint, where SHA-256 is a standard one-way checksum, of the
dry-run candidate tasks, so later steps can prove they are looking at the same
planned task list.
It also carries `provider_readiness_contract`, meaning the automatic approval
record still preserves the channel-readiness result and does not turn it into
permission to execute. It also carries `provider_field_map_digest`, meaning the
same field-map content fingerprint produced by dry-run. Its lineage also carries
`create_provider_field_map_check`, meaning the field-mapping check artifact that
dry-run used, so approval can be traced back to the same checked field map. It
also carries `provider_payload_draft_digest`, meaning the exact provider payload
draft fingerprint from dry-run.

Run the create plan snapshot:

```bash
PYTHONPATH=src scripts/run_create_plan_snapshot.py \
  --config configs/runtime.example.json
```

The snapshot is review-only, meaning it is a readable JSON summary for later
human and AI review. It lists target accounts, planned projects, planned units,
`material_id` values, upstream lineage references, and the same
`candidate_task_digest`. It also carries `payload_contract`, meaning reviewers
can see whether the future create-payload fields were complete without opening
the dry-run artifact, and `idempotency_contract`, meaning reviewers can see
whether duplicate operation keys were detected. It also carries
`idempotency_ledger`, meaning reviewers can see whether the planned keys were
recorded locally, and `payload_draft_contract`, meaning reviewers can verify
that the request-body drafts stayed non-executable and redacted. It also
carries `provider_adapter_contract`, meaning reviewers can see that provider
mapping is still unverified, and `provider_field_map_contract`, meaning
reviewers can see how many fields still need provider-field confirmation. It
also carries `provider_readiness_contract`, meaning reviewers can see the exact
future-execution blockers without opening the dry-run artifact, and
`provider_field_map_digest`, meaning the exact field-map content fingerprint.
It also carries `provider_payload_draft_digest`, meaning reviewers can verify
the provider request-shape preview did not change between dry-run and snapshot.
Its lineage also carries `create_provider_field_map_check`, meaning reviewers
can trace the snapshot back to the exact field-mapping check used by dry-run.
It writes `actions=[]`, meaning it cannot create, pause, delete, or change
anything.

Run the create execute hard-block:

```bash
PYTHONPATH=src scripts/run_create_execute.py \
  --config configs/runtime.example.json \
  --policy policies/strategy.example.json
```

In Phase 1 this always writes `status=blocked`,
`reason=phase1_execute_disabled`, `executed_task_count=0`, and `actions=[]`.
It carries the same `payload_schema`, while `live_api_payloads` remains empty,
meaning no real create payloads are produced. It exists to keep the future
execute link in the chain fixed without allowing real creation.
It also carries `provider_readiness_contract`, meaning the execute hard-block
records whether channel mapping is ready before future live execution can ever
be considered, and `provider_field_map_digest`, meaning the exact field-map
content fingerprint. Its lineage also carries `create_provider_field_map_check`,
meaning even the blocked execute artifact can be traced back to the same
field-mapping check. It also carries `provider_payload_draft_digest`, meaning
the blocked execute artifact can be compared against the exact dry-run provider
payload draft preview.

Run the create chain replay check:

```bash
PYTHONPATH=src scripts/run_create_chain_replay.py \
  --config configs/runtime.example.json
```

This step writes `create_chain_replay`, meaning a local replay check for the
whole create chain from request through execute hard-block. Replay means the
script rereads the existing JSON artifacts and verifies they still describe the
same plan; it does not create projects and does not call external APIs. It
checks `lineage`, meaning upstream artifact references, `candidate_task_digest`,
meaning the planned task-list fingerprint, `provider_field_map_digest`, meaning
the field-map content fingerprint, and `provider_payload_draft_digest`, meaning
the provider request-shape preview fingerprint. It also writes
`artifact_identity_contract`, meaning each artifact's `workflow` name and key
`status` value must match the expected create-chain step, so a wrong JSON file
cannot be silently replayed as the right step. It also writes
`phase1_safety_contract`, meaning the chain-wide safety check that every
artifact keeps `execution_enabled=false`, `external_api_calls=0`, and
`actions=[]`. If any fingerprint or safety value differs, replay writes
`status=blocked`, meaning the chain must be fixed before any future execute
phase can be considered.
The fixed CLI scripts can be run in order from `run_create_request.py` through
`run_create_chain_replay.py`, meaning the same local artifact handoff that a
future scheduler run will use is covered by tests.

Run the create chain manifest:

```bash
PYTHONPATH=src scripts/run_create_chain_manifest.py \
  --config configs/runtime.example.json
```

This step writes `create_chain_manifest`, meaning a local chain summary that
lists the artifact paths for request, strategy plan, preflight, dry-run,
approval, snapshot, execute hard-block, and replay. A manifest is a checklist:
it does not create projects and does not call external APIs. It reports
`status=ready` only when replay has `status=passed`, meaning every previous
artifact already proved the same lineage, fingerprints, and Phase 1 safety
values. It carries `candidate_task_digest`, meaning the planned task-list
fingerprint, `provider_field_map_digest`, meaning the provider field-map
fingerprint, and `provider_payload_draft_digest`, meaning the provider
request-shape preview fingerprint. It also carries `phase1_safety_contract`,
meaning the replayed proof that `execution_enabled=false`,
`external_api_calls=0`, and `actions=[]` stayed true across the chain.
Run the create readiness matrix:

```bash
PYTHONPATH=src scripts/run_create_readiness_matrix.py \
  --config configs/runtime.example.json
```

This step writes `create_readiness_matrix`, meaning a local readiness table for
the create chain. The matrix summarizes gates, meaning required checkpoints,
including provider field map, field mapping review pack, template slot review
pack, preflight, dry-run, chain replay, and chain manifest. It reports
`ready_for_live_execute=false` while any gate is still blocking. A blocking gate
is a checkpoint that is not ready yet, such as unverified provider fields or
template slots that still need review. The matrix can have `ok=true`, meaning
the local summary was generated successfully, while still having
`status=not_ready`, meaning real creation is not allowed.
It keeps `execution_enabled=false`, `external_api_calls=0`, and `actions=[]`,
meaning it cannot create projects or call external APIs.

Run the live execute phase gate:

```bash
PYTHONPATH=src scripts/run_create_live_execute_phase_gate.py \
  --config configs/runtime.example.json \
  --policy policies/strategy.example.json
```

This step writes `create_live_execute_phase_gate`, meaning a local phase gate
for future live creation development. A phase gate is a hard checkpoint that
decides whether the project may move from Phase 1 planning into a later live
execute development phase. It is not `create_execute`, meaning it does not call
the create API and does not create projects.
In Phase 1 it always reports `status=blocked`,
`live_execute_development_allowed=false`, and `live_execute_allowed=false`.
Even if the readiness matrix later reports `ready_for_live_execute=true`, this
gate still blocks while the policy phase is `phase1`, meaning the phase itself
must change before real execute development can start. If a Phase 1 policy tries
to set `allow_live_execute_development=true` or `allow_live_execute=true`, the
gate writes a violation, meaning the config is unsafe and must be fixed.
It keeps `execution_enabled=false`, `external_api_calls=0`, and `actions=[]`,
meaning it cannot create projects or call external APIs.

Run the live payload adapter scaffold:

```bash
PYTHONPATH=src scripts/run_create_live_payload_adapter_scaffold.py \
  --config configs/runtime.example.json \
  --policy policies/strategy.example.json
```

This step writes `create_live_payload_adapter_scaffold`, meaning the disabled
outer shell for a future live payload adapter. A payload adapter is code that
will eventually convert RoiBang-v2 internal create drafts into provider request
bodies. In Phase 1 this scaffold only defines the interface, meaning the input
and output shape, and the safety contract, meaning the values that prove it
cannot execute.
It reads the dry-run provider payload drafts, meaning non-executable request
shape previews, and the live execute phase gate, meaning the local phase
permission artifact. It does not fill real provider templates, does not produce
`live_payloads`, meaning sendable API request bodies, and does not produce
`executable_payloads`, meaning requests allowed to be sent. If policy tries to
turn on live payload generation in Phase 1, the scaffold writes a violation.
It keeps `live_payload_generation_enabled=false`, `live_payloads=[]`,
`executable_payloads=[]`, `execution_enabled=false`, `external_api_calls=0`,
and `actions=[]`, meaning it cannot create projects or call external APIs.

Run the adapter review pack:

```bash
PYTHONPATH=src scripts/run_create_adapter_review_pack.py \
  --config configs/runtime.example.json
```

This step writes `create_adapter_review_pack`, meaning a local review package
for the disabled live payload adapter scaffold. It summarizes the scaffold's
input contract, meaning what upstream artifact it reads, output contract,
meaning what it is allowed to emit, safety contract, meaning the no-execution
proof, and blocking reasons, meaning why live payload development is still not
open. It does not request user input now: `required_user_input_now=false`,
meaning the current step only prepares a readable review artifact.
The review pack rejects unsafe scaffold output if `live_payloads`, meaning
sendable request bodies, or `executable_payloads`, meaning requests allowed to
be sent, are non-empty. It keeps `execution_enabled=false`,
`external_api_calls=0`, and `actions=[]`, meaning it cannot create projects or
call external APIs.

Run the create chain index:

```bash
PYTHONPATH=src scripts/run_create_chain_index.py \
  --config configs/runtime.example.json
```

This step writes `create_chain_index`, meaning a local index of the whole
create chain. An index is a directory-style JSON file that records each
workflow's artifact path, status, ok flag, and safety values. It covers the
chain from `create_request`, meaning the original create request, through
`create_adapter_review_pack`, meaning the final adapter review artifact.
It also writes `safety_contract`, meaning the chain-wide check that
`execution_enabled=false`, `external_api_calls=0`, `actions=[]`, no live
execute permission, and no live payloads all remain true. This file is for
review, replay, and troubleshooting; it does not create projects and does not
call external APIs.

Run the create chain final report:

```bash
PYTHONPATH=src scripts/run_create_chain_final_report.py \
  --config configs/runtime.example.json
```

This step writes `create_chain_final_report`, meaning a human-readable local
summary for the whole create chain. It reads `create_chain_index`, meaning the
machine directory of artifacts, `create_readiness_matrix`, meaning the gate
readiness table, `create_live_execute_phase_gate`, meaning the phase transition
blocker, and `create_adapter_review_pack`, meaning the adapter safety review.
It reports `overall_status`, meaning the high-level business conclusion,
`business_summary`, meaning a short plain-language summary, `blocking_reasons`,
meaning why real creation is still blocked, and `recommended_next_steps`,
meaning the next review actions. It keeps `required_user_input_now=false`,
`execution_enabled=false`, `external_api_calls=0`, and `actions=[]`, meaning it
cannot create projects or call external APIs.

Run the Phase 1 create acceptance checklist:

```bash
PYTHONPATH=src scripts/run_create_phase1_acceptance_checklist.py \
  --config configs/runtime.example.json
```

This step writes `create_phase1_acceptance_checklist`, meaning a local
acceptance checklist for closing the safe front half of the create chain.
An acceptance checklist is a pass/fail list that checks whether the local
artifacts are complete, the safety contract still blocks real creation, the
final report exists, and no human input is required during scheduled runs.
It reports `phase1_acceptance_status`, meaning whether Phase 1 can be accepted
as a safe blocked baseline, `checklist`, meaning each individual acceptance
item, `accepted_items`, meaning checks that passed, and `blocking_items`,
meaning checks that still block acceptance. It still keeps
`execution_enabled=false`, `external_api_calls=0`, and `actions=[]`, meaning it
cannot create projects or call external APIs.

Run the Phase 1 create baseline freeze:

```bash
PYTHONPATH=src scripts/run_create_phase1_baseline_freeze.py \
  --config configs/runtime.example.json
```

This step writes `create_phase1_baseline_freeze`, meaning a local frozen
checkpoint for the safe front half of the create chain. A baseline freeze is a
stable record that says which acceptance result, final report, and chain index
were used as the Phase 1 reference point. It reports `baseline_id`, meaning the
fixed name of the baseline, `baseline_digest`, meaning a SHA-256 digest for
rechecking the same baseline content later, `freeze_contract`, meaning the
safety conditions required before the baseline can freeze, and
`source_artifact_paths`, meaning the local JSON files used as evidence. It
still keeps `execution_enabled=false`, `external_api_calls=0`, and `actions=[]`,
meaning it cannot create projects or call external APIs.

The fixed CLI scripts can now be run in order from `run_create_request.py`
through `run_create_phase1_baseline_freeze.py`, meaning the complete local
create-chain handoff is test-covered, acceptance-checked, and baseline-frozen
before any future real execution work is considered.

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
