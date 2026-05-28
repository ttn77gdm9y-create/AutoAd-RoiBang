import { Button, Input, Space, Typography } from "antd";
import { PlayCircleOutlined } from "@ant-design/icons";
import { useState } from "react";

type ConfirmExecutePanelProps = {
  disabled?: boolean;
  buttonText?: string;
  helperText?: string;
  onConfirm: () => void;
};

export function ConfirmExecutePanel({
  disabled = false,
  buttonText = "确认并执行",
  helperText = "真实执行前请输入：确认执行",
  onConfirm,
}: ConfirmExecutePanelProps) {
  const [value, setValue] = useState("");
  const ready = value === "确认执行" && !disabled;
  return (
    <Space direction="vertical" className="confirm-panel">
      <Typography.Text type="secondary">{helperText}</Typography.Text>
      <Input value={value} onChange={(event) => setValue(event.target.value)} placeholder="确认执行" />
      <Button type="primary" danger icon={<PlayCircleOutlined />} disabled={!ready} onClick={onConfirm}>
        {buttonText}
      </Button>
    </Space>
  );
}
