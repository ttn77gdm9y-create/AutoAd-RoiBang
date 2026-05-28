import { Card, Space, Steps, Typography } from "antd";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import type { ChineseResult, TaskDetailResponse } from "../types/api";
import { SummaryPanel } from "./SummaryPanel";

type WorkflowStepsProps = {
  current: number;
  items?: string[];
};

type InlineTaskStatusProps = {
  title: string;
  taskId?: string;
  workflow?: string;
  result?: ChineseResult;
  detail?: TaskDetailResponse;
  loading?: boolean;
  extra?: ReactNode;
};

const defaultSteps = ["配置", "检查", "执行", "结果"];

export function WorkflowSteps({ current, items = defaultSteps }: WorkflowStepsProps) {
  return <Steps className="workflow-steps" size="small" current={current} items={items.map((title) => ({ title }))} />;
}

export function InlineTaskStatus({ title, taskId, workflow, result, detail, loading = false, extra }: InlineTaskStatusProps) {
  if (!taskId && !result && !detail && !loading) {
    return null;
  }
  return (
    <Card size="small" title={title} className="workflow-task-card">
      <Space direction="vertical" size="middle" className="full-width">
        {taskId ? (
          <Space wrap className="workflow-task-links">
            <Typography.Text type="secondary">任务：{taskId}</Typography.Text>
            <Link to={`/tasks?task_id=${encodeURIComponent(taskId)}`}>查看任务记录</Link>
            <Link to={`/operations?task_id=${encodeURIComponent(taskId)}`}>查看操作日志</Link>
            {workflow ? <Link to={`/results?workflow=${encodeURIComponent(workflow)}`}>查看历史结果</Link> : null}
          </Space>
        ) : null}
        {extra}
        <SummaryPanel result={detail ?? result} loading={loading} detailsCollapsed showArtifactPath={false} showRawJson={false} />
      </Space>
    </Card>
  );
}
