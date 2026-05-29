import { DownloadOutlined, FileSearchOutlined, SaveOutlined, UploadOutlined } from "@ant-design/icons";
import { Alert, Button, Card, Checkbox, Col, Form, Input, Row, Select, Space, Typography, Upload, message as antdMessage } from "antd";
import type { UploadFile } from "antd";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import { apiGet, apiPost, apiUpload, apiUrl } from "../api/client";
import { SummaryPanel } from "../components/SummaryPanel";
import type { ChineseResult } from "../types/api";

type ProductAutomationForm = {
  product_key: string;
  product: string;
  platform: string;
  source_advertiser_name: string;
  source_advertiser_id: string;
  organization_id: string;
  allowed_target_accounts_path: string;
  account_name_keyword: string;
  account_remark_equals: string;
  enabled_jobs: string[];
  config_path?: string;
};

type JobOption = {
  value: string;
  label: string;
  description: string;
};

type DryRunRequest = {
  product_key: string;
  job: string;
  target_date: string;
};

const emptyForm: ProductAutomationForm = {
  product_key: "",
  product: "",
  platform: "WECHAT_GAME",
  source_advertiser_name: "",
  source_advertiser_id: "",
  organization_id: "",
  allowed_target_accounts_path: "",
  account_name_keyword: "",
  account_remark_equals: "",
  enabled_jobs: [],
};

const emptyDryRun: DryRunRequest = {
  product_key: "",
  job: "",
  target_date: "yesterday",
};

export function ProductAutomationPage() {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<ProductAutomationForm>(emptyForm);
  const [selectedProductKey, setSelectedProductKey] = useState("");
  const [dryRunRequest, setDryRunRequest] = useState<DryRunRequest>(emptyDryRun);
  const [allowedFileList, setAllowedFileList] = useState<UploadFile[]>([]);
  const [allowedImportResult, setAllowedImportResult] = useState<ChineseResult | undefined>();
  const [saveResult, setSaveResult] = useState<ChineseResult | undefined>();
  const [dryRunResult, setDryRunResult] = useState<ChineseResult | undefined>();
  const overview = useQuery({
    queryKey: ["product-automation", "overview"],
    queryFn: () => apiGet<ChineseResult>("/product-automation/overview"),
  });
  const products = useMemo(() => productFormsFromOverview(overview.data), [overview.data]);
  const jobs = useMemo(() => jobOptionsFromOverview(overview.data), [overview.data]);
  const productOptions = products.map((product) => ({ label: `${product.product}（${product.product_key}）`, value: product.product_key }));
  const jobOptions = jobs.map((job) => ({ label: job.label, value: job.value }));
  const templateReady = Boolean(form.product.trim() && form.product_key.trim());
  const selectedAllowedFile = Boolean(allowedFileList[0]?.originFileObj);

  useEffect(() => {
    if (!selectedProductKey) {
      return;
    }
    const product = products.find((item) => item.product_key === selectedProductKey);
    if (product) {
      setForm(product);
      setDryRunRequest((current) => ({ ...current, product_key: product.product_key }));
    }
  }, [products, selectedProductKey]);

  const save = useMutation({
    mutationFn: () => apiPost<ChineseResult>("/product-automation/config/save", form),
    onSuccess: async (result) => {
      setSaveResult(result);
      await queryClient.invalidateQueries({ queryKey: ["product-automation", "overview"] });
      antdMessage.success("产品配置已保存");
    },
  });
  const importAllowedAccounts = useMutation({
    mutationFn: () =>
      apiUpload<ChineseResult>(allowedAccountsImportPath(form), allowedFileList[0].originFileObj as File),
    onSuccess: async (result) => {
      setAllowedImportResult(result);
      const nextPath = typeof result.raw.allowed_target_accounts_path === "string" ? result.raw.allowed_target_accounts_path : "";
      if (nextPath && !result.summary.blocking_reasons.length) {
        setForm((current) => ({ ...current, allowed_target_accounts_path: nextPath }));
        antdMessage.success("允许创建账户名单已生成");
        await queryClient.invalidateQueries({ queryKey: ["product-automation", "overview"] });
        return;
      }
      antdMessage.warning("账户名单没有写入，请查看页面上的问题说明");
    },
  });
  const dryRun = useMutation({
    mutationFn: () => apiPost<ChineseResult>("/product-automation/dry-run", dryRunRequest),
    onSuccess: (result) => {
      setDryRunResult(result);
      antdMessage.success("预演 JSON 已生成，没有执行真实业务动作");
    },
  });

  function updateForm(patch: Partial<ProductAutomationForm>) {
    setForm((current) => ({ ...current, ...patch }));
    setSaveResult(undefined);
  }

  function updateJobs(values: Array<string | number | boolean>) {
    updateForm({ enabled_jobs: values.map((value) => String(value)) });
  }

  return (
    <main className="page">
      <Space direction="vertical" size="large" className="full-width">
        <Typography.Title level={2}>产品自动化配置</Typography.Title>
        <Alert
          type="info"
          showIcon
          message="这里只维护产品配置和生成预演 JSON；真实同步、补材和预推送仍由固定定时脚本执行。"
          description="新产品默认沿用点点英雄逻辑：源素材预推送目标账户来自允许创建账户名单，不使用最近巡检结果文件。"
        />

        {overview.error ? <Alert type="error" showIcon message={(overview.error as Error).message} /> : null}
        <SummaryPanel result={overview.data} loading={overview.isLoading} detailsCollapsed showArtifactPath={false} showRawJson={false} />

        <Card size="small" title="产品配置">
          <Space direction="vertical" size="middle" className="full-width">
            <Form layout="vertical" className="filter-bar">
              <Row gutter={[16, 0]}>
                <Col xs={24} lg={8}>
                  <Form.Item label="读取已有产品">
                    <Select
                      allowClear
                      value={selectedProductKey || undefined}
                      onChange={(value) => {
                        setSelectedProductKey(value ?? "");
                        if (!value) {
                          setForm(emptyForm);
                          setSaveResult(undefined);
                        }
                      }}
                      options={productOptions}
                      placeholder="选择已有产品，或直接填写新产品"
                    />
                  </Form.Item>
                </Col>
                <Col xs={24} lg={8}>
                  <Form.Item label="产品名">
                    <Input value={form.product} onChange={(event) => updateForm({ product: event.target.value })} />
                  </Form.Item>
                </Col>
                <Col xs={24} lg={8}>
                  <Form.Item label="产品 Key（产品唯一键）">
                    <Input value={form.product_key} onChange={(event) => updateForm({ product_key: event.target.value })} />
                  </Form.Item>
                </Col>
                <Col xs={24} lg={8}>
                  <Form.Item label="源素材账户名">
                    <Input value={form.source_advertiser_name} onChange={(event) => updateForm({ source_advertiser_name: event.target.value })} />
                  </Form.Item>
                </Col>
                <Col xs={24} lg={8}>
                  <Form.Item label="源素材账户 ID">
                    <Input value={form.source_advertiser_id} onChange={(event) => updateForm({ source_advertiser_id: event.target.value })} />
                  </Form.Item>
                </Col>
                <Col xs={24} lg={8}>
                  <Form.Item label="组织 ID">
                    <Input value={form.organization_id} onChange={(event) => updateForm({ organization_id: event.target.value })} />
                  </Form.Item>
                </Col>
                <Col xs={24} lg={12}>
                  <Form.Item label="允许创建账户名单文件路径">
                    <Space.Compact className="full-width">
                      <Input
                        value={form.allowed_target_accounts_path}
                        onChange={(event) => updateForm({ allowed_target_accounts_path: event.target.value })}
                        placeholder="上传账户表后自动生成，例如 configs/allowed-create-accounts.xxx.local.json"
                      />
                      <Button
                        icon={<DownloadOutlined />}
                        disabled={!templateReady}
                        href={templateReady ? apiUrl(allowedAccountsTemplatePath(form)) : undefined}
                      >
                        下载模板
                      </Button>
                    </Space.Compact>
                    <Space wrap className="allowed-account-tools">
                      <Upload
                        accept=".xlsx,.csv,.txt"
                        beforeUpload={() => false}
                        maxCount={1}
                        fileList={allowedFileList}
                        onChange={({ fileList: nextFileList }) => {
                          setAllowedFileList(nextFileList);
                          setAllowedImportResult(undefined);
                        }}
                      >
                        <Button icon={<UploadOutlined />}>选择账户表格</Button>
                      </Upload>
                      <Button
                        type="primary"
                        disabled={!templateReady || !selectedAllowedFile}
                        loading={importAllowedAccounts.isPending}
                        onClick={() => importAllowedAccounts.mutate()}
                      >
                        上传并生成名单
                      </Button>
                    </Space>
                    <Typography.Text type="secondary" className="allowed-account-help">
                      先填产品名和产品 Key，再下载模板；上传后只写本地 JSON，并回填路径，点保存配置后生效。
                    </Typography.Text>
                  </Form.Item>
                </Col>
                <Col xs={24} lg={6}>
                  <Form.Item label="账户发现关键词">
                    <Input value={form.account_name_keyword} onChange={(event) => updateForm({ account_name_keyword: event.target.value })} />
                  </Form.Item>
                </Col>
                <Col xs={24} lg={6}>
                  <Form.Item label="账户备注匹配">
                    <Input value={form.account_remark_equals} onChange={(event) => updateForm({ account_remark_equals: event.target.value })} />
                  </Form.Item>
                </Col>
                <Col xs={24}>
                  <Form.Item label="启用定时任务">
                    <Checkbox.Group value={form.enabled_jobs} onChange={updateJobs}>
                      <Row gutter={[16, 8]}>
                        {jobs.map((job) => (
                          <Col xs={24} md={12} xl={8} key={job.value}>
                            <Checkbox value={job.value}>{job.label}</Checkbox>
                            <Typography.Text type="secondary" className="job-help">
                              {job.description}
                            </Typography.Text>
                          </Col>
                        ))}
                      </Row>
                    </Checkbox.Group>
                  </Form.Item>
                </Col>
                <Col xs={24}>
                  <Alert
                    type="warning"
                    showIcon
                    message="源素材预推送默认目标：允许创建账户名单。保存配置不会执行预推送。"
                  />
                </Col>
              </Row>
            </Form>
            <Space wrap className="workflow-actions">
              <Button icon={<SaveOutlined />} type="primary" onClick={() => save.mutate()} loading={save.isPending}>
                保存配置
              </Button>
            </Space>
            {save.error ? <Alert type="error" showIcon message={(save.error as Error).message} /> : null}
            {importAllowedAccounts.error ? <Alert type="error" showIcon message={(importAllowedAccounts.error as Error).message} /> : null}
            <SummaryPanel
              result={allowedImportResult}
              loading={importAllowedAccounts.isPending}
              detailsCollapsed
              showArtifactPath={false}
              showRawJson={false}
            />
            <SummaryPanel result={saveResult} loading={save.isPending} detailsCollapsed showArtifactPath={false} showRawJson={false} />
          </Space>
        </Card>

        <Card size="small" title="生成预演">
          <Space direction="vertical" size="middle" className="full-width">
            <Alert type="info" showIcon message="预演只生成请求 JSON 和脚本命令，不执行真实同步、补材或预推送。" />
            <Form layout="vertical" className="filter-bar">
              <Row gutter={[16, 0]}>
                <Col xs={24} lg={8}>
                  <Form.Item label="产品">
                    <Select
                      allowClear
                      value={dryRunRequest.product_key || undefined}
                      onChange={(value) => setDryRunRequest({ ...dryRunRequest, product_key: value ?? "" })}
                      options={productOptions}
                    />
                  </Form.Item>
                </Col>
                <Col xs={24} lg={8}>
                  <Form.Item label="任务">
                    <Select
                      allowClear
                      value={dryRunRequest.job || undefined}
                      onChange={(value) => setDryRunRequest({ ...dryRunRequest, job: value ?? "" })}
                      options={jobOptions}
                    />
                  </Form.Item>
                </Col>
                <Col xs={24} lg={8}>
                  <Form.Item label="目标日期">
                    <Select
                      value={dryRunRequest.target_date}
                      onChange={(value) => setDryRunRequest({ ...dryRunRequest, target_date: value })}
                      options={[
                        { label: "昨天", value: "yesterday" },
                        { label: "今天", value: "today" },
                      ]}
                    />
                  </Form.Item>
                </Col>
              </Row>
            </Form>
            <Space wrap className="workflow-actions">
              <Button icon={<FileSearchOutlined />} onClick={() => dryRun.mutate()} loading={dryRun.isPending}>
                生成预演
              </Button>
            </Space>
            {dryRun.error ? <Alert type="error" showIcon message={(dryRun.error as Error).message} /> : null}
            <SummaryPanel result={dryRunResult} loading={dryRun.isPending} detailsCollapsed showArtifactPath={false} showRawJson={false} />
          </Space>
        </Card>
      </Space>
    </main>
  );
}

function productFormsFromOverview(result?: ChineseResult): ProductAutomationForm[] {
  const products = result?.raw?.products;
  if (!Array.isArray(products)) {
    return [];
  }
  return products
    .filter((item): item is Record<string, unknown> => typeof item === "object" && item !== null)
    .map((item) => ({
      product_key: String(item.product_key ?? ""),
      product: String(item.product ?? ""),
      platform: String(item.platform ?? "WECHAT_GAME"),
      source_advertiser_name: String(item.source_advertiser_name ?? ""),
      source_advertiser_id: String(item.source_advertiser_id ?? ""),
      organization_id: String(item.organization_id ?? ""),
      allowed_target_accounts_path: String(item.allowed_target_accounts_path ?? ""),
      account_name_keyword: String(item.account_name_keyword ?? ""),
      account_remark_equals: String(item.account_remark_equals ?? ""),
      enabled_jobs: Array.isArray(item.enabled_jobs) ? item.enabled_jobs.map((value) => String(value)) : [],
      config_path: String(item.config_path ?? ""),
    }));
}

function jobOptionsFromOverview(result?: ChineseResult): JobOption[] {
  const jobs = result?.raw?.jobs;
  if (!Array.isArray(jobs)) {
    return [];
  }
  return jobs
    .filter((item): item is Record<string, unknown> => typeof item === "object" && item !== null)
    .map((item) => ({
      value: String(item.value ?? ""),
      label: String(item.label ?? item.value ?? ""),
      description: String(item.description ?? ""),
    }))
    .filter((item) => item.value);
}

function allowedAccountsTemplatePath(form: ProductAutomationForm): string {
  return `/product-automation/allowed-accounts/template?${productContextParams(form).toString()}`;
}

function allowedAccountsImportPath(form: ProductAutomationForm): string {
  return `/product-automation/allowed-accounts/import?${productContextParams(form).toString()}`;
}

function productContextParams(form: ProductAutomationForm): URLSearchParams {
  const params = new URLSearchParams();
  params.set("product", form.product.trim());
  params.set("product_key", form.product_key.trim());
  params.set("platform", form.platform.trim() || "WECHAT_GAME");
  return params;
}
