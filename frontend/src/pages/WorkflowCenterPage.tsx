import { FileSearchOutlined, PlayCircleOutlined, ReloadOutlined } from "@ant-design/icons";
import { Alert, Button, Card, Col, DatePicker, Descriptions, Form, Input, Row, Select, Space, Table, Tag, Typography, message as antdMessage } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import dayjs from "dayjs";
import type { Dayjs } from "dayjs";
import { useEffect, useMemo, useRef, useState } from "react";

import { apiGet, apiPost } from "../api/client";
import { SummaryPanel } from "../components/SummaryPanel";
import { InlineTaskStatus } from "../components/WorkflowScaffold";
import type { ChineseResult, TaskDetailResponse, WorkflowCatalogItem, WorkflowParameter, WorkflowRunResponse } from "../types/api";
import { businessTableClassName, businessTableSticky } from "../utils/tableLayout";

type WorkflowRequest = Record<string, string>;

const defaultWorkflowId = "material_daily_sync";
const allProductsValue = "__all_enabled_products__";

export function WorkflowCenterPage() {
  const queryClient = useQueryClient();
  const [selectedWorkflowId, setSelectedWorkflowId] = useState(defaultWorkflowId);
  const [workflowRequest, setWorkflowRequest] = useState<WorkflowRequest>({});
  const [previewResult, setPreviewResult] = useState<ChineseResult | undefined>();
  const [runResult, setRunResult] = useState<WorkflowRunResponse | undefined>();
  const lastInitializedWorkflowId = useRef("");
  const activeTaskId = runResult?.task?.task_id ?? "";
  const catalog = useQuery({
    queryKey: ["workflow-runs", "catalog"],
    queryFn: () => apiGet<ChineseResult>("/workflow-runs/catalog"),
  });
  const filterCatalog = useQuery({
    queryKey: ["dashboard", "filters"],
    queryFn: () => apiGet<ChineseResult>("/dashboard/filters"),
  });
  const productOptions = useMemo(() => rowsToProductOptions(filterCatalog.data), [filterCatalog.data]);
  const productNameOptions = useMemo(() => rowsToProductNameOptions(filterCatalog.data), [filterCatalog.data]);
  const workflows = useMemo(() => workflowItemsFromCatalog(catalog.data), [catalog.data]);
  const selectedWorkflow = workflows.find((item) => item.workflow_id === selectedWorkflowId) ?? workflows[0];
  const activeTaskDetail = useQuery({
    queryKey: ["tasks", activeTaskId],
    queryFn: () => apiGet<TaskDetailResponse>(`/tasks/${activeTaskId}`),
    enabled: Boolean(activeTaskId),
    refetchInterval: 3000,
  });

  useEffect(() => {
    if (!workflows.length) {
      return;
    }
    const nextWorkflow = workflows.find((item) => item.workflow_id === selectedWorkflowId) ?? workflows[0];
    if (nextWorkflow.workflow_id !== selectedWorkflowId) {
      setSelectedWorkflowId(nextWorkflow.workflow_id);
      return;
    }
    if (lastInitializedWorkflowId.current !== nextWorkflow.workflow_id) {
      lastInitializedWorkflowId.current = nextWorkflow.workflow_id;
      setWorkflowRequest(defaultRequestForWorkflow(nextWorkflow));
      setPreviewResult(undefined);
      setRunResult(undefined);
    }
  }, [selectedWorkflowId, workflows]);

  useEffect(() => {
    const status = String(activeTaskDetail.data?.summary.status ?? "");
    if (status === "completed" || status === "failed") {
      void catalog.refetch();
    }
  }, [activeTaskDetail.data?.summary.status]);

  const preview = useMutation({
    mutationFn: () => apiPost<ChineseResult>(`/workflow-runs/${selectedWorkflowId}/preview`, { request: workflowRequest }),
    onSuccess: (result) => {
      setPreviewResult(result);
      setRunResult(undefined);
    },
  });
  const run = useMutation({
    mutationFn: () => apiPost<WorkflowRunResponse>(`/workflow-runs/${selectedWorkflowId}/run`, { request: workflowRequest }),
    onSuccess: async (result) => {
      setRunResult(result);
      await queryClient.invalidateQueries({ queryKey: ["tasks"] });
      antdMessage.success("任务已提交，本页会显示进度和结果");
    },
  });
  const canRun = Boolean(previewResult?.raw.can_run) && !run.isPending;

  function selectWorkflow(workflowId: string) {
    setSelectedWorkflowId(workflowId);
  }

  function updateRequest(name: string, value: string) {
    setWorkflowRequest((current) => ({ ...current, [name]: value }));
    setPreviewResult(undefined);
    setRunResult(undefined);
  }

  async function refreshWorkflowStatus() {
    await Promise.all([catalog.refetch(), queryClient.invalidateQueries({ queryKey: ["tasks"] })]);
  }

  return (
    <main className="page">
      <Space direction="vertical" size="large" className="full-width">
        <div className="page-heading-row">
          <Typography.Title level={2}>自动化工作台</Typography.Title>
          <Button icon={<ReloadOutlined />} onClick={refreshWorkflowStatus} loading={catalog.isFetching}>
            刷新任务状态
          </Button>
        </div>
        <Alert
          type="info"
          showIcon
          message="这里只运行只读同步、本地重算和预览任务；不会上传素材、创建广告、修改预算、出价或项目状态。"
        />
        {catalog.error ? <Alert type="error" showIcon message={(catalog.error as Error).message} /> : null}
        <Row gutter={[16, 16]} align="top">
          <Col xs={24} xl={9}>
            <Card size="small" title="任务状态列表">
              <Table<WorkflowCatalogItem>
                className={businessTableClassName("workflow-catalog-table")}
                rowKey="workflow_id"
                loading={catalog.isLoading}
                dataSource={workflows}
                pagination={false}
                size="small"
                sticky={businessTableSticky}
                rowClassName={(record) => (record.workflow_id === selectedWorkflowId ? "workflow-row-selected" : "summary-row-clickable")}
                onRow={(record) => ({ onClick: () => selectWorkflow(record.workflow_id) })}
                columns={workflowColumns()}
              />
            </Card>
          </Col>
          <Col xs={24} xl={15}>
            <Card size="small" title={selectedWorkflow?.name ?? "任务详情"}>
              <Space direction="vertical" size="middle" className="full-width">
                {selectedWorkflow ? (
                  <>
                    <Space wrap>
                      <Tag>{selectedWorkflow.category}</Tag>
                      <Tag color={riskColor(selectedWorkflow.risk_level)}>风险：{riskLabel(selectedWorkflow.risk_level)}</Tag>
                      <Tag color="blue">真实投放动作：否</Tag>
                      <Tag color={selectedWorkflow.ai_auto_run ? "cyan" : "default"}>
                        AI 自动运行：{selectedWorkflow.ai_auto_run ? "允许" : "不允许"}
                      </Tag>
                    </Space>
                    <Typography.Paragraph type="secondary" className="workflow-description">
                      {selectedWorkflow.description}
                    </Typography.Paragraph>
                    <WorkflowLatestStatusPanel workflow={selectedWorkflow} />
                    <Form layout="vertical" className="workflow-param-panel">
                      <Row gutter={[16, 0]}>
                        {selectedWorkflow.parameters.map((parameter) => (
                          <Col xs={24} md={12} key={parameter.name}>
                            <Form.Item label={parameter.label} required={parameter.required}>
                              {renderParameterControl({
                                parameter,
                                value: workflowRequest[parameter.name] ?? parameter.default,
                                productOptions,
                                productNameOptions,
                                productOptionsLoading: filterCatalog.isLoading,
                                onChange: (value) => updateRequest(parameter.name, value),
                              })}
                              {parameter.description ? (
                                <Typography.Text type="secondary" className="allowed-account-help">
                                  {parameter.description}
                                </Typography.Text>
                              ) : null}
                            </Form.Item>
                          </Col>
                        ))}
                      </Row>
                    </Form>
                    <Space wrap className="workflow-actions">
                      <Button icon={<FileSearchOutlined />} onClick={() => preview.mutate()} loading={preview.isPending}>
                        生成运行预览
                      </Button>
                      <Button
                        icon={<PlayCircleOutlined />}
                        type="primary"
                        disabled={!canRun}
                        loading={run.isPending}
                        onClick={() => run.mutate()}
                      >
                        启动安全任务
                      </Button>
                    </Space>
                  </>
                ) : (
                  <Alert type="warning" showIcon message="暂无可运行任务" />
                )}
              </Space>
            </Card>
            {preview.error ? <Alert className="page-alert" type="error" showIcon message={(preview.error as Error).message} /> : null}
            <SummaryPanel result={previewResult} loading={preview.isPending} detailsCollapsed showArtifactPath={false} showRawJson={false} />
            {run.error ? <Alert className="page-alert" type="error" showIcon message={(run.error as Error).message} /> : null}
            <InlineTaskStatus
              title="当前任务"
              taskId={activeTaskId}
              workflow={selectedWorkflow?.latest_workflow}
              result={runResult}
              detail={activeTaskDetail.data}
              loading={run.isPending || activeTaskDetail.isFetching}
              returnTo="/workflow-center"
            />
          </Col>
        </Row>
      </Space>
    </main>
  );
}

function workflowColumns(): ColumnsType<WorkflowCatalogItem> {
  return [
    {
      title: "任务名称",
      dataIndex: "name",
      render: (value, record) => (
        <Space direction="vertical" size={4} className="full-width">
          <Space wrap size={6}>
            <Typography.Text strong>{value}</Typography.Text>
            <Tag>{record.category}</Tag>
            <Tag color={riskColor(record.risk_level)}>风险{riskLabel(record.risk_level)}</Tag>
          </Space>
          <Typography.Text type="secondary" className="workflow-list-summary">
            {record.latest_status?.summary || "暂无最近运行结果"}
          </Typography.Text>
          {record.latest_status?.run_at_label ? (
            <Typography.Text type="secondary" className="workflow-list-time">
              最近：{record.latest_status.run_at_label}
            </Typography.Text>
          ) : null}
        </Space>
      ),
    },
    {
      title: "状态",
      dataIndex: "latest_status",
      width: 108,
      render: (_value, record) => <Tag color={statusColor(record.latest_status?.status)}>{record.latest_status?.status_label || "未运行"}</Tag>,
    },
    {
      title: "动作",
      dataIndex: "true_action",
      width: 84,
      render: () => <Tag color="blue">只读</Tag>,
    },
  ];
}

function WorkflowLatestStatusPanel({ workflow }: { workflow?: WorkflowCatalogItem }) {
  const latest = workflow?.latest_status;
  if (!workflow || !latest?.status_label) {
    return <Alert type="info" showIcon message="这个任务暂时没有最近运行记录，可以先生成运行预览。" />;
  }
  return (
    <div className="workflow-latest-panel">
      <Descriptions size="small" column={{ xs: 1, md: 2 }} labelStyle={{ color: "#667085" }}>
        <Descriptions.Item label="最近状态">
          <Tag color={statusColor(latest.status)}>{latest.status_label}</Tag>
        </Descriptions.Item>
        <Descriptions.Item label="运行来源">{latest.source || "本地记录"}</Descriptions.Item>
        <Descriptions.Item label="最近运行时间">{latest.run_at_label || "-"}</Descriptions.Item>
        <Descriptions.Item label="结果文件">{latest.artifact_path || "-"}</Descriptions.Item>
        <Descriptions.Item label="最近结果" span={2}>
          {latest.summary || "暂无中文摘要"}
        </Descriptions.Item>
      </Descriptions>
    </div>
  );
}

function renderParameterControl({
  parameter,
  value,
  productOptions,
  productNameOptions,
  productOptionsLoading,
  onChange,
}: {
  parameter: WorkflowParameter;
  value: string;
  productOptions: { label: string; value: string }[];
  productNameOptions: { label: string; value: string }[];
  productOptionsLoading: boolean;
  onChange: (value: string) => void;
}) {
  if (parameter.control === "product_select") {
    return (
      <Select
        className="workflow-param-control"
        loading={productOptionsLoading}
        value={value || allProductsValue}
        options={[{ label: "全部启用产品", value: allProductsValue }, ...productOptions]}
        onChange={(nextValue) => onChange(nextValue === allProductsValue ? "" : nextValue)}
      />
    );
  }
  if (parameter.control === "product_name_select") {
    return (
      <Select
        className="workflow-param-control"
        loading={productOptionsLoading}
        allowClear
        value={value || undefined}
        options={productNameOptions}
        placeholder="全部已绑定产品"
        onChange={(nextValue) => onChange(nextValue ?? "")}
      />
    );
  }
  if (parameter.control === "date_select") {
    const presetValue = value === "today" || value === "yesterday" ? value : "custom";
    const customDate = presetValue === "custom" ? parseDateValue(value) : null;
    return (
      <Space wrap className="workflow-date-control">
        <Select
          className="workflow-date-preset"
          value={presetValue}
          options={[
            { label: "今天", value: "today" },
            { label: "昨天", value: "yesterday" },
            { label: "指定日期", value: "custom" },
          ]}
          onChange={(nextValue) => {
            if (nextValue === "custom") {
              onChange(customDate?.format("YYYY-MM-DD") || dayjs().format("YYYY-MM-DD"));
              return;
            }
            onChange(nextValue);
          }}
        />
        {presetValue === "custom" ? (
          <DatePicker
            value={customDate}
            format="YYYY-MM-DD"
            onChange={(nextDate) => onChange(dateToRequestValue(nextDate))}
            allowClear={false}
          />
        ) : null}
      </Space>
    );
  }
  if (parameter.control === "select") {
    return (
      <select
        className="workflow-param-control workflow-native-select"
        value={value || parameter.default}
        onChange={(event) => onChange(event.target.value)}
      >
        {(parameter.options ?? []).map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    );
  }
  return <Input value={value} onChange={(event) => onChange(event.target.value)} placeholder={parameter.default} />;
}

function workflowItemsFromCatalog(catalog?: ChineseResult): WorkflowCatalogItem[] {
  const rawWorkflows = catalog?.raw.workflows;
  if (!Array.isArray(rawWorkflows)) {
    return [];
  }
  return rawWorkflows.filter(isWorkflowCatalogItem);
}

function isWorkflowCatalogItem(value: unknown): value is WorkflowCatalogItem {
  if (!value || typeof value !== "object") {
    return false;
  }
  const item = value as Partial<WorkflowCatalogItem>;
  return typeof item.workflow_id === "string" && typeof item.name === "string" && Array.isArray(item.parameters);
}

function defaultRequestForWorkflow(workflow: WorkflowCatalogItem): WorkflowRequest {
  const request: WorkflowRequest = {};
  workflow.parameters.forEach((parameter) => {
    request[parameter.name] = parameter.default;
  });
  return request;
}

function rowsToProductOptions(result?: ChineseResult) {
  return (result?.table.rows ?? [])
    .filter((row) => row["类型"] === "产品")
    .map((row) => ({
      label: String(row["显示名称"] ?? row["值"] ?? ""),
      value: String(row["值"] ?? ""),
    }));
}

function rowsToProductNameOptions(result?: ChineseResult) {
  return (result?.table.rows ?? [])
    .filter((row) => row["类型"] === "产品")
    .map((row) => {
      const label = String(row["显示名称"] ?? row["值"] ?? "");
      return { label, value: label };
    });
}

function parseDateValue(value: string): Dayjs | null {
  if (!value || value === "today" || value === "yesterday") {
    return null;
  }
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    return null;
  }
  const parsed = dayjs(value);
  return parsed.isValid() ? parsed : null;
}

function dateToRequestValue(value: Dayjs | null): string {
  return value?.format("YYYY-MM-DD") ?? dayjs().format("YYYY-MM-DD");
}

function statusColor(status?: string): string {
  if (status === "completed" || status === "success" || status === "succeeded") {
    return "green";
  }
  if (status === "failed" || status === "partial_failed") {
    return "red";
  }
  if (status === "queued" || status?.startsWith("running")) {
    return "blue";
  }
  if (status === "blocked") {
    return "orange";
  }
  return "default";
}

function riskColor(riskLevel?: string): string {
  if (riskLevel === "high") {
    return "red";
  }
  if (riskLevel === "medium") {
    return "orange";
  }
  if (riskLevel === "low") {
    return "green";
  }
  return "default";
}

function riskLabel(riskLevel?: string): string {
  if (riskLevel === "high") {
    return "高";
  }
  if (riskLevel === "medium") {
    return "中";
  }
  if (riskLevel === "low") {
    return "低";
  }
  return riskLevel || "未知";
}
