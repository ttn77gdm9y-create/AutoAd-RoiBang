import { FileSearchOutlined } from "@ant-design/icons";
import { Alert, Button, Card, Col, Collapse, Form, Input, Row, Space, Typography, message as antdMessage } from "antd";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { apiGet, apiPost } from "../api/client";
import { ConfirmExecutePanel } from "../components/ConfirmExecutePanel";
import { SummaryPanel } from "../components/SummaryPanel";
import { InlineTaskStatus, WorkflowSteps } from "../components/WorkflowScaffold";
import type { ChineseResult, TaskDetailResponse } from "../types/api";

type AccountRemarkRequest = {
  update_id: string;
  remark: string;
  advertiser_ids: string;
  output_path: string;
};

type TaskResponse = ChineseResult & {
  task?: {
    task_id: string;
    artifact_path: string;
    pid: number;
  };
};

const defaultRequest: AccountRemarkRequest = {
  update_id: "ui-account-remark",
  remark: "",
  advertiser_ids: "",
  output_path: "configs/account-updates/ui-account-remark.local.json",
};

export function AccountRemarksPage() {
  const queryClient = useQueryClient();
  const [request, setRequest] = useState<AccountRemarkRequest>(defaultRequest);
  const [previewResult, setPreviewResult] = useState<ChineseResult | undefined>();
  const [generateResult, setGenerateResult] = useState<TaskResponse | undefined>();
  const [executePreviewResult, setExecutePreviewResult] = useState<ChineseResult | undefined>();
  const [executeResult, setExecuteResult] = useState<TaskResponse | undefined>();
  const executeRequest = { account_remark_update_path: request.output_path || defaultRequest.output_path };
  const activeTaskId = executeResult?.task?.task_id ?? generateResult?.task?.task_id ?? "";
  const currentStep = executeResult ? 3 : executePreviewResult ? 2 : previewResult || generateResult ? 1 : 0;
  const activeTaskDetail = useQuery({
    queryKey: ["tasks", activeTaskId],
    queryFn: () => apiGet<TaskDetailResponse>(`/tasks/${activeTaskId}`),
    enabled: Boolean(activeTaskId),
    refetchInterval: 3000,
  });

  const preview = useMutation({
    mutationFn: () => apiPost<ChineseResult>("/account-remarks/config/preview", request),
    onSuccess: (result) => {
      setPreviewResult(result);
      setGenerateResult(undefined);
      setExecutePreviewResult(undefined);
      setExecuteResult(undefined);
    },
  });
  const generate = useMutation({
    mutationFn: () => apiPost<TaskResponse>("/account-remarks/config/generate", request),
    onSuccess: async (result) => {
      setGenerateResult(result);
      setExecutePreviewResult(undefined);
      setExecuteResult(undefined);
      await queryClient.invalidateQueries({ queryKey: ["tasks"] });
    },
  });
  const executePreview = useMutation({
    mutationFn: () => apiPost<ChineseResult>("/account-remarks/execute/preview", executeRequest),
    onSuccess: (result) => {
      setExecutePreviewResult(result);
      setExecuteResult(undefined);
    },
  });
  const execute = useMutation({
    mutationFn: () => apiPost<TaskResponse>("/account-remarks/execute", { ...executeRequest, confirmation: "确认执行" }),
    onSuccess: async (result) => {
      setExecuteResult(result);
      await queryClient.invalidateQueries({ queryKey: ["tasks"] });
      antdMessage.success("账户备注任务已提交，本页会显示进度");
    },
  });

  return (
    <main className="page">
      <Space direction="vertical" size="large" className="full-width">
        <Typography.Title level={2}>账户备注</Typography.Title>
        <WorkflowSteps current={currentStep} />
        <Alert
          type="info"
          showIcon
          message="先检查备注修改会影响哪些账户，再生成配置并确认写入；进度和结果会直接显示在本页。"
        />

        <Card size="small" title="第一步：填写并检查备注修改">
          <Form layout="vertical" className="filter-bar">
            <Row gutter={[16, 0]}>
              <Col xs={24} lg={8}>
                <Form.Item label="目标备注">
                  <Input value={request.remark} onChange={(event) => setRequest({ ...request, remark: event.target.value })} />
                </Form.Item>
              </Col>
              <Col xs={24}>
                <Form.Item label="账户 ID">
                  <Input.TextArea
                    rows={4}
                    value={request.advertiser_ids}
                    onChange={(event) => setRequest({ ...request, advertiser_ids: event.target.value })}
                    placeholder="多个账户用换行或逗号分隔"
                  />
                </Form.Item>
              </Col>
              <Col xs={24}>
                <Collapse
                  className="advanced-fields"
                  items={[
                    {
                      key: "advanced",
                      label: "高级信息：配置编号和文件路径",
                      children: (
                        <Row gutter={[16, 0]}>
                          <Col xs={24} lg={8}>
                            <Form.Item label="配置 ID">
                              <Input
                                value={request.update_id}
                                onChange={(event) => setRequest({ ...request, update_id: event.target.value })}
                              />
                            </Form.Item>
                          </Col>
                          <Col xs={24} lg={16}>
                            <Form.Item label="配置保存路径">
                              <Input
                                value={request.output_path}
                                onChange={(event) => setRequest({ ...request, output_path: event.target.value })}
                              />
                            </Form.Item>
                          </Col>
                        </Row>
                      ),
                    },
                  ]}
                />
              </Col>
              <Col xs={24}>
                <Space wrap className="workflow-actions">
                  <Button icon={<FileSearchOutlined />} type="primary" onClick={() => preview.mutate()} loading={preview.isPending}>
                    检查备注修改
                  </Button>
                  <Button disabled={!previewResult} onClick={() => generate.mutate()} loading={generate.isPending}>
                    生成备注配置
                  </Button>
                </Space>
              </Col>
            </Row>
          </Form>
          {preview.error ? <Alert type="error" showIcon message={(preview.error as Error).message} /> : null}
          <SummaryPanel result={previewResult} loading={preview.isPending} detailsCollapsed showArtifactPath={false} showRawJson={false} />
          {generate.error ? <Alert type="error" showIcon message={(generate.error as Error).message} /> : null}
        </Card>

        <Card size="small" title="第二步：确认并写入备注">
          <Space direction="vertical" size="middle" className="full-width">
            <Alert
              type="info"
              showIcon
              message="这里不会重新选择账户；执行对象以第一步生成的备注配置为准。"
            />
            <Button
              icon={<FileSearchOutlined />}
              onClick={() => executePreview.mutate()}
              loading={executePreview.isPending}
            >
              检查写入明细
            </Button>
            {executePreview.error ? <Alert type="error" showIcon message={(executePreview.error as Error).message} /> : null}
            <SummaryPanel
              result={executePreviewResult}
              loading={executePreview.isPending}
              detailsCollapsed
              showArtifactPath={false}
              showRawJson={false}
              footer={
                executePreviewResult?.summary.execution_enabled ? (
                  <ConfirmExecutePanel
                    buttonText="确认并写入备注"
                    disabled={execute.isPending}
                    onConfirm={() => execute.mutate()}
                  />
                ) : null
              }
            />
            {execute.error ? <Alert type="error" showIcon message={(execute.error as Error).message} /> : null}
          </Space>
        </Card>

        <InlineTaskStatus
          title="当前账户备注任务"
          taskId={activeTaskId}
          workflow="account_remark_update"
          result={executeResult ?? generateResult}
          detail={activeTaskDetail.data}
          loading={activeTaskDetail.isFetching || generate.isPending || execute.isPending}
        />
      </Space>
    </main>
  );
}
