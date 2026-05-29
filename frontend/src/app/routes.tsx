import type { ReactNode } from "react";
import {
  AppstoreOutlined,
  BarChartOutlined,
  ClusterOutlined,
  DatabaseOutlined,
  EditOutlined,
  HistoryOutlined,
  LinkOutlined,
  PlayCircleOutlined,
  PlusSquareOutlined,
  ProfileOutlined,
  SettingOutlined,
  ToolOutlined,
} from "@ant-design/icons";

import { AccountRemarksPage } from "../pages/AccountRemarksPage";
import { AccountsPage } from "../pages/AccountsPage";
import { CreatePlansPage } from "../pages/CreatePlansPage";
import { DashboardPage } from "../pages/DashboardPage";
import { ExecutionPage } from "../pages/ExecutionPage";
import { OperationsPage } from "../pages/OperationsPage";
import { ProductAutomationPage } from "../pages/ProductAutomationPage";
import { ProjectManagementPage } from "../pages/ProjectManagementPage";
import { ResultsPage } from "../pages/ResultsPage";
import { SitesPage } from "../pages/SitesPage";
import { SystemSettingsPage } from "../pages/SystemSettingsPage";
import { TasksPage } from "../pages/TasksPage";

export const routeItems = [
  { key: "/", label: "首页数据看板", group: "核心业务", icon: <BarChartOutlined />, element: <DashboardPage /> },
  { key: "/accounts", label: "产品账户库", group: "核心业务", icon: <DatabaseOutlined />, element: <AccountsPage /> },
  { key: "/create-plans", label: "创建计划", group: "核心业务", icon: <PlusSquareOutlined />, element: <CreatePlansPage /> },
  { key: "/project-management", label: "项目管理", group: "核心业务", icon: <ToolOutlined />, element: <ProjectManagementPage /> },
  { key: "/account-remarks", label: "账户备注", group: "核心业务", icon: <EditOutlined />, element: <AccountRemarksPage /> },
  { key: "/sites", label: "落地页管理", group: "核心业务", icon: <LinkOutlined />, element: <SitesPage /> },
  { key: "/tasks", label: "任务中心", group: "系统记录", icon: <ClusterOutlined />, element: <TasksPage /> },
  { key: "/operations", label: "操作日志", group: "系统记录", icon: <HistoryOutlined />, element: <OperationsPage /> },
  { key: "/results", label: "结果中心", group: "系统记录", icon: <ProfileOutlined />, element: <ResultsPage /> },
  { key: "/execute", label: "链路探针", group: "高级工具", icon: <PlayCircleOutlined />, element: <ExecutionPage /> },
  { key: "/product-automation", label: "产品自动化配置", group: "高级工具", icon: <AppstoreOutlined />, element: <ProductAutomationPage /> },
  { key: "/settings", label: "系统设置", group: "高级工具", icon: <SettingOutlined />, element: <SystemSettingsPage /> },
] satisfies Array<{ key: string; label: string; group: "核心业务" | "系统记录" | "高级工具"; icon: ReactNode; element: ReactNode }>;
