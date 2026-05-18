# RoiBang-v2

RoiBang-v2 是一个“固定脚本 + JSON 配置 + JSON 结果”的广告投放自动化系统。

核心方向：

```text
数据同步 -> 配置/模式生成计划 -> 人工确认 -> execute（执行） -> report（汇报）
```

AI（人工智能）只负责写代码、修脚本、看数据生成配置、复盘结果。真实业务动作只能由固定脚本读取 JSON 配置后执行，不能由 AI 临场猜账户、猜素材、猜预算、猜项目或改参数。

## 当前主线

当前主线已经从“创建链路”推进到“自动化投放控制”的基础能力：

- 创建链路：`create_project（创建项目） -> bind_material（素材推送） -> lookup_target_material（目标账户素材回查） -> create_unit（创建单元）`。
- 创建模式：用固定 `create-modes（创建模式）` 替代每次手写大 JSON。
- 项目管理：项目状态、预算、出价、ROI 系数、投放时段都走固定配置和执行脚本。
- 源素材账户：不再使用“源素材候选池”概念，统一从源素材账户同步和补材。
- 定时任务：`scheduler（定时任务）` 直接写固定 `script.command（脚本命令）`，不依赖 prompt（提示词）解释业务流程。
- 结果契约：脚本输出固定 JSON，包括 `ok`、`workflow（流程名）`、`summary（摘要）`、`blocking_reasons（阻断原因）`、`artifact_path（结果文件路径）`、`external_api_calls（外部接口调用数）`。

## 创建模式

创建时必须明确模板类型，不能省略“通投/男”。放量还要明确“历史/近期”，复测还要明确“低转化/无转化”。例如 `7R 放量` 是歧义说法，脚本会阻断；必须写成 `7R 通投历史放量` 或 `7R 通投近期放量`。7R 模式只保留放量，测新和复测统一使用每付模板。

当前固定模式：

| 中文模式 | mode_key（模式键） | 模板 |
| --- | --- | --- |
| 7R 通投历史放量 | `wx_7r_general_scale` | `wx_7r_general（微小每付 7R 通投）` |
| 7R 通投近期放量 | `wx_7r_general_recent_scale` | `wx_7r_general（微小每付 7R 通投）` |
| 7R 男历史放量 | `wx_7r_male_scale` | `wx_7r_male（微小每付 7R 男）` |
| 7R 男近期放量 | `wx_7r_male_recent_scale` | `wx_7r_male（微小每付 7R 男）` |
| 每付通投历史放量 | `wx_pay_general_scale` | `wx_pay_general（微小每付通投）` |
| 每付通投近期放量 | `wx_pay_general_recent_scale` | `wx_pay_general（微小每付通投）` |
| 每付通投测新 | `wx_pay_general_test_new` | `wx_pay_general（微小每付通投）` |
| 每付通投低转化复测 | `wx_pay_general_retest` | `wx_pay_general（微小每付通投）` |
| 每付通投无转化复测 | `wx_pay_general_no_conversion_retest` | `wx_pay_general（微小每付通投）` |
| 每付男历史放量 | `wx_pay_male_scale` | `wx_pay_male（微小每付男）` |
| 每付男近期放量 | `wx_pay_male_recent_scale` | `wx_pay_male（微小每付男）` |
| 每付男测新 | `wx_pay_male_test_new` | `wx_pay_male（微小每付男）` |
| 每付男低转化复测 | `wx_pay_male_retest` | `wx_pay_male（微小每付男）` |
| 每付男无转化复测 | `wx_pay_male_no_conversion_retest` | `wx_pay_male（微小每付男）` |

放量默认：

- `daily_budget（日预算）`：88888
- `cpa_bid（项目出价）`：103
- `roi_coefficient（ROI 系数）`：7R 模板为 0.419
- 每账户 5 个项目，每项目 1 个单元，每单元 5 个素材
- 历史放量：素材回看 30 天，只选 `stat_cost（素材消耗）` 大于等于 1000 的高消耗素材
- 近期放量：素材回看 7 天，只选 `stat_cost（素材消耗）` 大于等于 200 的高消耗素材
- 禁止旧说法 `7R 通投放量`、`每付男放量` 这类不带历史/近期的放量模式，脚本会阻断

测新默认：

- `daily_budget（日预算）`：10000
- `cpa_bid（项目出价）`：111
- 每付模板不写 `roi_coefficient（ROI 系数）`
- 每账户 5 个项目，每项目 1 个单元，每单元 6 个素材
- 素材回看 7 天，并要求 `effective_create_date（有效创建日期）` 在近 7 天内；按有效创建日期倒序取最近 200 条候选，再稳定随机打乱

低转化复测默认：

- 预算、出价、项目数、单元数、素材数和测新一致
- 素材筛选 30 天内
- 只选择 `convert_cnt（转化数）` 大于等于 1 且小于等于 5 的素材
- 按 `effective_create_date（有效创建日期）` 倒序排序后稳定随机打乱

无转化复测默认：

- 预算、出价、项目数、单元数、素材数和测新一致
- 素材筛选 30 天内
- 只选择 `convert_cnt（转化数）` 等于 0、`stat_cost（素材消耗）` 小于等于 500、且有效创建日期距目标日期至少 7 天的素材
- 按 `effective_create_date（有效创建日期）` 倒序排序后稳定随机打乱

单元层固定规则：

- `title_pool（文案池）`：放量和测新共用模板文案池。
- `CTA（行动按钮）`：每个单元从模板池稳定随机选 2-3 个。
- `product_selling_points（产品卖点）`：每个单元稳定随机选 2-3 个。
- `aweme_ids（抖音号 ID）`：固定两个抖音号，每个单元稳定随机选 1 个。
- `anchor（锚点）`、`landing_url（落地页）`、`fixed_video_cover_id（固定封面）`、`product_image_id（产品图）`：固定来自模板。
- `effective_touch_url（有效触点链接）`：产品级固定字段，生成到项目层 `action_track_url（点击监测链接）`。
- 稳定随机的意思是：同一个 `plan_id（计划 ID）` 和 `unit_key（单元键）` 预演和执行结果一致。

## 素材表现汇总

`product_source_material_metric_rollups（源素材表现汇总表）` 的消耗、转化、ROI（付费回收）口径以 `material_daily_metrics（素材日维度数据）` 为准，按 `material_id（素材 ID）` 汇总全量日维度表现，不再只统计 `product_source_materials（源素材表）` 已覆盖的素材。

- `material_id（素材 ID）` 是素材表现归因主键。
- `video_id / vid（视频 ID）` 只作为素材推送、回查和创建接口字段，不作为历史表现归因主键。
- `product_source_materials（源素材表）`、`account_materials（账户素材表）`、`material_profiles（素材详情表）` 只用于补素材名称、审核状态、创建时间等信息。
- `material_source_mappings（素材源映射表）` 只处理少数目标素材 ID 需要回源的情况，不作为主统计口径。
- `first_seen_metric_date（首次出现数据日期）` 来自 `material_daily_metrics（素材日维度数据）` 中该素材第一次出现的日期。
- `effective_create_date（有效创建日期）` 优先使用 `first_seen_metric_date（首次出现数据日期）`，用于修正源素材账户集中导入导致的创建时间失真。
- 创建选素材仍从源素材账户可用素材出发，避免选到当前源素材账户不可用的历史素材。
- 每天新增数据先跑 `material_kind_reconcile（素材类型校正）`，把文案、非视频、无法确认的视频素材从创建候选里剔除。
- 再跑 `product_source_material_rollup（源素材表现汇总）`，只把有 `video_id（视频 ID）` 的视频素材写入创建选材主表。

素材详情覆盖率检查：

```bash
PYTHONPATH=src python3 scripts/run_material_profile_coverage.py \
  --config configs/runtime.example.json \
  --request configs/material-profile-coverage.example.json
```

素材详情缺口只读回补：

```bash
PYTHONPATH=src python3 scripts/run_material_profile_backfill_batch.py \
  --config configs/runtime.openapi-execute.local.example.json \
  --request configs/material-profile-backfill-batch.disabled.example.json \
  --enable-readonly
```

生成创建计划示例：

```bash
PYTHONPATH=src python3 scripts/run_create_mode.py \
  --config configs/runtime.example.json \
  --request configs/create-mode-requests/wx_7r_general_recent_scale.example.json \
  --policy policies/create-policy.example.json
```

少写 `request（请求配置）` 的创建计划入口：

```bash
PYTHONPATH=src python3 scripts/run_create_mode.py \
  --config configs/runtime.example.json \
  --mode 每付通投近期放量 \
  --account 185xxx \
  --account 185xxx \
  --target-date 2026-05-14 \
  --policy policies/create-policy.example.json
```

这个入口只生成创建计划，不执行真实创建；预算、出价、项目数、单元数、素材数都来自 `configs/create-modes（创建模式配置）`。

素材选择会自动排除 `fixtures（测试样例）` 来源，以及明显无效的 `video_id（视频 ID）`，例如 `v001`。

## AI 创建模板草稿

`AI 创建模板` 和上面的人工固定 `create-modes（创建模式）` 是两套东西，不能混在一起。

固定入口：

```bash
PYTHONPATH=src python3 scripts/run_ai_create_template_drafts.py \
  --config configs/runtime.example.json \
  --request configs/ai-create-template-drafts/example.json
```

这个脚本只做只读分析：

- 读取本地 `product_source_material_metric_rollups（源素材表现汇总表）`。
- 读取现有 `configs/create-modes（人工创建模式目录）` 作为对照。
- 输出 `ai_create_template_drafts（AI 创建模板草稿）` JSON 到 `data/runs/ai_create_template_drafts/`。
- `external_api_calls（外部接口调用数）=0`，不调用平台接口。
- `execution_enabled（执行开关）=false`，不能执行真实创建。
- 不写入 `configs/create-modes（人工创建模式目录）`。
- 不写入 `configs/create-mode-requests（创建请求配置目录）`。
- 不生成 `create_mode（创建计划）` 或 `create_execute（创建执行）` 产物。

草稿 JSON 里每个候选模板都会带：

- `status=draft_only（仅草稿）`
- `human_review_required=true（需要人工确认）`
- `usage_blocking_reasons（使用阻断原因）`
- `evidence（数据证据）`
- `differences_from_manual_template（和人工模板差异）`

后续如果要使用 AI 草稿，必须新增一个单独的 `promote（转正）` 脚本，由人工明确选择某个草稿后，才允许显式转换成新的人工模板；AI 草稿不会自动覆盖现有模板。

## 创建执行

创建真实执行仍走固定脚本，真实执行前必须由用户明确说“确认执行”。

固定顺序：

```text
create_project（创建项目）
-> lookup_target_material（创建前查目标账户素材库）
-> bind_material（仅把目标账户没有的素材从源素材账户推送到目标账户）
-> lookup_target_material（目标账户素材回查）
-> create_unit（创建单元）
```

素材推送规则：

- 创建前先查目标账户素材库。
- 如果目标账户已经有素材，直接记录目标账户 `video_id（视频 ID）` 和 `video_cover_id（封面 ID）`，跳过素材推送。
- 如果目标账户没有素材，才从源素材账户推送。
- 单元创建始终使用目标账户素材 ID 和封面 ID，不使用源素材账户视频 ID。

执行入口：

```bash
PYTHONPATH=src python3 scripts/run_create_live_execute_once.py \
  --config configs/runtime.create-live.local.json \
  --policy policies/create-live-execute.local.json \
  --plan <create_mode 或 create_strategy_plan 计划产物路径>
```

终端执行入口：

```bash
PYTHONPATH=src python3 scripts/run_create_live_execute_terminal.py \
  --config configs/runtime.create-live.local.json \
  --policy policies/create-live-execute.local.json \
  --plan <create_mode 或 create_strategy_plan 计划产物路径> \
  --open-progress-window
```

`--check-config-only` 是轻量检查，只确认本地真实执行配置、token（令牌）指针、接口地址和计划基础字段，不生成预演产物，也不调用外部接口。`--create-execute-artifact` 仍兼容旧产物，但不再是主路径必填项。

`--open-progress-window` 会打开 Terminal.app（macOS 终端）显示本次执行进度，只读本地 `progress（进度）` 文件。

这个入口会拉起固定执行脚本，同时在当前终端显示：

- `operation（操作）`
- `status（状态）`
- `progress（进度）`
- `external_api_calls（外部接口调用数）`
- `account（账户）`
- `stdout_log（标准输出日志）`
- `stderr_log（标准错误日志）`

只观察进度：

```bash
PYTHONPATH=src python3 scripts/watch_create_live_progress.py
```

需要刷新式界面时：

```bash
PYTHONPATH=src python3 scripts/watch_create_live_progress.py --clear --recent-events 5
```

`policies/create-live-execute.local.example.json` 里已经默认打开 `progress（进度输出）`，真实创建时会写：

- `current.json（当前进度）`
- `events.jsonl（逐行进度日志）`
- `stderr（终端错误流/实时输出）`

创建效率参数：

- `retry_sleep_seconds_by_operation（按操作重试等待秒数）`：素材推送和素材回查可以分别配置 40100（请求频率超限）后的等待时间。
- `min_interval_seconds_by_operation（按操作最小调用间隔）`：项目创建、素材推送、素材回查、单元创建可以分别配置调用间隔。
- 当前 example（示例配置）已把素材推送和素材回查间隔压到 0.5 秒，单元创建间隔从 20 秒降到 8 秒；如果生产环境再出现 40100，可以只调这些 JSON 参数，不改脚本。
- `post_run_retry（跑完后补跑）`：只对临时失败的 `create_unit（创建单元）` 做补跑，默认包含 50000（服务内部错误）、网络超时、连接断开等临时错误；素材无权限、参数错误、项目不存在这类确定失败不会自动补跑。

创建执行结果 JSON 会输出 `efficiency_report（执行效率报告）`：

- `api_calls（接口调用）`：总调用数、各步骤调用数、真实 `bind_material（素材推送）` 次数、创建前目标素材库回查次数。
- `material_push（素材推送）`：实际推送、已推过跳过、目标账户已有素材跳过。
- `lookup（目标素材回查）`：目标素材 ID/封面 ID 落账数量、素材延迟可见等待重试次数。
- `failure_recovery（失败恢复）`：跳过账户数、跑完后补跑尝试数、恢复数、仍失败数。
- `timing（耗时）`：整体耗时和每个固定步骤耗时。

`create_live_execute_report（创建执行报告）` 会只读执行产物，输出 `next_steps（后续处理建议）`，比如是否需要补跑失败单元、排查素材权限、继续提高预推送覆盖率。

创建时如果平台返回“已创建30个项目”，固定脚本会：

1. 查询该账户关闭状态项目。
2. 删除最多 10 个关闭项目。
3. 重试当前创建项目。
4. 在结果 JSON 的 `project_cap_cleanup（项目上限清理结果）` 中汇报。

## 项目管理脚本

项目更新类动作统一走：

```text
项目控制配置文件 -> 用户确认 -> execute（执行） -> JSON 汇报
```

固定入口：

- `scripts/run_project_status_update.py`：项目开启/关停。
- `scripts/run_project_budget_update.py`：项目预算调整。
- `scripts/run_project_bid_update.py`：项目出价调整。
- `scripts/run_project_roi_coeff_update.py`：7R 项目 ROI 系数调整。
- `scripts/run_project_delete.py`：项目删除。
- `scripts/run_project_management_update_config.py`：按账户和项目名称查询后生成项目管理配置。
- `scripts/run_project_realtime_filter_config.py`：按平台实时数据筛选项目后生成项目管理配置。
- `scripts/run_project_update_execute.py`：项目更新执行。
- `scripts/run_project_schedule_restore_due.py`：到期时段恢复。

调试入口：

- `scripts/run_project_update_preflight.py`：项目更新本地检查，不在主流程里使用；真实接口问题以执行结果为准。

按名称生成配置的固定入口：

- `scripts/run_project_status_update_config.py`：按名称生成开启/关停配置。
- `scripts/run_project_budget_update_config.py`：按名称生成预算调整配置。
- `scripts/run_project_bid_update_config.py`：按名称生成出价调整配置。
- `scripts/run_project_roi_coeff_update_config.py`：按名称生成 ROI 系数调整配置。
- `scripts/run_project_delete_config.py`：按名称生成删除项目配置，默认不额外限定项目状态。

按实时数据筛选项目的固定入口：

```bash
PYTHONPATH=src python3 scripts/run_project_realtime_filter_config.py \
  --config configs/runtime.openapi-execute.local.example.json \
  --project-update-id delete-0515-today-low-cost \
  --advertiser-id 185xxxxxxxxxxxxx \
  --action-type delete_project \
  --name-contains 0515 \
  --spend-window today \
  --metric-filter "stat_cost:lt:100" \
  --output configs/project-updates/delete-0515-today-low-cost.local.json
```

第一版只支持 3 个实时窗口：

- `today（今天）`
- `yesterday（昨天）`
- `last_3_days（近 3 天，包含今天、昨天、前天）`

支持的指标筛选字段：

- `stat_cost（消耗）`
- `active_register（注册数）`
- `register_cost（注册成本）`
- `billing_convert_cnt（转化数：计费时间）`
- `billing_conversion_cost（转化成本：计费时间）`
- `billing_1day_pay_roi（计费当日付费 ROI）`

`--metric-filter` 格式：

```text
字段:比较符:数值
```

比较符支持：

```text
lt（小于）
lte（小于等于）
gt（大于）
gte（大于等于）
eq（等于）
```

示例：

```bash
--metric-filter "billing_convert_cnt:eq:0"
--metric-filter "stat_cost:lt:200"
--metric-filter "register_cost:gte:100"
```

生成配置后，真实执行仍走固定执行脚本，并且必须人工确认：

```bash
PYTHONPATH=src python3 scripts/run_project_update_execute.py \
  --config configs/project-update-execute.local.json \
  --project-update configs/project-updates/delete-0515-today-low-cost.local.json \
  --execute \
  --yes
```

项目时段更新已经是固定脚本能力；当天拉空后，恢复逻辑固定在脚本和定时任务里，不靠 AI 记忆。

## 数据同步和源素材账户

只读同步脚本负责读平台数据、写 SQLite、输出 JSON，不执行业务修改：

- `scripts/run_daily_report_pipeline.py`：每日报表同步。
- `scripts/run_material_history_backfill_overnight.sh`：素材历史数据回补。
- `scripts/run_control_operation_log_history_sync.py`：操作日志同步。
- `scripts/run_source_material_account_auto_push.py`：源素材账户自动补材。
- `scripts/run_source_material_preload_to_accounts.py`：把源素材账户里的视频素材预推送到目标账户，减少创建时等待素材推送的时间。

源素材账户自动补材只处理视频素材，不处理文案素材；脚本会输出推送数量、失败样例和外部接口调用数。

源素材预推送分两种固定用法：

- 每日定时：源素材账户自动补材完成后，把新增源素材推送到昨天有消耗的 `account_remark（账户备注）=勇者突进-微小-郭靖` 账户。脚本会先查本地 `source_material_preload_ledger（源素材预推送账本）`、`account_materials（账户素材表）` 和 `material_bindings（素材绑定表）`，已经存在的素材不会重复推送。
- 新增账户手动：新增目标账户后，把源素材账户全部视频素材推送到指定新增账户。

新增账户手动预推送命令：

```bash
PYTHONPATH=src python3 scripts/run_source_material_preload_to_accounts.py \
  --config configs/runtime.openapi-execute.local.example.json \
  --request configs/source-material-preload-to-accounts.daily-guojing-yesterday-spent.example.json \
  --accounts "185xxxxxxxxxxxxx,185yyyyyyyyyyyyy" \
  --target-date today \
  --full-source \
  --execute \
  --yes
```

参数说明：

- `--accounts`：新增目标账户 ID，多个账户用英文逗号分隔。
- `--full-source`：使用源素材账户全部视频素材；已推送过的素材会被账本跳过。
- `--execute --yes`：真实执行素材推送；不加这两个参数时只生成本地 JSON 结果，不调用外部接口。

## 投放账户巡检

投放账户巡检是只读模块，用于查看今天和昨天的账户、项目、单元状态，不执行暂停、删除、调预算、调出价。

- `scripts/run_delivery_patrol.py`：读取账户、项目、单元实时数据，输出 `delivery_patrol（投放巡检结果）`。
- `configs/delivery-patrol.daily-readonly.example.json`：真实只读配置，按 `account_remark（账户备注）= 勇者突进-微小-郭靖` 发现今天有消耗账户。
- 输出字段包含 `accounts（账户）`、`projects（项目）`、`promotions（单元）`、`attention_items（重点关注项）`、`message（可读报告）`、`delivery（推送结果）`。
- 每个账户、项目、单元都会输出 `business_status（业务状态）`、`severity（严重程度）`、`status_reasons（状态原因）`。
- `scripts/run_delivery_patrol_suggestions.py`：读取巡检结果生成 `delivery_patrol_suggestions（投放巡检建议）`，只输出建议 JSON，不生成执行动作。
- `configs/delivery-patrol-suggestions.example.json`：建议规则配置，用于生成 `continue_running（继续跑）`、`watch（观察）`、`suggest_close_project（建议关闭项目）`、`suggest_delete_project（建议删除项目）`、`suggest_lower_budget（建议下调预算）`、`suggest_lower_bid（建议下调出价）`、`unit_good_signal（单元好信号）`、`unit_bad_signal（单元差信号）`。
- 建议脚本会读取本地 `operation_logs（操作日志）` 和 `material_daily_metrics（素材/项目/单元日维度数据）` 作为证据，但 `external_api_calls（外部接口调用数）` 必须为 `0`。
- 建议结果只供人工确认和后续回测，不直接转成真实修改。

业务巡检状态只做归类，不做真实操作。常见状态：

- `normal（正常）`
- `zero_billing_convert（有消耗无计费时间转化）`
- `high_cost_low_return（高消耗低回收）`
- `drop_from_yesterday（较昨日明显下滑）`
- `high_cost_zero_convert（项目高消耗无计费时间转化）`
- `low_roi（低 ROI）`
- `running_good（跑量有效）`
- `inactive_enabled（启用但无消耗）`
- `unit_high_cost_zero_convert（单元高消耗无计费时间转化）`

飞书只推业务摘要，包括整体表现、状态分布、重点账户、重点项目、重点单元和完整 JSON 路径；完整明细保存在 `data/runs/delivery_patrol/latest.json`。
正式巡检配置已开启同频建议生成：每次 `scripts/run_delivery_patrol.py（投放账户巡检脚本）` 跑完后，会本地生成 `delivery_patrol_suggestions（投放巡检建议）`，并把“今日建议”摘要合并到同一条飞书消息里，不单独推第二条。

只生成巡检计划：

```bash
PYTHONPATH=src python3 scripts/run_delivery_patrol.py \
  --config configs/runtime.example.json \
  --request configs/delivery-patrol.example.json
```

真实只读巡检：

```bash
PYTHONPATH=src python3 scripts/run_delivery_patrol.py \
  --config configs/runtime.openapi-execute.local.example.json \
  --request configs/delivery-patrol.daily-readonly.example.json \
  --enable-readonly
```

基于巡检结果生成建议：

```bash
PYTHONPATH=src python3 scripts/run_delivery_patrol_suggestions.py \
  --patrol-artifact data/runs/delivery_patrol/latest.json \
  --request configs/delivery-patrol-suggestions.example.json \
  --db data/roibang_v2.sqlite3
```

建议 JSON 会写入 `data/runs/delivery_patrol_suggestions/`，其中每条建议都带：

- `suggested_action（建议动作）`
- `confidence（置信度）`
- `reason（原因）`
- `metrics（指标证据）`
- `evidence.operation_history（操作日志证据）`
- `evidence.lifecycle（生命周期证据）`
- `execution.enabled=false（不允许执行）`

正式每小时巡检无需单独运行建议脚本；`configs/delivery-patrol.daily-readonly.example.json` 已通过 `suggestions（建议配置）` 指向 `configs/delivery-patrol-suggestions.example.json`，并使用本地 `data/roibang_v2.sqlite3` 补充操作日志和生命周期证据。

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

当前启用链路：

- `00:10` 项目时段到期恢复。
- `02:00` 昨日有消耗账户素材明细与计费当日 ROI（付费回收）同步。
- `02:30` 昨日有消耗账户操作日志同步。
- `04:00` 每日报表同步。
- `04:30` 素材类型校正。
- `05:00` 源素材账户自动补材。
- `05:20` 新增源素材预推送到昨天有消耗的郭靖账户。
- `05:30` 源素材表现汇总重建。
- `06:00` 定时任务日报。
- `08:30-23:30` 每小时投放账户巡检并推送飞书。

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
