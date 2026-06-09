import { DownloadOutlined, FileSearchOutlined, SaveOutlined, UploadOutlined } from "@ant-design/icons";
import { Alert, Button, Card, Col, Form, Input, Row, Select, Space, Switch, Table, Tag, Typography, Upload, message as antdMessage } from "antd";
import type { UploadFile } from "antd";
import type { ColumnsType } from "antd/es/table";
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

type JobSwitchRow = JobOption & {
  enabled: boolean;
  type_label: string;
  type_color: string;
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
  const taskSwitchRows = jobs.map((job) => ({
    ...job,
    enabled: form.enabled_jobs.includes(job.value),
    ...jobTypeMeta(job.value),
  }));
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

  function updateJob(job: string, enabled: boolean) {
    const current = new Set(form.enabled_jobs);
    if (enabled) {
      current.add(job);
    } else {
      current.delete(job);
    }
    updateForm({ enabled_jobs: jobs.map((item) => item.value).filter((value) => current.has(value)) });
  }

  const taskSwitchColumns: ColumnsType<JobSwitchRow> = [
    {
      title: "任务",
      dataIndex: "label",
      width: 220,
      render: (value: string, record) => (
        <Space direction="vertical" size={2}>
          <Typography.Text strong>{value}</Typography.Text>
          <Typography.Text type="secondary" className="job-help">
            {record.description}
          </Typography.Text>
        </Space>
      ),
    },
    {
      title: "类型",
      dataIndex: "type_label",
      width: 130,
      render: (value: string, record) => <Tag color={record.type_color}>{value}</Tag>,
    },
    {
      title: "当前状态",
      dataIndex: "enabled",
      width: 120,
      render: (enabled: boolean) => <Tag color={enabled ? "green" : "default"}>{enabled ? "已开启" : "已关闭"}</Tag>,
    },
    {
      title: "开关",
      dataIndex: "enabled",
      width: 110,
      render: (enabled: boolean, record) => (
        <Switch checked={enabled} checkedChildren="开" unCheckedChildren="关" onChange={(checked) => updateJob(record.value, checked)} />
      ),
    },
  ];

  return (
    <main className="page">
      <Space direction="vertical" size="large" className="full-width">
        <Typography.Title level={2}>产品自动化配置</Typography.Title>
        <Alert
          type="info"
          showIcon
          message="这里只维护产品配置和生成任务请求 JSON；真实同步、补材和预推送仍由固定定时脚本执行。"
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
                  <Form.Item label="名单文件路径（上传后自动回填）">
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
                  <Form.Item label="定时任务开关">
                    <Table<JobSwitchRow>
                      size="small"
                      rowKey="value"
                      pagination={false}
                      columns={taskSwitchColumns}
                      dataSource={taskSwitchRows}
                      scroll={{ x: 680 }}
                    />
                    <Typography.Text type="secondary" className="allowed-account-help">
                      关闭后只是不再自动定时跑这个任务；不会删除历史数据，也不会中断已经开始的任务。
                    </Typography.Text>
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

        <Card size="small" title="任务请求 JSON">
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
                  <Form.Item label="任务数据日期">
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
                生成任务请求 JSON
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

function jobTypeMeta(job: string): Pick<JobSwitchRow, "type_label" | "type_color"> {
  if (job === "source_material_auto_push" || job === "source_material_preload") {
    return { type_label: "真实动作预览", type_color: "orange" };
  }
  if (job === "source_material_rollup") {
    return { type_label: "本地重算", type_color: "blue" };
  }
  if (job === "delivery_patrol") {
    return { type_label: "只读巡检", type_color: "cyan" };
  }
  return { type_label: "只读同步", type_color: "green" };
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
