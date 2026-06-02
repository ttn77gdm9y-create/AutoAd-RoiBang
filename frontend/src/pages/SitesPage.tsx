import { FileSearchOutlined } from "@ant-design/icons";
import { Alert, Button, Col, Collapse, Form, Input, Row, Select, Space, Tabs, Typography, message as antdMessage } from "antd";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { apiGet, apiPost } from "../api/client";
import { ConfirmExecutePanel } from "../components/ConfirmExecutePanel";
import { SummaryPanel } from "../components/SummaryPanel";
import { InlineTaskStatus, WorkflowSteps } from "../components/WorkflowScaffold";
import { EXECUTE_CONFIRMATION_PHRASE } from "../constants/safety";
import type { ChineseResult, TaskDetailResponse } from "../types/api";

type SiteStatusRequest = {
  advertiser_id: string;
  site_ids: string;
  handsel_artifact: string;
  status: string;
};

type SiteTemplateRequest = {
  source_advertiser_id: string;
  source_site_id: string;
  template_id: string;
  template_name: string;
  wechat_game_index: string;
  game_instance_id: string;
  game_path: string;
  target_advertiser_ids: string;
  target_accounts_path: string;
  site_mapping_artifact: string;
  site_name_prefix: string;
  edit_existing: boolean | null;
  publish: boolean | null;
};

type TaskResponse = ChineseResult & {
  task?: {
    task_id: string;
    artifact_path: string;
    pid: number;
  };
};

const defaultRequest: SiteStatusRequest = {
  advertiser_id: "",
  site_ids: "",
  handsel_artifact: "",
  status: "",
};

const defaultTemplateRequest: SiteTemplateRequest = {
  source_advertiser_id: "",
  source_site_id: "",
  template_id: "",
  template_name: "",
  wechat_game_index: "",
  game_instance_id: "",
  game_path: "",
  target_advertiser_ids: "",
  target_accounts_path: "",
  site_mapping_artifact: "",
  site_name_prefix: "",
  edit_existing: null,
  publish: null,
};

export function SitesPage() {
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState("status");
  const [request, setRequest] = useState<SiteStatusRequest>(defaultRequest);
  const [handselArtifactPath, setHandselArtifactPath] = useState("");
  const [templateRequest, setTemplateRequest] = useState<SiteTemplateRequest>(defaultTemplateRequest);
  const [previewResult, setPreviewResult] = useState<ChineseResult | undefined>();
  const [reviewedStatusRequest, setReviewedStatusRequest] = useState<SiteStatusRequest | undefined>();
  const [executeResult, setExecuteResult] = useState<TaskResponse | undefined>();
  const [handselResult, setHandselResult] = useState<ChineseResult | undefined>();
  const [templatePreviewResult, setTemplatePreviewResult] = useState<ChineseResult | undefined>();
  const [reviewedTemplateRequest, setReviewedTemplateRequest] = useState<SiteTemplateRequest | undefined>();
  const [templateExecuteResult, setTemplateExecuteResult] = useState<TaskResponse | undefined>();
  const activeTaskId = templateExecuteResult?.task?.task_id ?? executeResult?.task?.task_id ?? "";
  const currentStep =
    templateExecuteResult || executeResult
      ? 3
      : templatePreviewResult || previewResult || handselResult
        ? 1
        : 0;
  const activeTaskDetail = useQuery({
    queryKey: ["tasks", activeTaskId],
    queryFn: () => apiGet<TaskDetailResponse>(`/tasks/${activeTaskId}`),
    enabled: Boolean(activeTaskId),
    refetchInterval: 3000,
  });
  useEffect(() => {
    setPreviewResult(undefined);
    setReviewedStatusRequest(undefined);
    setExecuteResult(undefined);
  }, [request]);
  useEffect(() => {
    setTemplatePreviewResult(undefined);
    setReviewedTemplateRequest(undefined);
    setTemplateExecuteResult(undefined);
  }, [templateRequest]);
  const preview = useMutation({
    mutationFn: () => apiPost<ChineseResult>("/sites/status/preview", request),
    onSuccess: (result) => {
      setPreviewResult(result);
      setReviewedStatusRequest(result.summary.execution_enabled ? { ...request } : undefined);
      setExecuteResult(undefined);
    },
  });
  const execute = useMutation({
    mutationFn: () => {
      if (!reviewedStatusRequest) {
        throw new Error("请先检查并核对落地页动作");
      }
      return apiPost<TaskResponse>("/sites/status/execute", { ...reviewedStatusRequest, confirmation: EXECUTE_CONFIRMATION_PHRASE });
    },
    onSuccess: async (result) => {
      setExecuteResult(result);
      await queryClient.invalidateQueries({ queryKey: ["tasks"] });
      antdMessage.success("落地页任务已提交，本页会显示进度");
    },
  });
  const handselResults = useMutation({
    mutationFn: () =>
      apiGet<ChineseResult>(
        `/sites/handsel-results${handselArtifactPath ? `?artifact_path=${encodeURIComponent(handselArtifactPath)}` : ""}`,
      ),
    onSuccess: setHandselResult,
  });
  const templatePreview = useMutation({
    mutationFn: () => apiPost<ChineseResult>("/sites/template-foundation/preview", templateRequest),
    onSuccess: (result) => {
      setTemplatePreviewResult(result);
      setReviewedTemplateRequest(result.summary.execution_enabled ? { ...templateRequest } : undefined);
      setTemplateExecuteResult(undefined);
    },
  });
  const templateExecute = useMutation({
    mutationFn: () => {
      if (!reviewedTemplateRequest) {
        throw new Error("请先检查并核对模板建站动作");
      }
      return apiPost<TaskResponse>("/sites/template-foundation/execute", { ...reviewedTemplateRequest, confirmation: EXECUTE_CONFIRMATION_PHRASE });
    },
    onSuccess: async (result) => {
      setTemplateExecuteResult(result);
      await queryClient.invalidateQueries({ queryKey: ["tasks"] });
      antdMessage.success("模板建站任务已提交，本页会显示进度");
    },
  });

  return (
    <main className="page">
      <Space direction="vertical" size="large" className="full-width">
        <Typography.Title level={2}>落地页管理</Typography.Title>
        <WorkflowSteps current={currentStep} />
        <Alert
          type="info"
          showIcon
          message="先选择落地页动作并检查影响对象，再确认执行；进度和结果会直接显示在本页。"
        />
        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          items={[
            {
              key: "status",
              label: "状态更新",
              children: (
                <Space direction="vertical" size="large" className="full-width">
                  <Form layout="vertical" className="filter-bar">
                    <Row gutter={[16, 0]}>
                      <Col xs={24} lg={8}>
                        <Form.Item label="账户 ID">
                          <Input
                            value={request.advertiser_id}
                            onChange={(event) => setRequest({ ...request, advertiser_id: event.target.value })}
                          />
                        </Form.Item>
                      </Col>
                      <Col xs={24} lg={8}>
                        <Form.Item label="要改成的落地页状态">
                          <Select
                            allowClear
                            value={request.status || undefined}
                            onChange={(value) => setRequest({ ...request, status: value ?? "" })}
                            options={[
                              { label: "删除", value: "delete" },
                              { label: "下线", value: "unpublished" },
                              { label: "发布", value: "published" },
                              { label: "恢复删除", value: "undeleted" },
                            ]}
                            placeholder="请选择要改成的落地页状态"
                          />
                        </Form.Item>
                      </Col>
                      <Col xs={24}>
                        <Form.Item label="落地页 ID">
                          <Input.TextArea
                            rows={4}
                            value={request.site_ids}
                            onChange={(event) => setRequest({ ...request, site_ids: event.target.value })}
                            placeholder="多个落地页用换行或逗号分隔"
                          />
                        </Form.Item>
                      </Col>
                      <Col xs={24}>
                        <Collapse
                          className="advanced-fields"
                          items={[
                            {
                              key: "handsel-path",
                              label: "高级信息：从转赠结果读取落地页",
                              children: (
                                <Form.Item label="转赠结果文件路径">
                                  <Input
                                    value={request.handsel_artifact}
                                    onChange={(event) => setRequest({ ...request, handsel_artifact: event.target.value })}
                                    placeholder="可空；填写后读取 success_list"
                                  />
                                </Form.Item>
                              ),
                            },
                          ]}
                        />
                      </Col>
                      <Col xs={24}>
                        <Button
                          icon={<FileSearchOutlined />}
                          type="primary"
                          onClick={() => preview.mutate()}
                          loading={preview.isPending}
                        >
                          检查落地页动作
                        </Button>
                      </Col>
                    </Row>
                  </Form>
                  {preview.error ? <Alert type="error" showIcon message={(preview.error as Error).message} /> : null}
                  <SummaryPanel result={previewResult} loading={preview.isPending} detailsCollapsed showArtifactPath={false} showRawJson={false} />
                  {reviewedStatusRequest ? (
                    <Alert
                      type="success"
                      showIcon
                      message="当前落地页动作已核对"
                      description={reviewedStatusRequest.handsel_artifact ? "执行对象来自转赠结果文件。" : "执行对象来自当前手动填写的账户和落地页。"}
                    />
                  ) : null}
                  {previewResult?.summary.execution_enabled && reviewedStatusRequest ? (
                    <ConfirmExecutePanel buttonText="确认并执行落地页动作" disabled={execute.isPending} onConfirm={() => execute.mutate()} />
                  ) : null}
                  {execute.error ? <Alert type="error" showIcon message={(execute.error as Error).message} /> : null}
                </Space>
              ),
            },
            {
              key: "handsel",
              label: "转赠结果",
              children: (
                <Space direction="vertical" size="large" className="full-width">
                  <Form layout="vertical" className="filter-bar">
                    <Row gutter={[16, 0]}>
                      <Col xs={24} lg={16}>
                        <Form.Item label="转赠结果 JSON">
                          <Input
                            value={handselArtifactPath}
                            onChange={(event) => setHandselArtifactPath(event.target.value)}
                            placeholder="可空；不填则读取最近一次 site_handsel 结果"
                          />
                        </Form.Item>
                      </Col>
                      <Col xs={24} lg={8}>
                        <Form.Item label=" ">
                          <Button
                            icon={<FileSearchOutlined />}
                            type="primary"
                            onClick={() => handselResults.mutate()}
                            loading={handselResults.isPending}
                          >
                            查看转赠中文结果
                          </Button>
                        </Form.Item>
                      </Col>
                    </Row>
                  </Form>
                  {handselResults.error ? <Alert type="error" showIcon message={(handselResults.error as Error).message} /> : null}
                  <SummaryPanel result={handselResult} loading={handselResults.isPending} detailsCollapsed showArtifactPath={false} showRawJson={false} />
                </Space>
              ),
            },
            {
              key: "template",
              label: "模板建站",
              children: (
                <Space direction="vertical" size="large" className="full-width">
                  <Alert
                    type="info"
                    showIcon
                    message="模板建站会先检查源落地页、目标账户和小游戏路径，再确认新建或修复落地页。"
                  />
                  <Form layout="vertical" className="filter-bar">
                    <Row gutter={[16, 0]}>
                      <Col xs={24} lg={8}>
                        <Form.Item label="源账户 ID">
                          <Input
                            value={templateRequest.source_advertiser_id}
                            onChange={(event) => setTemplateRequest({ ...templateRequest, source_advertiser_id: event.target.value })}
                          />
                        </Form.Item>
                      </Col>
                      <Col xs={24} lg={8}>
                        <Form.Item label="源落地页 ID">
                          <Input
                            value={templateRequest.source_site_id}
                            onChange={(event) => setTemplateRequest({ ...templateRequest, source_site_id: event.target.value })}
                          />
                        </Form.Item>
                      </Col>
                      <Col xs={24} lg={8}>
                        <Form.Item label="模板 ID">
                          <Input
                            value={templateRequest.template_id}
                            onChange={(event) => setTemplateRequest({ ...templateRequest, template_id: event.target.value })}
                            placeholder="已有模板可填；不填则执行时创建"
                          />
                        </Form.Item>
                      </Col>
                      <Col xs={24} lg={8}>
                        <Form.Item label="微信小游戏组件位置">
                          <Input
                            value={templateRequest.wechat_game_index}
                            onChange={(event) => setTemplateRequest({ ...templateRequest, wechat_game_index: event.target.value })}
                            placeholder="可空；执行时从模板识别"
                          />
                        </Form.Item>
                      </Col>
                      <Col xs={24} lg={8}>
                        <Form.Item label="小游戏组件 ID">
                          <Input
                            value={templateRequest.game_instance_id}
                            onChange={(event) => setTemplateRequest({ ...templateRequest, game_instance_id: event.target.value })}
                          />
                        </Form.Item>
                      </Col>
                      <Col xs={24} lg={8}>
                        <Form.Item label="小游戏路径参数">
                          <Input
                            value={templateRequest.game_path}
                            onChange={(event) => setTemplateRequest({ ...templateRequest, game_path: event.target.value })}
                          />
                        </Form.Item>
                      </Col>
                      <Col xs={24} lg={8}>
                        <Form.Item label="站点名称前缀">
                          <Input
                            value={templateRequest.site_name_prefix}
                            onChange={(event) => setTemplateRequest({ ...templateRequest, site_name_prefix: event.target.value })}
                          />
                        </Form.Item>
                      </Col>
                      <Col xs={24} lg={8}>
                        <Form.Item label="处理方式">
                          <Select
                            allowClear
                            value={templateRequest.edit_existing === null ? undefined : templateRequest.edit_existing ? "edit" : "create"}
                            onChange={(value) =>
                              setTemplateRequest({
                                ...templateRequest,
                                edit_existing: value ? value === "edit" : null,
                              })
                            }
                            options={[
                              { label: "新建落地页", value: "create" },
                              { label: "修复现有落地页", value: "edit" },
                            ]}
                            placeholder="请选择处理方式"
                          />
                        </Form.Item>
                      </Col>
                      <Col xs={24} lg={8}>
                        <Form.Item label="执行后发布">
                          <Select
                            allowClear
                            value={templateRequest.publish === null ? undefined : templateRequest.publish ? "yes" : "no"}
                            onChange={(value) =>
                              setTemplateRequest({
                                ...templateRequest,
                                publish: value ? value === "yes" : null,
                              })
                            }
                            options={[
                              { label: "是", value: "yes" },
                              { label: "否", value: "no" },
                            ]}
                            placeholder="请选择"
                          />
                        </Form.Item>
                      </Col>
                      <Col xs={24}>
                        <Form.Item label="目标账户 ID">
                          <Input.TextArea
                            rows={4}
                            value={templateRequest.target_advertiser_ids}
                            onChange={(event) =>
                              setTemplateRequest({ ...templateRequest, target_advertiser_ids: event.target.value })
                            }
                            placeholder="多个账户用换行或逗号分隔"
                          />
                        </Form.Item>
                      </Col>
                      <Col xs={24}>
                        <Form.Item label="转赠结果或站点映射 JSON">
                          <Input
                            value={templateRequest.site_mapping_artifact}
                            onChange={(event) => setTemplateRequest({ ...templateRequest, site_mapping_artifact: event.target.value })}
                            placeholder="修复现有落地页时可填写，读取 advertiser_id 和 site_id"
                          />
                        </Form.Item>
                      </Col>
                      <Col xs={24}>
                        <Space wrap>
                          <Button
                            icon={<FileSearchOutlined />}
                            type="primary"
                            onClick={() => templatePreview.mutate()}
                            loading={templatePreview.isPending}
                          >
                            检查模板建站动作
                          </Button>
                        </Space>
                      </Col>
                    </Row>
                  </Form>
                  {templatePreview.error ? <Alert type="error" showIcon message={(templatePreview.error as Error).message} /> : null}
                  <SummaryPanel
                    result={templatePreviewResult}
                    loading={templatePreview.isPending}
                    detailsCollapsed
                    showArtifactPath={false}
                    showRawJson={false}
                  />
                  {reviewedTemplateRequest ? (
                    <Alert
                      type="success"
                      showIcon
                      message="当前模板建站动作已核对"
                      description={reviewedTemplateRequest.edit_existing ? "执行对象为修复现有落地页。" : "执行对象为新建落地页。"}
                    />
                  ) : null}
                  {templatePreviewResult?.summary.execution_enabled && reviewedTemplateRequest ? (
                    <ConfirmExecutePanel buttonText="确认并执行模板建站" disabled={templateExecute.isPending} onConfirm={() => templateExecute.mutate()} />
                  ) : null}
                  {templateExecute.error ? <Alert type="error" showIcon message={(templateExecute.error as Error).message} /> : null}
                </Space>
              ),
            },
          ]}
        />
        <InlineTaskStatus
          title="当前落地页任务"
          taskId={activeTaskId}
          workflow={templateExecuteResult ? "site_template_foundation" : "site_status_update"}
          result={templateExecuteResult ?? executeResult}
          detail={activeTaskDetail.data}
          loading={activeTaskDetail.isFetching || execute.isPending || templateExecute.isPending}
        />
      </Space>
    </main>
  );
}
