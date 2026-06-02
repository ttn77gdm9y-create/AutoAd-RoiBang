import { Alert, Button, Space, Typography } from "antd";
import { ReloadOutlined } from "@ant-design/icons";
import { useQuery } from "@tanstack/react-query";

import { apiGet } from "../api/client";
import { SummaryPanel } from "../components/SummaryPanel";
import type { ChineseResult } from "../types/api";

export function AutomationHealthPage() {
  const health = useQuery({
    queryKey: ["automation-health", "overview"],
    queryFn: () => apiGet<ChineseResult>("/automation-health/overview"),
    refetchInterval: 15000,
  });

  return (
    <main className="page">
      <Space direction="vertical" size="large" className="full-width">
        <div className="page-heading-row">
          <Typography.Title level={2}>每日自动化健康看板</Typography.Title>
          <Button icon={<ReloadOutlined />} onClick={() => health.refetch()} loading={health.isFetching}>
            刷新
          </Button>
        </div>
        <Alert
          type="info"
          showIcon
          message="这里只读展示定时任务、业务产物和 06:00 定时任务日报状态；不会运行任务、不会调用媒体接口、不会发送飞书。"
        />
        {health.error ? <Alert type="error" showIcon message={(health.error as Error).message} /> : null}
        <SummaryPanel
          result={health.data}
          loading={health.isLoading}
          sortableColumns={["今日运行"]}
          defaultSort={{ column: "今日运行", order: "descend" }}
          detailsCollapsed={false}
        />
      </Space>
    </main>
  );
}
