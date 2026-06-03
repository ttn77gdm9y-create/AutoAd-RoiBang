import { FileSearchOutlined, PlayCircleOutlined, ReloadOutlined } from "@ant-design/icons";
import { Alert, Button, Card, Col, Form, Input, Row, Space, Table, Tag, Typography, message as antdMessage } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import { apiGet, apiPost } from "../api/client";
import { SummaryPanel } from "../components/SummaryPanel";
import { InlineTaskStatus } from "../components/WorkflowScaffold";
import type { ChineseResult, TaskDetailResponse, WorkflowCatalogItem, WorkflowRunResponse } from "../types/api";

type WorkflowRequest = Record<string, string>;

const defaultWorkflowId = "material_daily_sync";

export function WorkflowCenterPage() {
  const queryClient = useQueryClient();
  const [selectedWorkflowId, setSelectedWorkflowId] = useState(defaultWorkflowId);
  const [workflowRequest, setWorkflowRequest] = useState<WorkflowRequest>({});
  const [previewResult, setPreviewResult] = useState<ChineseResult | undefined>();
  const [runResult, setRunResult] = useState<WorkflowRunResponse | undefined>();
  const activeTaskId = runResult?.task?.task_id ?? "";
  const catalog = useQuery({
    queryKey: ["workflow-runs", "catalog"],
    queryFn: () => apiGet<ChineseResult>("/workflow-runs/catalog"),
  });
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
    setWorkflowRequest(defaultRequestForWorkflow(nextWorkflow));
    setPreviewResult(undefined);
    setRunResult(undefined);
  }, [selectedWorkflowId, workflows]);

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

  return (
    <main className="page">
      <Space direction="vertical" size="large" className="full-width">
        <div className="page-heading-row">
          <Typography.Title level={2}>自动化工作台</Typography.Title>
          <Button icon={<ReloadOutlined />} onClick={() => catalog.refetch()} loading={catalog.isFetching}>
            刷新任务菜单
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
            <Card size="small" title="任务菜单">
              <Table<WorkflowCatalogItem>
                rowKey="workflow_id"
                loading={catalog.isLoading}
                dataSource={workflows}
                pagination={false}
                size="small"
                rowClassName={(record) => (record.workflow_id === selectedWorkflowId ? "workflow-row-selected" : "summary-row-clickable")}
                onRow={(record) => ({ onClick: () => selectWorkflow(record.workflow_id) })}
                columns={workflowColumns}
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
                      <Tag color={selectedWorkflow.risk_level === "medium" ? "orange" : "green"}>
                        风险：{selectedWorkflow.risk_level === "medium" ? "中" : "低"}
                      </Tag>
                      <Tag color="blue">真实投放动作：否</Tag>
                      <Tag color={selectedWorkflow.ai_auto_run ? "cyan" : "default"}>
                        AI 自动运行：{selectedWorkflow.ai_auto_run ? "允许" : "不允许"}
                      </Tag>
                    </Space>
                    <Typography.Paragraph type="secondary" className="workflow-description">
                      {selectedWorkflow.description}
                    </Typography.Paragraph>
                    <Form layout="vertical" className="workflow-param-panel">
                      <Row gutter={[16, 0]}>
                        {selectedWorkflow.parameters.map((parameter) => (
                          <Col xs={24} md={12} key={parameter.name}>
                            <Form.Item label={parameter.label} required={parameter.required}>
                              <Input
                                value={workflowRequest[parameter.name] ?? parameter.default}
                                onChange={(event) => updateRequest(parameter.name, event.target.value)}
                                placeholder={parameter.default}
                              />
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

const workflowColumns: ColumnsType<WorkflowCatalogItem> = [
  {
    title: "任务名称",
    dataIndex: "name",
    render: (value, record) => (
      <Space direction="vertical" size={2}>
        <Typography.Text strong>{value}</Typography.Text>
        <Typography.Text type="secondary">{record.category}</Typography.Text>
      </Space>
    ),
  },
  {
    title: "风险",
    dataIndex: "risk_level",
    width: 84,
    render: (value) => <Tag color={value === "medium" ? "orange" : "green"}>{value === "medium" ? "中" : "低"}</Tag>,
  },
  {
    title: "动作",
    dataIndex: "true_action",
    width: 96,
    render: () => <Tag color="blue">只读</Tag>,
  },
];

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
