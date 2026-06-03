import { FileSearchOutlined, SafetyCertificateOutlined } from "@ant-design/icons";
import { Alert, Button, Card, Col, Collapse, Form, Input, Modal, Row, Select, Space, Typography, message as antdMessage } from "antd";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { apiGet, apiPost } from "../api/client";
import { ConfirmExecutePanel } from "../components/ConfirmExecutePanel";
import { SummaryPanel } from "../components/SummaryPanel";
import { InlineTaskStatus, WorkflowSteps } from "../components/WorkflowScaffold";
import { EXECUTE_CONFIRMATION_PHRASE } from "../constants/safety";
import type { ChineseResult, TaskDetailResponse } from "../types/api";
import { isTaskActive, taskStatus } from "../utils/workflowState";

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
  mode: "",
  advertiser_ids: "",
  owner: "",
  product_key: "",
  product_name: "",
  target_date: "",
  template_catalog: "",
  cpa_bid: "",
  roi_coefficient: "",
};

const fallbackCreateModeOptions = [
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

function createPlanRequestFromSuggestionPreview(result?: ChineseResult): CreatePlanRequest | undefined {
  const request = asRecord(result?.raw?.create_plan_request);
  if (!request) {
    return undefined;
  }
  return {
    mode: String(request.mode ?? request.mode_key ?? ""),
    advertiser_ids: String(request.advertiser_ids ?? ""),
    owner: String(request.owner ?? ""),
    product_key: String(request.product_key ?? ""),
    product_name: String(request.product_name ?? request.product ?? ""),
    target_date: String(request.target_date ?? ""),
    template_catalog: String(request.template_catalog ?? request.template_catalog_path ?? ""),
    cpa_bid: String(request.cpa_bid ?? ""),
    roi_coefficient: String(request.roi_coefficient ?? ""),
  };
}

function generatePreviewFromSuggestionPreview(result?: ChineseResult): ChineseResult | undefined {
  const preview = asRecord(result?.raw?.generate_preview);
  if (!preview || !asRecord(preview.summary) || !asRecord(preview.table)) {
    return undefined;
  }
  return preview as unknown as ChineseResult;
}

function modeOptionsFromResult(result?: ChineseResult): Array<{ label: string; value: string }> {
  const rows = result?.table.rows ?? [];
  const options = rows
    .map((row) => {
      const modeKey = String(row["模式 Key"] ?? "").trim();
      if (!modeKey) {
        return undefined;
      }
      const name = String(row["创建模式"] ?? modeKey).trim();
      const source = String(row["来源"] ?? "").trim();
      const label = source === "产品专属" ? `${name}（产品专属）` : name;
      return { label, value: modeKey };
    })
    .filter((item): item is { label: string; value: string } => Boolean(item));
  return options.length ? options : fallbackCreateModeOptions;
}

export function CreatePlansPage() {
  const queryClient = useQueryClient();
  const [searchParams] = useSearchParams();
  const suggestionPreviewPath = searchParams.get("create_plan_preview_path") ?? "";
  const returnTo = searchParams.get("return_to") || "/suggestions";
  const skipNextRequestReset = useRef(false);
  const [request, setRequest] = useState<CreatePlanRequest>(defaultRequest);
  const [planPath, setPlanPath] = useState("");
  const [planSource, setPlanSource] = useState<"" | "current_generated" | "manual">("");
  const [previewResult, setPreviewResult] = useState<ChineseResult | undefined>();
  const [generateResult, setGenerateResult] = useState<TaskResponse | undefined>();
  const [executionReviewResult, setExecutionReviewResult] = useState<ChineseResult | undefined>();
  const [executePreviewResult, setExecutePreviewResult] = useState<ChineseResult | undefined>();
  const [executeResult, setExecuteResult] = useState<TaskResponse | undefined>();
  const [suggestionImportResult, setSuggestionImportResult] = useState<ChineseResult | undefined>();
  const [templateDetailOpen, setTemplateDetailOpen] = useState(false);
  const generateTaskId = generateResult?.task?.task_id ?? "";
  const executeTaskId = executeResult?.task?.task_id ?? "";
  const activeTaskId = executeTaskId || generateTaskId;
  const executionReviewStatus = executionReviewResult?.summary.status ?? "";
  const executionReviewPassed = executionReviewStatus === "ready_for_confirmation" || executionReviewStatus === "warning_only";
  const currentStep = executeResult ? 4 : executePreviewResult ? 3 : executionReviewResult ? 2 : previewResult || generateResult ? 1 : 0;
  const executePath = useMemo(() => `/create-plans/${planIdFromPath(planPath)}/execute`, [planPath]);
  const executeRequest = {
    plan_path: planPath,
    plan_source: planSource,
    source_suggestion_preview_path: suggestionPreviewPath,
    execution_review_artifact_path: executionReviewResult?.artifact_path ?? "",
    operator: request.owner,
  };
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
  const suggestionPreview = useQuery({
    queryKey: ["create-plans", "suggestion-preview", suggestionPreviewPath],
    queryFn: () => apiGet<ChineseResult>(`/create-plans/suggestion-preview?path=${encodeURIComponent(suggestionPreviewPath)}`),
    enabled: Boolean(suggestionPreviewPath),
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
  const modesQuery = useQuery({
    queryKey: ["create-plans", "modes", request.product_key],
    queryFn: () => apiGet<ChineseResult>(`/create-plans/modes?product_key=${encodeURIComponent(request.product_key)}`),
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
  const createModeOptions = useMemo(() => modeOptionsFromResult(modesQuery.data), [modesQuery.data]);
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
  const planGenerationStatus = taskStatus(generateTaskDetail.data, generateResult);
  const planGenerationActive = Boolean(generateTaskId) && isTaskActive(planGenerationStatus);
  const canGenerate = previewResult?.summary.status === "planned";
  const canReviewExecution = Boolean(planPath.trim()) && !planGenerationActive;
  const canReadPlan = Boolean(planPath.trim()) && !planGenerationActive && executionReviewPassed;
  const canExecuteCurrentPlan = planSource === "current_generated";
  const existingPlanBlock = useMemo(
    () => existingPlanBlockFromResult(executeTaskDetail.data ?? executeResult),
    [executeTaskDetail.data, executeResult],
  );

  useEffect(() => {
    const generatedPlanPath = planPathFromTask(generateTaskDetail.data);
    if (generatedPlanPath && generatedPlanPath !== planPath) {
      setPlanPath(generatedPlanPath);
      setPlanSource("current_generated");
      setExecutionReviewResult(undefined);
      setExecutePreviewResult(undefined);
      setExecuteResult(undefined);
    }
  }, [generateTaskDetail.data, planPath]);

  useEffect(() => {
    const importedRequest = createPlanRequestFromSuggestionPreview(suggestionPreview.data);
    if (!importedRequest) {
      return;
    }
    skipNextRequestReset.current = true;
    setRequest(importedRequest);
    setSuggestionImportResult(suggestionPreview.data);
    setPlanPath("");
    setPlanSource("");
    setPreviewResult(generatePreviewFromSuggestionPreview(suggestionPreview.data));
    setGenerateResult(undefined);
    setExecutionReviewResult(undefined);
    setExecutePreviewResult(undefined);
    setExecuteResult(undefined);
  }, [suggestionPreview.data]);

  useEffect(() => {
    if (skipNextRequestReset.current) {
      skipNextRequestReset.current = false;
      return;
    }
    setPreviewResult(undefined);
    setGenerateResult(undefined);
    setExecutionReviewResult(undefined);
    setExecutePreviewResult(undefined);
    setExecuteResult(undefined);
    setPlanPath("");
    setPlanSource("");
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
      setPlanSource("");
      setExecutionReviewResult(undefined);
      setExecutePreviewResult(undefined);
      setExecuteResult(undefined);
    },
  });
  const generate = useMutation({
    mutationFn: () => apiPost<TaskResponse>("/create-plans/generate", request),
    onSuccess: async (result) => {
      setGenerateResult(result);
      setPlanPath("");
      setPlanSource("");
      setExecutionReviewResult(undefined);
      setExecutePreviewResult(undefined);
      setExecuteResult(undefined);
      await queryClient.invalidateQueries({ queryKey: ["tasks"] });
      antdMessage.success("创建计划正在生成，本页会显示进度");
    },
  });
  const executionReview = useMutation({
    mutationFn: () =>
      apiPost<ChineseResult>("/create-plans/execution-review/preview", {
        ...executeRequest,
        review_config_path: "configs/create-plan-reviews/example.json",
      }),
    onSuccess: (result) => {
      setExecutionReviewResult(result);
      setExecutePreviewResult(undefined);
      setExecuteResult(undefined);
    },
  });
  const executePreview = useMutation({
    mutationFn: () => apiPost<ChineseResult>(`${executePath}/preview`, executeRequest),
    onSuccess: (result) => {
      setExecutePreviewResult(result);
      setExecuteResult(undefined);
    },
  });
  const execute = useMutation({
    mutationFn: () => apiPost<TaskResponse>(executePath, { ...executeRequest, confirmation: EXECUTE_CONFIRMATION_PHRASE }),
    onSuccess: async (result) => {
      setExecuteResult(result);
      await queryClient.invalidateQueries({ queryKey: ["tasks"] });
      antdMessage.success("真实创建任务已提交，本页会显示进度");
    },
  });
  const readPlanPending = executePreview.isPending;
  function readPlanPreview() {
    if (!executionReviewPassed) {
      antdMessage.warning("请先完成执行前复核；复核通过或仅有警告后，才能进入真实创建确认。");
      return;
    }
    if (planPath.trim()) {
      executePreview.mutate();
      return;
    }
    if (generateTaskId) {
      antdMessage.info("本次创建计划还在生成或刚生成完成，系统会自动读取本次计划；不要读取历史最近计划。");
      return;
    }
    antdMessage.warning("请先生成本次创建计划，或在高级信息里手动填写计划 JSON 路径。");
  }

  return (
    <main className="page">
      <Space direction="vertical" size="large" className="full-width">
        <Typography.Title level={2}>创建计划</Typography.Title>
        <WorkflowSteps current={currentStep} items={["配置", "生成计划", "执行前复核", "确认执行", "结果"]} />
        <Alert
          type="info"
          showIcon
          message="先检查要创建的账户和项目，再生成计划文件并确认创建；进度和结果会直接显示在本页。"
        />
        {suggestionPreview.error ? <Alert type="error" showIcon message={(suggestionPreview.error as Error).message} /> : null}
        {suggestionPreview.isLoading ? <Alert type="info" showIcon message="正在读取创建建议预览并填入表单。" /> : null}
        {suggestionPreviewPath ? (
          <Alert
            type="success"
            showIcon
            message="已接收投放建议工作台生成的创建计划预览"
            description="页面已填入建议里的创建参数；请继续生成本次计划，真实创建仍必须执行前复核并输入确认短语。"
            action={
              <Link to={returnTo}>
                <Button>返回投放建议工作台</Button>
              </Link>
            }
          />
        ) : null}
        {suggestionImportResult ? (
          <SummaryPanel result={suggestionImportResult} detailsCollapsed showArtifactPath showRawJson={false} />
        ) : null}

        <Card size="small" title="第一步：填写并检查创建计划">
          <Form layout="vertical" className="filter-bar">
            <Row gutter={[16, 0]}>
              <Col xs={24} lg={8}>
                <Form.Item label="固定创建模式">
                  <Select
                    allowClear
                    showSearch
                    loading={modesQuery.isLoading}
                    optionFilterProp="label"
                    value={request.mode || undefined}
                    onChange={(value) => {
                      const nextMode = value ?? "";
                      setRequest({ ...request, mode: nextMode, roi_coefficient: is7rMode(nextMode) ? request.roi_coefficient : "" });
                    }}
                    options={createModeOptions}
                    placeholder="请选择固定创建模式"
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
                    placeholder="选择产品后可一键填入该产品启用账户"
                  />
                </Form.Item>
              </Col>
              <Col xs={24} lg={8}>
                <Form.Item label="负责人">
                  <Input value={request.owner} onChange={(event) => setRequest({ ...request, owner: event.target.value })} placeholder="必须填写" />
                </Form.Item>
              </Col>
              <Col xs={24} lg={8}>
                <Form.Item label="计划日期">
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
                      placeholder="请选择固定模板"
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
                    placeholder="多个账户用换行或逗号分隔；必须明确填写本次账户"
                  />
                </Form.Item>
                {request.product_key.trim() ? (
                  <Space direction="vertical" size="small">
                    <Alert
                      type="info"
                      showIcon
                      message="账户不会由后端自动补齐；需要你点击按钮把产品账户库的启用账户填入本次账户 ID。"
                    />
                    <Space wrap>
                      <Button
                        disabled={!accountIdsFromProduct.length}
                        loading={accountsQuery.isLoading}
                        onClick={() => setRequest({ ...request, advertiser_ids: accountIdsFromProduct.join("\n") })}
                      >
                        使用该产品启用账户
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
                {modesQuery.error ? <Alert type="error" showIcon message={(modesQuery.error as Error).message} /> : null}
              </Col>
              <Col xs={24}>
                <Space wrap>
                  <Button icon={<FileSearchOutlined />} type="primary" onClick={() => preview.mutate()} loading={preview.isPending}>
                    检查创建计划
                  </Button>
                  <Button disabled={!canGenerate} onClick={() => generate.mutate()} loading={generate.isPending}>
                    生成本次计划
                  </Button>
                </Space>
              </Col>
            </Row>
          </Form>
          {preview.error ? <Alert type="error" showIcon message={(preview.error as Error).message} /> : null}
          <SummaryPanel result={previewResult} loading={preview.isPending} detailsCollapsed showArtifactPath={false} showRawJson={false} />
          {generate.error ? <Alert type="error" showIcon message={(generate.error as Error).message} /> : null}
        </Card>

        <Card size="small" title="第二步：执行前复核和真实创建">
          <Space direction="vertical" size="middle" className="full-width">
            <Alert
              type="info"
              showIcon
              message="这里不会重新生成计划；主路径只执行本页刚生成的新计划，避免误拿历史 artifact 创建。"
            />
            {planGenerationActive ? (
              <Alert type="info" showIcon message="创建计划正在生成，完成后再核对计划明细。" />
            ) : planSource === "current_generated" ? (
              <Alert
                type="success"
                showIcon
                message="当前计划来源：本页刚生成的新计划"
                description={planPath}
              />
            ) : planSource === "manual" ? (
              <Alert
                type="warning"
                showIcon
                message="当前计划来源：手动指定的历史计划"
                description="手动指定计划只用于高级核对；本页不会直接执行历史计划。要真实新建一批，请回到第一步重新生成本次计划。"
              />
            ) : (
              <Alert type="info" showIcon message="当前还没有可执行计划；请先在第一步生成本次计划。" />
            )}
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
                  label: "高级信息：手动查看历史计划文件",
                  children: (
                    <Space direction="vertical" size="middle" className="full-width">
                      <Input
                        value={planPath}
                        onChange={(event) => {
                          const nextPath = event.target.value;
                          setPlanPath(nextPath);
                          setPlanSource(nextPath.trim() ? "manual" : "");
                          setExecutionReviewResult(undefined);
                          setExecutePreviewResult(undefined);
                          setExecuteResult(undefined);
                        }}
                        placeholder="例如 data/runs/create_mode/xxx.json；历史计划只用于核对"
                      />
                    </Space>
                  ),
                },
              ]}
            />
            <Space wrap>
              <Button
                icon={<SafetyCertificateOutlined />}
                disabled={!canReviewExecution}
                onClick={() => executionReview.mutate()}
                loading={executionReview.isPending}
              >
                执行前复核
              </Button>
              <Button icon={<FileSearchOutlined />} disabled={!canReadPlan} onClick={readPlanPreview} loading={readPlanPending}>
                {planGenerationActive ? "等待计划生成完成" : canExecuteCurrentPlan ? "核对本次计划明细" : "查看手动计划明细"}
              </Button>
            </Space>
            {!executionReviewPassed && planPath.trim() && !planGenerationActive ? (
              <Alert type="info" showIcon message="必须先通过执行前复核，才会开放真实创建确认。" />
            ) : null}
            {executionReview.error ? <Alert type="error" showIcon message={(executionReview.error as Error).message} /> : null}
            <SummaryPanel
              result={executionReviewResult}
              loading={executionReview.isPending}
              detailsCollapsed
              showArtifactPath
              showRawJson={false}
            />
            {executePreview.error ? <Alert type="error" showIcon message={(executePreview.error as Error).message} /> : null}
            <SummaryPanel
              result={executePreviewResult}
              loading={readPlanPending}
              detailsCollapsed
              showArtifactPath={false}
              showRawJson={false}
              footer={
                executePreviewResult?.summary.execution_enabled && canExecuteCurrentPlan && executionReviewPassed ? (
                  <ConfirmExecutePanel
                    buttonText="确认并创建"
                    disabled={execute.isPending}
                    onConfirm={() => execute.mutate()}
                  />
                ) : executePreviewResult?.summary.execution_enabled && planSource === "manual" ? (
                  <Alert
                    type="warning"
                    showIcon
                    message="手动指定的历史计划不能在本页直接执行；请重新生成本次计划后再确认创建。"
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
