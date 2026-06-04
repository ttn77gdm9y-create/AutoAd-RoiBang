import { DeleteOutlined, FileSearchOutlined, ReloadOutlined, SaveOutlined, SyncOutlined } from "@ant-design/icons";
import { Alert, Button, Card, Col, Form, Input, Row, Select, Space, Table, Tag, Typography, message as antdMessage } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { apiDelete, apiGet, apiPost } from "../api/client";
import { ConfirmExecutePanel } from "../components/ConfirmExecutePanel";
import { SummaryPanel } from "../components/SummaryPanel";
import { InlineTaskStatus } from "../components/WorkflowScaffold";
import { EXECUTE_CONFIRMATION_PHRASE } from "../constants/safety";
import type { ChineseResult, TaskDetailResponse } from "../types/api";
import { isTaskActive, isTaskCompleted, taskStatus } from "../utils/workflowState";

type BindingForm = {
  product: string;
  album_id: string;
  album_name: string;
  folder_id: string;
  folder_name: string;
};

type BindingRow = {
  id: number;
  product: string;
  album_id: string;
  album_name: string;
  folder_id: string;
  folder_name: string;
  is_active: number;
};

type AlbumNode = {
  "专辑/文件夹 ID": string;
  "名称": string;
  "层级": number;
  album_id?: string;
  album_name?: string;
  folder_id?: string;
  folder_name?: string;
};

type MaterialRow = Record<string, string | number | boolean | null>;

type UploadAccountOption = {
  label: string;
  value: string;
  account_name: string;
  product: string;
  status: string;
};

type TaskResponse = ChineseResult & {
  task?: {
    task_id: string;
    artifact_path: string;
    pid: number;
  };
};

const emptyBinding: BindingForm = {
  product: "",
  album_id: "",
  album_name: "",
  folder_id: "",
  folder_name: "",
};

const qualificationStatLabels = ["素材数", "可用于后续", "不可用", "缺 MD5", "已上传", "未上传", "有表现数据"];

export function GravityMaterialsPage() {
  const queryClient = useQueryClient();
  const [selectedProduct, setSelectedProduct] = useState("");
  const [statusFilter, setStatusFilter] = useState("eligible");
  const [keyword, setKeyword] = useState("");
  const [bindingForm, setBindingForm] = useState<BindingForm>(emptyBinding);
  const [saveResult, setSaveResult] = useState<ChineseResult | undefined>();
  const [deleteResult, setDeleteResult] = useState<ChineseResult | undefined>();
  const [selectedUploadMaterialIds, setSelectedUploadMaterialIds] = useState<string[]>([]);
  const [targetAccountIds, setTargetAccountIds] = useState<string[]>([]);
  const [authFile, setAuthFile] = useState("data/gravity_token.json");
  const [uploadPreviewResult, setUploadPreviewResult] = useState<ChineseResult | undefined>();
  const [uploadExecuteResult, setUploadExecuteResult] = useState<TaskResponse | undefined>();
  const [uploadStatusRefreshResult, setUploadStatusRefreshResult] = useState<TaskResponse | undefined>();
  const [selectedGravityTaskId, setSelectedGravityTaskId] = useState("");

  const filters = useQuery({
    queryKey: ["dashboard", "filters"],
    queryFn: () => apiGet<ChineseResult>("/dashboard/filters"),
  });
  const albums = useQuery({
    queryKey: ["gravity-materials", "albums"],
    queryFn: () => apiGet<ChineseResult>("/gravity-materials/albums"),
  });
  const bindings = useQuery({
    queryKey: ["gravity-materials", "bindings", selectedProduct],
    queryFn: () => apiGet<ChineseResult>(`/gravity-materials/bindings${selectedProduct ? `?product=${encodeURIComponent(selectedProduct)}` : ""}`),
  });
  const accounts = useQuery({
    queryKey: ["accounts", "gravity-upload"],
    queryFn: () => apiGet<ChineseResult>("/accounts"),
  });
  const materials = useQuery({
    queryKey: ["gravity-materials", "materials", selectedProduct, statusFilter, keyword],
    queryFn: () =>
      apiGet<ChineseResult>(
        `/gravity-materials/materials?product=${encodeURIComponent(selectedProduct)}&status=${encodeURIComponent(statusFilter)}&keyword=${encodeURIComponent(keyword)}`,
      ),
  });

  const productOptions = useMemo(() => productNameOptions(filters.data), [filters.data]);
  const albumOptions = useMemo(() => albumNodeOptions(albums.data), [albums.data]);
  const bindingRows = useMemo(() => bindingRowsFromResult(bindings.data), [bindings.data]);
  const qualificationStats = useMemo(() => summaryLookup(materials.data), [materials.data]);
  const uploadAccountOptions = useMemo(() => accountOptionsFromResult(accounts.data, selectedProduct), [accounts.data, selectedProduct]);
  const selectedTargetAccounts = useMemo(
    () =>
      targetAccountIds
        .map((accountId) => uploadAccountOptions.find((option) => option.value === accountId))
        .filter((option): option is UploadAccountOption => Boolean(option))
        .map((option) => ({ advertiser_id: option.value, account_name: option.account_name })),
    [targetAccountIds, uploadAccountOptions],
  );
  const materialRows = materials.data?.table.rows ?? [];
  const uploadTaskId = uploadExecuteResult?.task?.task_id ?? "";
  const statusRefreshTaskId = uploadStatusRefreshResult?.task?.task_id ?? "";
  const uploadTaskDetail = useQuery({
    queryKey: ["tasks", uploadTaskId],
    queryFn: () => apiGet<TaskDetailResponse>(`/tasks/${uploadTaskId}`),
    enabled: Boolean(uploadTaskId),
    refetchInterval: 3000,
  });
  const statusRefreshTaskDetail = useQuery({
    queryKey: ["tasks", statusRefreshTaskId],
    queryFn: () => apiGet<TaskDetailResponse>(`/tasks/${statusRefreshTaskId}`),
    enabled: Boolean(statusRefreshTaskId),
    refetchInterval: 3000,
  });
  const gravityTaskIds = useMemo(() => gravityTaskIdsFromResult(uploadTaskDetail.data ?? uploadExecuteResult), [uploadTaskDetail.data, uploadExecuteResult]);
  const uploadStatus = useQuery({
    queryKey: ["gravity-materials", "upload-status", selectedGravityTaskId],
    queryFn: () => apiGet<ChineseResult>(`/gravity-materials/upload-status/${encodeURIComponent(selectedGravityTaskId)}`),
    enabled: Boolean(selectedGravityTaskId),
  });
  const uploadRequiredCount = summaryItemNumber(uploadPreviewResult, "需上传");
  const canConfirmUpload = uploadPreviewResult?.summary.status === "ready_for_confirmation" && uploadRequiredCount > 0;
  const uploadTaskCurrentStatus = taskStatus(uploadTaskDetail.data, uploadExecuteResult);
  const statusRefreshCurrentStatus = taskStatus(statusRefreshTaskDetail.data, uploadStatusRefreshResult);

  useEffect(() => {
    if (!gravityTaskIds.length) {
      setSelectedGravityTaskId("");
      return;
    }
    setSelectedGravityTaskId((current) => (current && gravityTaskIds.includes(current) ? current : gravityTaskIds[0]));
  }, [gravityTaskIds]);

  useEffect(() => {
    if (isTaskCompleted(statusRefreshCurrentStatus)) {
      void uploadStatus.refetch();
      void materials.refetch();
    }
  }, [statusRefreshCurrentStatus]);

  const saveBinding = useMutation({
    mutationFn: () => apiPost<ChineseResult>("/gravity-materials/bindings", bindingForm),
    onSuccess: async (result) => {
      setSaveResult(result);
      setDeleteResult(undefined);
      await queryClient.invalidateQueries({ queryKey: ["gravity-materials", "bindings"] });
      antdMessage.success("引力素材绑定已保存");
    },
  });
  const deleteBinding = useMutation({
    mutationFn: (bindingId: number) => apiDelete<ChineseResult>(`/gravity-materials/bindings/${bindingId}`),
    onSuccess: async (result) => {
      setDeleteResult(result);
      setSaveResult(undefined);
      await queryClient.invalidateQueries({ queryKey: ["gravity-materials", "bindings"] });
      antdMessage.success("引力素材绑定已停用");
    },
  });
  const previewUpload = useMutation({
    mutationFn: () =>
      apiPost<ChineseResult>("/gravity-materials/upload-preview", {
        product: selectedProduct,
        target_accounts: selectedTargetAccounts,
        material_ids: selectedUploadMaterialIds,
      }),
    onSuccess: (result) => {
      setUploadPreviewResult(result);
      setUploadExecuteResult(undefined);
      setUploadStatusRefreshResult(undefined);
      antdMessage.success("上传预览已生成，请核对明细");
    },
  });
  const executeUpload = useMutation({
    mutationFn: () =>
      apiPost<TaskResponse>("/gravity-materials/upload-execute", {
        preview_path: uploadPreviewResult?.artifact_path ?? "",
        auth_file: authFile,
        confirmation: EXECUTE_CONFIRMATION_PHRASE,
      }),
    onSuccess: async (result) => {
      setUploadExecuteResult(result);
      setUploadStatusRefreshResult(undefined);
      await queryClient.invalidateQueries({ queryKey: ["tasks"] });
      antdMessage.success("上传任务已提交，本页会显示进度和结果");
    },
  });
  const refreshUploadStatus = useMutation({
    mutationFn: () =>
      apiPost<TaskResponse>("/gravity-materials/upload-status-refresh", {
        task_id: selectedGravityTaskId,
        auth_file: authFile,
      }),
    onSuccess: async (result) => {
      setUploadStatusRefreshResult(result);
      await queryClient.invalidateQueries({ queryKey: ["tasks"] });
      antdMessage.success("上传状态刷新任务已提交");
    },
  });
  const canPreviewUpload = Boolean(selectedProduct && selectedTargetAccounts.length && selectedUploadMaterialIds.length) && !previewUpload.isPending;

  function selectProduct(product: string) {
    setSelectedProduct(product);
    setBindingForm((current) => ({ ...current, product }));
    setSelectedUploadMaterialIds([]);
    setTargetAccountIds([]);
    setUploadPreviewResult(undefined);
    setUploadExecuteResult(undefined);
    setUploadStatusRefreshResult(undefined);
    setSelectedGravityTaskId("");
  }

  function selectAlbumNode(value: string) {
    const node = albumOptions.find((item) => item.value === value);
    if (!node) {
      return;
    }
    setBindingForm((current) => ({
      ...current,
      album_id: node.album_id || node.value,
      album_name: node.album_name || node.label,
      folder_id: node.folder_id || "",
      folder_name: node.folder_name || "",
    }));
  }

  return (
    <main className="page gravity-materials-page">
      <Space direction="vertical" size="large" className="full-width">
        <div className="page-heading-row">
          <Typography.Title level={2}>引力素材库</Typography.Title>
          <Space wrap>
            <Button icon={<ReloadOutlined />} onClick={() => void Promise.all([albums.refetch(), bindings.refetch(), materials.refetch()])}>
              刷新页面数据
            </Button>
            <Link to="/workflow-center">
              <Button icon={<SyncOutlined />}>去自动化工作台同步</Button>
            </Link>
          </Space>
        </div>
        <Alert
          type="info"
          showIcon
          message="这里只读同步引力素材并写入本地素材库；不会上传素材、创建广告、修改预算、出价或项目状态。"
        />
        <div className="gravity-qualification-strip">
          {qualificationStatLabels.map((label) => (
            <div className="gravity-qualification-tile" key={label}>
              <span>{label}</span>
              <strong>{statValue(qualificationStats.get(label))}</strong>
            </div>
          ))}
        </div>
        <Row gutter={[16, 16]} align="top">
          <Col xs={24} xl={9}>
            <Card size="small" title="产品-专辑绑定">
              <Space direction="vertical" size="middle" className="full-width">
                <Form layout="vertical">
                  <Form.Item label="产品">
                    <Select
                      showSearch
                      allowClear
                      loading={filters.isLoading}
                      value={selectedProduct || undefined}
                      options={productOptions}
                      placeholder="选择产品"
                      onChange={(value) => selectProduct(value ?? "")}
                    />
                  </Form.Item>
                  <Form.Item label="引力专辑/文件夹">
                    <Select
                      showSearch
                      loading={albums.isLoading}
                      options={albumOptions}
                      placeholder="选择专辑或文件夹"
                      onChange={selectAlbumNode}
                    />
                    <Typography.Text type="secondary" className="allowed-account-help">
                      没有选项时，先到自动化工作台运行“引力素材库只读探测”。
                    </Typography.Text>
                  </Form.Item>
                  <Row gutter={[12, 0]}>
                    <Col span={12}>
                      <Form.Item label="专辑 ID">
                        <Input value={bindingForm.album_id} onChange={(event) => setBindingForm({ ...bindingForm, album_id: event.target.value })} />
                      </Form.Item>
                    </Col>
                    <Col span={12}>
                      <Form.Item label="专辑名称">
                        <Input value={bindingForm.album_name} onChange={(event) => setBindingForm({ ...bindingForm, album_name: event.target.value })} />
                      </Form.Item>
                    </Col>
                  </Row>
                  <Row gutter={[12, 0]}>
                    <Col span={12}>
                      <Form.Item label="文件夹 ID">
                        <Input value={bindingForm.folder_id} onChange={(event) => setBindingForm({ ...bindingForm, folder_id: event.target.value })} />
                      </Form.Item>
                    </Col>
                    <Col span={12}>
                      <Form.Item label="文件夹名称">
                        <Input value={bindingForm.folder_name} onChange={(event) => setBindingForm({ ...bindingForm, folder_name: event.target.value })} />
                      </Form.Item>
                    </Col>
                  </Row>
                  <Button icon={<SaveOutlined />} type="primary" loading={saveBinding.isPending} onClick={() => saveBinding.mutate()}>
                    保存绑定
                  </Button>
                </Form>
                <Table<BindingRow>
                  rowKey="id"
                  size="small"
                  loading={bindings.isLoading}
                  pagination={false}
                  dataSource={bindingRows}
                  columns={[
                    { title: "产品", dataIndex: "product" },
                    {
                      title: "绑定",
                      render: (_, row) => (
                        <Space direction="vertical" size={2}>
                          <Typography.Text>{row.folder_name || row.album_name}</Typography.Text>
                          <Typography.Text type="secondary">{row.folder_id || row.album_id}</Typography.Text>
                        </Space>
                      ),
                    },
                    {
                      title: "操作",
                      width: 80,
                      render: (_, row) => (
                        <Button icon={<DeleteOutlined />} size="small" danger loading={deleteBinding.isPending} onClick={() => deleteBinding.mutate(row.id)} />
                      ),
                    },
                  ]}
                />
              </Space>
            </Card>
            {saveResult || deleteResult ? (
              <SummaryPanel result={saveResult ?? deleteResult} detailsCollapsed showArtifactPath={false} showRawJson={false} />
            ) : null}
          </Col>
          <Col xs={24} xl={15}>
            <Card size="small" title="素材资格明细">
              <Space direction="vertical" size="middle" className="full-width">
                <Row gutter={[12, 12]}>
                  <Col xs={24} md={8}>
                    <Select
                      className="full-width"
                      value={statusFilter}
                      options={[
                        { label: "可用于后续", value: "eligible" },
                        { label: "不可用", value: "ineligible" },
                        { label: "缺 MD5", value: "missing_md5" },
                        { label: "已上传", value: "uploaded" },
                        { label: "未上传", value: "not_uploaded" },
                        { label: "有表现数据", value: "has_performance" },
                        { label: "本地停用", value: "inactive" },
                        { label: "全部素材", value: "" },
                      ]}
                      onChange={setStatusFilter}
                    />
                  </Col>
                  <Col xs={24} md={16}>
                    <Input.Search value={keyword} onChange={(event) => setKeyword(event.target.value)} placeholder="搜索素材名 / 引力素材 ID / MD5" />
                  </Col>
                </Row>
                <Table<MaterialRow>
                  rowKey={(row) => String(row["引力素材 ID"] ?? "")}
                  loading={materials.isLoading}
                  size="small"
                  columns={materialColumns()}
                  dataSource={materialRows}
                  rowSelection={{
                    selectedRowKeys: selectedUploadMaterialIds,
                    onChange: (keys) => {
                      setSelectedUploadMaterialIds(keys.map(String));
                      setUploadPreviewResult(undefined);
                      setUploadExecuteResult(undefined);
                      setUploadStatusRefreshResult(undefined);
                    },
                    getCheckboxProps: (record) => ({
                      disabled: !canSelectUploadMaterial(record),
                      name: String(record["素材名"] ?? record["引力素材 ID"] ?? ""),
                    }),
                  }}
                  scroll={{ x: "max-content" }}
                  pagination={{ pageSize: 20, showSizeChanger: true }}
                />
              </Space>
            </Card>
            <Card size="small" title="上传到目标账户" className="gravity-upload-card">
              <Space direction="vertical" size="middle" className="full-width">
                <Alert
                  type="warning"
                  showIcon
                  message="上传素材到巨量账户是真实媒体动作。必须先生成预览并核对账户名、账户 ID、素材 ID、MD5；真实上传前还要输入“确认执行”。"
                />
                <Row gutter={[12, 12]} align="bottom">
                  <Col xs={24} md={10}>
                    <Typography.Text strong>目标账户</Typography.Text>
                    <Select
                      mode="multiple"
                      showSearch
                      className="full-width gravity-upload-control"
                      loading={accounts.isLoading}
                      value={targetAccountIds}
                      options={uploadAccountOptions}
                      placeholder={selectedProduct ? "选择要上传到的账户" : "先选择产品"}
                      onChange={(values) => {
                        setTargetAccountIds(values);
                        setUploadPreviewResult(undefined);
                        setUploadExecuteResult(undefined);
                        setUploadStatusRefreshResult(undefined);
                      }}
                    />
                    <Typography.Text type="secondary" className="gravity-upload-help">
                      账户来自产品账户库；预览和结果会同时显示账户 ID 与账户名。
                    </Typography.Text>
                  </Col>
                  <Col xs={24} md={7}>
                    <Typography.Text strong>引力 Token 文件</Typography.Text>
                    <Input className="gravity-upload-control" value={authFile} onChange={(event) => setAuthFile(event.target.value)} />
                    <Typography.Text type="secondary" className="gravity-upload-help">
                      仅固定脚本读取，不在页面展示 token 明文。
                    </Typography.Text>
                  </Col>
                  <Col xs={24} md={7}>
                    <Space wrap className="gravity-upload-actions">
                      <Button icon={<FileSearchOutlined />} loading={previewUpload.isPending} disabled={!canPreviewUpload} onClick={() => previewUpload.mutate()}>
                        生成上传预览
                      </Button>
                      <Tag color={selectedUploadMaterialIds.length ? "blue" : "default"}>已选素材 {selectedUploadMaterialIds.length}</Tag>
                    </Space>
                  </Col>
                </Row>
                {!selectedProduct ? <Alert type="info" showIcon message="先在左侧选择产品，再选择素材和目标账户。" /> : null}
                {previewUpload.error ? <Alert type="error" showIcon message={(previewUpload.error as Error).message} /> : null}
                {uploadPreviewResult ? (
                  <SummaryPanel
                    result={uploadPreviewResult}
                    detailsCollapsed
                    showArtifactPath
                    showRawJson
                    footer={
                      canConfirmUpload ? (
                        <ConfirmExecutePanel
                          buttonText="确认并上传素材"
                          disabled={executeUpload.isPending || Boolean(uploadExecuteResult) || isTaskActive(uploadTaskCurrentStatus)}
                          onConfirm={() => executeUpload.mutate()}
                        />
                      ) : uploadPreviewResult.summary.status === "ready_for_confirmation" ? (
                        <Alert type="success" showIcon message="目标账户里已经有这些素材，不需要上传。" />
                      ) : null
                    }
                  />
                ) : null}
                {executeUpload.error ? <Alert type="error" showIcon message={(executeUpload.error as Error).message} /> : null}
              </Space>
            </Card>
            <InlineTaskStatus
              title="当前上传任务"
              taskId={uploadTaskId}
              workflow="gravity_upload_to_account"
              result={uploadExecuteResult}
              detail={uploadTaskDetail.data}
              loading={executeUpload.isPending || uploadTaskDetail.isFetching}
              returnTo="/gravity-materials"
            />
            {gravityTaskIds.length || uploadStatus.data || uploadStatusRefreshResult ? (
              <Card size="small" title="上传状态复盘" className="gravity-upload-card">
                <Space direction="vertical" size="middle" className="full-width">
                  <Alert
                    type="info"
                    showIcon
                    message="上传是异步任务。刷新状态只查询引力 task，并在本地素材库已同步到合法媒体素材 ID 后回填账本；不会再次上传素材。"
                  />
                  <Row gutter={[12, 12]} align="bottom">
                    <Col xs={24} md={12}>
                      <Typography.Text strong>引力任务 ID</Typography.Text>
                      <Select
                        className="full-width gravity-upload-control"
                        value={selectedGravityTaskId || undefined}
                        options={gravityTaskIds.map((taskId) => ({ label: taskId, value: taskId }))}
                        placeholder="选择要刷新的引力 task"
                        onChange={setSelectedGravityTaskId}
                      />
                    </Col>
                    <Col xs={24} md={12}>
                      <Space wrap className="gravity-upload-actions">
                        <Button
                          icon={<SyncOutlined />}
                          loading={refreshUploadStatus.isPending}
                          disabled={!selectedGravityTaskId || refreshUploadStatus.isPending || isTaskActive(statusRefreshCurrentStatus)}
                          onClick={() => refreshUploadStatus.mutate()}
                        >
                          刷新上传状态
                        </Button>
                        <Button icon={<ReloadOutlined />} disabled={!selectedGravityTaskId} onClick={() => uploadStatus.refetch()}>
                          读取本地账本
                        </Button>
                      </Space>
                    </Col>
                  </Row>
                  {refreshUploadStatus.error ? <Alert type="error" showIcon message={(refreshUploadStatus.error as Error).message} /> : null}
                  <SummaryPanel result={uploadStatus.data} loading={uploadStatus.isFetching} detailsCollapsed showArtifactPath={false} showRawJson={false} />
                </Space>
              </Card>
            ) : null}
            <InlineTaskStatus
              title="当前状态刷新任务"
              taskId={statusRefreshTaskId}
              workflow="gravity_upload_status_poll"
              result={uploadStatusRefreshResult}
              detail={statusRefreshTaskDetail.data}
              loading={refreshUploadStatus.isPending || statusRefreshTaskDetail.isFetching}
              returnTo="/gravity-materials"
            />
            <SummaryPanel result={materials.data} loading={materials.isLoading} detailsCollapsed showArtifactPath={false} showRawJson={false} />
          </Col>
        </Row>
      </Space>
    </main>
  );
}

function productNameOptions(result?: ChineseResult) {
  return (result?.table.rows ?? [])
    .filter((row) => row["类型"] === "产品")
    .map((row) => {
      const label = String(row["显示名称"] ?? row["值"] ?? "");
      return { label, value: label };
    });
}

function albumNodeOptions(result?: ChineseResult) {
  const nodes = Array.isArray(result?.raw.nodes) ? (result?.raw.nodes as AlbumNode[]) : [];
  return nodes.map((node) => {
    const id = String(node["专辑/文件夹 ID"] ?? "");
    const name = String(node["名称"] ?? "");
    const level = Number(node["层级"] ?? 1);
    return {
      value: `${id}:${level}`,
      label: `${"  ".repeat(Math.max(0, level - 1))}${name}（${id}）`,
      album_id: String(node.album_id ?? id),
      album_name: String(node.album_name ?? name),
      folder_id: String(node.folder_id ?? ""),
      folder_name: String(node.folder_name ?? ""),
    };
  });
}

function bindingRowsFromResult(result?: ChineseResult): BindingRow[] {
  return Array.isArray(result?.raw.bindings) ? (result?.raw.bindings as BindingRow[]) : [];
}

function summaryLookup(result?: ChineseResult): Map<string, string | number | boolean | null> {
  return new Map((result?.summary.items ?? []).map((item) => [item.label, item.value]));
}

function summaryItemNumber(result: ChineseResult | undefined, label: string): number {
  const value = result?.summary.items.find((item) => item.label === label)?.value;
  const parsed = Number(value ?? 0);
  return Number.isFinite(parsed) ? parsed : 0;
}

function accountOptionsFromResult(result: ChineseResult | undefined, selectedProduct: string): UploadAccountOption[] {
  const seen = new Set<string>();
  return (result?.table.rows ?? [])
    .filter((row) => {
      const product = String(row["产品"] ?? "").trim();
      const productKey = String(row["产品 Key"] ?? "").trim();
      return !selectedProduct || product === selectedProduct || productKey === selectedProduct;
    })
    .map((row) => {
      const value = String(row["账户 ID"] ?? "").trim();
      const accountName = String(row["账户名"] ?? value).trim();
      const product = String(row["产品"] ?? "").trim();
      const status = String(row["状态"] ?? "").trim();
      return {
        value,
        account_name: accountName || value,
        product,
        status,
        label: `${accountName || value}（${value}）${status ? ` · ${status}` : ""}`,
      };
    })
    .filter((option) => {
      if (!option.value || seen.has(option.value)) {
        return false;
      }
      seen.add(option.value);
      return true;
    });
}

function canSelectUploadMaterial(row: MaterialRow): boolean {
  return Boolean(String(row["引力素材 ID"] ?? "").trim()) && String(row["资格状态"] ?? "") === "可用于后续";
}

function gravityTaskIdsFromResult(result?: ChineseResult): string[] {
  const seen = new Set<string>();
  return (result?.table.rows ?? [])
    .map((row) => String(row["引力任务 ID"] ?? "").trim())
    .filter((taskId) => {
      if (!taskId || seen.has(taskId)) {
        return false;
      }
      seen.add(taskId);
      return true;
    });
}

function statValue(value: string | number | boolean | null | undefined): string | number {
  if (value === undefined || value === null || value === "") {
    return 0;
  }
  return typeof value === "boolean" ? (value ? "是" : "否") : value;
}

function materialColumns(): ColumnsType<MaterialRow> {
  return [
    { title: "产品", dataIndex: "产品", width: 120 },
    { title: "专辑", dataIndex: "专辑", width: 140 },
    { title: "文件夹", dataIndex: "文件夹", width: 140 },
    { title: "素材名", dataIndex: "素材名", width: 180, ellipsis: true },
    { title: "引力素材 ID", dataIndex: "引力素材 ID", width: 160, ellipsis: true },
    { title: "MD5", dataIndex: "MD5", width: 180, ellipsis: true, render: renderEmpty },
    {
      title: "状态",
      dataIndex: "状态",
      width: 88,
      render: (value) => <Tag color={materialStatusColor(value)}>{String(value || "未知")}</Tag>,
    },
    {
      title: "资格状态",
      dataIndex: "资格状态",
      width: 118,
      render: (value) => <Tag color={String(value) === "可用于后续" ? "green" : "orange"}>{String(value || "未知")}</Tag>,
    },
    {
      title: "不可用原因",
      dataIndex: "不可用原因",
      width: 180,
      ellipsis: true,
      render: (value) => (value ? <Typography.Text type="danger">{String(value)}</Typography.Text> : <Typography.Text type="secondary">-</Typography.Text>),
    },
    {
      title: "上传状态",
      dataIndex: "上传状态",
      width: 106,
      render: (value) => <Tag color={String(value) === "已上传" ? "blue" : "default"}>{String(value || "未上传")}</Tag>,
    },
    { title: "媒体素材 ID", dataIndex: "媒体素材 ID", width: 150, ellipsis: true, render: renderEmpty },
    { title: "消耗", dataIndex: "消耗", width: 92 },
    { title: "展示", dataIndex: "展示", width: 92 },
    { title: "点击", dataIndex: "点击", width: 92 },
    { title: "转化", dataIndex: "转化", width: 92 },
    { title: "同步时间", dataIndex: "同步时间", width: 180 },
  ];
}

function renderEmpty(value: unknown) {
  return value ? String(value) : <Typography.Text type="secondary">-</Typography.Text>;
}

function materialStatusColor(value: unknown): string {
  const text = String(value || "");
  if (text === "可用" || text === "1") {
    return "green";
  }
  if (text.includes("拒审") || text.includes("不通过")) {
    return "red";
  }
  if (text === "禁用" || text === "停用" || text === "2") {
    return "orange";
  }
  return "default";
}
