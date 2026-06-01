# RoiBang 项目讲解与架构说明

记录日期：2026-05-31

## 一句话定位

RoiBang 是一个广告投放自动化运营平台，通过固定脚本、JSON 配置、定时任务、FastAPI/React 看板和本地数据，实现创建、项目管理、素材、落地页、账户等日常操作的可审计自动化。

它不是一个“AI 自己决定怎么投广告”的系统。AI 可以辅助分析、生成配置草稿、解释结果、汇总报告，但真实业务动作必须由固定脚本读取 JSON 配置后执行。

## 核心原则

- 投放决策要固化在确定性脚本、策略配置和阈值规则里。
- React/FastAPI 负责交互层、本地编排、中文摘要、任务状态和结果展示。
- AI 不临场猜账户、猜素材、猜预算、猜项目或改参数。
- 真实执行必须经过预览、人工确认、固定脚本执行、结果归档。
- 所有业务日期按北京时间 UTC+8 判断，不能直接使用 UTC 日期代替业务日期。
- 所有运行结果必须写入 `data/runs`，并保留 `workflow`、`summary`、`blocking_reasons`、`artifact_path`、`external_api_calls` 等契约字段。

## 整体架构

```text
人工操作 / 定时任务 / 固定脚本
          |
          v
React 看板  <---->  FastAPI 本地接口
                       |
                       v
              固定脚本 / 工作流
                       |
      +----------------+----------------+
      |                |                |
      v                v                v
 JSON 配置        SQLite / 本地数据     data/runs 结果产物
```

三个入口最终都汇聚到同一套固定脚本、配置和本地数据：

- 人工操作入口：React 页面发起预览、确认和任务。
- 定时入口：scheduler 按固定 `script.command` 启动只读或执行类任务。
- 脚本入口：`scripts/run_*.py` 作为可审计的固定命令。

## 主要模块

### React/FastAPI 主入口

FastAPI + React 是当前日常主入口，用来替换 Streamlit 的日常操作面板。

- 前端：`http://127.0.0.1:5180/`
- 后端：`http://127.0.0.1:8007/api`

当前主页面：

- `/` 首页
- `/accounts` 产品账户库
- `/suggestions` 规则建议中心
- `/create-plans` 创建计划
- `/project-management` 项目管理
- `/account-remarks` 账户备注
- `/sites` 落地页管理
- `/tasks` 任务中心
- `/operations` 操作日志
- `/results` 结果中心
- `/execute` 执行入口
- `/product-automation` 产品自动化配置
- `/settings` 系统设置

### 固定脚本与工作流

固定脚本是业务动作的唯一执行边界。

- 创建计划：`scripts/run_create_mode.py`
- 真实创建：`scripts/run_create_live_execute_once.py`
- 项目管理执行：`scripts/run_project_update_execute.py`
- 规则建议转项目管理 JSON：`scripts/run_project_update_from_suggestions.py`
- 建议刷新：`scripts/run_suggestions_refresh.py`
- AI 创建模板草稿：`scripts/run_ai_create_template_drafts.py`
- AI 模板草稿转正：`scripts/run_ai_template_draft_promote.py`

React/FastAPI 可以调用这些脚本，但不能绕过它们直接拼平台业务接口。

### JSON 配置

JSON 配置是业务输入的审计边界。

- `configs/create-modes`：固定创建模式。
- `configs/create-mode-requests`：创建计划请求。
- `configs/project-updates`：项目管理动作配置。
- `configs/product-automation`：产品自动化基础配置。
- `policies`：执行策略和安全策略。

后续“创建项目建议”需要新增独立策略配置层，例如：

- `configs/create-suggestion-strategies`

这层策略负责描述什么账户可扩量、什么素材够资格、什么 ROI/转化/消耗阈值触发创建建议。前端只展示结果，不负责判断“该不该创建项目”。

### 本地数据

SQLite 和本地表是建议、计划和复盘的事实来源。

常见输入包括：

- 账户归属和账户状态。
- 项目、单元、素材日维度数据。
- 源素材表现汇总。
- 操作日志和任务记录。
- 创建执行结果和巡检结果。

所有建议都应该能回溯到本地数据证据，不能只给一个无来源的结论。

### 结果产物

所有工作流都应该输出 JSON 产物到 `data/runs`。

结果产物必须优先服务人工复盘：

- 中文摘要先于原始 JSON。
- 阻塞原因必须明确。
- 外部接口调用数必须可见。
- artifact 路径必须可追溯。
- 真实执行结果必须能回到任务中心、操作日志和结果中心查看。

## 当前主业务链路

### 创建计划

创建计划页负责从固定创建模式生成计划、执行预览、人工确认、真实创建任务和结果复盘。

创建链路仍然是：

```text
create_project -> bind_material -> lookup_target_material -> create_unit
```

建议中心不能直接创建项目，后续创建建议也必须先转到创建计划页。

### 项目管理

项目管理负责项目状态、预算、出价、ROI 系数、投放时段等动作。

所有高风险动作必须经过：

```text
生成项目管理 JSON -> 执行预览 -> 输入确认 -> 固定脚本执行 -> 结果复盘
```

### 规则建议中心

当前规则建议中心只处理项目管理类建议和只读观察/诊断建议。

可以转项目管理 JSON 的建议包括：

- 删除项目
- 关闭项目
- 下调预算
- 下调出价

不能转动作 JSON 的只读建议包括：

- 观察
- 诊断
- 继续跑
- 单元好/差信号

真正的“创建项目建议”属于下一阶段，不能混入当前项目管理建议闭环。

### 产品自动化配置

产品自动化配置页负责：

- 产品基础配置。
- 允许创建账户名单。
- 自动化 dry-run。
- AI 创建模板草稿。
- AI 模板草稿转正预览。

AI 创建模板草稿只读分析本地数据；草稿转正只写本地 `configs/create-modes`，不调用平台接口，也不生成或执行创建计划。

## AI 的角色边界

AI 可以做：

- 帮开发者写代码、修脚本、补测试。
- 阅读本地数据后生成配置草稿或建议草稿。
- 解释结果产物和阻塞原因。
- 总结任务、日志和报告。

AI 不可以做：

- 临场决定真实投放动作。
- 绕过固定脚本直接调用平台接口。
- 在没有策略配置和证据的情况下生成创建建议。
- 自动覆盖人工模板或执行真实创建。
- 把页面 UI 写成投放决策规则的唯一来源。

## 后续创建项目建议的原则

创建项目建议必须走策略配置层，而不是写死在前端 UI。

正确方向：

```text
本地数据
  + 产品配置
  + 账户状态
  + 素材表现
  + 项目现状
  + 创建建议策略配置
= suggest_create_project 建议 JSON
```

前端只消费建议结果：

- 展示建议。
- 展示证据。
- 展示命中策略。
- 展示风险和阻塞原因。
- 提供下一步入口。

前端不能写这种判断：

```text
ROI 达标 + 转化达标 + 素材数量足够 -> 直接显示创建建议
```

这些阈值和判断应该来自 `configs/create-suggestion-strategies` 和固定后端脚本。

## 后续开发顺序

1. 新增创建项目建议策略配置和只读脚本。
2. 生成 `suggest_create_project` 建议 JSON，只读展示，不转计划，不执行。
3. 接入规则建议中心展示创建机会，并证明它不能生成项目管理 JSON。
4. 稳定后再做“创建建议 -> 创建计划预览 -> 创建计划页确认执行”。
5. 把创建建议纳入回测和运营复盘。

每一步都必须先提供详细设计方案并确认，再修改代码。
