import { Alert, Button, Collapse, Drawer, Progress, Space, Table, Typography } from "antd";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { apiGet } from "../api/client";
import { SummaryPanel } from "../components/SummaryPanel";
import type { TaskDetailResponse, TaskListResponse, TaskRow } from "../types/api";
import { DEFAULT_TABLE_PAGE_SIZE, TABLE_PAGE_SIZE_OPTIONS } from "../utils/tablePagination";

export function TasksPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [taskId, setTaskId] = useState<string | null>(searchParams.get("task_id"));
  const [tasksPagination, setTasksPagination] = useState({ current: 1, pageSize: DEFAULT_TABLE_PAGE_SIZE });
  const returnTo = searchParams.get("return_to") ?? "";
  useEffect(() => {
    const nextTaskId = searchParams.get("task_id");
    if (nextTaskId !== taskId) {
      setTaskId(nextTaskId);
    }
  }, [searchParams, taskId]);
  const selectTaskId = (nextTaskId: string | null) => {
    setTaskId(nextTaskId);
    if (nextTaskId) {
      setSearchParams(returnTo ? { task_id: nextTaskId, return_to: returnTo } : { task_id: nextTaskId });
    } else {
      setSearchParams(returnTo ? { return_to: returnTo } : {});
    }
  };
  const returnQuery = returnTo ? `&return_to=${encodeURIComponent(returnTo)}` : "";
  const tasks = useQuery({
    queryKey: ["tasks"],
    queryFn: () => apiGet<TaskListResponse>("/tasks"),
    refetchInterval: 5000,
  });
  const detail = useQuery({
    queryKey: ["tasks", taskId],
    queryFn: () => apiGet<TaskDetailResponse>(`/tasks/${taskId}`),
    enabled: Boolean(taskId),
  });
  const businessDetail = useMemo(() => toBusinessTaskDetail(detail.data), [detail.data]);

  return (
    <main className="page">
      <Typography.Title level={2}>任务中心</Typography.Title>
      <Alert
        className="page-alert"
        type="info"
        showIcon
        message="这里是系统任务记录。正常业务进度会优先显示在发起页面，这里用于追踪历史任务和查看高级日志。"
        action={returnTo ? <Button onClick={() => navigate(returnTo)}>返回投放建议工作台</Button> : undefined}
      />
      {tasks.error ? <Alert type="error" showIcon message={(tasks.error as Error).message} /> : null}
      <Table<TaskRow>
        rowKey="task_id"
        loading={tasks.isLoading}
        dataSource={tasks.data?.items ?? []}
        onRow={(record) => ({ onClick: () => selectTaskId(record.task_id) })}
        columns={[
          { title: "任务 ID", dataIndex: "task_id", ellipsis: true },
          { title: "任务内容", dataIndex: "operation_label" },
          { title: "业务内容", dataIndex: "business_context", ellipsis: true },
          { title: "状态", dataIndex: "status_label" },
          {
            title: "进度",
            dataIndex: "progress",
            width: 220,
            render: (_value, record) =>
              record.progress?.label ? (
                <div className="table-progress">
                  <Progress
                    percent={Number(record.progress.percent ?? 0)}
                    size="small"
                    status={progressStatus(record.progress.status)}
                  />
                  <Typography.Text type="secondary">{record.progress.label}</Typography.Text>
                </div>
              ) : (
                "-"
              ),
          },
          { title: "业务摘要", dataIndex: "result_summary", ellipsis: true },
          { title: "创建时间", dataIndex: "created_at" },
          { title: "更新时间", dataIndex: "updated_at" },
        ]}
        size="small"
        scroll={{ x: "max-content" }}
        pagination={{
          current: tasksPagination.current,
          pageSize: tasksPagination.pageSize,
          showSizeChanger: true,
          pageSizeOptions: TABLE_PAGE_SIZE_OPTIONS,
          onChange: (current, pageSize) => setTasksPagination({ current, pageSize }),
          onShowSizeChange: (_current, pageSize) => setTasksPagination({ current: 1, pageSize }),
        }}
      />
      <Drawer title={businessDetail?.summary.title ?? taskId ?? "任务详情"} open={Boolean(taskId)} width={860} onClose={() => selectTaskId(null)}>
        {detail.error ? <Alert type="error" showIcon message={(detail.error as Error).message} /> : null}
        <SummaryPanel result={businessDetail} loading={detail.isLoading} detailsCollapsed showArtifactPath={false} showRawJson={false} />
        {taskId ? (
          <Space wrap className="section-actions">
            <Button onClick={() => navigate(`/operations?task_id=${encodeURIComponent(taskId)}${returnQuery}`)}>查看关联操作日志</Button>
            <Button onClick={() => navigate(returnTo ? `/results?return_to=${encodeURIComponent(returnTo)}` : "/results")}>打开结果中心</Button>
          </Space>
        ) : null}
        <Collapse
          className="advanced-fields"
          items={[
            { key: "stdout", label: "高级日志：执行输出", children: <pre className="log-panel">{detail.data?.stdout ?? ""}</pre> },
            { key: "stderr", label: "高级日志：错误输出", children: <pre className="log-panel">{detail.data?.stderr ?? ""}</pre> },
          ]}
        />
      </Drawer>
    </main>
  );
}

const lowValueLabels = new Set(["标准输出长度", "标准错误长度", "退出码", "结果文件"]);

function progressStatus(status?: string): "normal" | "active" | "exception" | "success" {
  if (status === "active" || status === "exception" || status === "success") {
    return status;
  }
  return "normal";
}

function toBusinessTaskDetail(result?: TaskDetailResponse): TaskDetailResponse | undefined {
  if (!result) {
    return undefined;
  }
  return {
    ...result,
    summary: {
      ...result.summary,
      items: result.summary.items.filter((item) => !lowValueLabels.has(item.label)),
    },
  };
}
