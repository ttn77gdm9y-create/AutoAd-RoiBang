# 本地开发授权策略

日期：2026-05-27  
目标：让 Codex 能持续开发 FastAPI + React 新系统，同时减少系统级审批弹窗。

## 原因

Codex 对本地进程管理会触发系统级审批，尤其是：
- 查看进程：`ps -ef`
- 停止进程：`kill <pid>`
- 本地 HTTP 冒烟：访问 `127.0.0.1`

这些审批不是业务确认，也不是执行真实广告动作，而是本地开发环境保护。

## 执行策略

1. 后端开发服务默认开启热重载：
   - 固定入口：`python3 scripts/run_fastapi_backend.py`
   - 默认 `ROIBANG_API_RELOAD=1`
   - 修改后端代码后尽量不再重启进程。

2. 前端开发服务使用 Vite 热更新：
   - 固定入口：`bash scripts/run_react_frontend.sh`

3. 新系统联调使用固定入口：
   - `bash scripts/run_new_ui_dev.sh`

4. 不给宽泛命令授权：
   - 不授权裸 `python3`
   - 不授权裸 `bash`
   - 不授权通配 `kill`

5. 如需授权，优先只授权固定脚本前缀：
   - `python3 scripts/run_fastapi_backend.py`
   - `bash scripts/run_react_frontend.sh`
   - `bash scripts/run_new_ui_dev.sh`

## 边界

- 开发服务管理不等于真实业务执行。
- 真实业务动作仍必须走中文摘要、输入 `确认执行`、固定脚本、任务中心。
- React 不直接调用平台 API。
- FastAPI 不接受任意 shell 命令。
