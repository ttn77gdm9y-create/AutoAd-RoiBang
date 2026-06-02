import { Button, Input, Space, Typography } from "antd";
import { PlayCircleOutlined } from "@ant-design/icons";
import { useState } from "react";

import { EXECUTE_CONFIRMATION_HELPER_TEXT, EXECUTE_CONFIRMATION_PHRASE } from "../constants/safety";

type ConfirmExecutePanelProps = {
  disabled?: boolean;
  buttonText?: string;
  helperText?: string;
  onConfirm: () => void;
};

export function ConfirmExecutePanel({
  disabled = false,
  buttonText = "确认并执行",
  helperText = EXECUTE_CONFIRMATION_HELPER_TEXT,
  onConfirm,
}: ConfirmExecutePanelProps) {
  const [value, setValue] = useState("");
  const ready = value === EXECUTE_CONFIRMATION_PHRASE && !disabled;
  return (
    <Space direction="vertical" className="confirm-panel">
      <Typography.Text type="secondary">{helperText}</Typography.Text>
      <Input value={value} onChange={(event) => setValue(event.target.value)} placeholder={EXECUTE_CONFIRMATION_PHRASE} />
      <Button type="primary" danger icon={<PlayCircleOutlined />} disabled={!ready} onClick={onConfirm}>
        {buttonText}
      </Button>
    </Space>
  );
}
