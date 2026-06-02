import { Alert, Col, DatePicker, Drawer, Form, Row, Select, Statistic, Tabs, Typography } from "antd";
import { useQuery } from "@tanstack/react-query";
import dayjs from "dayjs";
import type { Dayjs } from "dayjs";
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { apiGet } from "../api/client";
import { SummaryPanel } from "../components/SummaryPanel";
import type { ChineseResult } from "../types/api";

const metrics = [
  "今日消耗",
  "计费转化",
  "转化成本",
  "付费 ROI",
  "活跃账户",
  "活跃项目",
  "异常项目",
  "建议事项",
];

const dashboardTabKeys = new Set(["products", "accounts", "projects", "materials", "suggestions"]);

export function DashboardPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [filters, setFilters] = useState({
    product_key: searchParams.get("product_key") ?? "",
    channel: searchParams.get("channel") ?? "",
    owner: searchParams.get("owner") ?? "",
    status: searchParams.get("status") ?? "",
    date_range: searchParams.get("date_range") ?? "",
    start_date: searchParams.get("start_date") ?? "",
    end_date: searchParams.get("end_date") ?? "",
  });
  const defaultProductApplied = useRef(false);
  const [selectedAdvertiserId, setSelectedAdvertiserId] = useState("");
  const [selectedAdvertiserLabel, setSelectedAdvertiserLabel] = useState("");
  const [selectedProductKey, setSelectedProductKey] = useState("");
  const [selectedProductLabel, setSelectedProductLabel] = useState("");
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [selectedProjectLabel, setSelectedProjectLabel] = useState("");
  const [selectedMaterialId, setSelectedMaterialId] = useState("");
  const [selectedMaterialLabel, setSelectedMaterialLabel] = useState("");
  const querySuffix = useMemo(() => {
    const params = new URLSearchParams();
    Object.entries(filters).forEach(([key, value]) => {
      if (value) {
        params.set(key, value);
      }
    });
    const value = params.toString();
    return value ? `?${value}` : "";
  }, [filters]);
  const detailDateSuffix = useMemo(() => {
    const params = new URLSearchParams();
    ["date_range", "start_date", "end_date"].forEach((key) => {
      const value = filters[key as keyof typeof filters];
      if (value) {
        params.set(key, value);
      }
    });
    const value = params.toString();
    return value ? `?${value}` : "";
  }, [filters.date_range, filters.start_date, filters.end_date]);
  const filterCatalog = useQuery({
    queryKey: ["dashboard", "filters"],
    queryFn: () => apiGet<ChineseResult>("/dashboard/filters"),
  });
  const { data, error, isLoading } = useQuery({
    queryKey: ["dashboard", "overview", filters],
    queryFn: () => apiGet<ChineseResult>(`/dashboard/overview${querySuffix}`),
  });
  const projects = useQuery({
    queryKey: ["dashboard", "projects", filters],
    queryFn: () => apiGet<ChineseResult>(`/dashboard/projects${querySuffix}`),
  });
  const accounts = useQuery({
    queryKey: ["dashboard", "accounts", filters],
    queryFn: () => apiGet<ChineseResult>(`/dashboard/accounts${querySuffix}`),
  });
  const suggestions = useQuery({
    queryKey: ["dashboard", "suggestions", filters],
    queryFn: () => apiGet<ChineseResult>(`/dashboard/suggestions${querySuffix}`),
  });
  const materials = useQuery({
    queryKey: ["dashboard", "materials", filters],
    queryFn: () => apiGet<ChineseResult>(`/dashboard/materials${querySuffix}`),
  });
  const accountDetail = useQuery({
    queryKey: ["dashboard", "account-detail", selectedAdvertiserId, detailDateSuffix],
    queryFn: () => apiGet<ChineseResult>(`/dashboard/accounts/${encodeURIComponent(selectedAdvertiserId)}${detailDateSuffix}`),
    enabled: Boolean(selectedAdvertiserId),
  });
  const productDetail = useQuery({
    queryKey: ["dashboard", "product-detail", selectedProductKey, detailDateSuffix],
    queryFn: () => apiGet<ChineseResult>(`/dashboard/products/${encodeURIComponent(selectedProductKey)}${detailDateSuffix}`),
    enabled: Boolean(selectedProductKey),
  });
  const projectDetail = useQuery({
    queryKey: ["dashboard", "project-detail", selectedProjectId, detailDateSuffix],
    queryFn: () => apiGet<ChineseResult>(`/dashboard/projects/${encodeURIComponent(selectedProjectId)}${detailDateSuffix}`),
    enabled: Boolean(selectedProjectId),
  });
  const materialDetail = useQuery({
    queryKey: ["dashboard", "material-detail", selectedMaterialId, detailDateSuffix],
    queryFn: () => apiGet<ChineseResult>(`/dashboard/materials/${encodeURIComponent(selectedMaterialId)}${detailDateSuffix}`),
    enabled: Boolean(selectedMaterialId),
  });
  const summaryValues = new Map(data?.summary.items.map((item) => [item.label, item.value]) ?? []);
  const filterOptions = buildFilterOptions(filterCatalog.data);
  const defaultProductKey = getDefaultProductKey(filterCatalog.data);
  const activeDashboardTab = validDashboardTab(searchParams.get("tab"));
  const projectScope = searchParams.get("project_scope") === "abnormal" ? "abnormal" : "";
  const scopedProjects = useMemo(() => withProjectScope(projects.data, projectScope), [projects.data, projectScope]);

  useEffect(() => {
    if (!defaultProductKey || defaultProductApplied.current) {
      return;
    }
    defaultProductApplied.current = true;
    setFilters((current) => (current.product_key ? current : { ...current, product_key: defaultProductKey }));
  }, [defaultProductKey]);

  function updateDashboardSearch(patch: Record<string, string | null>) {
    const next = new URLSearchParams(searchParams);
    Object.entries(patch).forEach(([key, value]) => {
      if (value) {
        next.set(key, value);
      } else {
        next.delete(key);
      }
    });
    setSearchParams(next);
  }

  function currentProductKey(): string {
    return filters.product_key || defaultProductKey;
  }

  function openAbnormalProjects() {
    updateDashboardSearch({
      product_key: currentProductKey(),
      tab: "projects",
      project_scope: "abnormal",
    });
  }

  function openSuggestionsWorkbench() {
    const params = new URLSearchParams();
    const productKey = currentProductKey();
    if (productKey) {
      params.set("product_key", productKey);
    }
    params.set("suggestion_type", "全部");
    params.set("focus", "list");
    navigate(`/suggestions?${params.toString()}`);
  }

  function metricAction(label: string): (() => void) | undefined {
    if (label === "异常项目") {
      return openAbnormalProjects;
    }
    if (label === "建议事项") {
      return openSuggestionsWorkbench;
    }
    return undefined;
  }

  return (
    <main className="page">
      <Typography.Title level={2}>首页数据看板</Typography.Title>
      <Alert
        type="info"
        showIcon
        message="先看整体指标和异常建议；点击表格行可以查看对应产品、账户、项目或单元详情。"
        className="page-alert"
      />
      {error ? <Alert type="error" showIcon message={(error as Error).message} className="page-alert" /> : null}
      <Form layout="inline" className="filter-bar">
        <Form.Item label="产品">
          <Select
            allowClear
            className="dashboard-filter-select"
            loading={filterCatalog.isLoading}
            value={filters.product_key || undefined}
            onChange={(value) => {
              const nextProductKey = value ?? "";
              setFilters({ ...filters, product_key: nextProductKey });
              updateDashboardSearch({ product_key: nextProductKey || null });
            }}
            options={filterOptions.products}
          />
        </Form.Item>
        <Form.Item label="渠道">
          <Select
            allowClear
            className="dashboard-filter-select"
            value={filters.channel || undefined}
            onChange={(value) => setFilters({ ...filters, channel: value ?? "" })}
            options={filterOptions.channels}
          />
        </Form.Item>
        <Form.Item label="负责人">
          <Select
            allowClear
            className="dashboard-filter-select"
            value={filters.owner || undefined}
            onChange={(value) => setFilters({ ...filters, owner: value ?? "" })}
            options={filterOptions.owners}
          />
        </Form.Item>
        <Form.Item label="状态">
          <Select
            allowClear
            className="status-select"
            value={filters.status || undefined}
            onChange={(value) => setFilters({ ...filters, status: value ?? "" })}
            options={[
              { label: "启用", value: "active" },
              { label: "暂停", value: "paused" },
              { label: "停用", value: "disabled" },
            ]}
          />
        </Form.Item>
        <Form.Item label="日期">
          <Select
            className="status-select"
            value={filters.date_range || undefined}
            placeholder="最近一次"
            options={[
              { label: "最近一次", value: "" },
              { label: "今天", value: "today" },
              { label: "昨天", value: "yesterday" },
              { label: "近 3 天", value: "last_3_days" },
              { label: "近 7 天", value: "last_7_days" },
              { label: "近 30 天", value: "last_30_days" },
              { label: "自定义", value: "custom" },
            ]}
            onChange={(value) => setFilters({ ...filters, ...datePresetToFilter(value ?? "") })}
          />
        </Form.Item>
        <Form.Item label="自定义日期">
          <DatePicker.RangePicker
            disabled={filters.date_range !== "custom"}
            value={datePickerValue(filters.start_date, filters.end_date)}
            onChange={(_, dateStrings) =>
              setFilters({
                ...filters,
                date_range: "custom",
                start_date: dateStrings[0],
                end_date: dateStrings[1],
              })
            }
          />
        </Form.Item>
      </Form>
      <Row gutter={[16, 16]} className="metric-grid">
        {metrics.map((label) => {
          const action = metricAction(label);
          const content = <Statistic title={label} value={formatMetricValue(summaryValues.get(label))} loading={isLoading} />;
          return (
            <Col xs={24} sm={12} lg={6} key={label}>
              {action ? (
                <button type="button" className="metric-tile metric-tile-clickable" onClick={action}>
                  {content}
                </button>
              ) : (
                <div className="metric-tile">{content}</div>
              )}
            </Col>
          );
        })}
      </Row>
      <Tabs
        activeKey={activeDashboardTab}
        onChange={(key) => {
          updateDashboardSearch({
            product_key: currentProductKey(),
            tab: key,
            project_scope: key === "projects" ? projectScope || null : null,
          });
        }}
        items={[
          {
            key: "products",
            label: "产品汇总",
            children: (
              <SummaryPanel
                result={data}
                loading={isLoading}
                onRowClick={(row) => {
                  const productName = String(row["产品"] ?? "");
                  const productKey = filterOptions.products.find((option) => option.label === productName)?.value ?? "";
                  if (productKey) {
                    setSelectedProductLabel(productName);
                    setSelectedProductKey(productKey);
                  }
                }}
                showArtifactPath={false}
                showRawJson={false}
              />
            ),
          },
          {
            key: "accounts",
            label: "账户明细",
            children: (
              <SummaryPanel
                result={accounts.data}
                loading={accounts.isLoading}
                sortableColumns={["消耗"]}
                defaultSort={{ column: "消耗", order: "descend" }}
                onRowClick={(row) => {
                  const advertiserId = String(row["账户 ID"] ?? "");
                  if (advertiserId) {
                    setSelectedAdvertiserLabel(String(row["账户名"] ?? row["账户"] ?? advertiserId));
                    setSelectedAdvertiserId(advertiserId);
                  }
                }}
                showArtifactPath={false}
                showRawJson={false}
              />
            ),
          },
          {
            key: "projects",
            label: projectScope === "abnormal" ? "异常项目" : "项目明细",
            children: (
              <SummaryPanel
                result={scopedProjects}
                loading={projects.isLoading}
                sortableColumns={["消耗"]}
                defaultSort={{ column: "消耗", order: "descend" }}
                onRowClick={(row) => {
                  const projectId = String(row["项目 ID"] ?? "");
                  if (projectId) {
                    setSelectedProjectLabel(String(row["项目名"] ?? row["项目"] ?? projectId));
                    setSelectedProjectId(projectId);
                  }
                }}
                showArtifactPath={false}
                showRawJson={false}
              />
            ),
          },
          {
            key: "materials",
            label: "单元素材",
            children: (
              <SummaryPanel
                result={materials.data}
                loading={materials.isLoading}
                sortableColumns={["消耗"]}
                defaultSort={{ column: "消耗", order: "descend" }}
                onRowClick={(row) => {
                  const materialId = String(row["单元 ID"] ?? "");
                  if (materialId) {
                    setSelectedMaterialLabel(String(row["单元名"] ?? row["项目名"] ?? materialId));
                    setSelectedMaterialId(materialId);
                  }
                }}
                showArtifactPath={false}
                showRawJson={false}
              />
            ),
          },
          {
            key: "suggestions",
            label: "异常与建议中心",
            children: (
              <SummaryPanel
                result={suggestions.data}
                loading={suggestions.isLoading}
                onRowClick={(row) => {
                  const projectId = String(row["项目 ID"] ?? "");
                  const advertiserId = String(row["账户 ID"] ?? "");
                  if (projectId) {
                    setSelectedProjectLabel(String(row["项目名"] ?? row["项目"] ?? projectId));
                    setSelectedProjectId(projectId);
                  } else if (advertiserId) {
                    setSelectedAdvertiserLabel(String(row["账户名"] ?? row["账户"] ?? advertiserId));
                    setSelectedAdvertiserId(advertiserId);
                  }
                }}
                showArtifactPath={false}
                showRawJson={false}
              />
            ),
          },
        ]}
      />
      <Drawer
        title={selectedAdvertiserId ? `账户详情：${selectedAdvertiserLabel || selectedAdvertiserId}（${selectedAdvertiserId}）` : "账户详情"}
        open={Boolean(selectedAdvertiserId)}
        onClose={() => {
          setSelectedAdvertiserId("");
          setSelectedAdvertiserLabel("");
        }}
        width={1040}
        destroyOnClose
      >
        {accountDetail.error ? (
          <Alert type="error" showIcon message={(accountDetail.error as Error).message} className="page-alert" />
        ) : null}
        <SummaryPanel result={accountDetail.data} loading={accountDetail.isFetching} showArtifactPath={false} showRawJson={false} />
      </Drawer>
      <Drawer
        title={selectedProductKey ? `产品详情：${selectedProductLabel || selectedProductKey}（${selectedProductKey}）` : "产品详情"}
        open={Boolean(selectedProductKey)}
        onClose={() => {
          setSelectedProductKey("");
          setSelectedProductLabel("");
        }}
        width={1040}
        destroyOnClose
      >
        {productDetail.error ? (
          <Alert type="error" showIcon message={(productDetail.error as Error).message} className="page-alert" />
        ) : null}
        <SummaryPanel result={productDetail.data} loading={productDetail.isFetching} showArtifactPath={false} showRawJson={false} />
      </Drawer>
      <Drawer
        title={selectedProjectId ? `项目详情：${selectedProjectLabel || selectedProjectId}（${selectedProjectId}）` : "项目详情"}
        open={Boolean(selectedProjectId)}
        onClose={() => {
          setSelectedProjectId("");
          setSelectedProjectLabel("");
        }}
        width={1040}
        destroyOnClose
      >
        {projectDetail.error ? (
          <Alert type="error" showIcon message={(projectDetail.error as Error).message} className="page-alert" />
        ) : null}
        <SummaryPanel result={projectDetail.data} loading={projectDetail.isFetching} showArtifactPath={false} showRawJson={false} />
      </Drawer>
      <Drawer
        title={selectedMaterialId ? `单元素材详情：${selectedMaterialLabel || selectedMaterialId}（${selectedMaterialId}）` : "单元素材详情"}
        open={Boolean(selectedMaterialId)}
        onClose={() => {
          setSelectedMaterialId("");
          setSelectedMaterialLabel("");
        }}
        width={1040}
        destroyOnClose
      >
        {materialDetail.error ? (
          <Alert type="error" showIcon message={(materialDetail.error as Error).message} className="page-alert" />
        ) : null}
        <SummaryPanel result={materialDetail.data} loading={materialDetail.isFetching} showArtifactPath={false} showRawJson={false} />
      </Drawer>
    </main>
  );
}

function formatMetricValue(value: unknown): string | number {
  if (typeof value === "number" || typeof value === "string") {
    return value;
  }
  return "-";
}

function buildFilterOptions(result?: ChineseResult) {
  const rows = result?.table.rows ?? [];
  return {
    products: rowsToOptions(rows, "产品"),
    channels: rowsToOptions(rows, "渠道"),
    owners: rowsToOptions(rows, "负责人"),
  };
}

function getDefaultProductKey(result?: ChineseResult): string {
  const value = result?.raw?.default_product_key;
  return typeof value === "string" ? value : "";
}

function validDashboardTab(value: string | null): string {
  return value && dashboardTabKeys.has(value) ? value : "products";
}

function withProjectScope(result: ChineseResult | undefined, scope: string): ChineseResult | undefined {
  if (!result || scope !== "abnormal") {
    return result;
  }
  const rows = result.table.rows.filter((row) => row["是否异常"] === true || row["是否异常"] === "是");
  return {
    ...result,
    summary: {
      ...result.summary,
      title: "异常项目明细",
      items: result.summary.items.map((item) => {
        if (item.label === "项目数" || item.label === "异常项目") {
          return { ...item, value: rows.length };
        }
        return item;
      }),
    },
    table: {
      ...result.table,
      rows,
    },
  };
}

function rowsToOptions(rows: ChineseResult["table"]["rows"], type: string) {
  return rows
    .filter((row) => row["类型"] === type)
    .map((row) => ({
      label: String(row["显示名称"] ?? row["值"] ?? ""),
      value: String(row["值"] ?? ""),
    }));
}

function datePresetToFilter(value: string) {
  if (!value) {
    return { date_range: "", start_date: "", end_date: "" };
  }
  if (value === "custom") {
    return { date_range: "custom", start_date: "", end_date: "" };
  }
  const today = new Date();
  const end = toDateString(today);
  if (value === "today") {
    return { date_range: value, start_date: end, end_date: end };
  }
  if (value === "yesterday") {
    const yesterday = addDays(today, -1);
    const day = toDateString(yesterday);
    return { date_range: value, start_date: day, end_date: day };
  }
  const days = { last_3_days: 3, last_7_days: 7, last_30_days: 30 }[value as "last_3_days" | "last_7_days" | "last_30_days"];
  if (days) {
    return { date_range: value, start_date: toDateString(addDays(today, -(days - 1))), end_date: end };
  }
  return { date_range: value, start_date: "", end_date: "" };
}

function datePickerValue(startDate: string, endDate: string): [Dayjs, Dayjs] | null {
  if (!startDate || !endDate) {
    return null;
  }
  return [dayjs(startDate), dayjs(endDate)];
}

function addDays(value: Date, days: number): Date {
  const next = new Date(value);
  next.setDate(value.getDate() + days);
  return next;
}

function toDateString(value: Date): string {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}
