import { DeleteOutlined, FileSearchOutlined, PlusOutlined } from "@ant-design/icons";
import { Alert, Button, Card, Col, Collapse, Form, Input, Row, Select, Space, Typography, message as antdMessage } from "antd";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

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
  metric_filters: MetricFilter[];
  output_path: string;
  opt_status: string;
  budget: string;
  cpa_bid: string;
  roi_goal: string;
};

type MetricFilter = {
  field: string;
  op: string;
  value: string;
};

type TaskResponse = ChineseResult & {
  task?: {
    task_id: string;
    artifact_path: string;
    pid: number;
  };
};

const defaultRequest: ProjectManagementRequest = {
  project_update_id: "",
  advertiser_ids: "",
  action_type: "",
  name_contains: "",
  spend_window: "",
  metric_filters: [{ field: "", op: "", value: "" }],
  output_path: "",
  opt_status: "",
  budget: "",
  cpa_bid: "",
  roi_goal: "",
};

function projectUpdatePathFromTask(detail?: TaskDetailResponse): string {
  const result = detail?.raw?.result;
  if (result && typeof result === "object" && "project_update_path" in result) {
    return String((result as { project_update_path?: unknown }).project_update_path ?? "").trim();
  }
  return "";
}

export function ProjectManagementPage() {
  const queryClient = useQueryClient();
  const [request, setRequest] = useState<ProjectManagementRequest>(defaultRequest);
  const [configPath, setConfigPath] = useState("");
  const [configSource, setConfigSource] = useState<"" | "current_generated" | "manual">("");
  const [previewResult, setPreviewResult] = useState<ChineseResult | undefined>();
  const [generateResult, setGenerateResult] = useState<TaskResponse | undefined>();
  const [executePreviewResult, setExecutePreviewResult] = useState<ChineseResult | undefined>();
  const [executeResult, setExecuteResult] = useState<TaskResponse | undefined>();
  const executeRequest = { project_update_path: configPath, config_source: configSource };
  const generateTaskId = generateResult?.task?.task_id ?? "";
  const executeTaskId = executeResult?.task?.task_id ?? "";
  const activeTaskId = executeTaskId || generateTaskId;
  const currentStep = executeResult ? 3 : executePreviewResult ? 2 : previewResult || generateResult ? 1 : 0;
  const generateTaskDetail = useQuery({
    queryKey: ["tasks", generateTaskId],
    queryFn: () => apiGet<TaskDetailResponse>(`/tasks/${generateTaskId}`),
    enabled: Boolean(generateTaskId),
    refetchInterval: 3000,
  });
  const executeTaskDetail = useQuery({
    queryKey: ["tasks", executeTaskId],
    queryFn: () => apiGet<TaskDetailResponse>(`/tasks/${executeTaskId}`),
    enabled: Boolean(executeTaskId),
    refetchInterval: 3000,
  });
  const canGenerate = previewResult?.summary.status === "planned";
  const canReadConfig = Boolean(configPath.trim());
  const canExecuteCurrentConfig = configSource === "current_generated";

  useEffect(() => {
    const generatedConfigPath = projectUpdatePathFromTask(generateTaskDetail.data);
    if (generatedConfigPath && generatedConfigPath !== configPath) {
      setConfigPath(generatedConfigPath);
      setConfigSource("current_generated");
      setExecutePreviewResult(undefined);
      setExecuteResult(undefined);
    }
  }, [generateTaskDetail.data, configPath]);

  useEffect(() => {
    setPreviewResult(undefined);
    setGenerateResult(undefined);
    setExecutePreviewResult(undefined);
    setExecuteResult(undefined);
    setConfigPath("");
    setConfigSource("");
  }, [request]);

  const preview = useMutation({
    mutationFn: () => apiPost<ChineseResult>("/project-management/config/preview", request),
    onSuccess: (result) => {
      setPreviewResult(result);
      setGenerateResult(undefined);
      setExecutePreviewResult(undefined);
      setExecuteResult(undefined);
      setConfigPath("");
      setConfigSource("");
    },
  });
  const generate = useMutation({
    mutationFn: () => apiPost<TaskResponse>("/project-management/config/generate", request),
    onSuccess: async (result) => {
      setGenerateResult(result);
      setExecutePreviewResult(undefined);
      setExecuteResult(undefined);
      setConfigPath(request.output_path);
      setConfigSource("current_generated");
      await queryClient.invalidateQueries({ queryKey: ["tasks"] });
      antdMessage.success("项目动作配置正在生成，本页会显示进度");
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

  function updateMetricFilter(index: number, patch: Partial<MetricFilter>) {
    const metricFilters = request.metric_filters.map((item, itemIndex) => (itemIndex === index ? { ...item, ...patch } : item));
    setRequest({ ...request, metric_filters: metricFilters });
  }

  function addMetricFilter() {
    setRequest({ ...request, metric_filters: [...request.metric_filters, { field: "", op: "", value: "" }] });
  }

  function removeMetricFilter(index: number) {
    const next = request.metric_filters.filter((_item, itemIndex) => itemIndex !== index);
    setRequest({ ...request, metric_filters: next.length ? next : [{ field: "", op: "", value: "" }] });
  }

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
                    allowClear
                    value={request.action_type || undefined}
                    onChange={(value) => setRequest({ ...request, action_type: value ?? "" })}
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
                    allowClear
                    value={request.spend_window || undefined}
                    onChange={(value) => setRequest({ ...request, spend_window: value ?? "" })}
                    options={[
                      { label: "今天", value: "today" },
                      { label: "昨天", value: "yesterday" },
                      { label: "近 3 天", value: "last_3_days" },
                    ]}
                  />
                </Form.Item>
              </Col>
              <Col xs={24}>
                <Form.Item label="筛选条件（且）">
                  <Space direction="vertical" size="small" className="full-width">
                    {request.metric_filters.map((filter, index) => (
                      <Row gutter={[12, 8]} key={`metric-filter-${index}`}>
                        <Col xs={24} lg={8}>
                          <Select
                            allowClear
                            className="full-width"
                            value={filter.field || undefined}
                            onChange={(value) => updateMetricFilter(index, { field: value ?? "" })}
                            options={[
                              { label: "消耗", value: "stat_cost" },
                              { label: "注册数", value: "active_register" },
                              { label: "注册成本", value: "register_cost" },
                              { label: "计费时间转化数", value: "billing_convert_cnt" },
                              { label: "计费时间转化成本", value: "billing_conversion_cost" },
                              { label: "计费当日付费 ROI", value: "billing_1day_pay_roi" },
                            ]}
                            placeholder="选择指标"
                          />
                        </Col>
                        <Col xs={24} lg={6}>
                          <Select
                            allowClear
                            className="full-width"
                            value={filter.op || undefined}
                            onChange={(value) => updateMetricFilter(index, { op: value ?? "" })}
                            options={[
                              { label: "小于", value: "lt" },
                              { label: "小于等于", value: "lte" },
                              { label: "大于", value: "gt" },
                              { label: "大于等于", value: "gte" },
                              { label: "等于", value: "eq" },
                            ]}
                            placeholder="比较符"
                          />
                        </Col>
                        <Col xs={18} lg={6}>
                          <Input
                            value={filter.value}
                            onChange={(event) => updateMetricFilter(index, { value: event.target.value })}
                            placeholder={index === 0 ? "例如 500" : "例如 0"}
                          />
                        </Col>
                        <Col xs={6} lg={4}>
                          <Button icon={<DeleteOutlined />} disabled={request.metric_filters.length <= 1} onClick={() => removeMetricFilter(index)}>
                            删除
                          </Button>
                        </Col>
                      </Row>
                    ))}
                    <Button icon={<PlusOutlined />} onClick={addMetricFilter}>
                      增加且条件
                    </Button>
                  </Space>
                </Form.Item>
              </Col>
              {request.action_type === "status_update" ? (
                <Col xs={24} lg={8}>
                  <Form.Item label="目标状态">
                    <Select
                      allowClear
                      value={request.opt_status || undefined}
                      onChange={(value) => setRequest({ ...request, opt_status: value ?? "" })}
                      options={[
                        { label: "关闭", value: "DISABLE" },
                        { label: "开启", value: "ENABLE" },
                      ]}
                      placeholder="请选择目标状态"
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
                  <Button disabled={!canGenerate} onClick={() => generate.mutate()} loading={generate.isPending}>
                    生成本次动作配置
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
              message="这里不会重新筛选项目；主路径只执行本页刚生成的新配置，避免误拿历史 JSON 执行。"
            />
            {configSource === "current_generated" ? (
              <Alert type="success" showIcon message="当前配置来源：本页刚生成的新配置" description={configPath} />
            ) : configSource === "manual" ? (
              <Alert
                type="warning"
                showIcon
                message="当前配置来源：手动指定的历史配置"
                description="手动指定配置只用于高级核对；本页不会直接执行历史配置。要真实执行，请回到第一步重新生成本次动作配置。"
              />
            ) : (
              <Alert type="info" showIcon message="当前还没有可执行配置；请先在第一步生成本次动作配置。" />
            )}
            <Collapse
              className="advanced-fields"
              items={[
                {
                  key: "manual-config",
                  label: "高级信息：手动查看历史项目管理 JSON",
                  children: (
                    <Input
                      value={configPath}
                      onChange={(event) => {
                        const nextPath = event.target.value;
                        setConfigPath(nextPath);
                        setConfigSource(nextPath.trim() ? "manual" : "");
                        setExecutePreviewResult(undefined);
                        setExecuteResult(undefined);
                      }}
                      placeholder="例如 configs/project-updates/xxx.local.json；历史配置只用于核对"
                    />
                  ),
                },
              ]}
            />
            <Button icon={<FileSearchOutlined />} disabled={!canReadConfig} onClick={() => executePreview.mutate()} loading={executePreview.isPending}>
              {canExecuteCurrentConfig ? "核对本次执行明细" : "查看手动配置明细"}
            </Button>
            {executePreview.error ? <Alert type="error" showIcon message={(executePreview.error as Error).message} /> : null}
            <SummaryPanel
              result={executePreviewResult}
              loading={executePreview.isPending}
              detailsCollapsed
              showArtifactPath={false}
              showRawJson={false}
              footer={
                executePreviewResult?.summary.execution_enabled && canExecuteCurrentConfig ? (
                  <ConfirmExecutePanel
                    buttonText="确认并执行项目动作"
                    disabled={execute.isPending}
                    onConfirm={() => execute.mutate()}
                  />
                ) : executePreviewResult?.summary.execution_enabled && configSource === "manual" ? (
                  <Alert
                    type="warning"
                    showIcon
                    message="手动指定的历史配置不能在本页直接执行；请重新生成本次动作配置后再确认执行。"
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
          detail={executeTaskDetail.data ?? generateTaskDetail.data}
          loading={executeTaskDetail.isFetching || generateTaskDetail.isFetching || generate.isPending || execute.isPending}
        />
      </Space>
    </main>
  );
}
