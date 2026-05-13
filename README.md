# RoiBang-v2

RoiBang-v2 是一个“固定脚本 + JSON 配置 + JSON 结果”的广告投放自动化系统。

核心方向：

```text
数据同步 -> 配置/模式生成计划 -> preflight（预演前检查） -> dry-run（预演） -> 人工确认 -> execute（执行） -> report（汇报）
```

AI（人工智能）只负责写代码、修脚本、看数据生成配置、复盘结果。真实业务动作只能由固定脚本读取 JSON 配置后执行，不能由 AI 临场猜账户、猜素材、猜预算、猜项目或改参数。

## 当前主线

当前主线已经从“创建链路”推进到“自动化投放控制”的基础能力：

- 创建链路：`create_project（创建项目） -> bind_material（素材推送） -> lookup_target_material（目标账户素材回查） -> create_unit（创建单元）`。
- 创建模式：用固定 `create-modes（创建模式）` 替代每次手写大 JSON。
- 项目管理：项目状态、预算、出价、ROI 系数、投放时段都走固定配置、预演和执行脚本。
- 源素材账户：不再使用“源素材候选池”概念，统一从源素材账户同步和补材。
- 定时任务：`scheduler（定时任务）` 直接写固定 `script.command（脚本命令）`，不依赖 prompt（提示词）解释业务流程。
- 结果契约：脚本输出固定 JSON，包括 `ok`、`workflow（流程名）`、`summary（摘要）`、`blocking_reasons（阻断原因）`、`artifact_path（结果文件路径）`、`external_api_calls（外部接口调用数）`。

## 创建模式

创建时必须明确模板类型，不能省略“通投/男”。例如 `7R 放量` 是歧义说法，脚本会阻断；必须写成 `7R 通投放量` 或 `7R 男放量`。

当前固定模式：

| 中文模式 | mode_key（模式键） | 模板 |
| --- | --- | --- |
| 7R 通投放量 | `wx_7r_general_scale` | `wx_7r_general（微小每付 7R 通投）` |
| 7R 通投测新 | `wx_7r_general_test_new` | `wx_7r_general（微小每付 7R 通投）` |
| 7R 男放量 | `wx_7r_male_scale` | `wx_7r_male（微小每付 7R 男）` |
| 7R 男测新 | `wx_7r_male_test_new` | `wx_7r_male（微小每付 7R 男）` |
| 每付通投放量 | `wx_pay_general_scale` | `wx_pay_general（微小每付通投）` |
| 每付通投测新 | `wx_pay_general_test_new` | `wx_pay_general（微小每付通投）` |
| 每付男放量 | `wx_pay_male_scale` | `wx_pay_male（微小每付男）` |
| 每付男测新 | `wx_pay_male_test_new` | `wx_pay_male（微小每付男）` |

放量默认：

- `daily_budget（日预算）`：88888
- `cpa_bid（项目出价）`：103
- `roi_coefficient（ROI 系数）`：7R 模板为 0.419
- 每账户 5 个项目，每项目 1 个单元，每单元 5 个素材
- 素材回看 60 天，按高消耗素材选择

测新默认：

- `daily_budget（日预算）`：10000
- `cpa_bid（项目出价）`：105
- `roi_coefficient（ROI 系数）`：7R 模板为 0.41
- 每账户 8 个项目，每项目 1 个单元，每单元 6 个素材
- 素材回看 30 天，按测新素材选择

单元层固定规则：

- `title_pool（文案池）`：放量和测新共用模板文案池。
- `CTA（行动按钮）`：每个单元从模板池稳定随机选 2-3 个。
- `product_selling_points（产品卖点）`：每个单元稳定随机选 2-3 个。
- `aweme_ids（抖音号 ID）`：固定两个抖音号，每个单元稳定随机选 1 个。
- `anchor（锚点）`、`landing_url（落地页）`、`fixed_video_cover_id（固定封面）`、`product_image_id（产品图）`：固定来自模板。
- 稳定随机的意思是：同一个 `plan_id（计划 ID）` 和 `unit_key（单元键）` 预演和执行结果一致。

生成创建计划示例：

```bash
PYTHONPATH=src python3 scripts/run_create_mode.py \
  --config configs/runtime.example.json \
  --request configs/create-mode-requests/wx_7r_general_scale.example.json \
  --policy policies/create-policy.example.json
```

## 创建执行

创建真实执行仍走固定脚本，真实执行前必须由用户明确说“确认执行”。

固定顺序：

```text
create_project（创建项目）
-> bind_material（素材从源素材账户推送到目标账户）
-> lookup_target_material（目标账户素材回查）
-> create_unit（创建单元）
```

执行入口：

```bash
PYTHONPATH=src python3 scripts/run_create_live_execute_once.py \
  --config configs/runtime.create-live.local.json \
  --policy policies/create-live-execute.local.json \
  --create-execute-artifact <create_execute 产物路径>
```

创建时如果平台返回“已创建30个项目”，固定脚本会：

1. 查询该账户关闭状态项目。
2. 删除最多 10 个关闭项目。
3. 重试当前创建项目。
4. 在结果 JSON 的 `project_cap_cleanup（项目上限清理结果）` 中汇报。

## 项目管理脚本

项目更新类动作统一走：

```text
项目控制配置文件 -> preflight（预演前检查） -> 用户确认 -> execute（执行） -> JSON 汇报
```

固定入口：

- `scripts/run_project_status_update.py`：项目开启/关停。
- `scripts/run_project_budget_update.py`：项目预算调整。
- `scripts/run_project_bid_update.py`：项目出价调整。
- `scripts/run_project_roi_coeff_update.py`：7R 项目 ROI 系数调整。
- `scripts/run_project_update_preflight.py`：项目更新预演。
- `scripts/run_project_update_execute.py`：项目更新执行。
- `scripts/run_project_schedule_restore_due.py`：到期时段恢复。

项目时段更新已经是固定脚本能力；当天拉空后，恢复逻辑固定在脚本和定时任务里，不靠 AI 记忆。

## 数据同步和源素材账户

只读同步脚本负责读平台数据、写 SQLite、输出 JSON，不执行业务修改：

- `scripts/run_daily_report_pipeline.py`：每日报表同步。
- `scripts/run_material_history_backfill_overnight.sh`：素材历史数据回补。
- `scripts/run_control_operation_log_history_sync.py`：操作日志同步。
- `scripts/run_source_material_account_auto_push.py`：源素材账户自动补材。

源素材账户自动补材只处理视频素材，不处理文案素材；脚本会输出推送数量、失败样例和外部接口调用数。

## 定时任务

示例配置：

- `configs/scheduler/roibang-v2.jobs.example.json`
- `scheduler/cron/roibang-v2.cron.example`
- `scheduler/launchd/*.plist.example`

定时任务原则：

- 成熟任务 `enabled=true（启用）`。
- 未成熟任务 `enabled=false（停用）`。
- 每个 job（定时任务）必须写固定 `script.command（脚本命令）`。
- 定时日报只读执行结果，不参与业务判断。

常用检查：

```bash
PYTHONPATH=src python3 scripts/validate_scheduler_jobs.py \
  --registry configs/scheduler/roibang-v2.jobs.example.json

PYTHONPATH=src python3 scripts/render_scheduler_templates.py \
  --registry configs/scheduler/roibang-v2.jobs.example.json \
  --output-dir scheduler

PYTHONPATH=src python3 scripts/run_scheduler_status.py \
  --config configs/runtime.example.json \
  --request configs/scheduler-status.example.json
```

## 本地文件边界

不要提交：

- token（令牌）、session（会话）、本地密钥。
- `data/secrets/`。
- 真实账户 CSV。
- SQLite 数据库。
- `data/runs/` 下的运行产物。
- `*.local.json` 本地私有配置。

本地私有创建配置示例路径：

- `configs/create/yzt-wx-mini-game.preview.local.json`
- `configs/runtime.create-live.local.json`
- `policies/create-live-execute.local.json`

不要提交真实账户。

`.gitignore` 已忽略常见本地文件和运行产物。

## 测试

关键创建链路测试：

```bash
PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 python3 -m pytest \
  tests/test_create_mode.py \
  tests/test_create_workflow.py \
  tests/test_create_plan_from_strategy.py \
  tests/test_create_live_execute_once.py \
  tests/test_create_http_transport.py \
  -q
```

项目管理和定时任务测试：

```bash
PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 python3 -m pytest \
  tests/test_project_update_config.py \
  tests/test_project_update_preflight.py \
  tests/test_project_update_execute.py \
  tests/test_project_schedule_restore_due.py \
  tests/test_scheduler_status.py \
  tests/test_scheduler_jobs.py \
  -q
```

全量测试如果失败，先看是否是历史测试还在按旧报表字段断言；不要为了过测试回退业务字段。

## 禁止事项

- 不让 AI 临场执行业务动作。
- 不让 AI 猜账户、模板、预算、ROI、出价、素材数、项目数、单元数。
- 不提交本地密钥、token、真实账户和运行产物。
- 不新增复杂审批包、复核包、执行包作为主路径。
- 不绕过固定脚本和 JSON 配置。
