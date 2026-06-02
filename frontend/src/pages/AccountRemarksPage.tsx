import { FileSearchOutlined } from "@ant-design/icons";
import { Alert, Button, Card, Col, Collapse, Form, Input, Row, Space, Typography, message as antdMessage } from "antd";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { apiGet, apiPost } from "../api/client";
import { ConfirmExecutePanel } from "../components/ConfirmExecutePanel";
import { SummaryPanel } from "../components/SummaryPanel";
import { InlineTaskStatus, WorkflowSteps } from "../components/WorkflowScaffold";
import { EXECUTE_CONFIRMATION_PHRASE } from "../constants/safety";
import type { ChineseResult, TaskDetailResponse } from "../types/api";
import { isTaskActive, taskStatus } from "../utils/workflowState";

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
  update_id: "",
  remark: "",
  advertiser_ids: "",
  output_path: "",
};

function accountRemarkPathFromTask(detail?: TaskDetailResponse): string {
  const result = detail?.raw?.result;
  if (result && typeof result === "object" && "account_remark_update_path" in result) {
    return String((result as { account_remark_update_path?: unknown }).account_remark_update_path ?? "").trim();
  }
  if (result && typeof result === "object" && "artifact_path" in result) {
    return String((result as { artifact_path?: unknown }).artifact_path ?? "").trim();
  }
  return "";
}

export function AccountRemarksPage() {
  const queryClient = useQueryClient();
  const [request, setRequest] = useState<AccountRemarkRequest>(defaultRequest);
  const [configPath, setConfigPath] = useState("");
  const [configSource, setConfigSource] = useState<"" | "current_generated" | "manual">("");
  const [previewResult, setPreviewResult] = useState<ChineseResult | undefined>();
  const [generateResult, setGenerateResult] = useState<TaskResponse | undefined>();
  const [executePreviewResult, setExecutePreviewResult] = useState<ChineseResult | undefined>();
  const [executeResult, setExecuteResult] = useState<TaskResponse | undefined>();
  const executeRequest = { account_remark_update_path: configPath, config_source: configSource };
  const generateTaskId = generateResult?.task?.task_id ?? "";
  const executeTaskId = executeResult?.task?.task_id ?? "";
  const activeTaskId = executeTaskId || generateTaskId;
  const currentStep = executeResult ? 3 : executePreviewResult ? 2 : previewResult || generateResult ? 1 : 0;
  const generateTaskDetail = useQuery({
    queryKey: ["tasks", generateTaskId],
    queryFn: () => apiGet<TaskDetailResponse>(`/tasks/${generateTaskId}`),
    enabled: Boolean(generateTaskId),
    refetchInterval: 3000,
  });
  const executeTaskDetail = useQuery({
    queryKey: ["tasks", executeTaskId],
    queryFn: () => apiGet<TaskDetailResponse>(`/tasks/${executeTaskId}`),
    enabled: Boolean(executeTaskId),
    refetchInterval: 3000,
  });
  const configGenerationStatus = taskStatus(generateTaskDetail.data, generateResult);
  const configGenerationActive = Boolean(generateTaskId) && isTaskActive(configGenerationStatus);
  const canGenerate = previewResult?.summary.status === "planned";
  const canReadConfig = Boolean(configPath.trim()) && !configGenerationActive;
  const canExecuteCurrentConfig = configSource === "current_generated";

  useEffect(() => {
    const generatedConfigPath = accountRemarkPathFromTask(generateTaskDetail.data);
    if (generatedConfigPath && generatedConfigPath !== configPath) {
      setConfigPath(generatedConfigPath);
      setConfigSource("current_generated");
      setExecutePreviewResult(undefined);
      setExecuteResult(undefined);
    }
  }, [generateTaskDetail.data, configPath]);

  useEffect(() => {
    setPreviewResult(undefined);
    setGenerateResult(undefined);
    setExecutePreviewResult(undefined);
    setExecuteResult(undefined);
    setConfigPath("");
    setConfigSource("");
  }, [request]);

  const preview = useMutation({
    mutationFn: () => apiPost<ChineseResult>("/account-remarks/config/preview", request),
    onSuccess: (result) => {
      setPreviewResult(result);
      setGenerateResult(undefined);
      setExecutePreviewResult(undefined);
      setExecuteResult(undefined);
      setConfigPath("");
      setConfigSource("");
    },
  });
  const generate = useMutation({
    mutationFn: () => apiPost<TaskResponse>("/account-remarks/config/generate", request),
    onSuccess: async (result) => {
      setGenerateResult(result);
      setExecutePreviewResult(undefined);
      setExecuteResult(undefined);
      setConfigPath("");
      setConfigSource("");
      await queryClient.invalidateQueries({ queryKey: ["tasks"] });
      antdMessage.success("账户备注配置正在生成，本页会显示进度");
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
    mutationFn: () => apiPost<TaskResponse>("/account-remarks/execute", { ...executeRequest, confirmation: EXECUTE_CONFIRMATION_PHRASE }),
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
                <Form.Item label="要写入的账户备注">
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
                      label: "高级信息：本次备注配置文件",
                      children: (
                        <Row gutter={[16, 0]}>
                          <Col xs={24} lg={8}>
                            <Form.Item label="备注配置 ID（可空，系统自动生成）">
                              <Input
                                value={request.update_id}
                                onChange={(event) => setRequest({ ...request, update_id: event.target.value })}
                                placeholder="不填则自动生成"
                              />
                            </Form.Item>
                          </Col>
                          <Col xs={24} lg={16}>
                            <Form.Item label="备注配置 JSON 路径（可空，系统自动生成）">
                              <Input
                                value={request.output_path}
                                onChange={(event) => setRequest({ ...request, output_path: event.target.value })}
                                placeholder="不填则保存到 configs/account-updates/"
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
                  <Button disabled={!canGenerate} onClick={() => generate.mutate()} loading={generate.isPending}>
                    生成本次备注配置
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
              message="这里不会重新选择账户；主路径只执行本页刚生成的新配置，避免误拿历史 JSON 写备注。"
            />
            {configGenerationActive ? (
              <Alert type="info" showIcon message="账户备注配置正在生成，完成后再核对写入明细。" />
            ) : configSource === "current_generated" ? (
              <Alert type="success" showIcon message="当前配置来源：本页刚生成的新配置" description={configPath} />
            ) : configSource === "manual" ? (
              <Alert
                type="warning"
                showIcon
                message="当前配置来源：手动指定的历史配置"
                description="手动指定配置只用于高级核对；本页不会直接执行历史配置。要真实写入备注，请回到第一步重新生成本次备注配置。"
              />
            ) : (
              <Alert type="info" showIcon message="当前还没有可执行配置；请先在第一步生成本次备注配置。" />
            )}
            <Collapse
              className="advanced-fields"
              items={[
                {
                  key: "manual-config",
                  label: "高级信息：手动查看历史账户备注 JSON",
                  children: (
                    <Input
                      value={configPath}
                      onChange={(event) => {
                        const nextPath = event.target.value;
                        setConfigPath(nextPath);
                        setConfigSource(nextPath.trim() ? "manual" : "");
                        setExecutePreviewResult(undefined);
                        setExecuteResult(undefined);
                      }}
                      placeholder="例如 configs/account-updates/xxx.local.json；历史配置只用于核对"
                    />
                  ),
                },
              ]}
            />
            <Button
              icon={<FileSearchOutlined />}
              disabled={!canReadConfig}
              onClick={() => executePreview.mutate()}
              loading={executePreview.isPending}
            >
              {configGenerationActive ? "等待配置生成完成" : canExecuteCurrentConfig ? "核对本次写入明细" : "查看手动配置明细"}
            </Button>
            {executePreview.error ? <Alert type="error" showIcon message={(executePreview.error as Error).message} /> : null}
            <SummaryPanel
              result={executePreviewResult}
              loading={executePreview.isPending}
              detailsCollapsed
              showArtifactPath={false}
              showRawJson={false}
              footer={
                executePreviewResult?.summary.execution_enabled && canExecuteCurrentConfig ? (
                  <ConfirmExecutePanel
                    buttonText="确认并写入备注"
                    disabled={execute.isPending}
                    onConfirm={() => execute.mutate()}
                  />
                ) : executePreviewResult?.summary.execution_enabled && configSource === "manual" ? (
                  <Alert
                    type="warning"
                    showIcon
                    message="手动指定的历史配置不能在本页直接执行；请重新生成本次备注配置后再确认执行。"
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
          detail={executeTaskDetail.data ?? generateTaskDetail.data}
          loading={executeTaskDetail.isFetching || generateTaskDetail.isFetching || generate.isPending || execute.isPending}
        />
      </Space>
    </main>
  );
}
