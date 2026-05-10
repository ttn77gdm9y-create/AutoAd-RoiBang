# Phase 2.1 YZT Payload Draft Closeout

Date: 2026-05-10

This document closes the first Phase 2.1 implementation slice for RoiBang-v2
勇者突进 creation. `closeout` means 收口总结. `payload draft` means 请求体草稿:
the JSON payload shape that can be reviewed locally, but is not sent to the ad
platform in this phase.

## Scope

Phase 2.1 implemented a draft-only bridge from local dry-run output to
future provider-facing create payloads.

The implemented chain remains:

```text
request -> strategy -> preflight -> dry-run -> approve -> execute
```

`execute` means 执行, but in this phase it is still a hard-blocked local review
artifact. `hard-blocked` means 硬阻断: the workflow reports what would be needed
later, but it does not perform real creation.

## Safety State

The safety contract is unchanged:

- `execution_enabled=false`: execution is disabled.
- `external_api_calls=0`: no external API call is made.
- `actions=[]`: no executable business action is emitted.
- `approved_for_execute=false`: approval never becomes real execution approval.
- `create_execute` remains hard-blocked with reason `phase1_execute_disabled`.

No real project, unit, or material binding is created by this slice.

## Implemented Components

### 1. Provider-facing unit name

`promotion_name` means 平台侧单元/广告名称.

It is now generated as:

```text
{project_name}_U{unit_index:02d}
```

Example:

```text
0509_郭靖_勇者突进_微小每付7R男_B281B2BCB_01_U01
```

`unit_key` remains internal. `unit_key` means 本地单元键, used for idempotency
and later ID lookup, not as the platform-facing name.

### 2. Lookup placeholders

`lookup` means 查表/查映射. Since real provider IDs do not exist before live
creation, dry-run now uses placeholders:

- `project_id`: `<lookup:{project_key}>`
- `promotion_id`: `<lookup:{unit_key}>`

`project_id` means 平台项目 ID. `promotion_id` means 平台单元 ID.

### 3. Provider ID ledger

`ledger` means 本地台账.

The new local table `create_provider_id_ledger` stores mappings such as:

```text
project_key -> project_id
unit_key    -> promotion_id
```

The helper `record_create_provider_id` records returned IDs into this local
ledger. It refuses to overwrite the same local key with a different provider ID,
returning `conflict` instead.

The helper `resolve_create_lookup_placeholders` reads the ledger and replaces
lookup placeholders in local payload drafts.

### 4. Execute payload resolver

`resolver` means 解析器.

`create_execute` can now resolve `provider_payload_drafts` with local ledger
data and emit `resolved_provider_payload_drafts`.

Important limits:

- Resolved drafts remain `executable=false`.
- Resolved drafts include `live_api_payload=false`.
- `execution_plan.live_api_payloads` remains empty.
- Missing ledger IDs block the resolved payload contract but still perform no
  external action.

### 5. Resolved payload contract

`contract` means 契约/校验规则.

`resolved_payload_contract` verifies:

- no unresolved `<lookup:...>` placeholders remain,
- no resolved draft is executable,
- no live payload exists.

When provider IDs are not recorded yet, the contract status is `blocked`.
This is expected before a real creation phase records provider IDs.

### 6. Execute review summary

`execute_review_summary` is a Chinese review summary for humans.

It reports:

- whether execute is still hard-blocked,
- provider payload resolution status,
- resolved payload contract status,
- project/unit/material counts,
- unresolved lookup count,
- human next steps.

This lets the operator review the execute artifact without reading the full
large JSON file first.

## Current Artifact Behavior

With the current local configuration, the local chain can run through:

```text
preview -> create_request -> strategy_plan -> preflight -> provider_field_map_check -> dry_run
```

Then approval and execute can be generated locally.

Because real provider IDs have not been recorded, execute currently reports:

- `status=blocked`
- `reason=phase1_execute_disabled`
- `provider_payload_resolution.status=blocked`
- `resolved_payload_contract.status=blocked`
- unresolved lookup placeholders remain

This is correct. It means the local draft path is ready for review, while real
creation remains disabled.

## Version Note

The original Phase 2.1 design suggested a new schema version such as:

```text
phase2.yzt.live_payload_draft.v1
```

The implementation deliberately kept the current schema version
`phase1.create_payload.v1` and expanded its required fields. This avoids
breaking existing create workflow artifacts while the live phase is still
disabled.

A schema version bump should be revisited when provider field mapping is
verified and the project enters a separately approved live-payload phase.

## Verification

The closeout state was verified by:

- `python3 -m pytest -q`: 327 passed.
- `git diff --check`: passed.
- Local 勇者突进 dry-chain: passed.
- Local approval and execute CLI: passed.

The execute CLI still reports:

- `execution_enabled=false`
- `external_api_calls=0`
- `status=blocked`
- `reason=phase1_execute_disabled`

## Next Recommended Slice

Before any live creation work, add a provider evidence review slice:

1. Verify the exact OceanEngine project create fields.
2. Verify the exact OceanEngine promotion create fields.
3. Verify whether material binding is separate or nested.
4. Update provider field maps with evidence references.
5. Keep `mapping_verified=false` until evidence is reviewed.
6. Keep `create_execute` hard-blocked.

Only after that should the project design a separate live phase gate.
