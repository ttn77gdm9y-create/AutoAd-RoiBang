import { DeleteOutlined, FileSearchOutlined, PlayCircleOutlined, ReloadOutlined, SaveOutlined, SyncOutlined } from "@ant-design/icons";
import { Alert, Button, Card, Col, Form, Input, Row, Select, Space, Steps, Table, Tag, Typography, message as antdMessage } from "antd";
import type { ColumnsType } from "antd/es/table";
import type { SorterResult } from "antd/es/table/interface";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { apiDelete, apiGet, apiPost } from "../api/client";
import { ConfirmExecutePanel } from "../components/ConfirmExecutePanel";
import { SummaryPanel } from "../components/SummaryPanel";
import { InlineTaskStatus } from "../components/WorkflowScaffold";
import { EXECUTE_CONFIRMATION_PHRASE } from "../constants/safety";
import type { ChineseResult, TaskDetailResponse } from "../types/api";
import { businessTableClassName, businessTableScrollX, businessTableSticky } from "../utils/tableLayout";
import { DEFAULT_TABLE_PAGE_SIZE, TABLE_PAGE_SIZE_OPTIONS } from "../utils/tablePagination";
import { isTaskActive, isTaskCompleted, taskStatus } from "../utils/workflowState";
import { buildGravityMaterialFlowState } from "./gravityMaterialsFlow";
import { buildAlbumChoiceGroups, flattenAlbumChoiceGroups, type AlbumChoiceGroup, type AlbumChoiceOption, type TargetAlbumRow } from "./gravityMaterialsOptions";
import { buildGravityMaterialSyncRequest, gravityMaterialSyncCopy } from "./gravityMaterialsSync";

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

type MaterialRow = Record<string, string | number | boolean | null>;

type UploadAccountOption = {
  label: string;
  value: string;
  account_name: string;
  product: string;
  status: string;
};

type AlbumSelectOption = {
  label: ReactNode;
  value?: string;
  searchText?: string;
  options?: AlbumSelectOption[];
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

const qualificationStatsConfig = [
  { label: "可铺货素材", lookup: "可铺货素材" },
  { label: "异常/不可铺货", lookup: "不可入库/不可铺货" },
  { label: "缺 MD5", lookup: "缺 MD5" },
  { label: "已推送", lookup: "已推送" },
  { label: "未推送", lookup: "未推送" },
  { label: "郭靖启用目标账户", lookup: "郭靖启用目标账户" },
];

const GRAVITY_PRELOAD_TARGET_OWNER = "郭靖";

export function GravityMaterialsPage() {
  const queryClient = useQueryClient();
  const [selectedProduct, setSelectedProduct] = useState("");
  const [keyword, setKeyword] = useState("");
  const [materialPagination, setMaterialPagination] = useState({ current: 1, pageSize: DEFAULT_TABLE_PAGE_SIZE });
  const [materialSort, setMaterialSort] = useState({ sortBy: "引力创建时间", sortOrder: "descend" });
  const [bindingForm, setBindingForm] = useState<BindingForm>(emptyBinding);
  const [saveResult, setSaveResult] = useState<ChineseResult | undefined>();
  const [deleteResult, setDeleteResult] = useState<ChineseResult | undefined>();
  const [selectedUploadMaterialIds, setSelectedUploadMaterialIds] = useState<string[]>([]);
  const [targetAccountIds, setTargetAccountIds] = useState<string[]>([]);
  const [authFile, setAuthFile] = useState("data/gravity_token.json");
  const [syncPageSize, setSyncPageSize] = useState("100");
  const [syncMaxPages, setSyncMaxPages] = useState("20");
  const [syncPreviewResult, setSyncPreviewResult] = useState<ChineseResult | undefined>();
  const [syncRunResult, setSyncRunResult] = useState<TaskResponse | undefined>();
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
    queryFn: () => apiGet<ChineseResult>("/accounts?status=active"),
  });
  const materials = useQuery({
    queryKey: ["gravity-materials", "materials", selectedProduct, keyword, materialPagination.current, materialPagination.pageSize, materialSort],
    queryFn: () => {
      const params = new URLSearchParams();
      params.set("product", selectedProduct);
      params.set("keyword", keyword);
      params.set("page", String(materialPagination.current));
      params.set("page_size", String(materialPagination.pageSize));
      params.set("sort_by", materialSort.sortBy);
      params.set("sort_order", materialSort.sortOrder);
      return apiGet<ChineseResult>(`/gravity-materials/materials?${params.toString()}`);
    },
  });
  const syncReadiness = useQuery({
    queryKey: ["gravity-materials", "sync-readiness", selectedProduct, authFile],
    queryFn: () =>
      apiGet<ChineseResult>(
        `/gravity-materials/sync-readiness?product=${encodeURIComponent(selectedProduct)}&auth_file=${encodeURIComponent(authFile)}`,
      ),
  });

  const productOptions = useMemo(() => productNameOptions(filters.data), [filters.data]);
  const targetAlbumRows = useMemo(() => targetAlbumRowsFromResult(albums.data), [albums.data]);
  const albumChoiceGroups = useMemo(() => buildAlbumChoiceGroups(targetAlbumRows), [targetAlbumRows]);
  const albumOptions = useMemo(() => flattenAlbumChoiceGroups(albumChoiceGroups), [albumChoiceGroups]);
  const albumSelectOptions = useMemo(() => renderAlbumSelectOptions(albumChoiceGroups), [albumChoiceGroups]);
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
  const materialTotal = materialTotalFromResult(materials.data, materialRows.length);
  const syncTaskId = syncRunResult?.task?.task_id ?? "";
  const syncTaskDetail = useQuery({
    queryKey: ["tasks", syncTaskId],
    queryFn: () => apiGet<TaskDetailResponse>(`/tasks/${syncTaskId}`),
    enabled: Boolean(syncTaskId),
    refetchInterval: 3000,
  });
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
  const uploadRequiredCount = summaryItemNumber(uploadPreviewResult, "需上传") + summaryItemNumber(uploadPreviewResult, "需铺货");
  const isPreloadPreview = uploadPreviewResult?.summary.title === "引力素材提前铺货预览";
  const canConfirmUpload = uploadPreviewResult?.summary.status === "ready_for_confirmation" && uploadRequiredCount > 0;
  const syncTaskCurrentStatus = taskStatus(syncTaskDetail.data, syncRunResult);
  const uploadTaskCurrentStatus = taskStatus(uploadTaskDetail.data, uploadExecuteResult);
  const statusRefreshCurrentStatus = taskStatus(statusRefreshTaskDetail.data, uploadStatusRefreshResult);
  const totalMaterials = statNumber(qualificationStats.get("可铺货素材"));
  const eligibleMaterials = totalMaterials;
  const hasBinding = bindingRows.length > 0;
  const flowState = useMemo(
    () =>
      buildGravityMaterialFlowState({
        bindingCount: bindingRows.length,
        totalMaterials,
        eligibleMaterials,
        selectedMaterials: selectedUploadMaterialIds.length,
        selectedAccounts: targetAccountIds.length,
        readinessStatus: syncReadiness.data?.summary.status,
        readinessNextAction: readinessNextActionTitle(syncReadiness.data),
      }),
    [
      bindingRows.length,
      eligibleMaterials,
      selectedUploadMaterialIds.length,
      syncReadiness.data,
      targetAccountIds.length,
      totalMaterials,
    ],
  );

  useEffect(() => {
    if (selectedProduct || !productOptions.length) {
      return;
    }
    const firstProduct = String(productOptions[0]?.value ?? "");
    if (firstProduct) {
      selectProduct(firstProduct);
    }
  }, [productOptions, selectedProduct]);

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

  useEffect(() => {
    if (isTaskCompleted(syncTaskCurrentStatus)) {
      void syncReadiness.refetch();
      void materials.refetch();
      void queryClient.invalidateQueries({ queryKey: ["workflow-runs", "catalog"] });
    }
  }, [syncTaskCurrentStatus]);

  const saveBinding = useMutation({
    mutationFn: () => apiPost<ChineseResult>("/gravity-materials/bindings", bindingForm),
    onSuccess: async (result) => {
      setSaveResult(result);
      setDeleteResult(undefined);
      await queryClient.invalidateQueries({ queryKey: ["gravity-materials", "bindings"] });
      await queryClient.invalidateQueries({ queryKey: ["gravity-materials", "sync-readiness"] });
      antdMessage.success("引力素材绑定已保存");
    },
  });
  const deleteBinding = useMutation({
    mutationFn: (bindingId: number) => apiDelete<ChineseResult>(`/gravity-materials/bindings/${bindingId}`),
    onSuccess: async (result) => {
      setDeleteResult(result);
      setSaveResult(undefined);
      await queryClient.invalidateQueries({ queryKey: ["gravity-materials", "bindings"] });
      await queryClient.invalidateQueries({ queryKey: ["gravity-materials", "sync-readiness"] });
      antdMessage.success("引力素材绑定已停用");
    },
  });
  const previewSync = useMutation({
    mutationFn: () =>
      apiPost<ChineseResult>("/workflow-runs/gravity_material_sync/preview", {
        request: buildGravityMaterialSyncRequest({
          product: selectedProduct,
          authFile,
          pageSize: syncPageSize,
          maxPages: syncMaxPages,
        }),
      }),
    onSuccess: (result) => {
      setSyncPreviewResult(result);
      setSyncRunResult(undefined);
      antdMessage.success("资料同步预览已生成");
    },
  });
  const runSync = useMutation({
    mutationFn: () =>
      apiPost<TaskResponse>("/workflow-runs/gravity_material_sync/run", {
        request: buildGravityMaterialSyncRequest({
          product: selectedProduct,
          authFile,
          pageSize: syncPageSize,
          maxPages: syncMaxPages,
        }),
      }),
    onSuccess: async (result) => {
      setSyncRunResult(result);
      await queryClient.invalidateQueries({ queryKey: ["tasks"] });
      antdMessage.success("资料同步任务已提交，本页会显示进度和结果");
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
      antdMessage.success("推送预览已生成，请核对明细");
    },
  });
  const preloadPreview = useMutation({
    mutationFn: () =>
      apiPost<ChineseResult>("/gravity-materials/preload-preview", {
        product: selectedProduct,
        batch_size: 50,
      }),
    onSuccess: (result) => {
      setUploadPreviewResult(result);
      setUploadExecuteResult(undefined);
      setUploadStatusRefreshResult(undefined);
      antdMessage.success("提前铺货预览已生成，请核对账户和素材明细");
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
      antdMessage.success("推送任务已提交，本页会显示进度和结果");
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
  const canPreviewPreload = Boolean(selectedProduct) && !preloadPreview.isPending;
  const canRunSync = Boolean(syncPreviewResult?.raw.can_run) && !runSync.isPending && !isTaskActive(syncTaskCurrentStatus);
  const syncBusy = previewSync.isPending || runSync.isPending || isTaskActive(syncTaskCurrentStatus);

  function selectProduct(product: string) {
    setSelectedProduct(product);
    setBindingForm((current) => ({ ...current, product }));
    setMaterialPagination((current) => ({ ...current, current: 1 }));
    setSelectedUploadMaterialIds([]);
    setTargetAccountIds([]);
    setSyncPreviewResult(undefined);
    setSyncRunResult(undefined);
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

  function fillBindingFromTarget(row: TargetAlbumRow) {
    if (row["匹配状态"] !== "已匹配") {
      return;
    }
    setBindingForm((current) => ({
      ...current,
      album_id: String(row.album_id || row["专辑/文件夹 ID"] || ""),
      album_name: String(row.album_name || row["名称"] || row["目标专辑"] || ""),
      folder_id: String(row.folder_id || ""),
      folder_name: String(row.folder_name || ""),
    }));
  }

  async function startSyncFromMaterialList() {
    if (syncBusy) {
      return;
    }
    try {
      const preview = syncPreviewResult?.raw.can_run ? syncPreviewResult : await previewSync.mutateAsync();
      if (!preview?.raw.can_run) {
        antdMessage.warning("更新前检查未通过，请查看第 2 步明细。");
        scrollToSyncCard();
        return;
      }
      await runSync.mutateAsync();
    } catch (error) {
      antdMessage.error((error as Error).message || "更新引力素材失败，请查看第 2 步明细。");
    }
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
              <Button icon={<SyncOutlined />}>查看自动化工作台</Button>
            </Link>
          </Space>
        </div>
        <Alert
          type="info"
          showIcon
          message="这里只读取引力素材资料并写入本地素材库；不会下载素材文件、不会上传素材、创建广告、修改预算、出价或项目状态。"
        />
        <Steps
          size="small"
          className="gravity-material-steps"
          current={flowState.currentStep}
          items={flowState.steps}
        />
        <Alert
          type={flowState.recommendation.type}
          showIcon
          message={flowState.recommendation.title}
          description={flowState.recommendation.description}
        />
        <div className="gravity-qualification-strip">
          {qualificationStatsConfig.map((item) => (
            <div className="gravity-qualification-tile" key={item.label}>
              <span>{item.label}</span>
              <strong>{statValue(qualificationStats.get(item.lookup))}</strong>
            </div>
          ))}
        </div>
        <Row gutter={[16, 16]} align="top">
          <Col xs={24} xl={9}>
            <Card size="small" title={stepTitle("1", "绑定素材来源")}>
              <Space direction="vertical" size="middle" className="full-width">
                <Alert
                  type="info"
                  showIcon
                  message="先告诉系统：这个产品只从哪些引力专辑或文件夹同步素材。这里只展示允许同步的 3 个目标专辑，避免误选其他游戏素材。"
                />
                <Table<TargetAlbumRow>
                  className={businessTableClassName("gravity-target-albums-table")}
                  rowKey={(row) => row["目标专辑"]}
                  size="small"
                  loading={albums.isLoading}
                  pagination={false}
                  sticky={businessTableSticky}
                  dataSource={targetAlbumRows}
                  columns={[
                    {
                      title: "目标专辑",
                      dataIndex: "目标专辑",
                      render: (value, row) => (
                        <Space direction="vertical" size={2}>
                          <Typography.Text strong>{String(value || "")}</Typography.Text>
                          <Typography.Text type="secondary">{Number(row["匹配数量"] || 0)} 个可选范围</Typography.Text>
                        </Space>
                      ),
                    },
                    {
                      title: "状态",
                      dataIndex: "匹配状态",
                      width: 76,
                      render: (value) => <Tag color={targetAlbumStatusColor(value)}>{String(value || "未知")}</Tag>,
                    },
                    {
                      title: "操作",
                      width: 96,
                      render: (_, row) => (
                        <Button size="small" disabled={row["匹配状态"] !== "已匹配"} onClick={() => fillBindingFromTarget(row)}>
                          填入专辑
                        </Button>
                      ),
                    },
                  ]}
                />
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
                      options={albumSelectOptions}
                      popupMatchSelectWidth={560}
                      placeholder="选择整个专辑，或只选择它下面的文件夹"
                      filterOption={(input, option) =>
                        String((option as { searchText?: string } | undefined)?.searchText ?? "")
                          .toLowerCase()
                          .includes(input.toLowerCase())
                      }
                      onChange={selectAlbumNode}
                    />
                    <Typography.Text type="secondary" className="allowed-account-help">
                      选专辑 = 同步整个专辑；选文件夹 = 只同步这个文件夹。没有选项时，先到自动化工作台运行“引力素材库只读探测”。
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
                  <Space wrap>
                    <Button icon={<SaveOutlined />} type="primary" loading={saveBinding.isPending} onClick={() => saveBinding.mutate()}>
                      保存绑定
                    </Button>
                    <Button icon={<SyncOutlined />} onClick={scrollToSyncCard}>
                      查看更新区域
                    </Button>
                  </Space>
                </Form>
                <Table<BindingRow>
                  className={businessTableClassName("gravity-bindings-table")}
                  rowKey="id"
                  size="small"
                  loading={bindings.isLoading}
                  pagination={false}
                  sticky={businessTableSticky}
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
            <Card size="small" title={stepTitle("2", gravityMaterialSyncCopy.title)} id="gravity-sync-card">
              <Space direction="vertical" size="middle" className="full-width">
                <Alert type="info" showIcon message={gravityMaterialSyncCopy.description} />
                <SummaryPanel result={syncReadiness.data} loading={syncReadiness.isFetching} detailsCollapsed showArtifactPath={false} showRawJson={false} />
                <Row gutter={[12, 12]} align="bottom">
                  <Col xs={24} md={8}>
                    <Typography.Text strong>引力 Token 文件</Typography.Text>
                    <Input
                      className="gravity-upload-control"
                      value={authFile}
                      onChange={(event) => {
                        setAuthFile(event.target.value);
                        setSyncPreviewResult(undefined);
                        setSyncRunResult(undefined);
                        setUploadPreviewResult(undefined);
                        setUploadExecuteResult(undefined);
                      }}
                    />
                    <Typography.Text type="secondary" className="gravity-upload-help">
                      仅固定脚本读取，不在页面展示 token 明文。
                    </Typography.Text>
                  </Col>
                  <Col xs={12} md={5}>
                    <Typography.Text strong>每页素材数</Typography.Text>
                    <Select
                      className="full-width gravity-upload-control"
                      value={syncPageSize}
                      options={[
                        { label: "50 条", value: "50" },
                        { label: "100 条", value: "100" },
                        { label: "200 条", value: "200" },
                      ]}
                      onChange={(value) => {
                        setSyncPageSize(value);
                        setSyncPreviewResult(undefined);
                        setSyncRunResult(undefined);
                      }}
                    />
                  </Col>
                  <Col xs={12} md={5}>
                    <Typography.Text strong>最多页数</Typography.Text>
                    <Select
                      className="full-width gravity-upload-control"
                      value={syncMaxPages}
                      options={[
                        { label: "5 页", value: "5" },
                        { label: "20 页", value: "20" },
                        { label: "50 页", value: "50" },
                      ]}
                      onChange={(value) => {
                        setSyncMaxPages(value);
                        setSyncPreviewResult(undefined);
                        setSyncRunResult(undefined);
                      }}
                    />
                  </Col>
                  <Col xs={24} md={6}>
                    <Space wrap className="gravity-upload-actions">
                      <Button icon={<ReloadOutlined />} onClick={() => syncReadiness.refetch()} loading={syncReadiness.isFetching}>
                        重新检查
                      </Button>
                      <Button icon={<FileSearchOutlined />} onClick={() => previewSync.mutate()} loading={previewSync.isPending}>
                        生成更新预览
                      </Button>
                      <Button
                        icon={<PlayCircleOutlined />}
                        type="primary"
                        disabled={!canRunSync}
                        loading={runSync.isPending}
                        onClick={() => runSync.mutate()}
                      >
                        启动更新素材
                      </Button>
                    </Space>
                  </Col>
                </Row>
                {previewSync.error ? <Alert type="error" showIcon message={(previewSync.error as Error).message} /> : null}
                <SummaryPanel result={syncPreviewResult} loading={previewSync.isPending} detailsCollapsed showArtifactPath={false} showRawJson={false} />
                {runSync.error ? <Alert type="error" showIcon message={(runSync.error as Error).message} /> : null}
                <InlineTaskStatus
                  title="当前资料同步任务"
                  taskId={syncTaskId}
                  workflow="gravity_material_sync"
                  result={syncRunResult}
                  detail={syncTaskDetail.data}
                  loading={runSync.isPending || syncTaskDetail.isFetching}
                  returnTo="/gravity-materials"
                />
              </Space>
            </Card>
            <Card size="small" title={stepTitle("3", "本地素材库")}>
              <Space direction="vertical" size="middle" className="full-width">
                {!hasBinding ? <Alert type="info" showIcon message="先在左侧保存产品和引力专辑/文件夹绑定；绑定后再更新引力素材。" /> : null}
                {hasBinding && totalMaterials === 0 ? (
                  <Alert
                    type="info"
                    showIcon
                    message={
                      syncBusy
                        ? "正在更新引力素材。完成后这里会自动刷新本地素材库。"
                        : isTaskCompleted(syncTaskCurrentStatus)
                          ? "刚刚更新完成，但本地仍没有素材。请查看第 2 步结果，重点看绑定范围、扫描文件夹数和发现素材数。"
                          : "已经有绑定，但本地还没有引力素材资料。下一步运行“更新引力素材”。"
                    }
                    action={
                      <Space wrap>
                        <Button
                          size="small"
                          type="primary"
                          icon={<SyncOutlined />}
                          loading={syncBusy}
                          disabled={!hasBinding || syncBusy}
                          onClick={() => void startSyncFromMaterialList()}
                        >
                          立即更新引力素材
                        </Button>
                        <Button size="small" onClick={scrollToSyncCard}>
                          查看第 2 步详情
                        </Button>
                      </Space>
                    }
                  />
                ) : null}
                <Alert
                  type="info"
                  showIcon
                  message="这里只展示可铺货素材：引力状态不是禁用、本地未停用、没有拒审、并且有 MD5。禁用素材不会出现在这张表里。"
                />
                <Row gutter={[12, 12]}>
                  <Col xs={24} md={16}>
                    <Space direction="vertical" size={4} className="full-width">
                      <Typography.Text strong>搜索素材</Typography.Text>
                      <Input.Search
                        value={keyword}
                        onChange={(event) => {
                          setKeyword(event.target.value);
                          setMaterialPagination((current) => ({ ...current, current: 1 }));
                        }}
                        placeholder="搜索素材名 / 引力素材 ID / MD5"
                      />
                    </Space>
                  </Col>
                </Row>
                <Table<MaterialRow>
                  className={businessTableClassName("gravity-materials-table")}
                  rowKey={(row) => String(row["引力素材 ID"] ?? "")}
                  loading={materials.isLoading}
                  size="small"
                  columns={materialColumns()}
                  dataSource={materialRows}
                  sticky={businessTableSticky}
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
                  scroll={businessTableScrollX}
                  pagination={{
                    current: materialPagination.current,
                    pageSize: materialPagination.pageSize,
                    total: materialTotal,
                    showSizeChanger: true,
                    pageSizeOptions: TABLE_PAGE_SIZE_OPTIONS,
                    showTotal: (total) => `可铺货素材 ${total} 条`,
                  }}
                  onChange={(pagination, _filters, sorter) => {
                    setMaterialPagination({
                      current: pagination.current ?? 1,
                      pageSize: pagination.pageSize ?? DEFAULT_TABLE_PAGE_SIZE,
                    });
                    const currentSorter = (Array.isArray(sorter) ? sorter[0] : sorter) as SorterResult<MaterialRow>;
                    if (currentSorter?.order) {
                      setMaterialSort({
                        sortBy: String(currentSorter.field ?? currentSorter.columnKey ?? "引力创建时间"),
                        sortOrder: currentSorter.order,
                      });
                    }
                  }}
                />
              </Space>
            </Card>
            <Card
              size="small"
              title={
                <Space wrap>
                  {stepTitle("4", "提前铺货到巨量账户")}
                  <Tag color="orange">真实媒体动作</Tag>
                </Space>
              }
              className="gravity-upload-card"
            >
              <Space direction="vertical" size="middle" className="full-width">
                <Alert
                  type="info"
                  showIcon
                  message="系统会自动使用产品账户库里负责人为郭靖的启用账户，以及本地素材库里可铺货的引力素材，生成提前铺货预览；不会创建广告、不会改预算、不会启动投放。"
                />
                <Row gutter={[12, 12]} align="bottom">
                  <Col xs={24} md={8}>
                    <Typography.Text strong>铺货范围</Typography.Text>
                    <div className="gravity-preload-stats">
                      <Tag color="blue">郭靖启用账户 {uploadAccountOptions.length}</Tag>
                      <Tag color="green">可铺货素材 {totalMaterials}</Tag>
                      <Tag color="default">50 条/批</Tag>
                    </div>
                    <Typography.Text type="secondary" className="gravity-upload-help">
                      停用账户、非郭靖负责人账户不会进入预览；历史补全账户会在明细里标出来源。
                    </Typography.Text>
                  </Col>
                  <Col xs={24} md={8}>
                    <Typography.Text strong>引力 Token 文件</Typography.Text>
                    <Input className="gravity-upload-control" value={authFile} onChange={(event) => setAuthFile(event.target.value)} />
                    <Typography.Text type="secondary" className="gravity-upload-help">
                      仅固定脚本读取，不在页面展示 token 明文。
                    </Typography.Text>
                  </Col>
                  <Col xs={24} md={8}>
                    <Space wrap className="gravity-upload-actions">
                      <Button
                        icon={<FileSearchOutlined />}
                        loading={preloadPreview.isPending}
                        disabled={!canPreviewPreload}
                        onClick={() => preloadPreview.mutate()}
                      >
                        生成提前铺货预览
                      </Button>
                    </Space>
                  </Col>
                </Row>
                <details className="gravity-advanced-panel">
                  <summary>手动指定账户和素材（高级）</summary>
                  <Space direction="vertical" size="middle" className="full-width">
                    <Alert
                      type={selectedUploadMaterialIds.length && targetAccountIds.length ? "warning" : "info"}
                      showIcon
                      message={
                        selectedUploadMaterialIds.length && targetAccountIds.length
                          ? "这一步会把已选引力素材推送到所选巨量账户素材库。生成预览后必须核对账户名、账户 ID、素材 ID、MD5；真实推送前还要输入“确认执行”。"
                          : "只在需要临时指定少量账户或素材时使用；日常建议直接生成提前铺货预览。"
                      }
                    />
                    <Row gutter={[12, 12]} align="bottom">
                      <Col xs={24} md={12}>
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
                          账户来自产品账户库，只展示负责人为郭靖的启用账户；预览和结果会同时显示账户 ID 与账户名。
                        </Typography.Text>
                      </Col>
                      <Col xs={24} md={12}>
                        <Space wrap className="gravity-upload-actions">
                          <Button icon={<FileSearchOutlined />} loading={previewUpload.isPending} disabled={!canPreviewUpload} onClick={() => previewUpload.mutate()}>
                            生成指定范围预览
                          </Button>
                          <Tag color={selectedUploadMaterialIds.length ? "blue" : "default"}>已选素材 {selectedUploadMaterialIds.length}</Tag>
                        </Space>
                      </Col>
                    </Row>
                  </Space>
                </details>
                {!selectedProduct ? <Alert type="info" showIcon message="先在左侧选择产品，再生成提前铺货预览。" /> : null}
                {preloadPreview.error ? <Alert type="error" showIcon message={(preloadPreview.error as Error).message} /> : null}
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
                          buttonText={isPreloadPreview ? "确认并铺货素材" : "确认并推送素材"}
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
              title="当前推送任务"
              taskId={uploadTaskId}
              workflow="gravity_upload_to_account"
              result={uploadExecuteResult}
              detail={uploadTaskDetail.data}
              loading={executeUpload.isPending || uploadTaskDetail.isFetching}
              returnTo="/gravity-materials"
            />
            {gravityTaskIds.length || uploadStatus.data || uploadStatusRefreshResult ? (
              <Card size="small" title="推送状态复盘" className="gravity-upload-card">
                <Space direction="vertical" size="middle" className="full-width">
                  <Alert
                    type="info"
                    showIcon
                    message="推送是异步任务。刷新状态只查询引力 task，并在本地素材库已同步到合法媒体素材 ID 后回填账本；不会再次推送素材。"
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

function renderAlbumSelectOptions(groups: AlbumChoiceGroup[]): AlbumSelectOption[] {
  return groups.map((group) => ({
    label: <span className="gravity-album-select-group">专辑：{group.label}</span>,
    searchText: group.targetAlbum,
    options: group.options.map((option) => ({
      value: option.value,
      searchText: option.searchText,
      label: (
        <Space direction="vertical" size={0} className="gravity-album-select-option">
          <Space size={8} wrap>
            <Tag color={option.optionType === "album" ? "blue" : "default"}>{option.optionType === "album" ? "专辑" : "文件夹"}</Tag>
            <Typography.Text>{option.label}</Typography.Text>
          </Space>
          <Typography.Text type="secondary">{option.subLabel}</Typography.Text>
        </Space>
      ),
    })),
  }));
}

function targetAlbumRowsFromResult(result?: ChineseResult): TargetAlbumRow[] {
  return Array.isArray(result?.raw?.target_albums) ? (result.raw.target_albums as TargetAlbumRow[]) : [];
}

function bindingRowsFromResult(result?: ChineseResult): BindingRow[] {
  return Array.isArray(result?.raw?.bindings) ? (result.raw.bindings as BindingRow[]) : [];
}

function readinessNextActionTitle(result?: ChineseResult): string {
  const nextAction = result?.raw?.next_action;
  if (!nextAction || typeof nextAction !== "object") {
    return "";
  }
  const title = (nextAction as { title?: unknown }).title;
  return typeof title === "string" ? title : "";
}

function scrollToSyncCard() {
  document.getElementById("gravity-sync-card")?.scrollIntoView({ behavior: "smooth", block: "start" });
}

function stepTitle(step: string, title: ReactNode) {
  return (
    <Space size={10} className="gravity-step-title">
      <span className="gravity-step-number">{step}</span>
      <span>{title}</span>
    </Space>
  );
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
      const status = String(row["状态"] ?? "").trim();
      const owner = String(row["负责人"] ?? "").trim();
      const active = !status || status === "active" || status === "启用";
      return active && owner === GRAVITY_PRELOAD_TARGET_OWNER && (!selectedProduct || product === selectedProduct || productKey === selectedProduct);
    })
    .map((row) => {
      const value = String(row["账户 ID"] ?? "").trim();
      const accountName = String(row["账户名"] ?? value).trim();
      const product = String(row["产品"] ?? "").trim();
      const status = String(row["状态"] ?? "").trim();
      const owner = String(row["负责人"] ?? "").trim();
      return {
        value,
        account_name: accountName || value,
        product,
        status,
        label: `${accountName || value}（${value}） · ${owner || "未填负责人"}${status ? ` · ${status}` : ""}`,
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

function targetAlbumStatusColor(value: unknown): string {
  const text = String(value || "");
  if (text === "已匹配") {
    return "green";
  }
  if (text === "多个匹配") {
    return "orange";
  }
  return "red";
}

function canSelectUploadMaterial(row: MaterialRow): boolean {
  return Boolean(String(row["引力素材 ID"] ?? "").trim()) && Boolean(String(row["MD5"] ?? "").trim());
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

function statNumber(value: string | number | boolean | null | undefined): number {
  const parsed = Number(value ?? 0);
  return Number.isFinite(parsed) ? parsed : 0;
}

function materialTotalFromResult(result: ChineseResult | undefined, fallback: number): number {
  const total = Number((result?.raw?.pagination as { total?: unknown } | undefined)?.total ?? fallback);
  return Number.isFinite(total) ? total : fallback;
}

function materialColumns(): ColumnsType<MaterialRow> {
  return [
    { title: "专辑", dataIndex: "专辑", width: 180, sorter: true },
    { title: "素材名", dataIndex: "素材名", width: 260, ellipsis: true, sorter: true },
    { title: "7天消耗", dataIndex: "7天消耗", width: 112, sorter: true, render: renderEmpty },
    { title: "7天转化", dataIndex: "7天转化", width: 112, sorter: true, render: renderEmpty },
    { title: "30天消耗", dataIndex: "30天消耗", width: 120, sorter: true, render: renderEmpty },
    { title: "30天转化", dataIndex: "30天转化", width: 120, sorter: true, render: renderEmpty },
    { title: "引力素材 ID", dataIndex: "引力素材 ID", width: 160, ellipsis: true, sorter: true },
    { title: "MD5", dataIndex: "MD5", width: 180, ellipsis: true, sorter: true, render: renderEmpty },
    { title: "引力创建时间", dataIndex: "引力创建时间", width: 190, sorter: true, render: renderEmpty },
    { title: "最近同步时间", dataIndex: "最近同步时间", width: 190, sorter: true, render: renderEmpty },
    { title: "推送覆盖情况", dataIndex: "推送覆盖情况", width: 170, render: renderEmpty },
    { title: "文件夹", dataIndex: "文件夹", width: 160, ellipsis: true, sorter: true, render: renderEmpty },
  ];
}

function renderEmpty(value: unknown) {
  return value === undefined || value === null || value === "" ? <Typography.Text type="secondary">-</Typography.Text> : String(value);
}
