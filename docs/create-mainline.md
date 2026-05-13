# 创建链路主路径

这份文档只记录当前创建链路的固定脚本主线。不要在这里扩展审批包、执行包或临时业务流程。

## 原则

- AI 只写 `strategy.json`（策略配置）或改代码。
- 真实创建只走固定脚本。
- 账户、模板、预算、ROI、出价、素材数、项目数、单元数都来自 JSON 配置。
- 每个脚本输出 JSON，并写入 `data/runs/...` 下的 artifact（执行结果文件）。

## 主路径

```text
mode request（创建模式请求）或 strategy.json（策略配置）
-> create_plan（创建计划）
-> check-config-only（只检查配置）
-> 用户确认
-> live_execute_once（一次性真实创建）
-> live_execute_report（执行结果汇报）
```

## 1. 创建模式生成创建计划

输入：

- `configs/create-mode-requests/<name>.local.json`
- `configs/create-modes/*.example.json`
- `configs/create-templates/wx-mini-game.json`

命令：

```bash
PYTHONPATH=src python3 scripts/run_create_mode.py \
  --config configs/runtime.example.json \
  --request configs/create-mode-requests/<name>.local.json \
  --policy policies/create-policy.example.json \
  --template-catalog configs/create-templates/wx-mini-game.json
```

输出：

- `data/runs/create_mode/*.json`

## 2. 策略生成创建计划

输入：

- `configs/strategies/<name>.local.json`
- `configs/create-templates/wx-mini-game.json`
- `policies/create-policy.example.json`

命令：

```bash
PYTHONPATH=src python3 scripts/run_create_plan_from_strategy.py \
  --config configs/runtime.example.json \
  --strategy configs/strategies/<name>.local.json \
  --policy policies/create-policy.example.json \
  --template-catalog configs/create-templates/wx-mini-game.json \
  --output-dir configs/create-plans
```

输出：

- `configs/create-plans/<plan_id>.local.json`
- `data/runs/create_plan_from_strategy/*.json`

## 3. 单独校验创建计划

命令：

```bash
PYTHONPATH=src python3 scripts/run_create_plan_validate.py \
  --config configs/runtime.example.json \
  --plan configs/create-plans/<plan_id>.local.json \
  --policy policies/create-policy.example.json
```

输出：

- `data/runs/create_plan_validate/*.json`

## 4. 只检查配置

`check-config-only（只检查配置）` 只看本地执行配置、token（令牌）指针、接口地址、账户准允许名单和计划基础字段，不调用外部接口，不生成真实 payload（接口载荷），也不执行创建。

命令形态：

```bash
PYTHONPATH=src python3 scripts/run_create_live_execute_once.py \
  --config configs/runtime.create-live.local.json \
  --policy policies/create-live-execute.local.json \
  --plan data/runs/create_mode/<artifact>.json \
  --check-config-only
```

输出：

- `data/runs/create_live_execute_once/*.json`

## 5. 真实创建

只在人工确认后运行。需要可见进度时，使用 `run_create_live_execute_terminal.py`（带终端进度的真实执行入口）。

命令形态：

```bash
PYTHONPATH=src python3 scripts/run_create_live_execute_terminal.py \
  --config configs/runtime.create-live.local.json \
  --policy policies/create-live-execute.local.json \
  --plan data/runs/create_mode/<artifact>.json \
  --open-progress-window
```

输出：

- `data/runs/create_live_execute_once/*.json`

真实创建顺序固定为：

```text
create_project（创建项目）
-> lookup_target_material（创建前查目标账户素材库）
-> bind_material（仅推送目标账户没有的素材）
-> lookup_target_material（目标账户素材回查）
-> create_unit（创建单元）
```

`run_create_live_execute_once.py` 会从 `create_mode（创建模式）` 或 `create_strategy_plan（创建策略计划）` 产物内部生成本次执行所需的接口草稿。`--create-execute-artifact` 只保留给旧产物兼容，不再是主路径必填项。

## 6. 执行结果汇报

命令：

```bash
PYTHONPATH=src python3 scripts/run_create_live_execute_report.py \
  --config configs/runtime.example.json \
  --plan configs/create-plans/<plan_id>.local.json \
  --create-live-execute-once-artifact data/runs/create_live_execute_once/<artifact>.json
```

输出：

- `data/runs/create_live_execute_report/*.json`

## 当前不做

- 不新增 CLI（命令行菜单）。
- 不新增飞书交互。
- 不新增审批包、准备包、执行包。
- 不让 AI 临场拼真实业务参数。

## 兼容调试入口

以下脚本只作为本地调试或旧产物兼容，不属于创建主路径：

- `scripts/run_create_preflight.py`：preflight（预演前检查）。
- `scripts/run_create_provider_field_map_check.py`：provider field map check（平台字段映射检查）。
- `scripts/run_create_dry_run.py`：dry-run（预演）。
- `scripts/run_create_execute.py`：create_execute（创建执行交接产物）。
