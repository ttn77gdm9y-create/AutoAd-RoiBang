# Report Snapshot Fetching

This note defines how RoiBang-v2 should fetch read-only reporting data and turn
it into the `report snapshot JSON` consumed by `run_data_sync.py`.

Phase 1 rule: fetching data is read-only. Fetch scripts may call reporting/list
APIs only when explicitly enabled by config. They must not create, pause, delete,
upload, push, bind, update budgets, update bids, or change schedules.

## Source Documents

Use these local references first:

- Old API index:
  `/Users/hongen/Codes/RoiBang/docs/API索引.md`
- Old report preset mapping:
  `/Users/hongen/Codes/RoiBang/templates/report-api-mapping.json`
- MiniGameApi report docs:
  `/Users/hongen/Codes/RoiBang/MiniGameApi/数据报表/数据报表/自定义报表.md`
  `/Users/hongen/Codes/RoiBang/MiniGameApi/数据报表/数据报表/获取自定义报表可用指标和维度.md`
- Original WeChat-delivered API docs:
  `/Users/hongen/Library/Containers/com.tencent.xinWeChat/Data/Documents/xwechat_files/fhe123456_277e/msg/file/2026-04/MiniGameApi`

Old code may be used only as reference for token handling, request shape,
pagination, retry, and field compatibility.

## Target Chain

```text
fetch_report_snapshot.py
  -> data/snapshots/report/<date>.json

run_data_sync.py
  -> SQLite tables

run_daily_learning.py
  -> data/runs/daily_learning/<timestamp>.json
```

`run_daily_learning.py` must never call OpenAPI directly.

## Snapshot Shape

The current importer expects this normalized structure:

```json
{
  "period": {
    "start": "YYYY-MM-DD",
    "end": "YYYY-MM-DD"
  },
  "accounts": [
    {
      "advertiser_id": "185...",
      "projects": [],
      "promotions": [],
      "promotion_metrics": [],
      "operation_logs": []
    }
  ]
}
```

The importer writes:

- `projects`
- `promotions`
- `material_bindings`
- `metric_snapshots`
- `material_metric_summaries`
- `operation_logs`

## Minimal API Set

### 1. Custom report config

Purpose: verify available dimensions and metrics before choosing a custom report
preset.

- Name: `获取自定义报表可用指标和维度`
- Method: `GET`
- Path: `/open_api/v3.0/report/custom/config/get/`
- Host: `https://api.oceanengine.com`
- Required params:
  - `advertiser_id`
  - `data_topics`
- Primary topics:
  - `BASIC_DATA`
  - `MATERIAL_DATA`

This should be cached per account and topic. It is a schema capability check,
not the daily data source itself.

### 2. Custom report query

Purpose: fetch daily account/project/promotion/material reporting rows.

- Name: `自定义报表`
- Method: `GET`
- Path: `/open_api/v3.0/report/custom/get/`
- Host: `https://api.oceanengine.com`
- Required params:
  - `advertiser_id`
  - `data_topic`
  - `dimensions`
  - `metrics`
  - `filters`
  - `start_time`
  - `end_time`
  - `order_by`
  - `page`
  - `page_size`
- Response shape:
  - `data.rows[].dimensions`
  - `data.rows[].metrics`
  - `data.page_info.page`
  - `data.page_info.total_page`

Pagination should continue until `page >= total_page`.

### 3. Project list

Purpose: enrich project IDs with stable project names/statuses when custom
report rows are incomplete.

- Name: `获取项目列表`
- Method: `GET`
- Path: `/open_api/v3.0/project/list/`
- Host: `https://api.oceanengine.com`
- Output target: snapshot `accounts[].projects[]`

Only list/read fields are allowed in Phase 1.

### 4. Promotion list

Purpose: enrich promotion IDs with project relationship, name, status, and
material binding information when available.

- Name: `获取单元列表`
- Method: `GET`
- Path: `/open_api/v3.0/promotion/list/`
- Host: `https://api.oceanengine.com`
- Output target:
  - snapshot `accounts[].promotions[]`
  - `promotion_materials` when returned or derivable

Only list/read fields are allowed in Phase 1.

### 5. Video/material library reads

Purpose: optional enrichment for material metadata and source material account
logic. This should remain separate from report snapshot fetching unless the
snapshot needs missing material names or video IDs.

Relevant customer-account read APIs from the old index:

- `获取同主体下客户视频素材`: `/open_api/2/file/video/ad/get/`
- `获取视频素材`: `/open_api/2/file/video/get/`
- `获取账户可用的组织视频列表`: `/open_api/v3.0/file/ebp_video/get/`
- `获取视频素材评估标签`: `/open_api/2/file/material_attributes/list/`

Material profile sync should keep these two concepts separate:

- `material_profiles`: material file metadata such as `material_id`, `video_id`,
  filename, duration, cover URL, and `signature`.
- `material_attribute_snapshots`: official platform tags such as high quality,
  low quality, first publish, inefficient, similar material, and carry risk.

The official tag API does not replace profile metadata because it does not
return `signature`.

Do not use upload, push, bind, delete, pause, or update material APIs in Phase 1.

## Report Presets

The old mapping file defines the original minimal set:

`/Users/hongen/Codes/RoiBang/templates/report-api-mapping.json`

Those presets should be ported conceptually, but v2 must adapt the exact field
names to the current account's `report_custom_config` response before issuing
`report_custom` requests. In practice, current mini-game upgraded accounts may
expose the `cdp_*` dimensions used by the old backend fast-cost path rather than
the older generic names.

RoiBang-v2's current BASIC_DATA defaults are:

- `account_daily`
  - topic: `BASIC_DATA`
  - dimensions: `stat_time_day`
  - metrics: `stat_cost`, `show_cnt`, `click_cnt`, `convert_cnt`
- `project_daily`
  - topic: `BASIC_DATA`
  - dimensions: `stat_time_day`, `cdp_project_id`, `cdp_project_name`
  - metrics: `stat_cost`, `show_cnt`, `click_cnt`, `convert_cnt`
- `promotion_daily`
  - topic: `BASIC_DATA`
  - dimensions: `stat_time_day`, `cdp_project_id`, `cdp_project_name`,
    `cdp_promotion_id`, `cdp_promotion_name`
  - metrics: `stat_cost`, `show_cnt`, `click_cnt`, `convert_cnt`
- `material_daily`
  - topic: `MATERIAL_DATA`
  - dimensions: `stat_time`, `material_id`, `promotion_id`
  - metrics: `stat_cost`, `show_cnt`, `click_cnt`, `convert_cnt`

The old mapping also filters mini-game traffic with:

```json
{
  "field": "micro_promotion_type",
  "type": 1,
  "operator": 10,
  "values": ["WECHAT_GAME", "BYTE_GAME"]
}
```

If a target account does not expose this field, v2 must not send it. The current
fallback is to send no platform filter and keep account scope constrained by
`advertiser_id` plus the local account pool. Future fallback filtering may use
project or promotion name patterns after rows are fetched.

Implementation note from the old backend fast-cost path:
`backend/app/services/report_service.py` queried BASIC_DATA with
`cdp_project_id`, `cdp_project_name`, `stat_cost`, and `filters: []`. This is a
better reference for upgraded accounts than the older minimal mapping when the
capability response disagrees.

## Field Mapping Into Snapshot

### Projects

Source candidates:

- `project_daily` report rows
- `project/list` enrichment rows

Snapshot fields:

- `advertiser_id`
- `project_id`
- `project_name`
- `project_status`

### Promotions

Source candidates:

- `promotion_daily` report rows
- `promotion/list` enrichment rows

Snapshot fields:

- `advertiser_id`
- `project_id`
- `project_name`
- `promotion_id`
- `promotion_name`
- `promotion_status_name`
- `promotion_materials`

### Promotion metrics

Source candidates:

- `promotion_daily` report rows

Snapshot fields currently consumed by v2:

- `promotion_id`
- `stat_cost`
- `active_register`
- `attribution_convert_cnt`
- `convert_cnt`
- `attribution_billing_game_in_app_roi_1day`
- `pay_amount_roi`
- `attribution_billing_game_in_app_roi_7days`

The first fetcher may start with `stat_cost` and `convert_cnt`, then expand once
the available-metrics check confirms the ROI and mini-game conversion fields for
the account.

### Material bindings and material metrics

Source candidates:

- `promotion/list` for binding details, if returned
- `material_daily` report rows for material performance
- optional material library read APIs for material metadata enrichment

Snapshot fields:

- `promotion_materials.video_material_list[].material_id`
- `promotion_materials.video_material_list[].video_id`
- `promotion_materials.video_material_list[].title`
- `promotion_materials.title_material_list[].title`

`run_data_sync.py` uses these fields to build `material_bindings` and then
summarize material performance from promotion metrics.

### Operation logs

Operation logs are required learning context. Reporting rows explain what
happened; operation logs explain what changed before or during that performance.

Source candidates:

- `操作日志查询`: `GET https://ad.oceanengine.com/open_api/2/tools/log_search/`
- old project/exported operation log files
- manually exported platform operation logs normalized into snapshot format

Snapshot fields:

- `operation_id`
- `occurred_at`
- `operator`
- `entity_type`: `account`, `project`, or `promotion`
- `entity_id`
- `action`
- `before`
- `after`
- `detail`

`run_data_sync.py` stores these rows in SQLite `operation_logs`.
`run_daily_learning.py` reads same-day rows and emits
`operation_log_summary`, including counts by entity type, counts by action, and
recent logs. AI review should compare operation logs with account/project/unit
performance before suggesting policy changes.

OpenAPI v1 log fields are normalized as follows:

- `request_id` -> `operation_id`
- `create_time` -> `occurred_at`
- `object_type` -> `entity_type`, mapped to `account`, `project`, `promotion`,
  or `creative` where possible
- `object_id` -> `entity_id`
- `content_title` -> `action`
- `content_log[]` -> `detail`
- `operator` -> `operator`

## Fetcher Design

The first v2 fetcher should be deterministic:

```text
scripts/fetch_report_snapshot.py
  -> read configs/report-fetch.example.json
  -> read API index/preset metadata
  -> fetch or mock rows by configured source
  -> normalize into report snapshot JSON
  -> write data/snapshots/report/<date>.json
  -> write data/runs/report_fetch/<timestamp>.json
```

Current local/mock entry:

```bash
PYTHONPATH=src scripts/fetch_report_snapshot.py \
  --request configs/report-fetch.mock-sample.example.json
```

This uses the account pool CSV and deterministic mock rows to generate standard
snapshot files under `data/snapshots/report/mock/`. It is intended to prove the
shape of `fetch -> data_sync -> daily_learning` before any real API fetching is
enabled.

Recommended source modes:

- `local_fixture`: copy/normalize an existing fixture into snapshot output.
- `mock_openapi`: use static mock responses shaped like OpenAPI responses.
- `openapi_readonly`: current planning mode. It produces a redacted read-only
  request plan only, with `external_api_calls=0`. It does not fetch data until a
  later implementation explicitly adds an HTTP executor.
- `openapi_mock_execute`: current local execution mode. It runs the readonly
  request plan through a local fixture transport, follows pagination, normalizes
  report rows into snapshot JSON, and still keeps `external_api_calls=0`.

`openapi_readonly` currently requires:

- read-only endpoint allowlist
- `execution.status=planned_only`
- `execution.external_api_enabled=false`
- no access token in config or artifacts
- redacted headers in every planned request

Generate a plan with:

```bash
PYTHONPATH=src scripts/fetch_report_snapshot.py \
  --request configs/report-fetch.openapi-readonly.example.json
```

The plan artifact contains `request_plan.requests[]`, but the CLI summary does
not print the full request list. Allowed request keys are:

- `report_custom_config`
- `report_custom`
- `project_list`
- `promotion_list`
- `account_video_material_get`
- `video_material_get`
- `ebp_video_material_get`
- `material_attributes_list`
- `operation_log_search`

Mutation-shaped keys or paths, including create, update, delete, budget, bid,
schedule, upload, push, and bind, are rejected before any request plan is
written.

Future real fetching must add, in this order:

- access token source configured outside strategy policy
- real transport opt-in guarded by `enabled=true`
- per-account/page rate limits
- retry and pagination executor
- OpenAPI response normalization into snapshot JSON
- artifact contract validation before `run_data_sync.py`

The HTTP transport shell already exists but remains disabled by default:

- Module: `src/roibang_v2/fetch/openapi_http.py`
- Example config: `configs/openapi-http.disabled.example.json`
- Disabled report-fetch template:
  `configs/report-fetch.openapi-http-execute.disabled.example.json`
- Token sources: `token_env` or `token_file`
- Audit output: JSONL responses with `Access-Token` redacted
- Safety: accepts only allowlisted read-only GET requests

The dedicated real-fetch source is `openapi_http_execute`. It is accepted only
when all gates are open:

- report request uses `source=openapi_http_execute`
- report request has `execution.status=execute`
- report request has `execution.external_api_enabled=true`
- nested `openapi_http.enabled=true`
- CLI runtime config has `external_api_enabled=true`
- CLI runtime config keeps `execution_enabled=false`

The local runtime example for this is:

```text
configs/runtime.openapi-execute.local.example.json
```

No Phase 1 scheduler job or default report fetch config enables this transport.
Real HTTP fetching should be introduced as a separate reviewed step.

The local fixture executor already provides the pagination and normalization
shape without network access:

```bash
PYTHONPATH=src scripts/fetch_report_snapshot.py \
  --request configs/report-fetch.openapi-mock-execute.example.json
```

It reads OpenAPI-shaped responses from
`data/fixtures/openapi-report-responses.sample.json` and writes snapshot JSON
under `data/snapshots/report/openapi-mock/`.

## Account Pool

The account pool is a CSV maintained outside code:

```csv
account_name,advertiser_id,消耗,product,platform
黑旗-勇者突进-微小-示例账户,1850000000000001,"12,345.67",勇者突进,WECHAT_GAME
```

Import it with:

```bash
PYTHONPATH=src scripts/import_accounts_csv.py \
  --csv data/sources/accounts/roibangv2yztj.csv
```

The importer writes SQLite `account_pool` and does not call external APIs.

For historical backfill, build a dry-run plan:

```bash
PYTHONPATH=src scripts/plan_report_backfill.py \
  --product 勇者突进 \
  --platform WECHAT_GAME \
  --start-date 2026-02-10 \
  --end-date 2026-05-05
```

The plan estimates account/date fetch tasks only. It does not fetch report data.

For historical backfill at real scale, build a dry-run batch plan:

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

The batch artifact is a review object. It does not fetch data. Each batch
contains:

- account IDs and date window
- estimated account-date tasks
- estimated readonly request count
- a disabled `openapi_http_execute` request draft for later review

Those request drafts deliberately keep `execution.status=planned_only`,
`execution.external_api_enabled=false`, and `openapi_http.enabled=false`.

Export one batch request for review with:

```bash
PYTHONPATH=src scripts/export_backfill_batch_request.py \
  --plan data/runs/report_backfill_batch_plan/20260506T150241Z.json \
  --batch-id batch_0001
```

The exported request is a standalone JSON under `data/requests/backfill/` and
remains disabled. Turning it into a real fetch config should be a separate
reviewed step.

For the one-time historical pull, prefer the fixed runner script instead of
manually editing each batch request:

```bash
PYTHONPATH=src scripts/run_backfill_batches.py \
  --config configs/runtime.openapi-execute.local.example.json \
  --request configs/backfill-runner.execute.local.json
```

The checked-in example `configs/backfill-runner.disabled.example.json` only
dry-runs selected batches. A local execute config should select batch IDs or a
small initial slice, set `execution.status=execute`,
`execution.external_api_enabled=true`, and set `openapi_http.enabled=true`.

For ongoing daily data, use the daily pipeline instead of the historical batch
runner:

```bash
PYTHONPATH=src scripts/run_daily_report_pipeline.py \
  --config configs/runtime.example.json \
  --request configs/daily-report-pipeline.example.json
```

The daily pipeline computes the target date, fetches one daily snapshot, imports
that snapshot into SQLite, and builds the daily learning artifact. The example
configuration is local/mock; a real read-only daily job should use the same
script with `source=openapi_http_execute` and the OpenAPI runtime gate.

## Safety Requirements

The fetcher must not:

- call create/update/delete/status/budget/bid/schedule/material push endpoints
- write SQLite directly
- generate strategy actions
- modify policy JSON
- infer business decisions

The fetcher may:

- call allowed read/report endpoints
- normalize rows into snapshot JSON
- write fetch result artifacts
- report missing dimensions/metrics as structured errors
- normalize read-only operation logs into snapshot JSON

## First Implementation Target

Build the first version as local-only:

```text
configs/report-fetch.example.json
scripts/fetch_report_snapshot.py
src/roibang_v2/fetch/report_snapshot.py
tests/test_report_snapshot_fetch.py
```

It should support `local_fixture` first, producing:

```text
data/snapshots/report/2026-05-05.json
```

Then `run_data_sync.py` can be pointed at that generated snapshot instead of
`data/fixtures/report-snapshot.sample.json`.
