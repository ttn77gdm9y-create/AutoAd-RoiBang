export type SummaryItem = {
  label: string;
  value: string | number | boolean | null;
};

export type TaskProgress = {
  percent: number;
  current: number;
  total: number;
  label: string;
  status: "normal" | "active" | "exception" | "success" | string;
};

export type ChineseSummary = {
  title: string;
  status: string;
  risk_level: "low" | "medium" | "high" | string;
  execution_enabled: boolean;
  items: SummaryItem[];
  warnings: string[];
  blocking_reasons: string[];
  progress?: TaskProgress;
};

export type ChineseTable = {
  columns: string[];
  rows: Record<string, string | number | boolean | null>[];
};

export type ChineseSection = {
  title: string;
  table: ChineseTable;
};

export type ChineseResult = {
  summary: ChineseSummary;
  table: ChineseTable;
  sections?: ChineseSection[];
  artifact_path?: string;
  raw: Record<string, unknown>;
};

export type AccountsQuery = {
  product_key?: string;
  channel?: string;
  owner?: string;
  status?: string;
};

export type TaskRow = {
  task_id: string;
  operation_type: string;
  operation_label: string;
  status: string;
  status_label: string;
  business_context: string;
  created_at: string;
  updated_at: string;
  return_code: number | null;
  artifact_path: string;
  result_artifact_path: string;
  result_summary: string;
  progress?: TaskProgress;
};

export type TaskListResponse = {
  items: TaskRow[];
};

export type TaskDetailResponse = ChineseResult & {
  task: Record<string, unknown>;
  stdout: string;
  stderr: string;
};

export type WorkflowParameter = {
  name: string;
  label: string;
  default: string;
  required: boolean;
  description: string;
  control?: "product_select" | "date_select" | "text" | string;
};

export type WorkflowLatestStatus = {
  status?: string;
  status_label?: string;
  run_at?: string;
  run_at_label?: string;
  source?: string;
  task_id?: string;
  artifact_path?: string;
  summary?: string;
};

export type WorkflowCatalogItem = {
  workflow_id: string;
  name: string;
  category: string;
  description: string;
  operation_type: string;
  latest_workflow: string;
  risk_level: string;
  true_action: boolean;
  ai_auto_run: boolean;
  parameters: WorkflowParameter[];
  latest_status?: WorkflowLatestStatus;
};

export type WorkflowRunResponse = ChineseResult & {
  task?: {
    task_id: string;
    pid: number;
    artifact_path: string;
  };
};

export type SettingsPayload = {
  project_root: string;
  runs_dir: string;
  configs_dir: string;
  streamlit_status: string;
};
