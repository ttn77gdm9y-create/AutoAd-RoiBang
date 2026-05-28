import { Alert, Button, Form, Input, Select, Space, Typography } from "antd";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { apiGet } from "../api/client";
import { SummaryPanel } from "../components/SummaryPanel";
import type { ChineseResult } from "../types/api";

const operationOptions = [
  { label: "创建计划生成", value: "create_plan_generate" },
  { label: "创建真实执行", value: "create_live_execute" },
  { label: "项目管理配置生成", value: "project_management_config_generate" },
  { label: "项目管理真实执行", value: "project_update_execute" },
  { label: "落地页状态更新", value: "site_status_update" },
  { label: "模板建站", value: "site_template_foundation" },
  { label: "账户备注配置生成", value: "account_remark_config_generate" },
  { label: "账户备注真实执行", value: "account_remark_update" },
  { label: "连通性检查", value: "dry_run_probe" },
];

const statusOptions = [
  { label: "已完成", value: "completed" },
  { label: "失败", value: "failed" },
  { label: "排队中", value: "queued" },
  { label: "运行中", value: "running" },
];

export function OperationsPage() {
  const [filters, setFilters] = useState({ product: "", operation_type: "", status: "" });
  const [searchParams, setSearchParams] = useSearchParams();
  const [selectedTaskId, setSelectedTaskId] = useState(searchParams.get("task_id") ?? "");
  useEffect(() => {
    const taskId = searchParams.get("task_id") ?? "";
    if (taskId !== selectedTaskId) {
      setSelectedTaskId(taskId);
    }
  }, [searchParams, selectedTaskId]);
  const selectTaskId = (taskId: string) => {
    setSelectedTaskId(taskId);
    if (taskId) {
      setSearchParams({ task_id: taskId });
    } else {
      setSearchParams({});
    }
  };
  const querySuffix = useMemo(() => {
    const params = new URLSearchParams();
    Object.entries(filters).forEach(([key, value]) => {
      if (value) {
        params.set(key, value);
      }
    });
    const value = params.toString();
    return value ? `?${value}` : "";
  }, [filters]);
  const query = useQuery({
    queryKey: ["operations", filters],
    queryFn: () => apiGet<ChineseResult>(`/operations${querySuffix}`),
  });
  const detail = useQuery({
    queryKey: ["operations", "detail", selectedTaskId],
    queryFn: () => apiGet<ChineseResult>(`/operations/${encodeURIComponent(selectedTaskId)}`),
    enabled: Boolean(selectedTaskId),
  });

  return (
    <main className="page">
      <Space direction="vertical" size="large" className="full-width">
        <Typography.Title level={2}>操作日志</Typography.Title>
        <Alert
          type="info"
          showIcon
          message="这里是审计记录，用来回看每次业务动作的触发人、状态和执行对象；普通执行结果会优先显示在对应业务页。"
        />
        <Form layout="inline" className="filter-bar">
          <Form.Item label="产品">
            <Input
              value={filters.product}
              onChange={(event) => setFilters({ ...filters, product: event.target.value })}
              placeholder="产品名或产品 Key"
            />
          </Form.Item>
          <Form.Item label="操作类型">
            <Select
              allowClear
              showSearch
              optionFilterProp="label"
              className="operation-select"
              value={filters.operation_type}
              onChange={(value) => setFilters({ ...filters, operation_type: value ?? "" })}
              options={operationOptions}
              placeholder="选择操作类型"
            />
          </Form.Item>
          <Form.Item label="状态">
            <Select
              allowClear
              className="status-select"
              value={filters.status || undefined}
              onChange={(value) => setFilters({ ...filters, status: value ?? "" })}
              options={statusOptions}
            />
          </Form.Item>
        </Form>
        {query.error ? <Alert type="error" showIcon message={(query.error as Error).message} /> : null}
        <SummaryPanel
          result={query.data}
          loading={query.isLoading}
          detailsCollapsed={false}
          showArtifactPath={false}
          showRawJson={false}
          onRowClick={(row) => selectTaskId(String(row["任务 ID"] ?? ""))}
        />
        {selectedTaskId ? (
          <Alert
            type="info"
            showIcon
            message={
              <Space wrap>
                <span>当前复盘任务：{selectedTaskId}</span>
                <Button size="small" onClick={() => selectTaskId("")}>
                  清除选择
                </Button>
              </Space>
            }
          />
        ) : null}
        {detail.error ? <Alert type="error" showIcon message={(detail.error as Error).message} /> : null}
        {selectedTaskId ? (
          <SummaryPanel result={detail.data} loading={detail.isLoading} detailsCollapsed={false} showArtifactPath={false} showRawJson={false} />
        ) : null}
      </Space>
    </main>
  );
}
