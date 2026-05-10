# RoiBang-v2 Development Plan

Date: 2026-05-10

This document is the RoiBang-v2 roadmap. `roadmap` means 路线图. It records the
development order and safety boundaries for the project. It is not a phase
closeout document and should not contain private account IDs, tokens, sessions,
runtime artifacts, or local-only config contents.

## Direction

RoiBang-v2 should continue with the current stable shape first:

```text
scripts + JSON policies + SQLite + run artifacts
```

Field meanings:

- `scripts`: fixed command scripts, such as `scripts/run_xxx.py`.
- `JSON policies`: strategy rule files, such as budget, naming, material, and
  safety rules.
- `SQLite`: the local database for accounts, materials, history, and sync state.
- `run artifacts`: JSON output files under `data/runs`, used for review and
  replay.

The future target can be:

```text
CLI + policy engine
```

Field meanings:

- `CLI`: command line interface, meaning a unified terminal command such as
  `roibang create yzt dry-run`.
- `policy engine`: strategy engine, meaning centralized policy loading,
  validation, explanation, and application.

Do not move to the future target too early. The business flow must become stable
before we productize the operator interface.

## Current Stage

Current stage:

```text
scripts + JSON policies + SQLite + run artifacts
```

Goal: make the business chain correct and reproducible before abstracting it
into a unified CLI.

Current rules:

1. Mature business operations are executed by fixed scripts.
2. Scripts read JSON config, policy files, and SQLite.
3. AI writes and repairs scripts, reviews run artifacts, and updates strategy
   JSON. AI does not make runtime execution decisions.
4. Every business workflow must write reviewable run artifacts.
5. No real create action is allowed in the current stage.
6. `create_execute` remains hard-blocked. `hard-blocked` means 硬阻断: even if
   previous checks pass, the script must not perform live creation.
7. 勇者突进 local rehearsal remains the Phase 2 baseline chain.

The current stable create chain is:

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

Current priorities:

1. Keep Phase 2 local preparation and rehearsal stable.
2. Keep private local configs ignored by git.
3. Keep source material account and material pool selection explicit.
4. Keep all run outputs reviewable and replayable.
5. Fix script bugs when scripts produce misleading or incorrect results.

## Mid-Term Stage

Mid-term stage:

```text
dry-run / approve / execute boundary hardening
```

Goal: make the safety boundary before live creation unambiguous.

Field meanings:

- `payload`: the request body that would be sent to the ad platform API.
- `payload draft`: a generated request body draft that is not sent.
- `schema`: field structure rules, used to validate config and payload shape.
- `enum`: enumerated values, such as `APPROVED` or platform status code `3`.
- `idempotency`: 幂等, meaning repeated execution of the same logical request
  must not create duplicate business effects.

Mid-term priorities:

1. Complete project and unit payload draft generation without live API calls.
2. Design the final platform-facing unit name, such as `promotion_name`.
3. Strengthen schema validation for create request, strategy plan, preflight,
   dry-run, approval, and execute artifacts.
4. Strengthen enum mapping, such as platform review status code `3` mapping to
   `APPROVED`.
5. Make dry-run artifacts show projects, units, budgets, materials, provider
   fields, idempotency keys, and blocking reasons clearly.
6. Require an explicit approve artifact before any execute attempt.
7. Keep `create_execute` disabled unless a separate live phase is approved.
8. Add audit records for any future live execution attempt.

The first live create phase, when separately approved, should be deliberately
small:

```text
one account -> one project -> one unit -> two materials
```

That phase must still require manual review before execution.

## Later Stage

Later stage:

```text
CLI + policy engine
```

Goal: productize the stable script workflows into a unified operator interface.

Do this after the real workflow has stabilized, not before.

Later priorities:

1. Add a unified `roibang` command.
2. Convert existing scripts into CLI subcommands while keeping old scripts
   available during migration.
3. Extract policy loading, validation, and explanation into a policy engine.
4. Add consistent commands such as `doctor`, `status`, `explain`, and `report`.
5. Keep cron and launchd compatibility during migration.
6. Consider a Web dashboard only after the CLI and policy engine are stable.

Field meanings:

- `doctor`: health check command, meaning 健康检查.
- `status`: state query command, meaning 状态查看.
- `explain`: decision explanation command, meaning 解释为什么这么决策.
- `report`: report output command, meaning 报告输出.
- `Web dashboard`: Web 看板, meaning browser-based status and review UI.

## Estimated Cycle

Estimated remaining work from the current point:

- Phase 2 local rehearsal polish: 0.5 to 1 development day.
- Real payload draft development: 1 to 2 development days.
- Real create safety gate hardening: about 1 development day.
- First small live create, after explicit approval: 0.5 to 1 development day.
- Stable automation loop: 1 to 2 weeks.
- CLI and policy engine migration after stabilization: 3 to 5 development days.

These estimates assume the project continues to prioritize safety over speed.
The goal is not the fastest possible first create. The goal is that the first
real create cannot run out of control.

## Non-Negotiable Safety Rules

1. Do not commit tokens, sessions, runtime artifacts, real account CSVs, or
   private local configs.
2. Do not perform real business actions unless a separate live phase is
   approved.
3. Do not let AI make runtime execution decisions.
4. Do not bypass `request -> strategy -> preflight -> dry-run -> approve ->
   execute`.
5. Treat script errors as bugs. Fix the script, do not manually work around the
   bug in a one-off way.
6. Keep `create_execute` hard-blocked until the live phase explicitly changes
   that rule.
