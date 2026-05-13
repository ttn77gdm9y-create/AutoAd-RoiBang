# 项目时段控制

目标：用固定脚本和 JSON 配置完成项目拉空时段，并在第二天凌晨自动恢复。AI 只负责写配置、跑预演、改脚本，不临场判断真实业务动作。

## 标准说法

你可以这样说：

```text
生成项目时段控制配置文件：这两个项目今天 12:00-13:00 拉空，明天 00:10 恢复，先写配置文件，再预演，预演之后输出结果让我确认。
```

系统只能做：

```text
生成 project_update.json（项目时段控制配置文件）
-> preflight（预演，只检查）
-> 输出结果等你确认
```

不能直接执行真实拉空。

## 固定流程

```text
project_update.json（项目时段控制配置文件）
-> preflight（预演）
-> 用户确认
-> execute（执行拉空）
-> ledger（账本，保存原始投放时段）
-> restore_queue（恢复队列）
-> 第二天 00:10 launchd（macOS 定时任务）自动恢复
```

## 文件职责

- `scripts/run_project_update_config.py`：生成 `project_update.json（项目时段控制配置文件）`。
- `scripts/run_project_update_preflight.py`：预演，只检查账户、项目和恢复动作，不调真实修改接口。
- `scripts/run_project_update_execute.py`：用户确认后执行拉空，并写 `ledger（账本）` 和 `restore_queue（恢复队列）`。
- `scripts/run_project_schedule_restore_due.py`：第二天凌晨读取恢复队列，到期后按账本恢复原始 `schedule_time（投放时段）`。
- `scheduler/launchd/com.roibang.v2.roibang-project-schedule-restore-due.plist.example`：每天 00:10 自动恢复任务示例。

## 关键约束

- 账户必须在 `allowlist（准允许名单）` 中。
- `schedule_time（投放时段）` 是周维度字符串，脚本只能按 `target_date（目标日期）` 算出当天星期几，只改当天对应时段。
- 恢复时不能重新猜时段，必须读取 `ledger（账本）` 里的原始时段。
- 真实执行必须经过用户确认。
- 定时恢复由脚本执行，不需要 AI 参与。
