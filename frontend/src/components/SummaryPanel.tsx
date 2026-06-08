import { Alert, Collapse, Descriptions, Empty, Progress, Space, Table, Tabs, Tag, Typography } from "antd";
import type { TableProps } from "antd";
import type { ColumnsType } from "antd/es/table";
import type { KeyboardEvent } from "react";
import type { ReactNode } from "react";
import { useEffect, useState } from "react";

import type { ChineseResult } from "../types/api";
import { RawJsonDrawer } from "./RawJsonDrawer";

type SummaryRow = ChineseResult["table"]["rows"][number];

type SummaryPanelProps = {
  result?: ChineseResult;
  loading?: boolean;
  onRowClick?: (row: SummaryRow) => void;
  detailsCollapsed?: boolean;
  sortableColumns?: string[];
  defaultSort?: { column: string; order: "ascend" | "descend" };
  showArtifactPath?: boolean;
  showRawJson?: boolean;
  footer?: ReactNode;
};

type KeyedSummaryRow = SummaryRow & { __row_key: string };

type PagedSummaryTableProps = {
  columns: ColumnsType<KeyedSummaryRow>;
  dataSource: KeyedSummaryRow[];
  loading?: boolean;
  rowClassName?: string;
  onRow?: TableProps<KeyedSummaryRow>["onRow"];
};

const riskColor: Record<string, string> = {
  low: "green",
  medium: "orange",
  high: "red",
};

const riskLabel: Record<string, string> = {
  low: "低",
  medium: "中",
  high: "高",
};

const statusLabel: Record<string, string> = {
  blocked: "已阻塞",
  committed: "已写入",
  completed: "已完成",
  draft_only: "仅草稿",
  empty: "暂无结果",
  failed: "失败",
  loaded: "已加载",
  not_found: "未找到",
  planned: "已生成计划",
  queued: "排队中",
  ready: "待确认",
  ready_for_confirmation: "可确认",
  running: "运行中",
  split_required: "需拆分",
  success: "成功",
  succeeded: "成功",
  trial_ready: "试用就绪",
  warning: "需关注",
  warning_only: "有警告",
};

function progressStatus(status?: string): "normal" | "active" | "exception" | "success" {
  if (status === "active" || status === "exception" || status === "success") {
    return status;
  }
  return "normal";
}

function withRowKeys(rows: SummaryRow[], prefix: string): KeyedSummaryRow[] {
  return rows.map((row, index) => ({ ...row, __row_key: `${prefix}-${index}-${JSON.stringify(row)}` }));
}

function sortableValue(value: SummaryRow[string]): number | string {
  if (typeof value === "number") {
    return value;
  }
  const text = String(value ?? "").trim();
  const numberValue = Number(text.replace(/,/g, "").replace("%", ""));
  return Number.isFinite(numberValue) && text ? numberValue : text;
}

function compareSortableValues(left: SummaryRow[string], right: SummaryRow[string]): number {
  const leftValue = sortableValue(left);
  const rightValue = sortableValue(right);
  if (typeof leftValue === "number" && typeof rightValue === "number") {
    return leftValue - rightValue;
  }
  if (typeof leftValue === "number") {
    return 1;
  }
  if (typeof rightValue === "number") {
    return -1;
  }
  return leftValue.localeCompare(rightValue, "zh-Hans-CN");
}

function PagedSummaryTable({ columns, dataSource, loading = false, rowClassName = "", onRow }: PagedSummaryTableProps) {
  const [pagination, setPagination] = useState({ current: 1, pageSize: 20 });

  useEffect(() => {
    setPagination((current) => {
      const maxPage = Math.max(1, Math.ceil(dataSource.length / current.pageSize));
      return current.current > maxPage ? { ...current, current: maxPage } : current;
    });
  }, [dataSource.length]);

  return (
    <Table<KeyedSummaryRow>
      rowKey="__row_key"
      loading={loading}
      columns={columns}
      dataSource={dataSource}
      pagination={{
        ...pagination,
        showSizeChanger: true,
        pageSizeOptions: ["10", "20", "50", "100"],
        onChange: (current, pageSize) => setPagination({ current, pageSize }),
        onShowSizeChange: (_current, pageSize) => setPagination({ current: 1, pageSize }),
      }}
      size="small"
      scroll={{ x: "max-content" }}
      rowClassName={rowClassName}
      onRow={onRow}
    />
  );
}

export function SummaryPanel({
  result,
  loading = false,
  onRowClick,
  detailsCollapsed = false,
  sortableColumns = [],
  defaultSort,
  showArtifactPath = true,
  showRawJson = true,
  footer,
}: SummaryPanelProps) {
  if (!result && !loading) {
    return <Empty description="暂无结果" />;
  }

  const sortableColumnSet = new Set(sortableColumns);
  const columns: ColumnsType<KeyedSummaryRow> = (result?.table.columns ?? []).map((column) => {
    const sortable = sortableColumnSet.has(column);
    return {
      title: column,
      dataIndex: column,
      key: column,
      ellipsis: true,
      sorter: sortable ? (left, right) => compareSortableValues(left[column], right[column]) : undefined,
      defaultSortOrder: defaultSort?.column === column ? defaultSort.order : undefined,
      sortDirections: sortable ? ["descend", "ascend"] : undefined,
    };
  });
  const tableRows = withRowKeys(result?.table.rows ?? [], "main");
  const sectionItems = (result?.sections ?? []).map((section) => {
    const sectionColumns: ColumnsType<KeyedSummaryRow> = section.table.columns.map((column) => ({
      title: column,
      dataIndex: column,
      key: column,
      ellipsis: true,
    }));
    const sectionRows = withRowKeys(section.table.rows, section.title);
    return {
      key: section.title,
      label: section.title,
      children: (
        <PagedSummaryTable
          columns={sectionColumns}
          dataSource={sectionRows}
        />
      ),
    };
  });

  const mainTable = (
    <PagedSummaryTable
      loading={loading}
      columns={columns}
      dataSource={tableRows}
      rowClassName={onRowClick ? "summary-row-clickable" : ""}
      onRow={(record) =>
        onRowClick
          ? {
              onClick: () => onRowClick(record),
              onKeyDown: (event: KeyboardEvent<HTMLElement>) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  onRowClick(record);
                }
              },
              role: "button",
              tabIndex: 0,
            }
          : {}
      }
    />
  );
  const sectionTabs = sectionItems.length ? <Tabs items={sectionItems} /> : null;
  const details = (
    <>
      {mainTable}
      {sectionTabs}
    </>
  );
  const detailsLabel = `明细：${tableRows.length} 条${sectionItems.length ? `，${sectionItems.length} 组附加表` : ""}`;
  const executionLabel = result?.summary.execution_label || (result?.summary.execution_enabled ? "可执行" : "只读");
  const executionColor = result?.summary.execution_enabled
    ? "red"
    : executionLabel.includes("未执行") || executionLabel.includes("已阻止")
      ? "orange"
      : "blue";

  return (
    <section className="summary-panel">
      <div className="summary-header">
        <div>
          <Typography.Title level={3}>{result?.summary.title ?? "加载中"}</Typography.Title>
          {result ? (
            <div className="summary-tags">
              <Tag>{statusLabel[result.summary.status] ?? result.summary.status}</Tag>
              <Tag color={riskColor[result.summary.risk_level] ?? "default"}>
                风险：{riskLabel[result.summary.risk_level] ?? result.summary.risk_level}
              </Tag>
              <Tag color={executionColor}>{executionLabel}</Tag>
            </div>
          ) : null}
        </div>
        {result && showRawJson ? <RawJsonDrawer value={result.raw} /> : null}
      </div>

      {result?.summary.warnings.map((warning) => (
        <Alert key={warning} type="warning" showIcon message={warning} />
      ))}
      {result?.summary.blocking_reasons.map((reason) => (
        <Alert key={reason} type="error" showIcon message={reason} />
      ))}

      {result?.summary.progress?.label ? (
        <div className="summary-progress">
          <Progress
            percent={Number(result.summary.progress.percent ?? 0)}
            status={progressStatus(result.summary.progress.status)}
          />
          <Space size={8} wrap>
            <Typography.Text strong>{result.summary.progress.label}</Typography.Text>
            <Typography.Text type="secondary">{Number(result.summary.progress.percent ?? 0)}%</Typography.Text>
          </Space>
        </div>
      ) : null}

      <Descriptions bordered column={{ xs: 1, sm: 2, lg: 4 }} size="small">
        {(result?.summary.items ?? []).map((item) => (
          <Descriptions.Item key={item.label} label={item.label}>
            {String(item.value ?? "")}
          </Descriptions.Item>
        ))}
        {showArtifactPath && result?.artifact_path ? <Descriptions.Item label="结果文件">{result.artifact_path}</Descriptions.Item> : null}
      </Descriptions>

      {footer}
      {detailsCollapsed ? <Collapse items={[{ key: "details", label: detailsLabel, children: details }]} /> : details}
    </section>
  );
}
