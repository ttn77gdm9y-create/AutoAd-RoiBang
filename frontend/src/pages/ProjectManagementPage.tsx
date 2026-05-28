import { FileSearchOutlined } from "@ant-design/icons";
import { Alert, Button, Card, Col, Collapse, Form, Input, Row, Select, Space, Typography, message as antdMessage } from "antd";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { apiGet, apiPost } from "../api/client";
import { ConfirmExecutePanel } from "../components/ConfirmExecutePanel";
import { SummaryPanel } from "../components/SummaryPanel";
import { InlineTaskStatus, WorkflowSteps } from "../components/WorkflowScaffold";
import type { ChineseResult, TaskDetailResponse } from "../types/api";

type ProjectManagementRequest = {
  project_update_id: string;
  advertiser_ids: string;
  action_type: string;
  name_contains: string;
  spend_window: string;
  metric_field: string;
  metric_op: string;
  metric_value: string;
  output_path: string;
  opt_status: string;
  budget: string;
  cpa_bid: string;
  roi_goal: string;
};

type TaskResponse = ChineseResult & {
  task?: {
    task_id: string;
    artifact_path: string;
    pid: number;
  };
};

const defaultRequest: ProjectManagementRequest = {
  project_update_id: "ui-project-filter",
  advertiser_ids: "",
  action_type: "delete_project",
  name_contains: "",
  spend_window: "today",
  metric_field: "stat_cost",
  metric_op: "lte",
  metric_value: "100",
  output_path: "configs/project-updates/ui-project-filter.local.json",
  opt_status: "DISABLE",
  budget: "",
  cpa_bid: "",
  roi_goal: "",
};

export function ProjectManagementPage() {
  const queryClient = useQueryClient();
  const [request, setRequest] = useState<ProjectManagementRequest>(defaultRequest);
  const [previewResult, setPreviewResult] = useState<ChineseResult | undefined>();
  const [generateResult, setGenerateResult] = useState<TaskResponse | undefined>();
  const [executePreviewResult, setExecutePreviewResult] = useState<ChineseResult | undefined>();
  const [executeResult, setExecuteResult] = useState<TaskResponse | undefined>();
  const executeRequest = { project_update_path: request.output_path || defaultRequest.output_path };
  const activeTaskId = executeResult?.task?.task_id ?? generateResult?.task?.task_id ?? "";
  const currentStep = executeResult ? 3 : executePreviewResult ? 2 : previewResult || generateResult ? 1 : 0;
  const activeTaskDetail = useQuery({
    queryKey: ["tasks", activeTaskId],
    queryFn: () => apiGet<TaskDetailResponse>(`/tasks/${activeTaskId}`),
    enabled: Boolean(activeTaskId),
    refetchInterval: 3000,
  });
  const preview = useMutation({
    mutationFn: () => apiPost<ChineseResult>("/project-management/config/preview", request),
    onSuccess: (result) => {
      setPreviewResult(result);
      setGenerateResult(undefined);
      setExecutePreviewResult(undefined);
      setExecuteResult(undefined);
    },
  });
  const generate = useMutation({
    mutationFn: () => apiPost<TaskResponse>("/project-management/config/generate", request),
    onSuccess: async (result) => {
      setGenerateResult(result);
      setExecutePreviewResult(undefined);
      setExecuteResult(undefined);
      await queryClient.invalidateQueries({ queryKey: ["tasks"] });
    },
  });
  const executePreview = useMutation({
    mutationFn: () => apiPost<ChineseResult>("/project-management/execute/preview", executeRequest),
    onSuccess: (result) => {
      setExecutePreviewResult(result);
      setExecuteResult(undefined);
    },
  });
  const execute = useMutation({
    mutationFn: () => apiPost<TaskResponse>("/project-management/execute", { ...executeRequest, confirmation: "确认执行" }),
    onSuccess: async (result) => {
      setExecuteResult(result);
      await queryClient.invalidateQueries({ queryKey: ["tasks"] });
      antdMessage.success("项目管理任务已提交，本页会显示进度");
    },
  });

  return (
    <main className="page">
      <Space direction="vertical" size="large" className="full-width">
        <Typography.Title level={2}>项目管理</Typography.Title>
        <WorkflowSteps current={currentStep} />
        <Alert
          type="info"
          showIcon
          message="先按账户和筛选条件检查会影响哪些项目，再生成动作配置并确认执行；进度和结果会直接显示在本页。"
        />

        <Card size="small" title="第一步：筛选并检查项目动作">
          <Form layout="vertical" className="filter-bar">
            <Row gutter={[16, 0]}>
              <Col xs={24} lg={8}>
                <Form.Item label="动作">
                  <Select
                    value={request.action_type}
                    onChange={(value) => setRequest({ ...request, action_type: value })}
                    options={[
                      { label: "删除项目", value: "delete_project" },
                      { label: "开启/关闭项目", value: "status_update" },
                      { label: "调整预算", value: "budget_update" },
                      { label: "调整出价", value: "bid_update" },
                      { label: "调整 ROI 系数", value: "roi_coeff_update" },
                    ]}
                  />
                </Form.Item>
              </Col>
              <Col xs={24} lg={8}>
                <Form.Item label="项目名包含">
                  <Input
                    value={request.name_contains}
                    onChange={(event) => setRequest({ ...request, name_contains: event.target.value })}
                    placeholder="可空"
                  />
                </Form.Item>
              </Col>
              <Col xs={24} lg={8}>
                <Form.Item label="数据窗口">
                  <Select
                    value={request.spend_window}
                    onChange={(value) => setRequest({ ...request, spend_window: value })}
                    options={[
                      { label: "今天", value: "today" },
                      { label: "昨天", value: "yesterday" },
                      { label: "近 3 天", value: "last_3_days" },
                    ]}
                  />
                </Form.Item>
              </Col>
              <Col xs={24} lg={8}>
                <Form.Item label="筛选字段">
                  <Select
                    value={request.metric_field}
                    onChange={(value) => setRequest({ ...request, metric_field: value })}
                    options={[
                      { label: "消耗", value: "stat_cost" },
                      { label: "注册数", value: "active_register" },
                      { label: "注册成本", value: "register_cost" },
                      { label: "计费时间转化数", value: "billing_convert_cnt" },
                      { label: "计费时间转化成本", value: "billing_conversion_cost" },
                      { label: "计费当日付费 ROI", value: "billing_1day_pay_roi" },
                    ]}
                  />
                </Form.Item>
              </Col>
              <Col xs={24} lg={4}>
                <Form.Item label="比较符">
                  <Select
                    value={request.metric_op}
                    onChange={(value) => setRequest({ ...request, metric_op: value })}
                    options={[
                      { label: "小于", value: "lt" },
                      { label: "小于等于", value: "lte" },
                      { label: "大于", value: "gt" },
                      { label: "大于等于", value: "gte" },
                      { label: "等于", value: "eq" },
                    ]}
                  />
                </Form.Item>
              </Col>
              <Col xs={24} lg={4}>
                <Form.Item label="筛选值">
                  <Input
                    value={request.metric_value}
                    onChange={(event) => setRequest({ ...request, metric_value: event.target.value })}
                  />
                </Form.Item>
              </Col>
              {request.action_type === "status_update" ? (
                <Col xs={24} lg={8}>
                  <Form.Item label="目标状态">
                    <Select
                      value={request.opt_status}
                      onChange={(value) => setRequest({ ...request, opt_status: value })}
                      options={[
                        { label: "关闭", value: "DISABLE" },
                        { label: "开启", value: "ENABLE" },
                      ]}
                    />
                  </Form.Item>
                </Col>
              ) : null}
              {request.action_type === "budget_update" ? (
                <Col xs={24} lg={8}>
                  <Form.Item label="预算">
                    <Input value={request.budget} onChange={(event) => setRequest({ ...request, budget: event.target.value })} />
                  </Form.Item>
                </Col>
              ) : null}
              {request.action_type === "bid_update" ? (
                <Col xs={24} lg={8}>
                  <Form.Item label="项目出价">
                    <Input value={request.cpa_bid} onChange={(event) => setRequest({ ...request, cpa_bid: event.target.value })} />
                  </Form.Item>
                </Col>
              ) : null}
              {request.action_type === "roi_coeff_update" ? (
                <Col xs={24} lg={8}>
                  <Form.Item label="ROI 系数">
                    <Input value={request.roi_goal} onChange={(event) => setRequest({ ...request, roi_goal: event.target.value })} />
                  </Form.Item>
                </Col>
              ) : null}
              <Col xs={24}>
                <Form.Item label="账户 ID">
                  <Input.TextArea
                    rows={4}
                    value={request.advertiser_ids}
                    onChange={(event) => setRequest({ ...request, advertiser_ids: event.target.value })}
                    placeholder="多个账户用换行或逗号分隔"
                  />
                </Form.Item>
              </Col>
              <Col xs={24}>
                <Collapse
                  className="advanced-fields"
                  items={[
                    {
                      key: "advanced",
                      label: "高级信息：配置编号和文件路径",
                      children: (
                        <Row gutter={[16, 0]}>
                          <Col xs={24} lg={8}>
                            <Form.Item label="配置 ID">
                              <Input
                                value={request.project_update_id}
                                onChange={(event) => setRequest({ ...request, project_update_id: event.target.value })}
                              />
                            </Form.Item>
                          </Col>
                          <Col xs={24} lg={16}>
                            <Form.Item label="配置保存路径">
                              <Input
                                value={request.output_path}
                                onChange={(event) => setRequest({ ...request, output_path: event.target.value })}
                              />
                            </Form.Item>
                          </Col>
                        </Row>
                      ),
                    },
                  ]}
                />
              </Col>
              <Col xs={24}>
                <Space wrap className="workflow-actions">
                  <Button icon={<FileSearchOutlined />} type="primary" onClick={() => preview.mutate()} loading={preview.isPending}>
                    检查项目动作
                  </Button>
                  <Button disabled={!previewResult} onClick={() => generate.mutate()} loading={generate.isPending}>
                    生成动作配置
                  </Button>
                </Space>
              </Col>
            </Row>
          </Form>
          {preview.error ? <Alert type="error" showIcon message={(preview.error as Error).message} /> : null}
          <SummaryPanel result={previewResult} loading={preview.isPending} detailsCollapsed showArtifactPath={false} showRawJson={false} />
          {generate.error ? <Alert type="error" showIcon message={(generate.error as Error).message} /> : null}
        </Card>

        <Card size="small" title="第二步：确认并执行项目动作">
          <Space direction="vertical" size="middle" className="full-width">
            <Alert
              type="info"
              showIcon
              message="这里不会重新筛选项目；执行对象以第一步生成的动作配置为准。"
            />
            <Button icon={<FileSearchOutlined />} onClick={() => executePreview.mutate()} loading={executePreview.isPending}>
              检查执行明细
            </Button>
            {executePreview.error ? <Alert type="error" showIcon message={(executePreview.error as Error).message} /> : null}
            <SummaryPanel
              result={executePreviewResult}
              loading={executePreview.isPending}
              detailsCollapsed
              showArtifactPath={false}
              showRawJson={false}
              footer={
                executePreviewResult?.summary.execution_enabled ? (
                  <ConfirmExecutePanel
                    buttonText="确认并执行项目动作"
                    disabled={execute.isPending}
                    onConfirm={() => execute.mutate()}
                  />
                ) : null
              }
            />
            {execute.error ? <Alert type="error" showIcon message={(execute.error as Error).message} /> : null}
          </Space>
        </Card>

        <InlineTaskStatus
          title="当前项目管理任务"
          taskId={activeTaskId}
          workflow="project_update_execute"
          result={executeResult ?? generateResult}
          detail={activeTaskDetail.data}
          loading={activeTaskDetail.isFetching || generate.isPending || execute.isPending}
        />
      </Space>
    </main>
  );
}
