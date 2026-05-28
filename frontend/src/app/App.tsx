import { ConfigProvider, Layout, Menu, theme, Typography } from "antd";
import zhCN from "antd/locale/zh_CN";
import { Link, Route, Routes, useLocation } from "react-router-dom";

import { routeItems } from "./routes";

const routeGroups = ["核心业务", "系统记录", "高级工具"] as const;

function Shell() {
  const location = useLocation();
  const selected = routeItems.find((item) => item.key === location.pathname)?.key ?? "/";
  const menuItems = routeGroups.map((group) => ({
    key: group,
    label: group,
    type: "group" as const,
    children: routeItems
      .filter((item) => item.group === group)
      .map((item) => ({
        key: item.key,
        icon: item.icon,
        label: <Link to={item.key}>{item.label}</Link>,
      })),
  }));

  return (
    <Layout className="app-shell">
      <Layout.Sider breakpoint="lg" collapsedWidth="0" width={232} className="app-sider">
        <Typography.Title level={4} className="app-brand">
          RoiBang
        </Typography.Title>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[selected]}
          items={menuItems}
        />
      </Layout.Sider>
      <Layout>
        <Layout.Content className="app-content">
          <Routes>
            {routeItems.map((item) => (
              <Route key={item.key} path={item.key} element={item.element} />
            ))}
          </Routes>
        </Layout.Content>
      </Layout>
    </Layout>
  );
}

export function App() {
  return (
    <ConfigProvider
      locale={zhCN}
      theme={{
        algorithm: theme.defaultAlgorithm,
        token: {
          borderRadius: 8,
          colorPrimary: "#1d6f62",
          colorInfo: "#2f6f9f",
          colorWarning: "#a65f00",
        },
      }}
    >
      <Shell />
    </ConfigProvider>
  );
}
