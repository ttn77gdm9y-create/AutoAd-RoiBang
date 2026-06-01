import { Alert, Button, Checkbox, Form, Input, Select, Space, Typography, Upload } from "antd";
import type { UploadFile } from "antd";
import { DatabaseOutlined, DownloadOutlined, EyeOutlined, FormOutlined, SaveOutlined, UploadOutlined } from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { apiGet, apiPost, apiUpload, apiUrl } from "../api/client";
import { SummaryPanel } from "../components/SummaryPanel";
import type { ChineseResult } from "../types/api";

export function AccountsPage() {
  const queryClient = useQueryClient();
  const [filters, setFilters] = useState({ product_key: "", channel: "", owner: "", status: "" });
  const [bulkFields, setBulkFields] = useState({ channel: false, owner: false, account_remark: false });
  const [bulkValues, setBulkValues] = useState({ channel: "", owner: "", account_remark: "" });
  const [pasteText, setPasteText] = useState("");
  const [fileList, setFileList] = useState<UploadFile[]>([]);
  const [preview, setPreview] = useState<ChineseResult | undefined>();
  const [pastePreviewReady, setPastePreviewReady] = useState(false);
  const [filePreviewReady, setFilePreviewReady] = useState(false);
  const [bulkPreviewReady, setBulkPreviewReady] = useState(false);
  const queryPath = useMemo(() => {
    const params = new URLSearchParams();
    Object.entries(filters).forEach(([key, value]) => {
      if (value) {
        params.set(key, value);
      }
    });
    const suffix = params.toString();
    return `/accounts${suffix ? `?${suffix}` : ""}`;
  }, [filters]);
  const query = useQuery({
    queryKey: ["accounts", filters],
    queryFn: () => apiGet<ChineseResult>(queryPath),
  });
  const pastePreview = useMutation({
    mutationFn: () => apiPost<ChineseResult>("/accounts/paste/preview", { text: pasteText }),
    onSuccess: (result) => {
      setPreview(result);
      setPastePreviewReady(result.summary.status === "planned");
    },
  });
  const pasteCommit = useMutation({
    mutationFn: () => apiPost<ChineseResult>("/accounts/paste/commit", { text: pasteText }),
    onSuccess: (result) => {
      setPreview(result);
      setPastePreviewReady(false);
      queryClient.invalidateQueries({ queryKey: ["accounts"] });
    },
  });
  const filePreview = useMutation({
    mutationFn: () => apiUpload<ChineseResult>("/accounts/import/preview", fileList[0].originFileObj as File),
    onSuccess: (result) => {
      setPreview(result);
      setFilePreviewReady(result.summary.status === "planned");
    },
  });
  const fileCommit = useMutation({
    mutationFn: () => apiUpload<ChineseResult>("/accounts/import/commit", fileList[0].originFileObj as File),
    onSuccess: (result) => {
      setPreview(result);
      setFilePreviewReady(false);
      queryClient.invalidateQueries({ queryKey: ["accounts"] });
    },
  });
  const historyBackfill = useMutation({
    mutationFn: () => apiPost<ChineseResult>("/accounts/backfill/history", {}),
    onSuccess: (result) => {
      setPreview(result);
      queryClient.invalidateQueries({ queryKey: ["accounts"] });
    },
  });
  const bulkPreview = useMutation({
    mutationFn: () => apiPost<ChineseResult>("/accounts/bulk-update/preview", { ...filters, updates: buildBulkUpdates() }),
    onSuccess: (result) => {
      setPreview(result);
      setBulkPreviewReady(result.summary.status === "planned");
    },
  });
  const bulkUpdate = useMutation({
    mutationFn: () => apiPost<ChineseResult>("/accounts/bulk-update", { ...filters, updates: buildBulkUpdates() }),
    onSuccess: (result) => {
      setPreview(result);
      setBulkPreviewReady(false);
      queryClient.invalidateQueries({ queryKey: ["accounts"] });
    },
  });
  const accountCount = query.data?.summary.items.find((item) => item.label === "账户数")?.value ?? 0;
  const selectedFile = Boolean(fileList[0]?.originFileObj);
  const hasBulkFields = bulkFields.channel || bulkFields.owner || bulkFields.account_remark;
  const busy =
    pastePreview.isPending ||
    pasteCommit.isPending ||
    filePreview.isPending ||
    fileCommit.isPending ||
    historyBackfill.isPending ||
    bulkPreview.isPending ||
    bulkUpdate.isPending;
  const canCommitPaste = Boolean(pasteText.trim()) && pastePreviewReady && !busy;
  const canCommitFile = selectedFile && filePreviewReady && !busy;
  const canCommitBulk = hasBulkFields && bulkPreviewReady && !busy;

  function buildBulkUpdates() {
    const updates: Record<string, string> = {};
    if (bulkFields.channel) {
      updates.channel = bulkValues.channel;
    }
    if (bulkFields.owner) {
      updates.owner = bulkValues.owner;
    }
    if (bulkFields.account_remark) {
      updates.account_remark = bulkValues.account_remark;
    }
    return updates;
  }

  function updateFilters(patch: Partial<typeof filters>) {
    setFilters({ ...filters, ...patch });
    setBulkPreviewReady(false);
  }

  function updateBulkFields(patch: Partial<typeof bulkFields>) {
    setBulkFields({ ...bulkFields, ...patch });
    setBulkPreviewReady(false);
  }

  function updateBulkValues(patch: Partial<typeof bulkValues>) {
    setBulkValues({ ...bulkValues, ...patch });
    setBulkPreviewReady(false);
  }

  return (
    <main className="page">
      <div className="page-toolbar">
        <Typography.Title level={2}>产品账户库</Typography.Title>
        <Space wrap>
          <Button icon={<DatabaseOutlined />} loading={historyBackfill.isPending} disabled={busy} onClick={() => historyBackfill.mutate()}>
            补全历史账户
          </Button>
          <Button icon={<DownloadOutlined />} href={apiUrl("/accounts/template")}>
            下载账户模板
          </Button>
          <Button href={apiUrl("/accounts/export")}>导出账户库</Button>
        </Space>
      </div>
      <Alert
        className="page-alert"
        type="info"
        showIcon
        message="账户库用于给创建计划自动匹配产品账户。导入和批量修改都会先展示中文结果，确认影响范围后再写入。"
      />

      <Form layout="inline" className="filter-bar">
        <Form.Item label="产品">
          <Input
            value={filters.product_key}
            onChange={(event) => updateFilters({ product_key: event.target.value })}
            placeholder="产品 Key，例如 diandian-hero"
          />
        </Form.Item>
        <Form.Item label="渠道">
          <Input value={filters.channel} onChange={(event) => updateFilters({ channel: event.target.value })} />
        </Form.Item>
        <Form.Item label="负责人">
          <Input value={filters.owner} onChange={(event) => updateFilters({ owner: event.target.value })} />
        </Form.Item>
        <Form.Item label="状态">
          <Select
            allowClear
            className="status-select"
            value={filters.status || undefined}
            onChange={(value) => updateFilters({ status: value ?? "" })}
            options={[
              { label: "启用", value: "active" },
              { label: "暂停", value: "paused" },
              { label: "停用", value: "disabled" },
            ]}
          />
        </Form.Item>
      </Form>

      <section className="import-panel bulk-edit-panel">
        <div className="import-column">
          <Typography.Title level={4}>批量修改当前筛选结果</Typography.Title>
          <Alert
            type="warning"
            showIcon
            message={`将修改当前筛选命中的 ${accountCount} 个账户，只更新已勾选字段；勾选后留空会清空该字段。`}
          />
          <div className="bulk-edit-grid">
            <Checkbox
              checked={bulkFields.channel}
              onChange={(event) => updateBulkFields({ channel: event.target.checked })}
            >
              渠道
            </Checkbox>
            <Input
              disabled={!bulkFields.channel}
              value={bulkValues.channel}
              onChange={(event) => updateBulkValues({ channel: event.target.value })}
              placeholder="例如：微信"
            />
            <Checkbox checked={bulkFields.owner} onChange={(event) => updateBulkFields({ owner: event.target.checked })}>
              负责人
            </Checkbox>
            <Input
              disabled={!bulkFields.owner}
              value={bulkValues.owner}
              onChange={(event) => updateBulkValues({ owner: event.target.value })}
              placeholder="例如：郭靖"
            />
            <Checkbox
              checked={bulkFields.account_remark}
              onChange={(event) => updateBulkFields({ account_remark: event.target.checked })}
            >
              备注
            </Checkbox>
            <Input
              disabled={!bulkFields.account_remark}
              value={bulkValues.account_remark}
              onChange={(event) => updateBulkValues({ account_remark: event.target.value })}
              placeholder="例如：点点英雄-黑旗"
            />
          </div>
          <Space wrap>
            <Button icon={<EyeOutlined />} disabled={!hasBulkFields || busy} loading={bulkPreview.isPending} onClick={() => bulkPreview.mutate()}>
              检查批量修改
            </Button>
            <Button
              type="primary"
              danger
              icon={<SaveOutlined />}
              disabled={!canCommitBulk}
              loading={bulkUpdate.isPending}
              onClick={() => bulkUpdate.mutate()}
            >
              确认写入批量修改
            </Button>
          </Space>
        </div>
      </section>

      <section className="import-panel">
        <div className="import-column">
          <Typography.Title level={4}>上传账户表</Typography.Title>
          <Alert
            type="info"
            showIcon
            message="先下载账户模板，按表头填写后上传；也可以先点“从历史数据补全”自动写入已有记录。"
          />
          <Upload
            accept=".csv,.txt,.xlsx"
            beforeUpload={() => false}
            maxCount={1}
            fileList={fileList}
            onChange={({ fileList: nextFileList }) => {
              setFileList(nextFileList);
              setFilePreviewReady(false);
            }}
          >
            <Button icon={<UploadOutlined />}>选择 CSV / Excel</Button>
          </Upload>
          <Space>
            <Button icon={<EyeOutlined />} disabled={!selectedFile || busy} onClick={() => filePreview.mutate()}>
              检查上传内容
            </Button>
            <Button type="primary" icon={<SaveOutlined />} disabled={!canCommitFile} onClick={() => fileCommit.mutate()}>
              确认写入上传账户
            </Button>
          </Space>
        </div>
        <div className="import-column">
          <Typography.Title level={4}>粘贴账户</Typography.Title>
          <Input.TextArea
            rows={6}
            value={pasteText}
            onChange={(event) => {
              setPasteText(event.target.value);
              setPastePreviewReady(false);
            }}
            placeholder="粘贴带表头的 CSV 或 Tab 分隔文本"
          />
          <Space>
            <Button icon={<FormOutlined />} disabled={!pasteText.trim() || busy} onClick={() => pastePreview.mutate()}>
              检查粘贴内容
            </Button>
            <Button type="primary" icon={<SaveOutlined />} disabled={!canCommitPaste} onClick={() => pasteCommit.mutate()}>
              确认写入粘贴账户
            </Button>
          </Space>
        </div>
      </section>

      {[pastePreview.error, pasteCommit.error, filePreview.error, fileCommit.error, historyBackfill.error, bulkPreview.error, bulkUpdate.error, query.error]
        .filter(Boolean)
        .map((error) => (
          <Alert key={(error as Error).message} type="error" showIcon message={(error as Error).message} />
        ))}

      {preview ? <SummaryPanel result={preview} loading={busy} detailsCollapsed showArtifactPath={false} showRawJson={false} /> : null}
      <SummaryPanel result={query.data} loading={query.isLoading} showArtifactPath={false} showRawJson={false} />
    </main>
  );
}
