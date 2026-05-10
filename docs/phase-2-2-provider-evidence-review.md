# 第二阶段.2 平台字段证据复核

日期：2026-05-10

本文档说明 第二阶段.2 的安全切片：平台字段证据复核。

`provider evidence review` 的意思是“平台字段证据复核”。在未来生成真实平台请求体之前，每个字段都必须有可复核的来源证据。

## 目标

新增一个只读复核闸门，用来检查 OceanEngine 创建链路字段证据。

这个闸门读取：

- 平台字段映射 JSON。
- 平台证据目录 JSON。
- 当前运行安全配置。

它只写运行产物，不访问外网，不调用接口，不创建项目。

## 工作流

工作流名称：

```text
create_provider_evidence_review
```

字段解释：

- `provider`：广告平台，目前是 `oceanengine`。
- `evidence`：字段依据，例如官方文档或已捕获请求证据。
- `catalog`：证据目录，也就是列出证据引用的 JSON 文件。
- `reviewed`：已复核，表示人工已经检查过该证据。

## 输出内容

工作流会报告：

- 哪些字段缺平台字段名。
- 哪些字段缺证据引用。
- 哪些证据引用在证据目录里不存在。
- 哪些证据存在但还没有人工复核。
- 哪些本地字段还需要确认不进入平台请求体。

同时输出：

- `evidence_status_counts`：证据状态计数。
- `operator_guide`：操作员指南。
- `evidence_worksheet`：证据填写清单，每个字段一行。
- `provider_field_gap_report`：缺平台字段报告，只列出 `provider_field` 为空的字段。
- `provider_field_gap_resolution_plan`：缺平台字段处理计划，只说明每个缺口该如何人工复核。
- `project_type_local_usage_review`：`project_type` 本地用途复核清单。

## 状态解释

- `needs_provider_field`：缺平台字段名。
- `needs_evidence_ref`：缺证据引用。
- `needs_evidence_review`：有证据引用，但还没有人工复核。
- `local_only_needs_confirmation`：本地字段需要确认不会进入平台请求体。
- `local_only_confirmed`：本地字段已确认不进入平台请求体。
- `verified`：字段映射和证据都已确认。

## 安全契约

工作流必须始终返回：

```json
{
  "execution_enabled": false,
  "external_api_calls": 0,
  "actions": []
}
```

同时必须保持：

- `live_payload_generation_enabled=false`：不生成可发送的真实请求体。
- `create_execute_hard_block_required=true`：创建执行继续硬阻断。
- `mapping_verified_must_remain_false=true`：当前阶段不能把整体映射标记为已验证。

这意味着证据复核只能提高字段可信度，不能打开真实创建。

## 当前状态

当前示例证据目录已经完成项目、单元、素材推送三类字段的本地 API 文档复核：

```text
configs/provider-evidence/oceanengine.create.phase2-review.example.json
```

当前预期结果：

- 检查 22 个映射字段。
- 载入 3 条证据目录项。
- 已复核证据数为 3。
- 未解决字段数为 0。
- `operator_guide.status=needs_review`。
- `evidence_worksheet.summary.row_count=22`。
- `evidence_worksheet.summary.ready_row_count=22`。
- `provider_field_gap_report.summary.gap_count=0`。
- `provider_field_gap_resolution_plan.summary.gap_count=0`。
- 真实请求体开发仍未就绪。
- 真实执行仍未就绪。

## 证据填写清单

`evidence_worksheet` 是人工填写清单。它把每个字段整理成一行，并告诉操作员该行还需要补什么。

重要字段：

- `fill_required`：需要补的内容，例如 `source_url` 或复核人信息。
- `do_not_change`：禁止改动的安全字段，例如 `execution_enabled`。
- `ready_row_count`：已就绪字段行数。
- `local_only_confirmed`：本地字段确认开关。只有人工确认该字段只用于查表、幂等或链路追踪，并且绝不会发送到平台请求体后，才能改成 `true`。

这个填写清单不是批准产物，不能开启真实执行。

## 缺平台字段报告

`provider_field_gap_report` 会单独列出 `provider_field` 仍为空的字段。它比完整填写清单更窄，只用于聚焦缺字段问题。

当前 6 个 `field_defaults` 字段已经完成平台字段复核：

- `create_project.field_defaults.landing_type`
- `create_project.field_defaults.pricing`
- `create_project.field_defaults.inventory_type`
- `create_unit.field_defaults.landing_type`
- `create_unit.field_defaults.pricing`
- `create_unit.field_defaults.inventory_type`

这些字段现在已经有本地官方 API 文档证据。`verified` 的意思是“已核验”，表示字段名已经按文档确认。

`create_project.project_type` 已改为 `local_only` 字段。`local_only` 的意思是“只在本地流程使用，不进入平台请求体”。

`bind_material` 已纠正为“源素材账户推送到目标账户”。字段含义如下：

- `source_advertiser_id`：源素材账户 ID，会映射成平台请求体里的 `advertiser_id`。
- `target_advertiser_ids`：目标投放账户 ID 列表，会进入平台请求体。
- `source_video_ids`：源素材账户的视频 ID 列表，会映射成平台请求体里的 `video_ids`。
- `material_id`：本地素材全局身份，只用于追溯和后续回查目标账户素材，不进入素材推送请求体。
- `source_video_id`：本地单条源视频追溯字段，不直接进入平台请求体；请求体使用列表字段 `source_video_ids`。

素材推送 API 已按本地文档核对为 `/open_api/2/file/material/bind/`。它不需要 `project_id` 和 `promotion_id`，所以素材推送不再依赖项目/单元创建后的 ID 台账。

## 缺平台字段处理计划

`provider_field_gap_resolution_plan` 是人工复核计划，不是批准产物。它会为每个缺口生成：

- `recommended_action`：建议动作，会按字段类型给出不同复核方向。
- `review_questions`：人工复核时要回答的问题。
- `blocked_until`：解除阻塞前必须完成的条件。
- `do_not_do`：禁止事项，例如不要猜字段、不要打开 `create_execute`。

这个计划的目标是让剩余缺口逐个可复核，而不是让脚本替人判断平台字段。

当前缺平台字段名已经归零，所以这个计划不再输出单项缺口。真实请求体开发仍未就绪，因为 `create_execute` 仍必须硬阻断，并且真实创建链路还没有进入批准阶段。

## project_type 本地用途复核

`project_type_local_usage_review` 会把 `project_type` 的本地用途列出来，帮助判断它未来能不能改成 `local_only`。

当前能看到的本地用途包括：

- 模板选择：从模板名推导 `WX_PAY` 或 `WX_PAY_7R`。
- 请求校验：作为创建请求的必填输入。
- 项目命名：作为项目名模板变量。
- 批次码来源：参与批次码生成，保持批次可追踪。
- 命名预检查：用于生成样例项目名。
- dry-run 追踪：保留在本地计划里方便复盘。

当前已经处理掉两个阻塞点：

- 禁用版 payload schema 不再把它列在 `create_project.required_fields`。
- dry-run 草稿不再把它放在 `disabled_schema_only` 请求体里。

所以这个清单现在显示 `ready_to_mark_local_only=true`。但它仍然不做自动确认，下一步必须由人工确认字段映射里的 `mapping_kind` 和 `local_only_confirmed`。

## 字段缺口收敛计划

`field_gap_convergence_plan` 是 第二阶段.3 的收敛计划。它把剩余问题压缩成 3 类：

- `project_type`：已准备好进入人工本地字段确认，但不会自动确认。
- `field_defaults`：项目和单元各 3 个字段已经完成证据复核。
- `source_video_id`：已从平台字段缺口里移出，作为本地素材来源追溯字段；素材推送请求体使用 `source_video_ids -> video_ids`。

当前状态：

- `remaining_provider_field_gap_count=0`。
- `field_defaults_split_item_count=0`。
- `source_video_id_review_required=false`。
- `ready_for_live_payload_development=false`。

这个计划仍然只读、只复核，不会打开真实请求体开发，也不会打开 `create_execute`。

## 下一步人工复核

下一步不再是补字段证据，而是继续把真实创建前的边界做牢：

1. 继续保持 `create_execute` 硬阻断。
2. 完善 dry-run 请求体草稿，让项目、素材推送、目标账户素材回查、单元创建都能被人工复核。
3. 增加 approve 产物里的字段复核摘要。
4. 之后再进入 execute 边界设计，但仍不执行真实业务动作。

`approve` 的意思是“批准记录”，只表示人工看过并记录同意进入下一道检查；它不是执行真实创建的开关。

## approve 复核边界增强

`create_approval` 现在会输出 `payload_review` 人工复核视图。

`payload_review.drafts_by_operation` 按四类操作展示 payload 草稿：

- `create_project`：项目创建请求体草稿。
- `bind_material`：素材推送请求体草稿。
- `lookup_target_material`：目标账户素材回查草稿，用于拿到目标账户视频 ID 和封面 ID。
- `create_unit`：单元创建请求体草稿。

`payload_review.manual_review_summary` 会汇总：

- 每类 payload 数量。
- 所有 payload 是否仍为 `executable=false`。
- `live_payload_count` 是否仍为 0。
- 是否还有 candidate 草稿或 candidate 字段。
- 是否还有 `<lookup:...>` 占位符。
- `create_execute` 是否仍需 hard-block。
- `external_api_calls` 是否仍为 0。

这份摘要只服务人工复核，不是执行开关。即使 approve 记录为 `would_approve`，真实创建也仍必须继续停在 `create_execute` 的硬阻断边界。

## execute 与链路总报告边界增强

`create_execute` 现在会输出两个最终复核字段：

- `execute_review_pack`：按 `create_project`（创建项目）、`bind_material`（素材推送）、`lookup_target_material`（目标账户素材回查）、`create_unit`（创建单元）展示 resolved payload 草稿。`resolved` 的意思是“已经用本地 provider ID ledger（平台 ID 台账）尝试替换 `<lookup:...>` 占位符”。
- `chain_boundary_contract`：汇总 approve 是否仍是 record-only、execute 是否仍 hard-block、是否没有 live payload、是否没有可执行 payload、是否 `external_api_calls=0`、是否 `actions=[]`。

`create_chain_final_report` 现在会读取最新 `create_execute` 产物，并输出 `creation_boundary_summary`：

- 如果还有 `<lookup:...>` 占位符，`next_focus=provider_id_ledger`。
- 如果占位符已解析，`next_focus=manual_payload_review`。

## 真实执行包与目标素材回查

`create_live_execution_pack` 是“真实执行包”生成器。它不调用平台接口，只把已经通过前置检查的草稿整理成固定执行顺序。

当前真实创建顺序已经固定为：

```text
create_project -> bind_material -> lookup_target_material -> create_unit
```

中文含义：

- `create_project`：创建项目。
- `bind_material`：素材推送，从源素材账户推送到目标投放账户。
- `lookup_target_material`：目标账户素材回查，素材推送后在目标账户查询可用于单元创建的视频 ID 和封面 ID。
- `create_unit`：创建单元。

`lookup_target_material` 当前对应平台接口：

```text
/open_api/2/file/video/get/
```

HTTP transport（HTTP 请求发送模块）现在会把它作为 GET 请求发送。GET 的意思是“读取查询请求”，参数放在 URL 查询串里，不放在 POST 请求体里。

回查请求会从本地草稿转换成平台查询参数：

- `target_advertiser_id` -> `advertiser_id`：目标账户 ID。
- `material_id` -> `filtering.material_ids`：优先用本地追溯素材 ID 查。
- `source_video_id` -> `filtering.video_ids`：没有 `material_id` 时用源视频 ID 查。
- `page` / `page_size`：分页参数，默认 1 页、10 条。

真实执行器会从回查响应里提取：

- `target_video_id`：目标账户视频 ID。
- `target_video_cover_id`：目标账户视频封面 ID。

如果回查结果拿不到目标账户视频或封面 ID，流程应停在单元创建之前。这里不继续猜字段，因为单元创建必须使用目标账户自己的素材 ID。

固定脚本 `scripts/run_create_live_execute_once.py` 也已经调整：如果找不到上游 `create_live_execution_pack` 产物，会输出 blocked JSON（阻断状态 JSON），而不是直接抛 traceback（程序异常堆栈）。这能让后续自动化任务稳定复盘失败原因。
- 两种情况都继续保持 `create_execute` 硬阻断，不执行真实创建。

这一步把 `dry-run -> approve -> execute -> final_report` 串成了一个完整的本地复核边界包。后续如果要推进真实创建开发，必须另起明确批准阶段，不能从这些复核字段直接推导出可执行权限。

## mock execute 与首单 runbook

`create_mock_execute` 用本地 mock provider ID 打通真实创建顺序：

```text
create_project -> bind_material -> lookup_target_material -> create_unit
```

它会模拟平台返回的 `project_id`（平台项目 ID）、目标账户 `video_id`（目标账户视频 ID）、`video_cover_id`（目标账户视频封面 ID）和 `promotion_id`（平台单元 ID），写入 `create_provider_id_ledger`（平台 ID 台账），再回跑 `create_execute` 的 resolved payload 复核。这个流程只写本地 SQLite 和 run artifact，不调用真实接口，`external_api_calls` 必须继续为 0。

`create_live_payload_adapter_scaffold` 现在输出 `live_adapter_gate`，把正式执行所需闸门集中展示：

- runtime 是否允许执行。
- runtime 是否允许外部接口。
- policy 是否启用 live API。
- policy 是否允许生成 live payload。
- phase gate 是否允许 live execute。
- approval 是否允许 execute。

默认所有真实执行闸门都是关闭的。

`create_first_live_runbook` 会生成首单受控创建评审包。当前示例 scope 固定为 1 个项目、2 个单元、4 个素材；它只说明首单需要哪些人工批准、运行步骤和失败停止策略，不会打开真实执行。

`create_live_execute_runner` 是下一层真实执行器边界，但当前只开放 blocked review mode（阻断复核模式）和 injected test transport（测试注入发送层）：

- 默认固定脚本入口不注入 transport（请求发送层），所以只会生成 blocked artifact（阻断产物）。
- `approve` 仍只是 approval record（批准记录），不是 execute switch（执行开关）。
- 只有 runtime、policy、phase gate、runbook、人工批准记录和测试 transport 全部满足时，单元测试才会进入 `test_transport_completed`。
- 单元测试里的 transport 是假的本地函数，不是 HTTP 请求；因此 `external_api_calls` 仍必须是 0。
- 执行顺序固定为 `create_project -> bind_material -> lookup_target_material -> create_unit`。也就是先创建项目，再把源素材账户的视频推送到目标账户，然后回查目标账户素材 ID，最后用目标账户素材创建单元。
- 任一步失败立即停止，`auto_retry_enabled=false`，不自动重试。

当前 runner 的固定脚本入口用途：

```bash
PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 python3 scripts/run_create_live_execute_runner.py --config configs/runtime.example.json --policy policies/strategy.example.json
```

它会读取最新的 `create_execute`、`create_first_live_runbook` 和 `create_live_payload_adapter_scaffold` artifacts（运行产物），输出一个默认 blocked 的复核 artifact；不会调用真实创建接口。

## create HTTP transport 边界

`create_http_transport` 是真实创建接口的 HTTP transport（HTTP 请求发送层），目前只作为受控模块存在，不接入普通固定脚本：

- 默认 `enabled=false`，无法构造。
- 必须显式设置 `allow_mutation=true`，mutation 是变更操作，表示可能创建或修改线上对象。
- 必须有 `approval_id`，也就是人工批准编号。
- 只允许四个 endpoint（接口地址）：
  - `create_project`: `/open_api/2/project/create/`
  - `create_unit`: `/open_api/2/promotion/create/`
  - `lookup_target_material`: `/open_api/2/file/video/get/`
  - `bind_material`: `/open_api/2/file/material/bind/`
- `bind_material` 仍是素材推送绑定，不接收 `project_id` 或 `promotion_id`。
- 变更型请求不做 retry（重试），避免重复创建。
- audit（审计日志）会记录请求和响应，但 `Access-Token` 会脱敏为 `<redacted>`。

`create_live_execute_runner` 现在会输出 `transport_contract`：

- `injected_test_transport` 表示测试注入发送层，不计入 `external_api_calls`。
- `create_http` 表示真实创建 HTTP 发送层，除非 policy 中 `allow_create_http_transport=true`，否则 runner 会 blocked 且不会调用 transport。
- 当前示例策略中 `allow_create_http_transport=false`，所以真实 HTTP 创建仍然关闭。

## first live approval 文件

`create_live_approval` 是首单真实创建前的人工批准记录校验。它不是执行开关，只会生成本地 approval artifact（批准产物），继续保持：

- `execution_enabled=false`
- `external_api_calls=0`
- `actions=[]`

批准文件必须包含：

- `approval_id`：批准编号，用来追溯这一次人工批准。
- `approved_by`：批准人。
- `approved_at`：批准时间。
- `expires_at`：过期时间，过期后自动 blocked（阻断）。
- `target_workflow=create_live_execute_runner`：批准对象必须是 live runner（真实执行器）。
- `allow_create_http_transport`：是否允许真实 HTTP transport（HTTP 请求发送层）。
- `scope`：必须和 `create_first_live_runbook.scope` 完全一致。
- `approved_artifacts`：必须绑定当前三个 artifact 的 sha256 digest（摘要指纹）：
  - `create_execute`
  - `create_first_live_runbook`
  - `create_live_payload_adapter_scaffold`

生成命令：

```bash
PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 python3 scripts/run_create_live_approval.py --config configs/runtime.example.json --approval-file /path/to/approval.json
```

`create_live_execute_runner` 现在必须看到 `create_live_approval` artifact 才会认为 `human_approval_record_present=true`。只在 policy（策略配置）里写 `human_approval.approved=true` 不再能开闸。

## first live execution pack

`create_live_execution_pack` 是首单真实创建前的 execution pack（执行包）和 final preflight（最终执行前检查）。它仍是本地复核产物，不是执行开关：

- `execution_enabled=false`
- `live_execute_enabled=false`
- `external_api_calls=0`
- `actions=[]`

它会把以下信息集中到一个 artifact（运行产物）：

- `final_preflight`：最终执行前检查，列出 runtime（运行时配置）、policy（策略配置）、phase gate（阶段闸门）、runbook（首单手册）、approval artifact（批准产物）、payload（请求体）安全边界。
- `execution_pack`：执行包，按 `create_project`（创建项目）、`bind_material`（素材推送）、`lookup_target_material`（目标账户素材回查）、`create_unit`（创建单元）展示 payload drafts（请求体草稿）、endpoint（接口地址）、scope（首单范围）和 approval（批准记录）。
- `ready_for_live_enablement`：表示本地安全边界已通过，只差真实启用项。
- `ready_for_live_execute`：表示真实启用项也全部显式打开，但这个 artifact 本身仍不执行。

固定脚本入口：

```bash
PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 python3 scripts/run_create_live_execution_pack.py --config configs/runtime.example.json --policy policies/strategy.example.json
```

当前示例 runtime（运行时配置）和 policy（策略配置）默认关闭真实执行，所以固定脚本会输出 blocked（阻断）状态；这符合预期。`create_live_execution_pack` 现在只是辅助复核包，不是主执行路径的必需输入。

## one-shot first live execute

`create_live_execute_once` 是首单一次性真实执行边界。主路径只读取 `create_execute`（创建执行复核产物）、runtime（运行时配置）、policy（策略配置）和 SQLite 本地台账。`create_live_execution_pack`（执行包）、`create_first_live_runbook`（首单手册）和 `create_live_approval`（批准产物）只在命令行显式传入时作为兼容复核输入，不会被默认自动捡取。

默认情况下它仍然 blocked（阻断），不会构造 `create_http_transport`（真实 HTTP 请求发送层），因此也不会读取 token（访问令牌）或调用真实创建接口。只有同时满足以下条件时，固定脚本才会构造真实发送层：

- `runtime.execution_enabled=true`：运行时执行开关显式打开。
- `runtime.external_api_enabled=true`：运行时外部接口开关显式打开。
- `policy.create_execute.live_api.enabled=true`：策略允许真实创建接口。
- `policy.create_execute.payload_schema.live_payload_generation_enabled=true`：策略允许生成真实 payload（请求体）。
- `policy.create_live_execute_runner.allow_create_http_transport=true`：策略允许 HTTP transport（HTTP 请求发送层）。
- `policy.create_live_execute_runner.create_http_transport.enabled=true` 且 `allow_mutation=true`：真实发送层显式打开。

固定脚本入口：

```bash
PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 python3 scripts/run_create_live_execute_once.py \
  --config configs/runtime.create-live.local.json \
  --policy policies/create-live-execute.local.json \
  --create-execute-artifact data/runs/create_execute/<artifact>.json
```

在真实执行尝试发生后，artifact（运行产物）会如实记录：

- `execution_enabled=true`：本次确实进入执行尝试。
- `live_execute_enabled=true`：本次确实进入真实执行路径。
- `external_api_calls`：真实发送层调用次数。
- `provider_id_records`：平台返回的 `project_id`（平台项目 ID）、目标账户 `video_id`（目标账户视频 ID）、`video_cover_id`（目标账户视频封面 ID）和 `promotion_id`（平台单元 ID）写入本地台账的记录。
- `material_bind_records`：`bind_material`（素材推送）成功后的结果台账记录。

失败策略按新业务顺序执行：创建项目失败就不做素材推送；素材推送失败就不做目标账户素材回查；目标账户素材回查失败就不创建单元；创建单元失败则停止并保留已创建的 ID 供人工复核。变更请求不自动 retry（重试），避免重复创建。

## idempotency and resume

`create_live_execute_once` 现在带 idempotency（幂等，避免重复创建）和 resume（断点续跑）边界：

- 执行前先查 SQLite（本地数据库）里的 `create_provider_id_ledger`（平台 ID 台账）。
- 如果某个 `create_project`（创建项目）已有 active（有效）`project_id`（平台项目 ID），就跳过这个项目创建，不再调用真实接口。
- 如果某个 `create_unit`（创建单元）已有 active（有效）`promotion_id`（平台单元 ID），就跳过这个单元创建，不再调用真实接口。
- 项目和单元跳过记录会写入 `idempotency.skipped_provider_id_records`，便于人工复核。
- 素材推送成功后会写入 `create_material_bind_ledger`（素材推送台账）。
- 如果某次 `bind_material`（素材推送）已有 active（有效）台账记录，就跳过这次素材推送，不再调用真实接口。
- 素材推送跳过记录会写入 `idempotency.skipped_material_bind_records`。
- `lookup_target_material`（目标账户素材回查）成功后会把目标账户 `video_id` 和 `video_cover_id` 写入 `create_provider_id_ledger`，供后续 `create_unit` 的 `promotion_materials`（单元素材组合）使用。
- 后续 payload（请求体）里的 lookup placeholder（本地占位符）会继续从 SQLite 台账解析成真实平台 ID。

这意味着首单执行如果中途失败，下一次运行可以从已写入台账的位置继续，不会重复创建已经成功的平台项目、单元，也不会重复推送已经记录成功的同一组素材。

## first live prepare pack

`create_first_live_prepare_pack` 是真实首单创建前的本地交接包。它不是小批量执行包，也不是 execute switch（执行开关）；它只读取 `create_live_execution_pack`（执行包），把是否可以进入人工最终核对说清楚。主执行路径不依赖这个产物。

固定脚本入口：

```bash
PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 python3 scripts/run_create_first_live_prepare_pack.py --config configs/runtime.example.json
```

输出重点：

- `readiness.local_boundary_ready`：本地边界是否已准备好。
- `readiness.ready_for_live_execute`：真实执行开关是否已经全部显式打开。
- `payload_review`：首单项目、素材推送、目标账户素材回查、单元创建的 payload（请求体）数量和 scope（执行范围）。
- `required_enablement`：真正执行前需要打开哪些 runtime（运行时配置）和 policy（策略配置）开关。
- `human_review_checklist`：人工核对清单。

在默认示例配置下，它应该是 `ready_for_human_live_enablement`：意思是本地边界已可交给人核对，但真实执行开关仍未打开，固定脚本不会调用真实接口。

## first live local chain

`create_first_live_local_chain` 是首单真实创建前的本地链路入口。它读取现有 `yzt_create_preview`（勇者突进创建预览配置），但不会修改本地配置文件；运行时会派生一个首单范围：

- 只保留 1 个目标账户。
- 项目数不超过 `first_live_run.max_project_count`（首单最大项目数）。
- 单元数不超过 `first_live_run.max_unit_count`（首单最大单元数）。
- 素材数不超过 `first_live_run.max_material_count`（首单最大素材数）。

该入口会继续串起 preparation check（准备检查）和 dry chain（完整本地预演链路），产物状态为 `ready_for_approval_chain` 时，只表示可以进入 approve（批准记录）复核链路，不表示可以真实执行。

固定脚本：

```bash
PYTHONPATH=src python3 scripts/run_create_first_live_local_chain.py --config configs/runtime.example.json --preview-config configs/create/yzt-wx-mini-game.preview.local.json --policy policies/strategy.example.json
```

安全边界保持不变：

- `execution_enabled=false`，执行开关关闭。
- `external_api_calls=0`，外部接口调用数为 0。
- `approved_for_execute=false`，不批准执行。
- `actions=[]`，不生成真实动作。

首单固定脚本入口现在会直接阻断 `.example.json` 示例配置和 `target-advertiser-id` / `source-advertiser-id` 这类占位 ID。首单链路必须读取本地真实配置，例如 `configs/create/yzt-wx-mini-game.preview.local.json`；该文件属于本地私有配置，不提交到 Git。
