import { Alert, Typography } from "antd";
import { useQuery } from "@tanstack/react-query";

import { apiGet } from "../api/client";
import { SummaryPanel } from "../components/SummaryPanel";
import type { ChineseResult } from "../types/api";

export function SystemSettingsPage() {
  const query = useQuery({
    queryKey: ["settings"],
    queryFn: () => apiGet<ChineseResult>("/settings/summary"),
  });
  const readiness = useQuery({
    queryKey: ["settings", "readiness"],
    queryFn: () => apiGet<ChineseResult>("/settings/readiness"),
  });

  return (
    <main className="page">
      <Typography.Title level={2}>系统设置</Typography.Title>
      <Alert type="info" showIcon message="这里用于查看本地服务、目录和接口健康状态；普通业务操作不需要进入本页。" className="page-alert" />
      {query.error ? <Alert type="error" showIcon message={(query.error as Error).message} /> : null}
      <SummaryPanel result={query.data} loading={query.isLoading} detailsCollapsed showArtifactPath={false} showRawJson={false} />
      {readiness.error ? <Alert type="error" showIcon message={(readiness.error as Error).message} /> : null}
      <SummaryPanel result={readiness.data} loading={readiness.isLoading} detailsCollapsed showArtifactPath={false} showRawJson={false} />
    </main>
  );
}
