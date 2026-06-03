import { Alert, Button, Select, Space, Typography } from "antd";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { apiGet } from "../api/client";
import { SummaryPanel } from "../components/SummaryPanel";
import type { ChineseResult } from "../types/api";

const workflows = [
  { label: "落地页状态更新", value: "site_status_update" },
  { label: "投放巡检", value: "delivery_patrol" },
  { label: "项目管理执行", value: "project_update_execute" },
  { label: "创建计划", value: "create_mode" },
  { label: "创建执行", value: "create_live_execute_once" },
];

export function ResultsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [workflow, setWorkflow] = useState(searchParams.get("workflow") ?? workflows[0].value);
  const returnTo = searchParams.get("return_to") ?? "";
  useEffect(() => {
    const workflowFromUrl = searchParams.get("workflow") ?? workflows[0].value;
    if (workflowFromUrl !== workflow) {
      setWorkflow(workflowFromUrl);
    }
  }, [searchParams, workflow]);
  const selectWorkflow = (value: string) => {
    setWorkflow(value);
    setSearchParams(returnTo ? { workflow: value, return_to: returnTo } : { workflow: value });
  };
  const catalog = useQuery({
    queryKey: ["workflow", "catalog"],
    queryFn: () => apiGet<ChineseResult>("/workflows/catalog"),
  });
  const query = useQuery({
    queryKey: ["workflow", workflow],
    queryFn: () => apiGet<ChineseResult>(`/workflows/latest?workflow=${encodeURIComponent(workflow)}`),
    retry: false,
  });
  const workflowDescription = selectedWorkflowDescription(catalog.data, workflow);

  return (
    <main className="page">
      <Space direction="vertical" size="large" className="full-width">
        <div className="page-toolbar">
          <Typography.Title level={2}>结果中心</Typography.Title>
          <Select
            value={workflow}
            onChange={selectWorkflow}
            loading={catalog.isLoading}
            options={buildWorkflowOptions(catalog.data)}
            className="workflow-select"
          />
        </div>
        <Alert
          type="info"
          showIcon
          message="这里是历史结果备查。正常执行结果会优先显示在发起页面，这里用于按业务类型回看最近一次结果。"
          description={workflowDescription}
          action={
            returnTo ? (
              <Link to={returnTo}>
                <Button>返回投放建议工作台</Button>
              </Link>
            ) : undefined
          }
        />
        {catalog.error ? <Alert type="error" showIcon message={(catalog.error as Error).message} /> : null}
        {query.error ? <Alert type="warning" showIcon message={(query.error as Error).message} /> : null}
        <SummaryPanel result={query.data} loading={query.isLoading} detailsCollapsed showArtifactPath={false} showRawJson={false} />
      </Space>
    </main>
  );
}

function buildWorkflowOptions(catalog?: ChineseResult) {
  const rows = catalog?.table.rows ?? [];
  if (!rows.length) {
    return workflows;
  }
  return rows.map((row) => ({
    label: String(row["名称"] ?? row["结果类型"] ?? ""),
    value: String(row["结果类型"] ?? ""),
  }));
}

function selectedWorkflowDescription(catalog: ChineseResult | undefined, workflow: string) {
  const row = (catalog?.table.rows ?? []).find((item) => String(item["结果类型"] ?? "") === workflow);
  if (row?.["说明"]) {
    return String(row["说明"]);
  }
  return workflows.find((item) => item.value === workflow)?.label ?? "";
}
