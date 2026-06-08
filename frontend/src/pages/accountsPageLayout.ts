import type { TablePaginationConfig } from "antd/es/table";

export const accountTableScroll = { x: 1420 };

export const accountTablePagination: TablePaginationConfig = {
  pageSize: 20,
  showSizeChanger: true,
  pageSizeOptions: ["20", "50", "100"],
  position: ["bottomLeft"],
  showTotal: (total: number) => `当前 ${total} 个账户`,
};
