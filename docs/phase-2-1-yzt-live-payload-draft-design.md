# Phase 2.1 YZT Live Payload Draft Design

Date: 2026-05-10

This document designs the next RoiBang-v2 slice after the successful Phase 2
local rehearsal. It is still not live execution. `payload draft` means 请求体草稿:
the JSON shape that would be sent to the ad platform later, but is not sent in
this phase.

## Goal

Build a safe 勇者突进 payload-draft layer that turns the verified dry-run plan
into provider-facing project, unit, and material binding request drafts.

The layer must keep:

- `execution_enabled=false`, meaning business execution is disabled.
- `external_api_calls=0`, meaning no external API call is made.
- `actions=[]`, meaning no executable business action is emitted.
- `create_execute` hard-blocked, meaning 真实创建执行 remains blocked.

## Current Baseline

The current Phase 2 local rehearsal already proves:

- Manual local config can select target accounts.
- The local account pool check can pass.
- The local source-material candidate pool can satisfy material demand.
- The chain can run through preview, create request, strategy plan, preflight,
  provider field-map check, and dry-run.
- Candidate tasks remain `executable=false`.

The current dry-run produces internal keys:

- `project_key`: internal project key, meaning 内部项目键.
- `unit_key`: internal unit key, meaning 内部单元键.
- `material_id`: source material identity, meaning 源素材 ID.

The current unit key pattern is:

```text
{advertiser_id}-p{account_project_index:03d}-u{unit_index:02d}
```

This is useful for idempotency and local lookup, but it should not be treated as
the final platform-facing unit name.

## Proposed Unit Naming

Add a provider-facing unit name field:

```text
promotion_name
```

`promotion_name` means 平台里的单元/广告名称. It should be generated from the
project name plus a stable unit suffix:

```text
{project_name}_U{unit_index:02d}
```

Example shape:

```text
0509_归属_勇者突进_微小每付7R男_BXXXXXXXX_01_U01
```

Design rules:

1. `project_name` remains the parent project name.
2. `unit_index` is the unit sequence inside one project.
3. `U01`, `U02`, and so on make the unit name readable and stable.
4. `unit_key` remains internal and is still used for idempotency.
5. `promotion_name` is only a draft field until provider schema evidence is
   verified.

The internal and provider-facing names should coexist:

```json
{
  "unit_key": "<target-advertiser-id>-p001-u01",
  "promotion_name": "0509_归属_勇者突进_微小每付7R男_BXXXXXXXX_01_U01"
}
```

## Payload Draft Operations

The Phase 2.1 payload draft should produce three operation groups.

### create_project

`create_project` means 创建项目. The draft should be generated from
`create_strategy_plan.strategy.projects[]`.

Minimum draft fields:

- `advertiser_id`: target advertiser account ID, meaning 目标广告账户 ID.
- `project_key`: internal project key, meaning 内部项目键.
- `project_name`: project name, meaning 项目名.
- `project_type`: internal project type, meaning 内部项目类型.
- `daily_budget`: daily budget, meaning 日预算.
- `field_defaults`: fixed default fields, meaning 固定默认字段.
- `template_parameters`: template values such as gender and ROI coefficient,
  meaning 模板参数.

Provider field mapping remains unverified until matched against the real
OceanEngine API schema.

### create_unit

`create_unit` means 创建单元. The draft should be generated from each project
unit in the strategy plan.

Minimum draft fields:

- `advertiser_id`: target advertiser account ID.
- `project_key`: local parent project key.
- `project_id`: provider project ID placeholder. This is not known until a
  future project creation response is recorded.
- `unit_key`: internal unit key.
- `promotion_name`: provider-facing unit name draft.
- `field_defaults`: fixed default fields inherited from the project.
- `template_parameters`: template values that affect unit setup.

`project_id` should not be fabricated. In Phase 2.1 it should be represented as
a lookup placeholder:

```text
<lookup:project_key>
```

`lookup` means 查询映射: later, a creation ledger maps local `project_key` to
the provider's returned `project_id`.

### bind_material

`bind_material` means 绑定素材. The draft should be generated from each unit's
material list.

Minimum draft fields:

- `advertiser_id`: target advertiser account ID.
- `project_key`: local parent project key.
- `unit_key`: local unit key.
- `project_id`: lookup placeholder from `project_key`.
- `promotion_id`: lookup placeholder from `unit_key`.
- `material_id`: source material ID.
- `source_video_id`: source video ID when available.

`promotion_id` means platform unit ID. It should not be fabricated in Phase 2.1.
It should be represented as:

```text
<lookup:unit_key>
```

## Schema Contract

`schema` means 字段结构规则. Phase 2.1 should add a new schema version, for
example:

```text
phase2.yzt.live_payload_draft.v1
```

The schema should validate:

- Required fields exist.
- Budgets stay within policy limits.
- Project names match the existing project naming rule.
- `promotion_name` exists and is not equal to `unit_key`.
- `unit_key` remains present for idempotency.
- `project_id` and `promotion_id` are lookup placeholders, not fabricated IDs.
- Drafts keep `executable=false`.
- No draft creates `live_api_payloads`.

## Provider Field Mapping

`provider field mapping` means 平台字段映射. The current phase2 field map is
still `mapping_verified=false`.

Phase 2.1 should update the draft mapping intent:

- `project_name` maps to the project create provider name field after evidence.
- `promotion_name` maps to the promotion create provider name field after
  evidence.
- `project_key` maps to a local ledger lookup, not directly to provider payload.
- `unit_key` maps to a local ledger lookup, not directly to provider payload.
- `material_id` and `source_video_id` remain open until the provider material
  binding schema is verified.

Do not mark provider mapping as verified in this phase unless real API
documentation or observed request evidence is reviewed.

## Safety Contract

The payload draft workflow must return:

```json
{
  "execution_enabled": false,
  "external_api_calls": 0,
  "approved_for_execute": false,
  "actions": []
}
```

It must also report:

- `payload_draft_count`: number of generated drafts.
- `live_payload_count`: always zero in Phase 2.1.
- `executable_draft_count`: always zero in Phase 2.1.
- `mapping_verified`: false unless explicitly verified later.
- `ready_for_live_execute`: false.

## Recommended Implementation Slice

Implement Phase 2.1 in small steps:

1. Add `promotion_name` generation to the strategy or dry-run layer.
2. Add schema validation for `promotion_name` and lookup placeholders.
3. Add a payload-draft workflow that reads a dry-run artifact and emits project,
   unit, and material binding drafts.
4. Add a CLI script for the draft workflow.
5. Add tests proving all drafts are non-executable and no live payload is
   emitted.
6. Update the field-map review pack to mention `promotion_name` separately from
   `unit_key`.

Do not implement live API transport in this slice.

## Open Questions

These questions must be answered before live payload execution:

1. What exact OceanEngine project create endpoint and fields are required?
2. What exact OceanEngine promotion create endpoint and fields are required?
3. Does the provider expect material binding as a separate operation or nested
   inside promotion creation?
4. What is the provider's official max length for project names and promotion
   names?
5. Which enum values must be used for landing type, pricing, inventory, gender,
   age, optimization goal, and ROI target?

Until these are verified, Phase 2.1 remains draft-only.
