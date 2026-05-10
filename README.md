# RoiBang-v2

RoiBang-v2 是一个“脚本优先”的广告投放自动化系统。

当前仓库是干净的 v2 架构。老项目目录只允许作为历史参考，不能作为当前开发目标；除非明确要求，不要读取老目录。

## 当前阶段

当前处于 第二阶段准备阶段。这个阶段只做本地预演、字段复核、策略整理和安全闸门，不做真实创建，也不调用创建接口。

第二阶段准备收口文档见：`docs/phase-2-preparation-closeout.md`。

当前核心链路固定为：

```text
request -> strategy -> preflight -> dry-run -> approve -> execute
```

字段解释：

- `request`：创建请求。
- `strategy`：策略分配。
- `preflight`：执行前检查。
- `dry-run`：本地预演，不产生真实业务动作。
- `approve`：批准记录，目前仍不是允许真实执行。
- `execute`：执行阶段，目前必须硬阻断。

## 核心原则

业务动作必须由固定脚本确定性执行。脚本只能读取 JSON 配置、JSON 策略和 SQLite 状态。

AI 的职责是：

- 写脚本、修脚本。
- 阅读运行产物 JSON。
- 更新策略 JSON。
- 总结复盘结果。

AI 不能在业务运行时临场决定是否执行、创建、暂停、删除、改预算或调时段。

如果固定脚本执行出错，要把它当作代码、配置、策略或数据的 BUG 来修，并补测试。不能让 AI 临场绕过脚本。

## 安全边界

当前阶段必须保持：

```json
{
  "execution_enabled": false,
  "external_api_calls": 0,
  "actions": []
}
```

含义：

- `execution_enabled=false`：业务执行关闭。
- `external_api_calls=0`：没有外部接口调用。
- `actions=[]`：没有可执行业务动作。

`create_execute` 必须继续硬阻断。`hard-blocked` 的意思是：即使前面检查通过，脚本也必须停在本地复核产物，不能创建真实项目。

## 第二阶段 常用命令

### 平台字段映射准备

```bash
PYTHONPATH=src scripts/run_create_phase2_provider_mapping_prep.py \
  --config configs/runtime.example.json \
  --policy policies/strategy.example.json
```

这个命令生成 `create_phase2_provider_mapping_prep` 本地产物，用来检查未来平台字段映射准备情况。

### 模板槽位准备

```bash
PYTHONPATH=src scripts/run_create_phase2_template_slot_prep.py \
  --config configs/runtime.example.json \
  --request configs/requests/example.create-request.json \
  --policy policies/strategy.example.json
```

这个命令检查未来创建模板里的固定项、按账户填写项和策略固定项。

勇者突进微信小游戏当前有 4 个模板：

- 微小每付男
- 微小每付通投
- 微小每付7R男
- 微小每付7R通投

### 模板确认记录

```bash
PYTHONPATH=src scripts/run_create_phase2_template_confirmation_pack.py \
  --config configs/runtime.example.json
```

这个命令读取最新模板槽位准备产物，生成待确认记录。`required_user_input_now=true` 表示可以人工确认，但仍不允许真实创建。

### 勇者突进手填配置检查

```bash
PYTHONPATH=src python3 scripts/run_create_phase2_yzt_config_check.py \
  --config configs/runtime.example.json \
  --preview-config configs/create/yzt-wx-mini-game.preview.example.json \
  --policy policies/strategy.example.json
```

这个命令检查手填配置是否安全，包括账户、预算、模板、ROI 系数、项目数量、单元数量等。

### 目标账户池检查

```bash
PYTHONPATH=src python3 scripts/run_create_phase2_yzt_account_pool_check.py \
  --config configs/runtime.example.json \
  --preview-config configs/create/yzt-wx-mini-game.preview.example.json \
  --policy policies/strategy.example.json
```

这个命令只读本地 SQLite，确认配置里的目标账户是否存在于本地账户池。

### 素材候选池检查

```bash
PYTHONPATH=src python3 scripts/run_create_phase2_yzt_material_pool_check.py \
  --config configs/runtime.example.json \
  --preview-config configs/create/yzt-wx-mini-game.preview.example.json \
  --policy policies/strategy.example.json
```

这个命令只读本地 SQLite，检查当前配置需要的素材数量是否能被候选池满足。

### 一键准备检查

```bash
PYTHONPATH=src python3 scripts/run_create_phase2_yzt_preparation_check.py \
  --config configs/runtime.example.json \
  --preview-config configs/create/yzt-wx-mini-game.preview.example.json \
  --policy policies/strategy.example.json
```

这个命令依次运行配置检查、账户池检查和素材池检查，并输出 `operator_guide`。`operator_guide` 是操作员指南，告诉你下一步该修什么或跑什么。

### 本地私有配置准备

```bash
PYTHONPATH=src python3 scripts/run_create_phase2_yzt_local_config_prepare.py
```

这个命令把安全示例配置复制为本地私有配置：

```text
configs/create/yzt-wx-mini-game.preview.local.json
```

这个 `*.local.json` 文件已被 git 忽略，真实账户只能写在这里，不能提交。
不要提交真实账户。

### 创建预览

```bash
PYTHONPATH=src python3 scripts/run_create_phase2_yzt_create_preview.py \
  --config configs/runtime.example.json \
  --preview-config configs/create/yzt-wx-mini-game.preview.example.json \
  --policy policies/strategy.example.json
```

这个命令生成标准创建请求 `standard_create_request`，并检查项目名、账户、预算、ROI、固定 URL 等。仍然只写本地产物。

### 完整本地预演链

```bash
PYTHONPATH=src python3 scripts/run_create_phase2_yzt_dry_chain.py \
  --config configs/runtime.example.json \
  --preview-config configs/create/yzt-wx-mini-game.preview.example.json \
  --policy policies/strategy.example.json
```

这个命令完整跑：预览、创建请求记录、策略计划、执行前检查、字段映射检查和 dry-run。它不创建项目，只生成本地 JSON 产物。

### 平台字段证据复核

```bash
PYTHONPATH=src python3 scripts/run_create_provider_evidence_review.py \
  --config configs/runtime.example.json \
  --policy policies/strategy.example.json
```

这个命令生成平台字段证据复核产物。重点输出：

- `evidence_status_counts`：证据状态计数。
- `operator_guide`：操作员指南。
- `evidence_worksheet`：证据填写清单。
- `provider_field_gap_report`：缺平台字段报告。

这个命令不访问外网、不调用接口、不真实创建。

## 项目命名规则

当前勇者突进项目名规则：

```text
月日_归属_游戏名_项目模板名_批次码_序号
```

示例：

```text
0509_郭靖_勇者突进_微小每付7R男_B281B2BCB_01
```

单元名称当前草稿规则：

```text
{project_name}_U{unit_index:02d}
```

示例：

```text
0509_郭靖_勇者突进_微小每付7R男_B281B2BCB_01_U01
```

## 本地数据同步

本地同步和分析脚本只负责读数据、写 SQLite、写运行产物，不执行业务动作。

常用命令包括：

```bash
PYTHONPATH=src scripts/run_material_sync.py --config configs/runtime.example.json --request configs/material-sync.example.json
PYTHONPATH=src scripts/run_material_source.py --config configs/runtime.example.json --request configs/material-source.example.json
PYTHONPATH=src scripts/run_data_sync.py --config configs/runtime.example.json --request configs/data-sync.example.json
PYTHONPATH=src scripts/run_daily_learning.py --config configs/runtime.example.json --request configs/daily-learning.example.json
```

## 创建链路脚本

创建链路从请求到硬阻断执行，完整顺序是：

```bash
PYTHONPATH=src scripts/run_create_request.py --config configs/runtime.example.json --request configs/requests/example.create-request.json
PYTHONPATH=src scripts/run_create_strategy_plan.py --config configs/runtime.example.json --policy policies/strategy.example.json
PYTHONPATH=src scripts/run_create_preflight.py --config configs/runtime.example.json --policy policies/strategy.example.json
PYTHONPATH=src scripts/run_create_provider_field_map_check.py --config configs/runtime.example.json --policy policies/strategy.example.json
PYTHONPATH=src scripts/run_create_dry_run.py --config configs/runtime.example.json --policy policies/strategy.example.json
PYTHONPATH=src scripts/run_create_approval.py --config configs/runtime.example.json --policy policies/strategy.example.json
PYTHONPATH=src scripts/run_create_plan_snapshot.py --config configs/runtime.example.json
PYTHONPATH=src scripts/run_create_execute.py --config configs/runtime.example.json --policy policies/strategy.example.json
```

这些脚本必须保持本地化和可复盘，不能越过安全开关。

## 定时任务

定时任务配置是示例文件，不会自动安装或执行。

```bash
PYTHONPATH=src scripts/validate_scheduler_jobs.py --registry configs/scheduler/roibang-v2.jobs.example.json
PYTHONPATH=src scripts/render_scheduler_templates.py --registry configs/scheduler/roibang-v2.jobs.example.json --output-dir scheduler
PYTHONPATH=src scripts/run_scheduler_job.py --job-id roibang-material-sync
PYTHONPATH=src scripts/validate_run_artifact.py --job-id roibang-daily-report-pipeline
```

## 禁止事项

- 不提交 token、session、真实账户 CSV、数据库、运行产物、本地私有配置。
- 不执行真实创建、暂停、删除、改预算、调时段。
- 不让 AI 在运行时做业务决策。
- 不绕过 `request -> strategy -> preflight -> dry-run -> approve -> execute`。
- 不把 `create_execute` 从硬阻断改成真实执行，除非开启单独批准的 真实执行阶段。
