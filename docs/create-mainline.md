# 创建链路主路径

这份文档只记录当前创建链路的固定脚本主线。不要在这里扩展审批包、执行包或临时业务流程。

## 原则

- AI 只写 `strategy.json`（策略配置）或改代码。
- 真实创建只走固定脚本。
- 账户、模板、预算、ROI、出价、素材数、项目数、单元数都来自 JSON 配置。
- 每个脚本输出 JSON，并写入 `data/runs/...` 下的 artifact（执行结果文件）。

## 主路径

```text
strategy.json（策略配置）
-> create_plan（创建计划）
-> validate（校验）
-> local_chain（本地预演链路）
-> live_execute_once（一次性真实创建）
-> live_execute_report（执行结果汇报）
```

## 1. 策略生成创建计划

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
  --output-dir configs/create-plans \
  --run-local-chain
```

输出：

- `configs/create-plans/<plan_id>.local.json`
- `data/runs/create_plan_from_strategy/*.json`
- 如果 `--run-local-chain` 成功，会在输出 JSON 里给出 `live_execute_commands`（真实执行命令）。

## 2. 单独校验创建计划

命令：

```bash
PYTHONPATH=src python3 scripts/run_create_plan_validate.py \
  --config configs/runtime.example.json \
  --plan configs/create-plans/<plan_id>.local.json \
  --policy policies/create-policy.example.json
```

输出：

- `data/runs/create_plan_validate/*.json`

## 3. 本地预演链路

通常第 1 步加 `--run-local-chain` 已经会跑。需要单独跑时：

```bash
PYTHONPATH=src python3 scripts/run_create_first_live_local_chain.py \
  --config configs/runtime.example.json \
  --plan configs/create-plans/<plan_id>.local.json \
  --policy policies/create-policy.example.json \
  --create-execute-handoff data/runs/create_execute/<plan_id>.json
```

输出：

- `data/runs/create_first_live_local_chain/*.json`
- `data/runs/create_execute/<plan_id>.json`

## 4. 真实创建

只在人工确认后运行第 1 步输出里的 `live_execute_commands`。

命令形态：

```bash
PYTHONPATH=src python3 scripts/run_create_live_execute_once.py \
  --config configs/runtime.create-live.local.json \
  --policy policies/create-live-execute.local.json \
  --plan configs/create-plans/<plan_id>.local.json \
  --create-execute-artifact data/runs/create_execute/<plan_id>.json
```

输出：

- `data/runs/create_live_execute_once/*.json`

真实创建顺序固定为：

```text
create_project（创建项目）
-> bind_material（素材推送/绑定）
-> lookup_target_material（目标账户素材回查）
-> create_unit（创建单元）
```

## 5. 执行结果汇报

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
