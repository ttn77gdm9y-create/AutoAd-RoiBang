# Account Import Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 完成产品账户库第二阶段基础能力：CSV/Excel 上传预览与提交、多行粘贴预览与提交、重复账户识别、中文摘要、账户筛选和导出。所有 JSON 必须先显示中文摘要和明细表。

**Architecture:** React 只调用 FastAPI；FastAPI 只写本地 `configs/accounts/product-accounts.local.json`。导入账户归属不触发真实业务动作，不调用平台 API，不进入固定脚本执行链路。

**Tech Stack:** Python 3.11, FastAPI, Pydantic, pytest, React, TypeScript, Ant Design.

---

## Tasks

- [ ] Add backend account store/parser service with fixed fields:
  - `product_key`
  - `product_name`
  - `advertiser_id`
  - `advertiser_name`
  - `channel`
  - `owner`
  - `account_remark`
  - `status`
  - `notes`
- [ ] Add tests for paste preview, paste commit, CSV upload preview, CSV upload commit, filtering, export.
- [ ] Implement backend endpoints:
  - `GET /api/accounts?product_key=&channel=&owner=&status=`
  - `POST /api/accounts/paste/preview`
  - `POST /api/accounts/paste/commit`
  - `POST /api/accounts/import/preview`
  - `POST /api/accounts/import/commit`
  - `GET /api/accounts/export`
- [ ] Update React account page:
  - enable upload and paste input
  - show preview/commit buttons
  - always render Chinese summary first
  - keep raw JSON behind drawer only
- [ ] Verify:
  - `PYTHONPATH=.:src python3 -m pytest backend/tests/test_api_foundation.py backend/tests/test_script_registry.py backend/tests/test_accounts_import.py tests/test_ui_background_tasks.py -q`
  - `cd frontend && npm run lint && npm run build`

## Boundaries

- Do not call OceanEngine or any platform API.
- Do not trigger project creation, deletion, landing page update, account remark update, or token refresh.
- Do not accept arbitrary shell commands.
- Do not show raw JSON as the primary UI.
- Keep Streamlit code in place.
