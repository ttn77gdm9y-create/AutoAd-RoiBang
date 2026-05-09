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

Create it by copying the safe example config:

```bash
cp configs/create/yzt-wx-mini-game.preview.example.json \
  configs/create/yzt-wx-mini-game.preview.local.json
```

That local file is ignored by git through `configs/create/*.local.json`, so real
account IDs are not committed. The example config should remain safe and
shareable.
