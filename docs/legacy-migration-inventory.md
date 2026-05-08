# Legacy RoiBang Migration Inventory

## Scope

This document records the first read-only inventory of useful legacy code from
`/Users/hongen/Codes/RoiBang` and the external `MiniGameApi` documentation
directory. The inventory is for RoiBang-v2 migration planning only. No legacy
business script was executed.

## Migration Rule

Migrate capabilities, not old runtime state.

Useful legacy code should be copied only after it is reshaped into the v2 model:

`fixed script -> JSON config/policy -> SQLite -> result JSON`

Phase 1 keeps all live mutation disabled. Code that can create, pause, delete,
push, bind, or update live ad objects may be studied, but must not be wired into
an executable live path.

## High-Value Sources

### 1. Deterministic Automation Boundary

Source:

- `/Users/hongen/Codes/RoiBang/docs/runbooks/automation-task-overview.md`
- `/Users/hongen/Codes/RoiBang/templates/launchd/*.plist.example`
- `/Users/hongen/Codes/RoiBang/scripts/run_*.sh`

Value:

- Already documents the same boundary v2 wants: mature business tasks run as
  scheduled scripts, AI reviews outputs and edits strategy JSON.
- Lists existing task shapes for account sync, material pool, strategy review,
  managed account checks, material allocation, and create request generation.

v2 target:

- Fold the runbook principles into `docs/design-v2.md`.
- Rebuild launchd/cron examples under `scheduler/` only after Phase 1 scripts
  are real read-only workflows.
- Do not copy old launchd paths because they point at the old repo.

### 2. Common Local Utilities

Source:

- `/Users/hongen/Codes/RoiBang/scripts/automation_common.py`

Reusable parts:

- JSON read/write helpers.
- CSV read/write helpers.
- numeric parsing helpers.
- timestamp and latest-run directory helpers.
- paged request helper pattern, but not enabled by default in Phase 1.

Risk:

- Contains live HTTP request helpers and notification helpers.
- Old config defaults point to `/tmp/roibang_automation` and old templates.

v2 target:

- Migrate pure local helpers into `src/roibang_v2/io/`.
- Keep network helpers behind `external_api_enabled=false` guards.
- Use v2 config paths, not old template paths.

### 3. Token Handling

Source:

- `/Users/hongen/Codes/RoiBang/templates/token-utils.sh`
- `/Users/hongen/Codes/RoiBang/templates/token-健康检查.sh`
- `/Users/hongen/Codes/RoiBang/backend/app/services/ocean_token_service.py`

Reusable parts:

- Local token snapshot format.
- expiry parsing and refresh lead time.
- file lock concept for refresh.
- health-check reporting structure.

Risk:

- Shell utility can refresh tokens and call the OAuth endpoint.
- Backend service uses APScheduler and FastAPI-era app settings that v2 does
  not need in Phase 1.

v2 target:

- Phase 1: implement token inventory/health only, with remote checks disabled by
  default.
- Later read-only sync: add explicit token provider module under
  `src/roibang_v2/integrations/oceanengine/tokens.py`.
- Never let token refresh imply that live execution is enabled.

### 4. Report And Data Snapshot Sync

Source:

- `/Users/hongen/Codes/RoiBang/scripts/daily_snapshot.py`
- `/Users/hongen/Codes/RoiBang/backend/app/services/report_service.py`
- `/Users/hongen/Codes/RoiBang/scripts/report_query_policy.py`
- `/Users/hongen/Codes/RoiBang/templates/report-query-policies.json`

Reusable parts:

- Report metrics list for cost, conversion, ROI, CTR, video engagement, and
  negative feedback.
- Normalizers for project rows, promotion rows, and material bindings.
- Paged report fetch pattern.
- Fast cost cache concept.

Risk:

- Old code directly calls OceanEngine report APIs.
- Some service code depends on backend users, audit service, and hot-key cache.

v2 target:

- First migrate normalizers and report query policy as pure functions.
- Phase 1 data sync may import local fixtures and cached JSON first.
- Live read-only API sync should later require explicit
  `external_api_enabled=true`, never `execution_enabled=true`.

### 5. Daily Learning

Source:

- `/Users/hongen/Codes/RoiBang/scripts/daily_spend_learning.py`
- `/Users/hongen/Codes/RoiBang/scripts/learning_history_store.py`
- `/Users/hongen/Codes/RoiBang/scripts/learning_strategy_review.py`
- `/Users/hongen/Codes/RoiBang/scripts/daily_strategy_review.py`

Reusable parts:

- Spend account selection.
- account signal generation.
- material delta artifact shape.
- operation pattern aggregation.
- decision hints and guardrails.
- learning bundle JSON contract.

Risk:

- `daily_spend_learning.py` can pull live business console data and can call
  auto-push code depending on config.
- Old decision hints mention future pause/create paths.

v2 target:

- Migrate only artifact builders and SQLite import/read logic first.
- Inputs should be v2 SQLite and local cached snapshot files.
- Output should be `data/runs/daily_learning/*.json`.
- Keep hints as recommendations, not executable actions.

### 6. Material Library And Supplement Planning

Source:

- `/Users/hongen/Codes/RoiBang/scripts/local_material_library.py`
- `/Users/hongen/Codes/RoiBang/scripts/material_pool_update.py`
- `/Users/hongen/Codes/RoiBang/scripts/roibang_material_sync.py`
- `/Users/hongen/Codes/RoiBang/scripts/material_allocator.py`
- `/Users/hongen/Codes/RoiBang/scripts/material_cache_resolver.py`
- `/Users/hongen/Codes/RoiBang/scripts/product_source_material_cache.py`
- `/Users/hongen/Codes/RoiBang/templates/material-library.sqlite3`

Reusable parts:

- Rich SQLite schema for materials, accounts, account-material mappings,
  organization material ranking, product source materials, material histories,
  selection batches, creative groups, and provision tasks.
- Material name normalization.
- quality pool split: strong, stable, risky.
- deterministic material assignment output.
- product source and cache request contracts.

Risk:

- Some paths can trigger live material push/bind or source sync.
- Old DB file is runtime state and should not be copied as v2 source of truth.

v2 target:

- Migrate schema concepts into v2 schema in smaller sections.
- First implement local material inventory import and supplement plan generation.
- Do not implement push/bind/upload in Phase 1.
- Keep old `templates/material-library.sqlite3` as reference data only if a
  one-time read-only import script is explicitly written later.

### 7. Strategy Plan, Preflight, And Future Creation Chain

Source:

- `/Users/hongen/Codes/RoiBang/scripts/create_request_builder.py`
- `/Users/hongen/Codes/RoiBang/scripts/strict_creation_plan.py`
- `/Users/hongen/Codes/RoiBang/scripts/roibang_preflight.py`
- `/Users/hongen/Codes/RoiBang/scripts/strict_creation_execute.py`
- `/Users/hongen/Codes/RoiBang/scripts/strict_creation_run.py`
- `/Users/hongen/Codes/RoiBang/templates/strict-creation-templates.json`
- `/Users/hongen/Codes/RoiBang/templates/create-request-policy.example.json`
- `/Users/hongen/Codes/RoiBang/templates/strict-creation-request*.json`

Reusable parts:

- Strict request validation.
- template scope validation.
- deterministic project/unit name generation.
- copy/material uniqueness checks.
- preflight report structure.
- OpenAPI-only endpoint checks.
- action JSON shape with `requires_approval=true`.

Risk:

- `strict_creation_execute.py`, `strict_creation_run.py`, and shell templates
  can perform real creation or rollback deletion.
- Old shell templates call real project and promotion endpoints.

v2 target:

- Phase 1 can migrate request, strategy, preflight draft, and dry-run artifact
  contracts.
- Keep execute code out of v2 or hard-failed until a later phase.
- Treat `strict_creation_plan.py` as the most useful source for future
  deterministic plan generation.

### 8. Backend Models And Services

Source:

- `/Users/hongen/Codes/RoiBang/backend/app/models/*.py`
- `/Users/hongen/Codes/RoiBang/backend/app/schemas/*.py`
- `/Users/hongen/Codes/RoiBang/backend/app/services/*.py`
- `/Users/hongen/Codes/RoiBang/backend/tests/*.py`

Reusable parts:

- Data model names for accounts, materials, reports, tasks, templates.
- Token service tests and material candidate tests.
- Mapping between API response fields and UI/service schemas.

Risk:

- Backend is FastAPI/SQLAlchemy app architecture; v2 Phase 1 is script +
  SQLite.
- Some services expose live mutation actions.

v2 target:

- Use backend tests as behavioral reference.
- Do not migrate the web backend framework in Phase 1.
- Pull small model ideas into SQLite schema and dataclasses only where useful.

### 9. MiniGameApi Documentation

Source:

- `/Users/hongen/Library/Containers/com.tencent.xinWeChat/Data/Documents/xwechat_files/fhe123456_277e/msg/file/2026-04/MiniGameApi`
- `/Users/hongen/Codes/RoiBang/MiniGameApi`
- `/Users/hongen/Codes/RoiBang/docs/API索引.md`
- `/Users/hongen/Codes/RoiBang/docs/runbooks/minigameapi-reading-index.json`

Reusable parts:

- OAuth docs.
- project, promotion, material, report, account, and mini-game asset endpoint
  docs.
- endpoint field references for building adapters and validators.

Risk:

- Documentation includes live create/update/delete endpoints.

v2 target:

- Build a curated endpoint map for read-only sync first.
- Later annotate mutation endpoints as `phase: future` and
  `execution_enabled_required: true`.

## Do Not Migrate In Phase 1

These files are useful references but should not become runnable v2 scripts now:

- `/Users/hongen/Codes/RoiBang/templates/微小每付*.sh`
- `/Users/hongen/Codes/RoiBang/templates/字小每付*.sh`
- `/Users/hongen/Codes/RoiBang/templates/多账户并行创建.sh`
- `/Users/hongen/Codes/RoiBang/scripts/batch_create_pay_male_fast.py`
- `/Users/hongen/Codes/RoiBang/scripts/create_byte_game_7r_general.py`
- `/Users/hongen/Codes/RoiBang/scripts/create_from_product_source_cache.py`
- `/Users/hongen/Codes/RoiBang/scripts/strict_creation_execute.py`
- `/Users/hongen/Codes/RoiBang/scripts/strict_creation_run.py`
- `/Users/hongen/Codes/RoiBang/scripts/project_schedule_control.py`
- `/Users/hongen/Codes/RoiBang/scripts/promotion_status_control.py`
- `/Users/hongen/Codes/RoiBang/scripts/strategy_action_executor.py`

Reason: these files can create, delete, pause, update, push, bind, or execute
live actions. Phase 1 may extract validation or payload planning logic from
them only after tests are written around a no-op/dry-run boundary.

## Recommended Migration Order

1. **Local utility foundation**
   - migrate JSON/CSV helpers, numeric parsing, timestamp helpers, artifact
     writing, and config loading.
   - no network calls.

2. **Material schema and local inventory**
   - migrate material/account/product-source schema ideas.
   - implement fixture/cache import into v2 SQLite.
   - write material inventory and supplement-plan JSON.

3. **Report snapshot normalizers**
   - migrate report metrics and row normalizers.
   - load from local cached JSON/CSV first.
   - store project, promotion, material binding, and metric snapshots in SQLite.

4. **Daily learning artifact builder**
   - migrate account signals, material delta, operation patterns, and decision
     hints.
   - read only v2 SQLite and local snapshots.

5. **Strategy request and preflight draft**
   - migrate deterministic request builder and strict plan validation concepts.
   - generate plan/preflight/dry-run JSON only.
   - keep approval and execute disabled.

6. **Read-only OceanEngine adapter**
   - after local fixtures pass, add explicit read-only API sync with config
     gates.
   - no mutation endpoints in the adapter's default allowlist.

## First Implementation Slice

The safest first slice is material inventory plus local cache import:

- Create `src/roibang_v2/materials/library.py`.
- Extend `src/roibang_v2/db/schema.sql` with a focused subset of material
  tables.
- Add `src/roibang_v2/workflows/material_sync.py`.
- Add fixture tests that import sample material cache JSON and produce a
  supplement plan.

This gives v2 a useful capability without needing tokens, API calls, or live
execution.
