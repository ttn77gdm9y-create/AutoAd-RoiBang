import { FileSearchOutlined } from "@ant-design/icons";
import { Alert, Button, Card, Input, Select, Space, Typography, message as antdMessage } from "antd";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { apiGet, apiPost } from "../api/client";
import { ConfirmExecutePanel } from "../components/ConfirmExecutePanel";
import { SummaryPanel } from "../components/SummaryPanel";
import { InlineTaskStatus, WorkflowSteps } from "../components/WorkflowScaffold";
import type { ChineseResult, TaskDetailResponse } from "../types/api";

type ActionResponse = ChineseResult & {
  task?: {
    task_id: string;
    pid: number;
    artifact_path: string;
  };
};

export function ExecutionPage() {
  const queryClient = useQueryClient();
  const [action, setAction] = useState("dry_run_probe");
  const [probeMessage, setProbeMessage] = useState("probe-ok");
  const [previewResult, setPreviewResult] = useState<ChineseResult | undefined>();
  const [executeResult, setExecuteResult] = useState<ActionResponse | undefined>();
  const activeTaskId = executeResult?.task?.task_id ?? "";
  const currentStep = executeResult ? 3 : previewResult ? 1 : 0;

  const request = { message: probeMessage };
  const catalog = useQuery({
    queryKey: ["actions", "catalog"],
    queryFn: () => apiGet<ChineseResult>("/actions/catalog"),
  });
  const activeTaskDetail = useQuery({
    queryKey: ["tasks", activeTaskId],
    queryFn: () => apiGet<TaskDetailResponse>(`/tasks/${activeTaskId}`),
    enabled: Boolean(activeTaskId),
    refetchInterval: 3000,
  });
  const preview = useMutation({
    mutationFn: () => apiPost<ChineseResult>(`/actions/${action}/preview`, { request }),
    onSuccess: (result) => {
      setPreviewResult(result);
      setExecuteResult(undefined);
    },
  });
  const execute = useMutation({
    mutationFn: () => apiPost<ActionResponse>(`/actions/${action}/execute`, { confirmation: "确认执行", request }),
    onSuccess: async (result) => {
      setExecuteResult(result);
      await queryClient.invalidateQueries({ queryKey: ["tasks"] });
      antdMessage.success("链路探针任务已提交，本页会显示进度");
    },
  });

  return (
    <main className="page">
      <Space direction="vertical" size="large" className="full-width">
        <Typography.Title level={2}>链路探针</Typography.Title>
        <WorkflowSteps current={currentStep} items={["选择探针", "检查", "确认运行", "结果"]} />
        <Alert
          type="warning"
          showIcon
          message="这是高级工具，只验证本地白名单任务、确认、任务记录和中文结果展示链路，不是业务执行入口。"
        />
        <Card size="small" title="探针配置">
          <Space direction="vertical" className="full-width">
            {catalog.error ? <Alert type="error" showIcon message={(catalog.error as Error).message} /> : null}
            <Select
              value={action}
              onChange={setAction}
              loading={catalog.isLoading}
              options={buildActionOptions(catalog.data)}
              className="workflow-select"
            />
            <Input
              value={probeMessage}
              onChange={(event) => setProbeMessage(event.target.value)}
              addonBefore="探针消息"
              placeholder="probe-ok"
            />
            <Button icon={<FileSearchOutlined />} onClick={() => preview.mutate()} loading={preview.isPending}>
              检查探针动作
            </Button>
          </Space>
        </Card>
        {preview.error ? <Alert type="error" showIcon message={(preview.error as Error).message} /> : null}
        <SummaryPanel result={previewResult} loading={preview.isPending} detailsCollapsed showArtifactPath={false} showRawJson={false} />
        {previewResult?.summary.execution_enabled ? (
          <Card size="small" title="运行确认">
            <ConfirmExecutePanel buttonText="确认并运行探针" disabled={execute.isPending} onConfirm={() => execute.mutate()} />
          </Card>
        ) : null}
        {execute.error ? <Alert type="error" showIcon message={(execute.error as Error).message} /> : null}
        <InlineTaskStatus
          title="当前探针任务"
          taskId={activeTaskId}
          workflow={action}
          result={executeResult}
          detail={activeTaskDetail.data}
          loading={execute.isPending || activeTaskDetail.isFetching}
        />
      </Space>
    </main>
  );
}

function buildActionOptions(catalog?: ChineseResult) {
  const rows = catalog?.table.rows ?? [];
  if (!rows.length) {
    return [{ label: "dry_run_probe：固定脚本链路探针", value: "dry_run_probe" }];
  }
  return rows.map((row) => ({
    label: `${row["名称"] ?? row["动作"]}（${row["动作"]}）`,
    value: String(row["动作"] ?? ""),
  }));
}
