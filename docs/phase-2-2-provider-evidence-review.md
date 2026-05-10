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

当前示例证据目录故意保持未复核：

```text
configs/provider-evidence/oceanengine.create.phase2-review.example.json
```

当前预期结果：

- 检查 18 个映射字段。
- 载入 3 条证据目录项。
- 已复核证据数为 0。
- 未解决字段数为 18。
- `operator_guide.status=needs_review`。
- `evidence_worksheet.summary.row_count=18`。
- `provider_field_gap_report.summary.gap_count=4`。
- `provider_field_gap_resolution_plan.summary.gap_count=4`。
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

当前 4 个缺口：

- `create_project.project_type`
- `create_project.field_defaults`
- `create_unit.field_defaults`
- `bind_material.source_video_id`

不要猜这些字段。每个缺口都必须通过平台证据确认，或者明确决定该本地字段需要拆分、改名，或者不进入未来平台请求体草稿。

## 缺平台字段处理计划

`provider_field_gap_resolution_plan` 是人工复核计划，不是批准产物。它会为每个缺口生成：

- `recommended_action`：建议动作，会按字段类型给出不同复核方向。
- `review_questions`：人工复核时要回答的问题。
- `blocked_until`：解除阻塞前必须完成的条件。
- `do_not_do`：禁止事项，例如不要猜字段、不要打开 `create_execute`。

这个计划的目标是让 4 个缺口逐个可复核，而不是让脚本替人判断平台字段。

当前建议动作：

- `confirm_local_template_selector_or_split_to_provider_fields`：确认 `project_type` 是不是只用于本地模板选择、项目命名和策略分支；如果不是本地字段，就必须拆成明确平台字段。
- `split_field_defaults_into_explicit_provider_fields`：把 `field_defaults` 拆成明确平台字段，不能把默认字段集合整包塞进平台请求体。
- `confirm_material_identifier_or_local_provenance`：确认 `source_video_id` 是平台素材绑定字段，还是只用于本地素材来源追溯。

## project_type 本地用途复核

`project_type_local_usage_review` 会把 `project_type` 的本地用途列出来，帮助判断它未来能不能改成 `local_only`。

当前能看到的本地用途包括：

- 模板选择：从模板名推导 `WX_PAY` 或 `WX_PAY_7R`。
- 请求校验：作为创建请求的必填输入。
- 项目命名：作为项目名模板变量。
- 批次码来源：参与批次码生成，保持批次可追踪。
- 命名预检查：用于生成样例项目名。
- dry-run 追踪：保留在本地计划里方便复盘。

但当前还不能直接把 `project_type` 标记为 `local_only`，因为仍有两个阻塞点：

- 禁用版 payload schema 仍把它列在 `create_project.required_fields`。
- dry-run 草稿仍把它放在 `disabled_schema_only` 请求体里。

所以这个清单只说明“很像本地字段”，不做自动确认。要等这两个阻塞点处理完，再由人工确认。

## 下一步人工复核

在把任何字段改成 `verified=true` 之前，需要先复核：

1. 项目创建请求字段。
2. 单元创建请求字段。
3. 素材绑定请求字段。
4. 本地键是否确实不进入平台请求体。
5. `material_id` 和 `source_video_id` 在素材绑定里各自是否需要。

只有复核完成后，才能更新证据目录 JSON。
