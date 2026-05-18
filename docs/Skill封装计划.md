# RoiBang-v2 Skill 封装计划

版本日期：2026-05-16

## 目标

把 RoiBang-v2 封装成公司内部可复用的 `Skill（技能）`，让同事或 Codex 能用固定话术调用固定脚本，而不是临场理解业务流程、临场拼接口、临场写复杂 JSON。

Skill 只负责“把需求映射到固定脚本入口”，不替代 RoiBang-v2 系统本体。

```text
同事的一句话需求
-> Skill 判断场景
-> 固定脚本
-> JSON 配置 / JSON 结果
-> 人工确认后执行真实动作
```

## 固定边界

1. Skill 不能直接执行真实业务动作，真实动作仍然必须走 RoiBang-v2 固定脚本。
2. Skill 不能猜账户、猜素材、猜预算、猜出价、猜 ROI 系数。
3. Skill 不能绕过 `确认执行`。
4. Skill 不能自动改现有固定创建模板。
5. Skill 不能把 token（令牌）、session（登录态）、本地私有配置打包进去。
6. Skill 不能替代数据库、定时任务、运行环境、配置文件。
7. Skill 的作用是降低使用门槛，不改变系统主路径。

## 前置条件

封装 Skill 前，RoiBang-v2 需要先稳定以下主链路：

1. 创建链路：

```text
run_create_mode.py
-> run_create_live_execute_terminal.py
-> run_create_live_execute_report.py
```

2. 项目管理链路：

```text
run_project_status_update.py
run_project_delete.py
run_project_budget_update.py
run_project_bid_update.py
run_project_roi_coeff_update.py
run_project_schedule_restore_due.py
```

3. 投放巡检链路：

```text
run_delivery_patrol.py
-> run_delivery_patrol_suggestions.py
```

4. 定时任务链路：

```text
scheduler（定时任务）
-> script.command（固定脚本命令）
-> JSON result（JSON 结果）
```

## Skill 拆分方案

不建议做一个巨大的 RoiBang-v2 Skill。建议拆成 3 个小 Skill，每个 Skill 只处理一个明确场景。

### 1. roibang-create

用途：创建项目和单元。

触发场景：

```text
某些账户跑 每付通投近期放量
某些账户跑 每付通投测新
某些账户跑 7R 通投历史放量
```

固定入口：

```text
scripts/run_create_mode.py
scripts/run_create_live_execute_terminal.py
scripts/run_create_live_execute_report.py
```

必须遵守：

- 标准创建不手写复杂 request（请求配置）文件。
- 必须明确 `通投/男`。
- 放量必须明确 `历史放量/近期放量`。
- 复测必须明确 `低转化复测/无转化复测`。
- 不允许 `每付通投放量`、`7R 放量` 这类模糊说法。
- 真实执行前必须等待用户说 `确认执行`。

输出要求：

```text
创建计划路径
账户数
项目数
单元数
素材数
每个批次可选素材数
执行结果 artifact（执行结果文件）路径
失败账户/失败项目/失败单元
```

### 2. roibang-project-management

用途：项目管理。

触发场景：

```text
关闭某些账户的所有项目
删除项目名包含 0515 且今天消耗低于 100 的项目
调整项目预算
调整项目出价
调整 7R 项目 ROI 系数
拉空/恢复投放时段
```

固定入口：

```text
scripts/run_project_status_update.py
scripts/run_project_delete.py
scripts/run_project_budget_update.py
scripts/run_project_bid_update.py
scripts/run_project_roi_coeff_update.py
scripts/run_project_schedule_restore_due.py
```

必须遵守：

- 按实时数据筛选时，只能调用平台实时查询，不用历史数据猜。
- 删除、关闭、调预算、调出价、调 ROI 系数都必须输出 JSON 结果。
- 真实执行前必须等待用户说 `确认执行`。
- 不走 AI 临场拼接口。

后续需要补齐：

- 按 `今天/昨天/近3天/近7天` 消耗筛选项目。
- 按项目名关键词筛选项目。
- 按项目状态筛选项目。
- 按账户批量执行。
- 执行结果汇总失败原因和接口错误码。

### 3. roibang-delivery-patrol

用途：投放账户巡检和建议生成。

触发场景：

```text
跑一次投放巡检
查看今天账户表现
生成投放巡检建议
推送飞书巡检报告
```

固定入口：

```text
scripts/run_delivery_patrol.py
scripts/run_delivery_patrol_suggestions.py
```

必须遵守：

- 巡检是只读动作。
- 建议只生成 JSON，不直接执行。
- 建议必须能追溯到数据字段和规则。
- 飞书只推摘要、重点账户、重点项目、重点单元；完整明细留在 artifact（执行结果文件）。

第一版建议类型：

```text
继续观察
建议关闭
建议删除
建议保留
建议复测
建议创建补量
```

## 不做的 Skill

短期不做这些：

1. 不做 `roibang-admin` 这种大而全 Skill。
2. 不做让同事自由输入接口参数的 Skill。
3. 不做自动改模板的 Skill。
4. 不做自动执行真实动作的 Skill。
5. 不把私有配置、token、session 放进 Skill。

## Skill 目录结构建议

后续可以放在：

```text
~/.codex/skills/roibang-create/
~/.codex/skills/roibang-project-management/
~/.codex/skills/roibang-delivery-patrol/
```

每个 Skill 只需要：

```text
SKILL.md
agents/openai.yaml
references/commands.md
references/examples.md
```

其中：

- `SKILL.md`：只写触发条件、固定边界、主流程。
- `commands.md`：记录固定脚本命令。
- `examples.md`：记录合法和非法说法。
- 不放业务密钥。
- 不放运行产物。
- 不复制 RoiBang-v2 源码。

## 给同事使用前还要做的事

1. 固定项目安装路径，或让 Skill 通过环境变量读取项目路径。
2. 确认同事电脑上有 Python、依赖、数据库、配置文件。
3. 每个同事单独配置自己的 token（令牌）和 session（登录态）。
4. 写清楚哪些动作需要 `确认执行`。
5. 给每个 Skill 配一组最小测试口令。
6. 用真实但低风险任务验证一次。

## 推荐实施顺序

第一阶段：先不写 Skill，只把主链路继续稳定。

```text
项目管理实时筛选
-> 投放账户业务巡检
-> 投放巡检建议
-> 创建效率和执行反馈
-> AI 创建模板草稿
```

第二阶段：封装内部 Skill。

```text
roibang-create
-> roibang-project-management
-> roibang-delivery-patrol
```

第三阶段：给同事试用。

```text
只读巡检
-> 创建计划生成
-> 项目管理配置生成
-> 小批量真实执行
```

第四阶段：整理公司内部使用规范。

```text
合法口令
确认执行规则
失败处理规则
飞书汇报格式
新增账户流程
```

## 成功标准

Skill 封装完成后，同事应该能做到：

1. 用一句话生成创建计划。
2. 用一句话调用项目管理脚本。
3. 用一句话跑投放巡检。
4. 看得懂 JSON 汇报和飞书摘要。
5. 不需要理解巨量 API。
6. 不需要临时写复杂 JSON。
7. 不会绕过人工确认执行真实动作。

最终目标：

```text
RoiBang-v2 负责稳定执行
Skill 负责稳定调用
AI 负责解释、生成配置、修代码
真实业务动作由固定脚本完成
```
