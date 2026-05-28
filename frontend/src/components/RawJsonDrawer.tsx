import { Button, Drawer } from "antd";
import { CodeOutlined } from "@ant-design/icons";
import { useState } from "react";

type RawJsonDrawerProps = {
  title?: string;
  value: unknown;
};

export function RawJsonDrawer({ title = "原始 JSON", value }: RawJsonDrawerProps) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button icon={<CodeOutlined />} onClick={() => setOpen(true)}>
        查看原始 JSON
      </Button>
      <Drawer title={title} open={open} width={720} onClose={() => setOpen(false)}>
        <pre className="raw-json">{JSON.stringify(value, null, 2)}</pre>
      </Drawer>
    </>
  );
}
