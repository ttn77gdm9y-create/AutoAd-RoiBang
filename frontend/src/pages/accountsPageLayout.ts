import type { TablePaginationConfig } from "antd/es/table";

export const accountTableScroll = { x: 1420 };

const DEFAULT_TABLE_PAGE_SIZE = 100;
const TABLE_PAGE_SIZE_OPTIONS = ["20", "50", "100"];

export const accountTablePagination: TablePaginationConfig = {
  pageSize: DEFAULT_TABLE_PAGE_SIZE,
  showSizeChanger: true,
  pageSizeOptions: TABLE_PAGE_SIZE_OPTIONS,
  position: ["bottomLeft"],
  showTotal: (total: number) => `当前 ${total} 个账户`,
};
