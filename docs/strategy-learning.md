# 策略学习脚本

`strategy_learning` 是只读学习流程，用历史操作日志和历史指标生成候选策略。它不调用媒体接口，不创建项目，不暂停、删除、改预算或改出价。

## 每日运行

建议排在昨日素材明细、操作日志、每日报表和源素材汇总之后运行：

```bash
python3 scripts/run_strategy_learning.py \
  --config configs/runtime.example.json \
  --request configs/strategy-learning.example.json \
  --target-date yesterday
```

默认学习窗口是 `target_date` 往前 45 天。也可以手动回放：

```bash
python3 scripts/run_strategy_learning.py \
  --config configs/runtime.example.json \
  --request configs/strategy-learning.example.json \
  --start-date 2026-05-10 \
  --end-date 2026-06-01
```

## 运行边界

- 学习脚本每天至少运行一次，产出最新候选策略。
- 建议生成仍必须使用实时巡检快照判断今天的账户、项目和单元状态。
- 历史数据只作为学习和证据来源，不能冒充实时数据。
- 候选策略默认 `enabled: false`，人工确认前不能进入项目管理建议。
- 样本不足时只能输出只读诊断，不能用内置默认项目动作规则兜底。
- 二阶段学习只生成待复核规则预览；不会自动把暂停、删除、预算、出价规则写成启用状态。
- 暂停/删除样本里只要混有操作前已有转化的项目，就阻断为人工建模复核，不能自动推导成项目管理规则。

## 输出

主要产物：

- `data/runs/strategy_learning/latest.json`
- `data/runs/strategy_learning/<timestamp>.json`
- `configs/learned-strategies/*.learned.local.json`

每个候选策略包含：

- 中文摘要
- 产品范围
- 动作类型
- 风险等级
- 样本数和样本门槛
- 操作前指标分布
- 样本证据
- 阻断原因
- 运行时契约

开启二阶段学习后，还会包含：

- 样本分层：有指标/缺指标、无转化/有转化、可回测样本数。
- 回测摘要：操作后成本或 ROI 是否出现正向变化，只作为历史复盘参考。
- 规则预览：例如 `adjust_project_bid_high_cpa`、`adjust_project_budget_low_roi` 的待复核参数。
- 二阶段状态：`candidate_passed_backtest`、`candidate_requires_review`、`blocked_mixed_high_risk_samples` 或 `insufficient_samples_readonly`。

运行时契约固定为：

```json
{
  "strategy_source": "learned_strategy_only",
  "runtime_metric_source": "realtime_patrol_snapshot",
  "historical_data_usage": "learning_and_evidence_only",
  "allow_builtin_default_project_actions": false,
  "execution_enabled": false
}
```

## 样本门槛

第一版按动作风险分级：

| 动作 | 跨产品最低样本 | 本产品最低样本 | 说明 |
| --- | ---: | ---: | --- |
| 只读诊断 | 5 | 1 | 低风险，只读展示 |
| 调预算 / 调出价 | 30 | 5 | 中风险，需跨产品规律和本产品校准 |
| 创建项目建议 | 30 | 5 | 只生成创建计划预览 |
| 暂停项目 | 80 | 10 | 高风险，样本不足不进主建议 |
| 删除项目 | 100 | 15 | 最高风险，样本不足不进主建议 |

候选策略即使达到样本门槛，也只表示“可人工复核”，不代表自动启用。

## 二阶段学习

二阶段学习在一阶段候选样本上继续做三件事：

1. 样本分层：把同一个动作拆成无转化、有转化、指标缺失、可回测几类。
2. 历史回测：比较操作前后窗口内的消耗和 ROI，估算正向复盘率和误伤风险。
3. 规则预览：只有样本数、指标覆盖率和回测都满足门槛时，才生成禁用状态的 `control_strategy_rule` 预览。

示例配置：

```json
{
  "second_stage_learning": {
    "enabled": true,
    "min_backtest_samples": 5,
    "min_backtest_positive_rate": 0.5,
    "min_metric_available_rate": 0.5,
    "budget_decrease_percent_default": 20,
    "bid_decrease_percent_default": 10,
    "min_cost_floor": 100
  }
}
```

生成的 `control_strategy_rule` 仍然是：

```json
{
  "enabled": false,
  "review_required": true
}
```

建议工作台只接受人工确认后的学习规则：策略必须同时满足 `enabled=true`，且状态为 `approved`、`active` 或 `enabled`。因此学习脚本每天自动运行不会把历史阈值直接塞进今日建议。
