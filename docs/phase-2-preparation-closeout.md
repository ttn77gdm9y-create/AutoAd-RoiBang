# Phase 2 Preparation Closeout

Date: 2026-05-09

This document closes the current Phase 2 preparation slice for RoiBang-v2. This
is still not real creation development. It is the local preparation layer before
any live create payload or live execute work.

## Verdict

Phase 2 preparation can move into a local handoff state.

The project now has a safe 勇者突进 create-preparation flow:

1. Edit one manual config.
2. Run local preparation checks.
3. Run local create preview.
4. Run full local dry rehearsal.

The flow is still blocked from real creation. All new scripts keep:

- `execution_enabled=false`, meaning business execution is disabled.
- `external_api_calls=0`, meaning the reviewed scripts do not call outside
  services.
- `actions=[]`, meaning no executable business action is emitted.

## What Is Fixed

The current 勇者突进微信小游戏 script scope fixes:

- Product: 勇者突进.
- Platform: WECHAT_GAME.
- Marketing scene: 短视频+图文.
- Optimization goal: 付费.
- Age: 不限.
- Effective touch URL source: fixed in the 勇者突进 script.
- Material rule: video materials, two materials per unit, request-level dedupe.
- Project name rule: `月日_归属_游戏名_项目模板名_批次码_序号`.

The batch code is generated once from request id, date, product, project type,
account list, and generated time, then reused through later local steps.

## Templates

The current template list has four project templates:

- 微小每付男.
- 微小每付通投.
- 微小每付7R男.
- 微小每付7R通投.

The two 微小每付 templates do not fill ROI系数. The two 微小每付7R templates
require ROI系数. 男 templates fix gender to 男. 通投 templates use 不限.

## Manual Config

The human-editable config is:

```text
configs/create/yzt-wx-mini-game.preview.example.json
```

It only keeps fields that should be changed each time:

- Template name.
- Owner, meaning 归属.
- Target date.
- Batch generated time.
- Default budget.
- Default project count.
- Default unit count.
- ROI系数 when needed.
- Target account list.

Source account, material pool, material requirements, field defaults, and
effective touch URL are not meant to be filled by hand each time.

## Standard Run Order

Run all local preparation checks first:

```bash
PYTHONPATH=src python3 scripts/run_create_phase2_yzt_preparation_check.py \
  --config configs/runtime.example.json \
  --preview-config configs/create/yzt-wx-mini-game.preview.example.json \
  --policy policies/strategy.example.json
```

If this passes, run the preview:

```bash
PYTHONPATH=src python3 scripts/run_create_phase2_yzt_create_preview.py \
  --config configs/runtime.example.json \
  --preview-config configs/create/yzt-wx-mini-game.preview.example.json \
  --policy policies/strategy.example.json
```

If the preview is correct, run the full local rehearsal:

```bash
PYTHONPATH=src python3 scripts/run_create_phase2_yzt_dry_chain.py \
  --config configs/runtime.example.json \
  --preview-config configs/create/yzt-wx-mini-game.preview.example.json \
  --policy policies/strategy.example.json
```

Full rehearsal means local preview, local create-request record, local strategy
plan, local preflight, local field-map check, and local dry-run. It does not
execute real creation.

## Current Known Blockers

The example config is intentionally not ready for full rehearsal:

- It still contains placeholder account IDs such as `target-advertiser-id`.
- Those placeholder accounts are not in the local account pool.
- The local material candidate pool for the example has no usable materials.

These are expected blockers. They are not live API errors and not real create
failures.

## Before Real Create Development

Do not start live create execution yet.

Before live payload development, the following should be true:

1. The manual config uses real target account IDs in a local-only file that is
   not committed.
2. The target accounts exist in the local account pool.
3. The local material pool has enough usable materials.
4. The one-command preparation check passes.
5. The local create preview is reviewed.
6. The full local dry rehearsal passes.
7. Provider field mapping still has enough evidence for the real platform API.
8. `create_execute` remains hard-blocked until a separate approved live phase.

## Next Recommended Work

The next development step should be a local-only config path for real operator
use, for example:

```text
configs/create/yzt-wx-mini-game.preview.local.json
```

Create it with the local config prepare helper:

```bash
PYTHONPATH=src python3 scripts/run_create_phase2_yzt_local_config_prepare.py
```

The helper copies the safe example config only when the local file does not
already exist, so it does not overwrite real account IDs already filled by the
operator. `example` means 示例配置, and `local` means 本地私有配置. That local file
is ignored by git through `configs/create/*.local.json`, so real account IDs are
not committed. The example config should remain safe and shareable.

## Local Rehearsal Result

The local-only 勇者突进 rehearsal has passed once with a private local config.
`rehearsal` means 本地预演, and `local` means 本地私有配置. The private config is:

```text
configs/create/yzt-wx-mini-game.preview.local.json
```

That file remains ignored by git and must not be committed because it can carry
real account IDs.

The verified local inputs were:

- Template: 微小每付7R男.
- Target accounts: two local target accounts.
- Source material account: existing local source-material account.
- Material pool: existing local source-material candidate pool.
- Default budget: 1000.
- Project count: one project per account.
- Unit count: one unit per project.
- Material rule: two video materials per unit, request-level dedupe.

The successful local dry-chain artifact was:

```text
data/runs/create_phase2_yzt_dry_chain/20260509T165010Z.json
```

This run produced:

- `status=simulated`, meaning the chain was only simulated.
- `preview_project_count=2`.
- `create_request_project_count=2`.
- `strategy_project_count=2`.
- `preflight_status=passed`.
- `dry_run_status=simulated`.
- `ready_for_live_execute=false`.
- `execution_enabled=false`.
- `external_api_calls=0`.
- `actions=[]`.

The dry-run review confirmed:

- Project names were unique.
- Material IDs were unique across the request.
- Budgets stayed within the current policy range.
- Candidate tasks kept `executable=false`, meaning they cannot execute real
  creation.

The two preview project names were:

```text
0509_郭靖_勇者突进_微小每付7R男_B281B2BCB_01
0509_郭靖_勇者突进_微小每付7R男_B281B2BCB_02
```

The current unit key is still an internal key, not a final platform naming
rule. `unit_key` means 内部单元键. Its current pattern is:

```text
{advertiser_id}-p{account_project_index:03d}-u{unit_index:02d}
```

For example:

```text
<target-advertiser-id-1>-p001-u01
<target-advertiser-id-2>-p001-u01
```

This is acceptable for local rehearsal because Phase 2 has not started real
unit payload development. `promotion_name`, meaning the platform-facing unit
name, still needs a separate approved design before live payload work.

## Bugs Fixed During Rehearsal

Two local script bugs were fixed before this closeout:

1. `review_status` compatibility. Existing local candidate materials used the
   platform status code `3`, while the strategy policy allowed `APPROVED`.
   `APPROVED` means 审核通过. The candidate filter now treats `3` as
   `APPROVED`.
2. Successful dry-chain wording. A successful local dry-chain used to reuse a
   blocked-message sentence. It now reports that the local rehearsal passed
   while real creation remains disabled.

The preparation helper also fixed an operator handoff issue: when the CLI is
run with `--preview-config configs/create/yzt-wx-mini-game.preview.local.json`,
the returned `next_command` now keeps that same local path instead of pointing
back to the shareable example config.

## Next Phase Boundary

Do not jump directly to real creation.

The next live-payload phase must still keep the fixed chain:

```text
request -> strategy -> preflight -> dry-run -> approve -> execute
```

Field meanings:

- `request`: create request, meaning 创建请求.
- `strategy`: strategy plan, meaning 策略分配.
- `preflight`: preflight check, meaning 执行前检查.
- `dry-run`: local rehearsal, meaning 本地预演.
- `approve`: human approval, meaning 人工批准.
- `execute`: live execution, meaning 真实执行.

`create_execute` must remain hard-blocked until a separate approved live phase.
`hard-blocked` means 硬阻断: the script must not perform real creation even if
the earlier local rehearsal passes.
