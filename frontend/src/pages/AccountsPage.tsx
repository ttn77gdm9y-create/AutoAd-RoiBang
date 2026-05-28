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
    onSuccess: setPreview,
  });
  const pasteCommit = useMutation({
    mutationFn: () => apiPost<ChineseResult>("/accounts/paste/commit", { text: pasteText }),
    onSuccess: (result) => {
      setPreview(result);
      queryClient.invalidateQueries({ queryKey: ["accounts"] });
    },
  });
  const filePreview = useMutation({
    mutationFn: () => apiUpload<ChineseResult>("/accounts/import/preview", fileList[0].originFileObj as File),
    onSuccess: setPreview,
  });
  const fileCommit = useMutation({
    mutationFn: () => apiUpload<ChineseResult>("/accounts/import/commit", fileList[0].originFileObj as File),
    onSuccess: (result) => {
      setPreview(result);
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
  const bulkUpdate = useMutation({
    mutationFn: () => apiPost<ChineseResult>("/accounts/bulk-update", { ...filters, updates: buildBulkUpdates() }),
    onSuccess: (result) => {
      setPreview(result);
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
    bulkUpdate.isPending;

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
            onChange={(event) => setFilters({ ...filters, product_key: event.target.value })}
            placeholder="产品 Key，例如 diandian-hero"
          />
        </Form.Item>
        <Form.Item label="渠道">
          <Input value={filters.channel} onChange={(event) => setFilters({ ...filters, channel: event.target.value })} />
        </Form.Item>
        <Form.Item label="负责人">
          <Input value={filters.owner} onChange={(event) => setFilters({ ...filters, owner: event.target.value })} />
        </Form.Item>
        <Form.Item label="状态">
          <Select
            allowClear
            className="status-select"
            value={filters.status || undefined}
            onChange={(value) => setFilters({ ...filters, status: value ?? "" })}
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
              onChange={(event) => setBulkFields({ ...bulkFields, channel: event.target.checked })}
            >
              渠道
            </Checkbox>
            <Input
              disabled={!bulkFields.channel}
              value={bulkValues.channel}
              onChange={(event) => setBulkValues({ ...bulkValues, channel: event.target.value })}
              placeholder="例如：微信"
            />
            <Checkbox checked={bulkFields.owner} onChange={(event) => setBulkFields({ ...bulkFields, owner: event.target.checked })}>
              负责人
            </Checkbox>
            <Input
              disabled={!bulkFields.owner}
              value={bulkValues.owner}
              onChange={(event) => setBulkValues({ ...bulkValues, owner: event.target.value })}
              placeholder="例如：郭靖"
            />
            <Checkbox
              checked={bulkFields.account_remark}
              onChange={(event) => setBulkFields({ ...bulkFields, account_remark: event.target.checked })}
            >
              备注
            </Checkbox>
            <Input
              disabled={!bulkFields.account_remark}
              value={bulkValues.account_remark}
              onChange={(event) => setBulkValues({ ...bulkValues, account_remark: event.target.value })}
              placeholder="例如：点点英雄-黑旗"
            />
          </div>
          <Button type="primary" danger icon={<SaveOutlined />} disabled={!hasBulkFields || busy} onClick={() => bulkUpdate.mutate()}>
            确认批量修改
          </Button>
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
            onChange={({ fileList: nextFileList }) => setFileList(nextFileList)}
          >
            <Button icon={<UploadOutlined />}>选择 CSV / Excel</Button>
          </Upload>
          <Space>
            <Button icon={<EyeOutlined />} disabled={!selectedFile || busy} onClick={() => filePreview.mutate()}>
              检查上传内容
            </Button>
            <Button type="primary" icon={<SaveOutlined />} disabled={!selectedFile || busy} onClick={() => fileCommit.mutate()}>
              确认写入上传账户
            </Button>
          </Space>
        </div>
        <div className="import-column">
          <Typography.Title level={4}>粘贴账户</Typography.Title>
          <Input.TextArea
            rows={6}
            value={pasteText}
            onChange={(event) => setPasteText(event.target.value)}
            placeholder="粘贴带表头的 CSV 或 Tab 分隔文本"
          />
          <Space>
            <Button icon={<FormOutlined />} disabled={!pasteText.trim() || busy} onClick={() => pastePreview.mutate()}>
              检查粘贴内容
            </Button>
            <Button type="primary" icon={<SaveOutlined />} disabled={!pasteText.trim() || busy} onClick={() => pasteCommit.mutate()}>
              确认写入粘贴账户
            </Button>
          </Space>
        </div>
      </section>

      {[pastePreview.error, pasteCommit.error, filePreview.error, fileCommit.error, historyBackfill.error, bulkUpdate.error, query.error]
        .filter(Boolean)
        .map((error) => (
          <Alert key={(error as Error).message} type="error" showIcon message={(error as Error).message} />
        ))}

      {preview ? <SummaryPanel result={preview} loading={busy} detailsCollapsed showArtifactPath={false} showRawJson={false} /> : null}
      <SummaryPanel result={query.data} loading={query.isLoading} showArtifactPath={false} showRawJson={false} />
    </main>
  );
}
