# Phase 2.2 Provider Evidence Review

Date: 2026-05-10

This document defines the next safety slice after Phase 2.1 payload draft
closeout. `provider evidence review` means 平台字段证据复核: before real payload
generation, each provider field must have a reviewed source.

## Goal

Add a review-only gate for OceanEngine create field evidence.

The gate reads:

- provider field map JSON,
- provider evidence catalog JSON,
- existing runtime safety config.

It writes a run artifact and performs no external API call.

## New Workflow

The new workflow is:

```text
create_provider_evidence_review
```

Field meanings:

- `provider`: 广告平台, currently `oceanengine`.
- `evidence`: 字段依据, such as official docs or captured request evidence.
- `catalog`: 目录, the JSON file listing evidence references.
- `reviewed`: 已复核, meaning a human has checked the evidence.

The workflow reports:

- fields with empty provider field,
- fields missing evidence refs,
- evidence refs missing from the catalog,
- evidence entries that exist but are not reviewed,
- local-only fields that still need explicit confirmation.

It also reports:

- `evidence_status_counts`: 证据状态计数, grouped by unresolved reason.
- `operator_guide`: 操作员指南, the exact human next steps.
- `evidence_worksheet`: 证据填写清单, one row per reviewed field.

Common status meanings:

- `needs_provider_field`: 缺平台字段名.
- `needs_evidence_ref`: 缺证据引用.
- `needs_evidence_review`: 有证据引用, 但还没有人工复核.
- `local_only_needs_confirmation`: 本地字段需要确认不会进入平台请求体.
- `verified`: 字段映射和证据都已确认.

## Safety Contract

The workflow must always return:

```json
{
  "execution_enabled": false,
  "external_api_calls": 0,
  "actions": []
}
```

It also keeps:

- `live_payload_generation_enabled=false`
- `create_execute_hard_block_required=true`
- `mapping_verified_must_remain_false=true`

This means the review can improve confidence in field mapping, but it cannot
turn on real creation.

## Current Status

The current example catalog is intentionally not reviewed:

```text
configs/provider-evidence/oceanengine.create.phase2-review.example.json
```

This lets the script report `needs_review` until real evidence is checked.

Current expected result:

- 18 mapped fields inspected.
- 3 evidence catalog entries loaded.
- 0 evidence entries reviewed.
- 18 fields unresolved.
- `operator_guide.status=needs_review`.
- `evidence_worksheet.summary.row_count=18`.
- live payload development remains not ready.
- live execute remains not ready.

## Evidence Worksheet

`evidence_worksheet` is a human-fillable checklist. It groups each field into a
row and tells the operator what must be filled before that row can be marked
ready.

Important fields:

- `fill_required`: 需要补的内容, such as `source_url` or reviewer metadata.
- `do_not_change`: 禁止改动的安全字段, such as `execution_enabled`.
- `ready_row_count`: 已就绪字段行数.

The worksheet is not an approval artifact and cannot enable live execution.

## Next Manual Review

Before changing any field to verified, review the exact source for:

1. project create request fields,
2. promotion/unit create request fields,
3. material binding request fields,
4. whether local-only keys truly stay out of provider payloads,
5. whether `material_id` or `source_video_id` is required for material binding.

Only after that should the JSON evidence catalog be updated.
