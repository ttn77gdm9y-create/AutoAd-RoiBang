import { FileSearchOutlined, HistoryOutlined } from "@ant-design/icons";
import { Alert, Button, Card, Col, Collapse, Form, Input, Modal, Row, Select, Space, Typography, message as antdMessage } from "antd";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import { apiGet, apiPost } from "../api/client";
import { ConfirmExecutePanel } from "../components/ConfirmExecutePanel";
import { SummaryPanel } from "../components/SummaryPanel";
import { InlineTaskStatus, WorkflowSteps } from "../components/WorkflowScaffold";
import type { ChineseResult, TaskDetailResponse } from "../types/api";

type CreatePlanRequest = {
  mode: string;
  advertiser_ids: string;
  owner: string;
  product_key: string;
  product_name: string;
  target_date: string;
  template_catalog: string;
  cpa_bid: string;
  roi_coefficient: string;
};

type TaskResponse = ChineseResult & {
  task?: {
    task_id: string;
    artifact_path: string;
    pid: number;
  };
};

const defaultRequest: CreatePlanRequest = {
  mode: "wx_pay_male_random_materials",
  advertiser_ids: "",
  owner: "郭靖",
  product_key: "",
  product_name: "",
  target_date: "",
  template_catalog: "configs/create-templates/wx-mini-game.json",
  cpa_bid: "",
  roi_coefficient: "",
};

const createModeOptions = [
  { label: "每付男素材不限", value: "wx_pay_male_random_materials" },
  { label: "每付通投素材不限", value: "wx_pay_general_random_materials" },
  { label: "每付男测新", value: "wx_pay_male_test_new" },
  { label: "每付通投测新", value: "wx_pay_general_test_new" },
  { label: "每付男近期放量", value: "wx_pay_male_recent_scale" },
  { label: "每付通投近期放量", value: "wx_pay_general_recent_scale" },
  { label: "每付男历史放量", value: "wx_pay_male_scale" },
  { label: "每付通投历史放量", value: "wx_pay_general_scale" },
  { label: "7R 男近期放量", value: "wx_7r_male_recent_scale" },
  { label: "7R 通投近期放量", value: "wx_7r_general_recent_scale" },
];

function is7rMode(mode: string) {
  return mode.toLowerCase().includes("7r");
}

function planIdFromPath(planPath: string): string {
  const fileName = planPath.split(/[\\/]/).pop() ?? "manual";
  return encodeURIComponent(fileName.replace(/\.[^.]+$/, "") || "manual");
}

function planPathFromTask(detail?: TaskDetailResponse): string {
  const artifactPath = String(detail?.artifact_path ?? "").trim();
  if (artifactPath.includes("data/runs/create_mode/")) {
    return artifactPath;
  }
  const result = detail?.raw?.result;
  if (result && typeof result === "object" && "artifact_path" in result) {
    const value = String((result as { artifact_path?: unknown }).artifact_path ?? "").trim();
    if (value.includes("data/runs/create_mode/")) {
      return value;
    }
  }
  return "";
}

function existingPlanBlockFromResult(result?: ChineseResult): { reason: string; countsText: string } | undefined {
  const reason = result?.summary.blocking_reasons.find(
    (item) => item.includes("已有创建记录") || item.includes("existing active project/unit provider IDs"),
  );
  const ledger = ledgerFromResult(result);
  if (!reason && !ledger) {
    return undefined;
  }
  return {
    reason: reason || "这个创建计划已有创建记录，系统已阻止重复执行。",
    countsText: countsTextFromLedger(ledger),
  };
}

function ledgerFromResult(result?: ChineseResult): Record<string, unknown> | undefined {
  const raw = result?.raw;
  const candidates = [
    raw,
    asRecord(raw?.result),
    asRecord(raw?.result_artifact),
    asRecord(asRecord(raw?.task)?.result),
  ];
  for (const candidate of candidates) {
    const ledger = asRecord(candidate?.existing_plan_ledger);
    if (ledger) {
      return ledger;
    }
  }
  return undefined;
}

function countsTextFromLedger(ledger?: Record<string, unknown>): string {
  const byEntityType = asRecord(ledger?.by_entity_type);
  const projectCount = Number(byEntityType?.project ?? 0);
  const unitCount = Number(byEntityType?.promotion ?? 0);
  const parts = [];
  if (projectCount > 0) {
    parts.push(`项目 ${projectCount} 个`);
  }
  if (unitCount > 0) {
    parts.push(`单元 ${unitCount} 个`);
  }
  if (parts.length) {
    return parts.join("、");
  }
  const total = Number(ledger?.count ?? 0);
  return total > 0 ? `记录 ${total} 条` : "";
}

function asRecord(value: unknown): Record<string, unknown> | undefined {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : undefined;
}

export function CreatePlansPage() {
  const queryClient = useQueryClient();
  const [request, setRequest] = useState<CreatePlanRequest>(defaultRequest);
  const [planPath, setPlanPath] = useState("");
  const [previewResult, setPreviewResult] = useState<ChineseResult | undefined>();
  const [generateResult, setGenerateResult] = useState<TaskResponse | undefined>();
  const [executePreviewResult, setExecutePreviewResult] = useState<ChineseResult | undefined>();
  const [executeResult, setExecuteResult] = useState<TaskResponse | undefined>();
  const [templateDetailOpen, setTemplateDetailOpen] = useState(false);
  const generateTaskId = generateResult?.task?.task_id ?? "";
  const executeTaskId = executeResult?.task?.task_id ?? "";
  const activeTaskId = executeTaskId || generateTaskId;
  const currentStep = executeResult ? 3 : executePreviewResult ? 2 : previewResult || generateResult ? 1 : 0;
  const executePath = useMemo(() => `/create-plans/${planIdFromPath(planPath)}/execute`, [planPath]);
  const executeRequest = { plan_path: planPath };
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
  const productsQuery = useQuery({
    queryKey: ["accounts", "create-plan", "products"],
    queryFn: () => apiGet<ChineseResult>("/accounts?status=active"),
  });
  const accountsQuery = useQuery({
    queryKey: ["accounts", "create-plan", request.product_key],
    queryFn: () => apiGet<ChineseResult>(`/accounts?product_key=${encodeURIComponent(request.product_key)}&status=active`),
    enabled: Boolean(request.product_key.trim()),
  });
  const templatesQuery = useQuery({
    queryKey: ["create-plans", "templates"],
    queryFn: () => apiGet<ChineseResult>("/create-plans/templates"),
  });
  const templateDetailQuery = useQuery({
    queryKey: ["create-plans", "template-detail", request.template_catalog],
    queryFn: () => apiGet<ChineseResult>(`/create-plans/template-detail?path=${encodeURIComponent(request.template_catalog)}`),
    enabled: templateDetailOpen && Boolean(request.template_catalog.trim()),
  });
  const accountRows = accountsQuery.data?.table.rows ?? [];
  const accountIdsFromProduct = accountRows.map((row) => String(row["账户 ID"] ?? "")).filter(Boolean);
  const templateOptions = useMemo(
    () =>
      (templatesQuery.data?.table.rows ?? []).map((row) => ({
        label: String(row["模板"] ?? row["路径"] ?? ""),
        value: String(row["路径"] ?? ""),
        productName: String(row["产品"] ?? ""),
        productKey: String(row["产品 Key"] ?? ""),
      })),
    [templatesQuery.data],
  );
  const productOptions = useMemo(() => {
    const grouped = new Map<string, { productName: string; count: number }>();
    for (const row of productsQuery.data?.table.rows ?? []) {
      const productKey = String(row["产品 Key"] ?? "").trim();
      if (!productKey) {
        continue;
      }
      const productName = String(row["产品"] ?? productKey).trim();
      const item = grouped.get(productKey) ?? { productName, count: 0 };
      item.count += 1;
      grouped.set(productKey, item);
    }
    return [...grouped.entries()]
      .sort((left, right) => left[1].productName.localeCompare(right[1].productName, "zh-Hans-CN"))
      .map(([value, item]) => ({
        label: `${item.productName}（${item.count} 个启用账户）`,
        value,
        productName: item.productName,
      }));
  }, [productsQuery.data]);
  const is7rSelected = is7rMode(request.mode);
  const existingPlanBlock = useMemo(
    () => existingPlanBlockFromResult(executeTaskDetail.data ?? executeResult),
    [executeTaskDetail.data, executeResult],
  );

  useEffect(() => {
    const generatedPlanPath = planPathFromTask(generateTaskDetail.data);
    if (generatedPlanPath && generatedPlanPath !== planPath) {
      setPlanPath(generatedPlanPath);
      setExecutePreviewResult(undefined);
      setExecuteResult(undefined);
    }
  }, [generateTaskDetail.data, planPath]);

  useEffect(() => {
    setPreviewResult(undefined);
    setGenerateResult(undefined);
    setExecutePreviewResult(undefined);
    setExecuteResult(undefined);
    setPlanPath("");
  }, [request]);

  function matchingTemplatePath(productKey: string, productName: string): string | undefined {
    return templateOptions.find((option) => option.productKey === productKey || option.productName === productName)?.value;
  }

  const preview = useMutation({
    mutationFn: () => apiPost<ChineseResult>("/create-plans/preview", request),
    onSuccess: (result) => {
      setPreviewResult(result);
      setGenerateResult(undefined);
      setPlanPath("");
      setExecutePreviewResult(undefined);
      setExecuteResult(undefined);
    },
  });
  const generate = useMutation({
    mutationFn: () => apiPost<TaskResponse>("/create-plans/generate", request),
    onSuccess: async (result) => {
      setGenerateResult(result);
      setPlanPath("");
      setExecutePreviewResult(undefined);
      setExecuteResult(undefined);
      await queryClient.invalidateQueries({ queryKey: ["tasks"] });
      antdMessage.success("创建计划正在生成，本页会显示进度");
    },
  });
  const executePreview = useMutation({
    mutationFn: () => apiPost<ChineseResult>(`${executePath}/preview`, executeRequest),
    onSuccess: (result) => {
      setExecutePreviewResult(result);
      setExecuteResult(undefined);
    },
  });
  const latestExecutePreview = useMutation({
    mutationFn: async () => {
      const latest = await apiGet<ChineseResult>("/create-plans/latest");
      const latestPath = latest.artifact_path ?? "";
      if (!latestPath || latest.summary.status === "blocked") {
        return { planPath: latestPath, result: latest };
      }
      const result = await apiPost<ChineseResult>(`/create-plans/${planIdFromPath(latestPath)}/execute/preview`, {
        plan_path: latestPath,
      });
      return { planPath: latestPath, result };
    },
    onSuccess: ({ planPath: latestPath, result }) => {
      setPlanPath(latestPath);
      setExecutePreviewResult(result);
      setExecuteResult(undefined);
      if (result.summary.status === "ready") {
        antdMessage.success("已读取最近生成的创建计划，可以核对后确认执行");
      } else {
        antdMessage.warning("未找到可执行的最近创建计划");
      }
    },
  });
  const execute = useMutation({
    mutationFn: () => apiPost<TaskResponse>(executePath, { ...executeRequest, confirmation: "确认执行" }),
    onSuccess: async (result) => {
      setExecuteResult(result);
      await queryClient.invalidateQueries({ queryKey: ["tasks"] });
      antdMessage.success("真实创建任务已提交，本页会显示进度");
    },
  });
  const readPlanPending = executePreview.isPending || latestExecutePreview.isPending;
  function readPlanPreview() {
    if (planPath.trim()) {
      executePreview.mutate();
      return;
    }
    if (generateTaskId) {
      antdMessage.info("本次创建计划还在生成或刚生成完成，系统会自动读取本次计划；不要读取历史最近计划。");
      return;
    }
    latestExecutePreview.mutate();
  }

  return (
    <main className="page">
      <Space direction="vertical" size="large" className="full-width">
        <Typography.Title level={2}>创建计划</Typography.Title>
        <WorkflowSteps current={currentStep} />
        <Alert
          type="info"
          showIcon
          message="先检查要创建的账户和项目，再生成计划文件并确认创建；进度和结果会直接显示在本页。"
        />

        <Card size="small" title="第一步：填写并检查创建计划">
          <Form layout="vertical" className="filter-bar">
            <Row gutter={[16, 0]}>
              <Col xs={24} lg={8}>
                <Form.Item label="固定创建模式">
                  <Select
                    value={request.mode}
                    onChange={(value) => setRequest({ ...request, mode: value, roi_coefficient: is7rMode(value) ? request.roi_coefficient : "" })}
                    options={createModeOptions}
                  />
                </Form.Item>
              </Col>
              <Col xs={24} lg={8}>
                <Form.Item label="产品">
                  <Select
                    allowClear
                    showSearch
                    loading={productsQuery.isLoading}
                    optionFilterProp="label"
                    value={request.product_key || undefined}
                    onChange={(value, option) => {
                      const selected = Array.isArray(option) ? option[0] : option;
                      const nextProductKey = value ?? "";
                      const nextProductName = selected?.productName ?? "";
                      setRequest({
                        ...request,
                        product_key: nextProductKey,
                        product_name: nextProductName,
                        template_catalog: matchingTemplatePath(nextProductKey, nextProductName) ?? request.template_catalog,
                      });
                    }}
                    options={productOptions}
                    placeholder="选择产品；留空时手动填写账户 ID"
                  />
                </Form.Item>
              </Col>
              <Col xs={24} lg={8}>
                <Form.Item label="负责人">
                  <Input value={request.owner} onChange={(event) => setRequest({ ...request, owner: event.target.value })} />
                </Form.Item>
              </Col>
              <Col xs={24} lg={8}>
                <Form.Item label="目标日期">
                  <Input
                    value={request.target_date}
                    onChange={(event) => setRequest({ ...request, target_date: event.target.value })}
                    placeholder="可空，脚本默认今天"
                  />
                </Form.Item>
              </Col>
              <Col xs={24} lg={8}>
                <Form.Item label="本次项目出价">
                  <Input
                    value={request.cpa_bid}
                    onChange={(event) => setRequest({ ...request, cpa_bid: event.target.value })}
                    placeholder="可空"
                  />
                </Form.Item>
              </Col>
              <Col xs={24} lg={8}>
                <Form.Item label="本次 ROI 系数">
                  <Input
                    value={request.roi_coefficient}
                    disabled={!is7rSelected}
                    onChange={(event) => setRequest({ ...request, roi_coefficient: event.target.value })}
                    placeholder={is7rSelected ? "7R 项目可填写" : "非 7R 模式不可填写"}
                  />
                </Form.Item>
              </Col>
              <Col xs={24} lg={12}>
                <Form.Item label="创建模板">
                  <Space direction="vertical" size="small" className="full-width">
                    <Select
                      showSearch
                      loading={templatesQuery.isLoading}
                      optionFilterProp="label"
                      value={request.template_catalog || undefined}
                      onChange={(value) => setRequest({ ...request, template_catalog: value })}
                      options={templateOptions}
                      placeholder="选择模板；会写入下面的模板 JSON 路径"
                    />
                    <Button
                      icon={<FileSearchOutlined />}
                      disabled={!request.template_catalog.trim()}
                      onClick={() => setTemplateDetailOpen(true)}
                    >
                      查看模板内容
                    </Button>
                  </Space>
                </Form.Item>
              </Col>
              <Col xs={24}>
                <Collapse
                  className="advanced-fields"
                  items={[
                    {
                      key: "template-path",
                      label: "高级信息：手动指定模板 JSON 路径",
                      children: (
                        <Form.Item label="模板 JSON 路径">
                          <Input
                            value={request.template_catalog}
                            onChange={(event) => setRequest({ ...request, template_catalog: event.target.value })}
                          />
                        </Form.Item>
                      ),
                    },
                  ]}
                />
              </Col>
              <Col xs={24}>
                <Form.Item label="账户 ID">
                  <Input.TextArea
                    rows={5}
                    value={request.advertiser_ids}
                    onChange={(event) => setRequest({ ...request, advertiser_ids: event.target.value })}
                    placeholder="多个账户用换行或逗号分隔；留空时，后端会按所选产品自动使用产品账户库启用账户"
                  />
                </Form.Item>
                {request.product_key.trim() ? (
                  <Space direction="vertical" size="small">
                    <Alert
                      type="info"
                      showIcon
                      message="账户 ID 可留空：后端会自动使用该产品在产品账户库里的启用账户。"
                    />
                    <Space wrap>
                      <Button
                        disabled={!accountIdsFromProduct.length}
                        loading={accountsQuery.isLoading}
                        onClick={() => setRequest({ ...request, advertiser_ids: accountIdsFromProduct.join("\n") })}
                      >
                        填入该产品启用账户（可选）
                      </Button>
                      <Typography.Text type="secondary">
                        已从账户库读取 {accountIdsFromProduct.length} 个启用账户
                      </Typography.Text>
                    </Space>
                  </Space>
                ) : null}
                {productsQuery.error ? <Alert type="error" showIcon message={(productsQuery.error as Error).message} /> : null}
                {accountsQuery.error ? <Alert type="error" showIcon message={(accountsQuery.error as Error).message} /> : null}
                {templatesQuery.error ? <Alert type="error" showIcon message={(templatesQuery.error as Error).message} /> : null}
              </Col>
              <Col xs={24}>
                <Space wrap>
                  <Button icon={<FileSearchOutlined />} type="primary" onClick={() => preview.mutate()} loading={preview.isPending}>
                    检查创建计划
                  </Button>
                  <Button disabled={!previewResult} onClick={() => generate.mutate()} loading={generate.isPending}>
                    生成计划文件
                  </Button>
                </Space>
              </Col>
            </Row>
          </Form>
          {preview.error ? <Alert type="error" showIcon message={(preview.error as Error).message} /> : null}
          <SummaryPanel result={previewResult} loading={preview.isPending} detailsCollapsed showArtifactPath={false} showRawJson={false} />
          {generate.error ? <Alert type="error" showIcon message={(generate.error as Error).message} /> : null}
        </Card>

        <Card size="small" title="第二步：核对后真实创建">
          <Space direction="vertical" size="middle" className="full-width">
            <Alert
              type="info"
              showIcon
              message="这里不会重新生成计划；执行对象以第一步生成的账户、项目、单元、素材和文案为准。"
            />
            {existingPlanBlock ? (
              <Alert
                type="warning"
                showIcon
                message="这个计划已经执行过，刚才没有再次调用外部创建接口。"
                description={
                  <Space direction="vertical" size={4}>
                    <span>{existingPlanBlock.reason}</span>
                    {existingPlanBlock.countsText ? <span>已存在：{existingPlanBlock.countsText}</span> : null}
                    <span>要再新建一批，请回到第一步重新生成计划；系统不会让旧计划重复创建。</span>
                  </Space>
                }
              />
            ) : null}
            <Collapse
              className="advanced-fields"
              items={[
                {
                  key: "manual-plan",
                  label: "高级信息：手动指定计划文件",
                  children: (
                    <Space direction="vertical" size="middle" className="full-width">
                      <Input
                        value={planPath}
                        onChange={(event) => setPlanPath(event.target.value)}
                        placeholder="例如 data/runs/create_mode/xxx.json；留空时读取最近生成的计划"
                      />
                    </Space>
                  ),
                },
              ]}
            />
            <Button icon={planPath.trim() ? <FileSearchOutlined /> : <HistoryOutlined />} onClick={readPlanPreview} loading={readPlanPending}>
              检查创建明细
            </Button>
            {latestExecutePreview.error ? <Alert type="error" showIcon message={(latestExecutePreview.error as Error).message} /> : null}
            {executePreview.error ? <Alert type="error" showIcon message={(executePreview.error as Error).message} /> : null}
            <SummaryPanel
              result={executePreviewResult}
              loading={readPlanPending}
              detailsCollapsed
              showArtifactPath={false}
              showRawJson={false}
              footer={
                executePreviewResult?.summary.execution_enabled ? (
                  <ConfirmExecutePanel
                    buttonText="确认并创建"
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
          title="当前创建任务"
          taskId={activeTaskId}
          workflow={executeTaskId ? "create_live_execute_once" : "create_mode"}
          result={executeResult ?? generateResult}
          detail={executeTaskDetail.data ?? generateTaskDetail.data}
          loading={execute.isPending || generate.isPending || executeTaskDetail.isFetching || generateTaskDetail.isFetching}
          extra={
            existingPlanBlock ? (
              <Alert
                type="warning"
                showIcon
                message="本次任务被防重复保护拦截。要再新建一批，请回到第一步重新生成计划。"
              />
            ) : null
          }
        />
        <Modal
          title="固定模式模板内容"
          open={templateDetailOpen}
          width={980}
          footer={null}
          onCancel={() => setTemplateDetailOpen(false)}
        >
          {templateDetailQuery.error ? <Alert type="error" showIcon message={(templateDetailQuery.error as Error).message} /> : null}
          <SummaryPanel
            result={templateDetailQuery.data}
            loading={templateDetailQuery.isLoading}
            detailsCollapsed={false}
            showArtifactPath
            showRawJson
          />
        </Modal>
      </Space>
    </main>
  );
}
