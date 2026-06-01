# FastAPI + React 阶段 0 收口记录

记录日期：2026-05-30

总架构说明：[RoiBang 项目讲解与架构说明](roibang-project-architecture.md)

## 收口目标

阶段 0 只确认当前成果是否能作为后续开发基线，不新增真实业务能力。

- FastAPI + React 继续作为当前主入口，Streamlit 只作为旧版保留入口。
- 当前规则建议中心完成的是“巡检建议 -> 项目管理 JSON -> 项目管理页确认执行”的闭环。
- 当前规则建议中心不生成创建项目建议；创建项目建议属于下一阶段。
- 产品自动化配置页已经承载产品配置、允许创建账户名单、dry-run、AI 创建模板草稿和草稿转正预览。
- AI 创建模板草稿和转正都不调用平台接口，不生成或执行创建计划。

## 已确认的主入口范围

React 路由当前覆盖：

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

FastAPI 当前挂载的主要业务路由：

- `dashboard`
- `accounts`
- `suggestions`
- `create_plans`
- `project_management`
- `account_remarks`
- `sites`
- `tasks`
- `operations`
- `actions`
- `workflows`
- `product_automation`
- `health/settings`

## 当前业务边界

规则建议中心：

- 可以同步数据并重算建议。
- 可以展示可转动作建议和只读建议的数量。
- 只允许删除项目、关闭项目、下调预算、下调出价生成项目管理 JSON。
- 观察、诊断、继续跑等只读建议不能生成动作 JSON。
- 生成项目管理 JSON 后，仍必须跳转项目管理页做执行预览和确认。

创建计划：

- 继续使用固定 `create-modes` 和固定脚本生成计划。
- 真正创建执行仍必须先预览、再输入确认。
- 不从建议中心直接创建项目。

产品自动化配置：

- 维护产品基础配置和允许创建账户名单。
- dry-run 只做本地验证。
- AI 创建模板草稿只做只读分析。
- AI 模板草稿转正只写本地 `configs/create-modes`，默认不覆盖已有模板。

## 后续开发顺序建议

1. 阶段 1：新增真正的创建项目建议。
   - 新增建议动作，例如 `suggest_create_project`。
   - 明确证据来源：账户容量、产品归属、素材供给、历史 ROI/转化、近期消耗、现有项目状态。
   - 输出只读建议，先不直接生成创建计划。
   - 增加后端测试，证明项目管理建议和创建建议不会互相串线。

2. 阶段 2：创建建议转创建计划预览。
   - 从人工选中的创建建议生成 create-plan preview。
   - 必须复用创建计划页已有预览、确认和执行链路。
   - 不允许建议中心绕过创建计划页直接执行真实创建。

3. 阶段 3：建议有效性回测和运营复盘。
   - 把创建建议纳入回测口径。
   - 在首页和建议中心显示建议采纳、执行、后续表现。
   - 保留所有中文摘要、证据和 artifact 路径，便于人工复盘。

## 本阶段验收命令

本阶段收口后需要至少运行：

```bash
env PYTHONPATH=src python3 -m pytest backend/tests/test_api_foundation.py backend/tests/test_suggestions_api.py backend/tests/test_project_management_api.py backend/tests/test_product_automation_api.py backend/tests/test_create_plans_api.py
npm run build
```

如果公共契约或共享逻辑发生变化，再运行：

```bash
env PYTHONPATH=src python3 -m pytest backend/tests tests
```

浏览器抽查至少覆盖：

- `/settings`：React 替换验收清单能加载，并展示最新主入口范围。
- `/suggestions`：能看到建议转动作 JSON 的闭环和只读建议边界。
- `/project-management?config_source=suggestions_generated`：能看到建议来源风险提示。
