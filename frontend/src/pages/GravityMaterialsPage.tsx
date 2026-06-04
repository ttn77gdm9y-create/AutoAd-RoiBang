import { DeleteOutlined, ReloadOutlined, SaveOutlined, SyncOutlined } from "@ant-design/icons";
import { Alert, Button, Card, Col, Form, Input, Row, Select, Space, Table, Tag, Typography, message as antdMessage } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { apiDelete, apiGet, apiPost } from "../api/client";
import { SummaryPanel } from "../components/SummaryPanel";
import type { ChineseResult } from "../types/api";

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

const emptyBinding: BindingForm = {
  product: "",
  album_id: "",
  album_name: "",
  folder_id: "",
  folder_name: "",
};

export function GravityMaterialsPage() {
  const queryClient = useQueryClient();
  const [selectedProduct, setSelectedProduct] = useState("");
  const [statusFilter, setStatusFilter] = useState("active");
  const [keyword, setKeyword] = useState("");
  const [bindingForm, setBindingForm] = useState<BindingForm>(emptyBinding);
  const [saveResult, setSaveResult] = useState<ChineseResult | undefined>();
  const [deleteResult, setDeleteResult] = useState<ChineseResult | undefined>();

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
  const materialRows = materials.data?.table.rows ?? [];

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

  function selectProduct(product: string) {
    setSelectedProduct(product);
    setBindingForm((current) => ({ ...current, product }));
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
            <Card size="small" title="素材列表">
              <Space direction="vertical" size="middle" className="full-width">
                <Row gutter={[12, 12]}>
                  <Col xs={24} md={8}>
                    <Select
                      className="full-width"
                      value={statusFilter}
                      options={[
                        { label: "只看可用素材", value: "active" },
                        { label: "只看停用素材", value: "inactive" },
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
                  scroll={{ x: "max-content" }}
                  pagination={{ pageSize: 20, showSizeChanger: true }}
                />
              </Space>
            </Card>
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

function materialColumns(): ColumnsType<MaterialRow> {
  return [
    { title: "产品", dataIndex: "产品", width: 120 },
    { title: "专辑", dataIndex: "专辑", width: 140 },
    { title: "文件夹", dataIndex: "文件夹", width: 140 },
    { title: "素材名", dataIndex: "素材名", width: 180 },
    { title: "引力素材 ID", dataIndex: "引力素材 ID", width: 160 },
    { title: "MD5", dataIndex: "MD5", width: 180 },
    {
      title: "状态",
      dataIndex: "状态",
      width: 88,
      render: (value) => <Tag color={String(value) === "可用" ? "green" : "orange"}>{String(value || "未知")}</Tag>,
    },
    { title: "消耗", dataIndex: "消耗", width: 92 },
    { title: "展示", dataIndex: "展示", width: 92 },
    { title: "点击", dataIndex: "点击", width: 92 },
    { title: "转化", dataIndex: "转化", width: 92 },
    { title: "同步时间", dataIndex: "同步时间", width: 180 },
  ];
}
