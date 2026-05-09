# Phase 2 Preparation

Date: 2026-05-09

Closeout notes: `docs/phase-2-preparation-closeout.md`.

Phase 2 preparation is review-only work before any real create development. It
does not create projects, create units, bind materials, upload assets, pause
objects, delete objects, change budgets, or call external APIs.

## First Step: Provider Field Mapping Prep

The first Phase 2 preparation step is `create_phase2_provider_mapping_prep`.
It reads a reviewed JSON provider field map and emits a local review artifact
that answers:

- Which internal create fields exist for each operation.
- Which candidate provider API field each internal field may map to.
- Which value source and mapping kind each candidate uses.
- Which fields still need evidence, verification, splitting, or created-ID
  lookup confirmation.

Run it with:

```bash
PYTHONPATH=src scripts/run_create_phase2_provider_mapping_prep.py \
  --config configs/runtime.example.json \
  --policy policies/strategy.example.json
```

The default policy points at:

```text
configs/provider-field-maps/oceanengine.create.phase2-prep.example.json
```

## Safety Contract

Every artifact from this step must keep:

- `phase=phase2_preparation`
- `execution_enabled=false`
- `external_api_calls=0`
- `actions=[]`
- `phase2_preparation_contract.review_only=true`
- `phase2_preparation_contract.live_payload_generation_enabled=false`
- `phase2_preparation_contract.create_execute_hard_block_required=true`

This step can make mapping gaps visible, but it cannot make real create
execution possible. `create_execute` remains hard-blocked until a later approved
live execution phase.

## Next Preparation Reviews

After provider field mapping prep, Phase 2 preparation continues with
`create_phase2_template_slot_prep`, meaning a local check of the fixed default
values that future create payloads would need.

Run it with:

```bash
PYTHONPATH=src scripts/run_create_phase2_template_slot_prep.py \
  --config configs/runtime.example.json \
  --request configs/requests/example.create-request.json \
  --policy policies/strategy.example.json
```

It checks project, unit, and material-binding slots such as project type,
budget, landing type, pricing, inventory type, units per project, material type,
and materials per unit. It also writes `product_template_catalog`, meaning the
current 勇者突进微信小游戏 template list has four project templates: `微小每付男`,
`微小每付通投`, `微小每付7R男`, and `微小每付7R通投`. All four fix the
optimization goal to 付费. The two `微小每付` templates do not choose a deep
target and do not fill ROI, meaning 回本目标; the two `微小每付7R` templates
choose 7日ROI and require an ROI value. 男 templates fix gender to 男; 通投
templates fix gender to 不限. All four currently fix age to 不限. The front-end
field named 深度优化方式 is recorded as `deep_optimization_method`, and its
provider field is `deep_bid_type`, meaning the platform API field name. It also writes
`template_confirmation_groups`, meaning the 12 template items are grouped into
fixed defaults, per-account values, and fixed-strategy selections. It also
writes `template_confirmation_draft`, meaning a 12-row confirmation draft with
the current value, source, pending confirmation status, and suggested decision
for each template item. It also writes `template_confirmation_checklist`, meaning
the same 12 items in plain Chinese labels for manual review. The output still
has `execution_enabled=false`, `external_api_calls=0`, and `actions=[]`.

After template slot prep, Phase 2 preparation can write
`create_phase2_template_confirmation_pack`, meaning a local pending-confirmation
record for the same 12 items.

Run it with:

```bash
PYTHONPATH=src scripts/run_create_phase2_template_confirmation_pack.py \
  --config configs/runtime.example.json
```

Phase 2 preparation also has a 勇者突进 manual create preview. It lets a human
edit one config file, then generate local project-name and template previews
without real creation.

Check the config first with:

```bash
PYTHONPATH=src python3 scripts/run_create_phase2_yzt_config_check.py \
  --config configs/runtime.example.json \
  --preview-config configs/create/yzt-wx-mini-game.preview.example.json \
  --policy policies/strategy.example.json
```

This catches missing accounts, placeholder accounts, budget outside the policy
range, zero project or unit count, unknown templates, and missing ROI coefficient
for 7R templates. It only writes a local artifact and keeps `execution_enabled=false`,
`external_api_calls=0`, and `actions=[]`.
The example config uses a safe local budget of `1000`, so the quick check can
pass the budget rule under the current policy. The quick check still stops on
the placeholder accounts until they are replaced with real advertiser IDs.
Full rehearsal can still stop later if the local material pool has not been
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

Run it with:

```bash
PYTHONPATH=src python3 scripts/run_create_phase2_yzt_create_preview.py \
  --config configs/runtime.example.json \
  --preview-config configs/create/yzt-wx-mini-game.preview.example.json \
  --policy policies/strategy.example.json
```

The editable config is `configs/create/yzt-wx-mini-game.preview.example.json`.
It only contains the fields that should be filled each time: project template,
owner, target date, batch generated time, default budget, default project count,
default unit count, ROI coefficient when needed, and target accounts. The script
keeps product, platform, source advertiser, material pool, material requirements,
field defaults, marketing scene, optimization goal, age, and effective-touch URL
fixed. The output also writes `manual_config_contract`, meaning a Chinese field
guide for the manual config, and `preview_checks`, meaning local checks for
safety, template selection, target accounts, budget, ROI coefficient, unique
project names, and fixed effective-touch URL. The output also writes
`standard_create_request`, meaning the normal create-request shape that can enter
the fixed create chain, and `chain_handoff`, meaning the next safe steps: create
request, strategy plan, preflight, and dry-run. The output still has
`execution_enabled=false`, `external_api_calls=0`, and `actions=[]`.

For real operator use, run the local config prepare helper:

```bash
PYTHONPATH=src python3 scripts/run_create_phase2_yzt_local_config_prepare.py
```

The helper copies the example config to
`configs/create/yzt-wx-mini-game.preview.local.json` only when the local file
does not already exist, then prints an `operator_guide`. `example` means 示例配置,
`local` means 本地私有配置, and `operator_guide` means 操作员填写指南. The path
`configs/create/*.local.json` is ignored by git, so real account IDs must stay
there instead of in the example config.

Phase 2 preparation also has a 勇者突进 full dry create chain. It is a local
complete rehearsal, not real creation.

Run it with:

```bash
PYTHONPATH=src python3 scripts/run_create_phase2_yzt_dry_chain.py \
  --config configs/runtime.example.json \
  --preview-config configs/create/yzt-wx-mini-game.preview.example.json \
  --policy policies/strategy.example.json
```

The chain runs preview, create-request recording, strategy plan, preflight,
provider field-map check, and dry-run in order. The output writes
`chain_steps`, meaning the ordered step list, and `artifacts`, meaning the JSON
files created by each step. It also writes `blocking_summary`, meaning the plain
blocked reason, and `human_next_steps`, meaning the next manual fixes in
Chinese. It still has `execution_enabled=false`, `external_api_calls=0`,
`approved_for_execute=false`, and `actions=[]`.

This pack sets `required_user_input_now=true`, meaning it is ready for manual
confirmation, but it does not write policy, does not create anything, and keeps
`execution_enabled=false`, `external_api_calls=0`, and `actions=[]`.

After template slot prep, Phase 2 preparation continues with
`create_phase2_project_naming_prep`, meaning a local check of future project
names.

Run it with:

```bash
PYTHONPATH=src scripts/run_create_phase2_project_naming_prep.py \
  --config configs/runtime.example.json \
  --request configs/requests/example.create-request.json \
  --policy policies/strategy.example.json
```

It generates sample project names, checks length, checks the configured pattern,
checks duplicate names inside the local plan, and compares the current rule with
the old project reference rule. The old project used:

```text
月日_归属_游戏名_项目模板名_批次码_批内项目序号
```

The current rule keeps the same shape:

```text
月日_归属_游戏名_项目模板名_批次码_序号
```

The batch code is generated from request id, create date, product, project type,
account list, and second-level generated time. The script uses a hash, meaning a
fixed short code made from those fields, with the format `B` plus 8 uppercase
hex characters. It is generated once in the plan and then reused through
preflight, dry-run, approval, and execute, so a later step cannot silently create
a different name.

After project naming prep, Phase 2 preparation should continue with:

- `create_phase2_preparation_summary`, meaning one local summary that combines
  field mapping, template slots, and project naming.
- Only then, live payload generation design can be considered.

Run the summary with:

```bash
PYTHONPATH=src scripts/run_create_phase2_preparation_summary.py \
  --config configs/runtime.example.json
```

It reads the latest three preparation artifacts and writes one summary with the
remaining review items. The summary also writes `remaining_review_groups`,
meaning the remaining items are split into:

- `needs_provider_evidence`: platform field evidence still needs to be checked.
- `needs_human_decision`: fixed rules or default values still need manual
  confirmation.

It still keeps `ready_for_live_payload_development=false` and
`ready_for_live_execute=false`.
