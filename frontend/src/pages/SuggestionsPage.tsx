import { FileSearchOutlined, ReloadOutlined } from "@ant-design/icons";
import {
  Alert,
  Button,
  Card,
  Col,
  Collapse,
  Descriptions,
  Form,
  Input,
  InputNumber,
  Row,
  Segmented,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  message as antdMessage,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { apiGet, apiPost } from "../api/client";
import { InlineTaskStatus, WorkflowSteps } from "../components/WorkflowScaffold";
import { SummaryPanel } from "../components/SummaryPanel";
import type { ChineseResult, TaskDetailResponse } from "../types/api";
import { isTaskActive, isTaskCompleted, taskStatus } from "../utils/workflowState";

type ProjectUpdateRequest = {
  suggestions_artifact_path: string;
  project_update_id: string;
  operator: string;
  product_key: string;
  product_name: string;
  allowed_target_accounts_path: string;
  selected_suggestion_ids: string[];
  suggested_actions: string[];
  output_path: string;
};

type CreatePlanFromSuggestionRequest = {
  suggestions_artifact_path: string;
  selected_suggestion_ids: string[];
  product_key: string;
  product_name: string;
  owner: string;
  target_date: string;
  template_catalog: string;
  cpa_bid: string;
  roi_coefficient: string;
};

type TaskResponse = ChineseResult & {
  task?: {
    task_id: string;
    artifact_path: string;
    pid: number;
  };
};

type SuggestionRow = Record<string, string | number | boolean | null>;

type SuggestionTypeFilter = "扩量机会" | "项目管理建议" | "只读诊断" | "全部";
type WorkbenchLane = "create-plan" | "project-update" | "";

type SuggestionsTablePagination = {
  current: number;
  pageSize: number;
};

type SuggestionsWorkbenchCache = {
  version: 1;
  productKey: string;
  lifecycleFilter: string;
  suggestionTypeFilter: SuggestionTypeFilter | "";
  projectUpdateRequest: ProjectUpdateRequest;
  createPlanRequest: CreatePlanFromSuggestionRequest;
  tablePagination: SuggestionsTablePagination;
  activeLane: WorkbenchLane;
};

type CreatePlanGroupRow = {
  groupId: string;
  product: string;
  mode: string;
  accountCount: number;
  sourceSuggestionCount: number;
  strategyIds: string;
  templateCatalog: string;
  evidence: string;
  status: string;
  sourceSuggestionIds: string[];
};

const suggestionsWorkbenchCacheKey = "roibang_suggestions_workbench_v1";
const suggestionsForceRefreshKey = "roibang_suggestions_force_refresh";
const suggestionsQueryCacheOptions = {
  staleTime: 30 * 60 * 1000,
  refetchOnMount: false as const,
};
const defaultSuggestionsPagination: SuggestionsTablePagination = { current: 1, pageSize: 8 };

function readSuggestionsWorkbenchCache(): Partial<SuggestionsWorkbenchCache> {
  try {
    const raw = window.sessionStorage.getItem(suggestionsWorkbenchCacheKey);
    if (!raw) {
      return {};
    }
    const parsed = JSON.parse(raw) as Partial<SuggestionsWorkbenchCache>;
    return parsed.version === 1 ? parsed : {};
  } catch {
    return {};
  }
}

function writeSuggestionsWorkbenchCache(cache: SuggestionsWorkbenchCache) {
  try {
    window.sessionStorage.setItem(
      suggestionsWorkbenchCacheKey,
      JSON.stringify({
        ...cache,
        activeLane: "",
        projectUpdateRequest: {
          ...cache.projectUpdateRequest,
          selected_suggestion_ids: [],
          suggested_actions: [],
        },
        createPlanRequest: {
          ...cache.createPlanRequest,
          selected_suggestion_ids: [],
        },
      }),
    );
  } catch {
    // Session storage can be unavailable in restricted browser contexts.
  }
}

function projectUpdatePathFromTask(detail?: TaskDetailResponse): string {
  const result = detail?.raw?.result;
  if (result && typeof result === "object" && "project_update_path" in result) {
    return String((result as { project_update_path?: unknown }).project_update_path ?? "").trim();
  }
  return "";
}

function plannedProjectUpdatePath(result?: TaskResponse): string {
  const preview = result?.raw?.preview;
  if (!preview || typeof preview !== "object") {
    return "";
  }
  const raw = (preview as { raw?: unknown }).raw;
  if (!raw || typeof raw !== "object") {
    return "";
  }
  const request = (raw as { request?: unknown }).request;
  if (!request || typeof request !== "object") {
    return "";
  }
  return String((request as { output_path?: unknown }).output_path ?? "").trim();
}

function asRecord(value: unknown): Record<string, unknown> | undefined {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : undefined;
}

function createPlanGroupsFromResult(result?: ChineseResult): CreatePlanGroupRow[] {
  const groups = Array.isArray(result?.raw?.suggestion_groups) ? result.raw.suggestion_groups : [];
  return groups
    .map((item) => {
      const group = asRecord(item);
      if (!group) {
        return undefined;
      }
      const evidence = asRecord(group.evidence_summary);
      const sourceSuggestionIds = Array.isArray(group.source_suggestion_ids)
        ? group.source_suggestion_ids.map(String).filter(Boolean)
        : [];
      const strategyIds = Array.isArray(group.strategy_labels)
        ? group.strategy_labels.map(String).filter(Boolean).join("、")
        : Array.isArray(group.strategy_ids)
          ? group.strategy_ids.map(String).filter(Boolean).join("、")
          : "";
      const groupId = String(group.group_id ?? "").trim();
      if (!groupId) {
        return undefined;
      }
      const evidenceParts = [];
      if (evidence && "min_project_capacity" in evidence) {
        evidenceParts.push(`最小容量 ${String(evidence.min_project_capacity ?? "")}`);
      }
      if (evidence && "min_qualified_material_count" in evidence) {
        evidenceParts.push(`最少合格素材 ${String(evidence.min_qualified_material_count ?? "")}`);
      }
      return {
        groupId: String(group.group_label ?? groupId),
        product: String(group.product_name ?? group.product_key ?? ""),
        mode: String(group.mode_label ?? group.mode_key ?? ""),
        accountCount: Number(group.account_count ?? 0),
        sourceSuggestionCount: Number(group.source_suggestion_count ?? 0),
        strategyIds,
        templateCatalog: String(group.template_label ?? group.template_catalog ?? ""),
        evidence: evidenceParts.join("，"),
        status: group.can_generate_single_plan ? "可生成创建计划预览" : "需补配置",
        sourceSuggestionIds,
      };
    })
    .filter((item): item is CreatePlanGroupRow => Boolean(item));
}

const emptyProjectUpdateRequest: ProjectUpdateRequest = {
  suggestions_artifact_path: "",
  project_update_id: "",
  operator: "",
  product_key: "",
  product_name: "",
  allowed_target_accounts_path: "",
  selected_suggestion_ids: [],
  suggested_actions: [],
  output_path: "",
};

const emptyCreatePlanRequest: CreatePlanFromSuggestionRequest = {
  suggestions_artifact_path: "",
  selected_suggestion_ids: [],
  product_key: "",
  product_name: "",
  owner: "",
  target_date: "",
  template_catalog: "",
  cpa_bid: "",
  roi_coefficient: "",
};

const actionOptions = [
  { label: "删除项目", value: "suggest_delete_project" },
  { label: "暂停项目", value: "suggest_close_project" },
  { label: "调预算", value: "suggest_lower_budget" },
  { label: "调出价", value: "suggest_lower_bid" },
  { label: "调整时段", value: "schedule_hollow" },
];

function rowText(row: SuggestionRow, key: string): string {
  return String(row[key] ?? "").trim();
}

function isCreateSuggestionRow(row: SuggestionRow): boolean {
  return (
    rowText(row, "建议类型") === "扩量机会" ||
    rowText(row, "建议动作") === "建议创建项目" ||
    rowText(row, "下一步") === "生成创建项目计划"
  );
}

function isProjectUpdateSuggestionRow(row: SuggestionRow): boolean {
  const suggestionType = rowText(row, "建议类型");
  if (suggestionType === "项目管理建议") {
    return true;
  }
  if (suggestionType === "扩量机会" || suggestionType === "只读诊断") {
    return false;
  }
  const configHint = rowText(row, "可生成管理配置") || rowText(row, "可转动作 JSON");
  return !isCreateSuggestionRow(row) && Boolean(configHint) && !configHint.includes("不生成");
}

function suggestionTypeForRow(row: SuggestionRow): Exclude<SuggestionTypeFilter, "全部"> {
  const suggestionType = rowText(row, "建议类型");
  if (suggestionType === "扩量机会" || suggestionType === "项目管理建议" || suggestionType === "只读诊断") {
    return suggestionType;
  }
  if (isCreateSuggestionRow(row)) {
    return "扩量机会";
  }
  if (isProjectUpdateSuggestionRow(row)) {
    return "项目管理建议";
  }
  return "只读诊断";
}

function isSelectableSuggestionRow(row: SuggestionRow): boolean {
  if (!rowText(row, "建议 ID")) {
    return false;
  }
  if (isCreateSuggestionRow(row)) {
    return !Boolean(row["创建建议锁定"]);
  }
  return isProjectUpdateSuggestionRow(row);
}

function suggestionPriorityColor(priority: string): string {
  if (priority === "高") {
    return "red";
  }
  if (priority === "中") {
    return "orange";
  }
  return "blue";
}

function suggestionNextStepColor(nextStep: string): string {
  if (nextStep === "生成创建项目计划") {
    return "green";
  }
  if (nextStep === "生成项目管理配置") {
    return "gold";
  }
  if (nextStep === "已进入执行链路") {
    return "purple";
  }
  return "default";
}

function summaryItemValue(result: ChineseResult | undefined, label: string): string {
  const item = result?.summary.items.find((entry) => entry.label === label);
  return item?.value === null || item?.value === undefined ? "" : String(item.value);
}

export function SuggestionsPage() {
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const cachedWorkbench = useMemo(() => readSuggestionsWorkbenchCache(), []);
  const suggestionListRef = useRef<HTMLDivElement>(null);
  const createPlanPanelRef = useRef<HTMLDivElement>(null);
  const projectUpdatePanelRef = useRef<HTMLDivElement>(null);
  const [productKey, setProductKey] = useState(searchParams.get("product_key")?.trim() || cachedWorkbench.productKey || "");
  const [lifecycleFilter, setLifecycleFilter] = useState(cachedWorkbench.lifecycleFilter ?? "");
  const [suggestionTypeFilter, setSuggestionTypeFilter] = useState<SuggestionTypeFilter | "">(
    parseSuggestionType(searchParams.get("suggestion_type")) ?? cachedWorkbench.suggestionTypeFilter ?? "",
  );
  const [projectUpdateRequest, setProjectUpdateRequest] = useState<ProjectUpdateRequest>({
    ...emptyProjectUpdateRequest,
    ...cachedWorkbench.projectUpdateRequest,
    selected_suggestion_ids: [],
    suggested_actions: [],
  });
  const [createPlanRequest, setCreatePlanRequest] = useState<CreatePlanFromSuggestionRequest>({
    ...emptyCreatePlanRequest,
    ...cachedWorkbench.createPlanRequest,
    selected_suggestion_ids: [],
  });
  const [suggestionsPagination, setSuggestionsPagination] = useState<SuggestionsTablePagination>(
    cachedWorkbench.tablePagination ?? defaultSuggestionsPagination,
  );
  const [activeLane, setActiveLane] = useState<WorkbenchLane>("");
  const [previewResult, setPreviewResult] = useState<ChineseResult | undefined>();
  const [generateResult, setGenerateResult] = useState<TaskResponse | undefined>();
  const [createPlanPreviewResult, setCreatePlanPreviewResult] = useState<ChineseResult | undefined>();
  const [createPlanGroupPreviewResults, setCreatePlanGroupPreviewResults] = useState<Record<string, ChineseResult>>({});
  const [activeCreatePlanGroupId, setActiveCreatePlanGroupId] = useState("");
  const [refreshResult, setRefreshResult] = useState<TaskResponse | undefined>();
  const [aiDraftResult, setAiDraftResult] = useState<ChineseResult | undefined>();
  const [backtestResult, setBacktestResult] = useState<ChineseResult | undefined>();
  const [backtestLookaheadDays, setBacktestLookaheadDays] = useState(1);
  const querySuffix = productKey ? `?product_key=${encodeURIComponent(productKey)}` : "";
  const currentStep = generateResult ? 2 : previewResult || createPlanPreviewResult ? 1 : 0;
  const taskId = generateResult?.task?.task_id ?? "";
  const refreshTaskId = refreshResult?.task?.task_id ?? "";

  const filterCatalog = useQuery({
    queryKey: ["dashboard", "filters"],
    queryFn: () => apiGet<ChineseResult>("/dashboard/filters"),
  });
  const overview = useQuery({
    queryKey: ["suggestions", "overview", productKey],
    queryFn: () => apiGet<ChineseResult>(`/suggestions/overview${querySuffix}`),
    refetchInterval: 60 * 60 * 1000,
    ...suggestionsQueryCacheOptions,
  });
  const dailyOperations = useQuery({
    queryKey: ["suggestions", "daily-operations", productKey],
    queryFn: () => apiGet<ChineseResult>(`/suggestions/daily-operations${querySuffix}`),
    refetchInterval: 60 * 60 * 1000,
    ...suggestionsQueryCacheOptions,
  });
  const suggestions = useQuery({
    queryKey: ["suggestions", "list", productKey],
    queryFn: () => apiGet<ChineseResult>(`/suggestions${querySuffix}`),
    refetchInterval: 60 * 60 * 1000,
    ...suggestionsQueryCacheOptions,
  });
  const createStrategies = useQuery({
    queryKey: ["suggestions", "create-strategies", productKey],
    queryFn: () => apiGet<ChineseResult>(`/suggestions/create-strategies${querySuffix}`),
    refetchInterval: 60 * 60 * 1000,
    ...suggestionsQueryCacheOptions,
  });
  const effectReview = useQuery({
    queryKey: ["suggestions", "effect-review", productKey],
    queryFn: () => apiGet<ChineseResult>(`/suggestions/effect-review${querySuffix}`),
    refetchInterval: 60 * 60 * 1000,
    ...suggestionsQueryCacheOptions,
  });
  const taskDetail = useQuery({
    queryKey: ["tasks", taskId],
    queryFn: () => apiGet<TaskDetailResponse>(`/tasks/${taskId}`),
    enabled: Boolean(taskId),
    refetchInterval: 3000,
  });
  const refreshTaskDetail = useQuery({
    queryKey: ["tasks", refreshTaskId],
    queryFn: () => apiGet<TaskDetailResponse>(`/tasks/${refreshTaskId}`),
    enabled: Boolean(refreshTaskId),
    refetchInterval: 3000,
  });
  const generatedProjectUpdatePath = projectUpdatePathFromTask(taskDetail.data);
  const expectedProjectUpdatePath = generatedProjectUpdatePath || plannedProjectUpdatePath(generateResult);

  useEffect(() => {
    const forceRefresh = window.sessionStorage.getItem(suggestionsForceRefreshKey);
    if (!forceRefresh) {
      return;
    }
    window.sessionStorage.removeItem(suggestionsForceRefreshKey);
    clearSelectedSuggestions();
    void queryClient.invalidateQueries({ queryKey: ["suggestions"] });
  }, [queryClient]);

  const productOptions = useMemo(() => rowsToProductOptions(filterCatalog.data), [filterCatalog.data]);
  const suggestionRows = useMemo<SuggestionRow[]>(() => suggestions.data?.table.rows ?? [], [suggestions.data]);
  const lifecycleOptions = useMemo(() => {
    const values = [
      ...new Set(
        suggestionRows
          .map((row) => String(row["创建状态"] ?? "").trim())
          .filter(Boolean),
      ),
    ];
    return values.map((value) => ({ label: value, value }));
  }, [suggestionRows]);
  const filteredSuggestionRows = useMemo(
    () => {
      if (!lifecycleFilter) {
        return suggestionRows;
      }
      const rows = suggestionRows.filter((row) => String(row["创建状态"] ?? "").trim() === lifecycleFilter);
      return rows.length > 0 || suggestionRows.length === 0 ? rows : suggestionRows;
    },
    [lifecycleFilter, suggestionRows],
  );
  useEffect(() => {
    if (lifecycleFilter && suggestionRows.length > 0 && filteredSuggestionRows.length === 0) {
      setLifecycleFilter("");
      setSuggestionsPagination((current) => ({ ...current, current: 1 }));
    }
  }, [filteredSuggestionRows.length, lifecycleFilter, suggestionRows.length]);
  const convertibleSuggestionRows = useMemo(
    () => filteredSuggestionRows.filter(isProjectUpdateSuggestionRow),
    [filteredSuggestionRows],
  );
  const createSuggestionRows = useMemo(
    () => filteredSuggestionRows.filter(isCreateSuggestionRow),
    [filteredSuggestionRows],
  );
  const readonlySuggestionCount = filteredSuggestionRows.length - convertibleSuggestionRows.length - createSuggestionRows.length;
  const preferredSuggestionTypeFilter = useMemo<SuggestionTypeFilter>(() => {
    if (createSuggestionRows.length > 0) {
      return "扩量机会";
    }
    if (convertibleSuggestionRows.length > 0) {
      return "项目管理建议";
    }
    if (readonlySuggestionCount > 0) {
      return "只读诊断";
    }
    return "全部";
  }, [convertibleSuggestionRows.length, createSuggestionRows.length, readonlySuggestionCount]);
  const effectiveSuggestionTypeFilter = suggestionTypeFilter || preferredSuggestionTypeFilter;
  const visibleSuggestionRows = useMemo(
    () =>
      effectiveSuggestionTypeFilter === "全部"
        ? filteredSuggestionRows
        : filteredSuggestionRows.filter((row) => suggestionTypeForRow(row) === effectiveSuggestionTypeFilter),
    [effectiveSuggestionTypeFilter, filteredSuggestionRows],
  );
  useEffect(() => {
    setSuggestionsPagination((current) => {
      const maxPage = Math.max(1, Math.ceil(visibleSuggestionRows.length / current.pageSize));
      return current.current > maxPage ? { ...current, current: maxPage } : current;
    });
  }, [visibleSuggestionRows.length]);
  const suggestionTypeOptions = useMemo(
    () => [
      { label: `扩量机会 ${createSuggestionRows.length}`, value: "扩量机会" },
      { label: `项目管理建议 ${convertibleSuggestionRows.length}`, value: "项目管理建议" },
      { label: `只读诊断 ${Math.max(readonlySuggestionCount, 0)}`, value: "只读诊断" },
      { label: `全部 ${filteredSuggestionRows.length}`, value: "全部" },
    ],
    [convertibleSuggestionRows.length, createSuggestionRows.length, filteredSuggestionRows.length, readonlySuggestionCount],
  );
  const visibleSuggestionIdSet = useMemo(
    () => new Set(visibleSuggestionRows.map((row) => rowText(row, "建议 ID")).filter(Boolean)),
    [visibleSuggestionRows],
  );
  const selectedSuggestionIds = useMemo(
    () =>
      [...createPlanRequest.selected_suggestion_ids, ...projectUpdateRequest.selected_suggestion_ids].filter((id) =>
        visibleSuggestionIdSet.has(id),
      ),
    [createPlanRequest.selected_suggestion_ids, projectUpdateRequest.selected_suggestion_ids, visibleSuggestionIdSet],
  );
  const selectedCreateRows = useMemo(
    () => visibleSuggestionRows.filter((row) => createPlanRequest.selected_suggestion_ids.includes(rowText(row, "建议 ID"))),
    [createPlanRequest.selected_suggestion_ids, visibleSuggestionRows],
  );
  const selectedProjectUpdateRows = useMemo(
    () => visibleSuggestionRows.filter((row) => projectUpdateRequest.selected_suggestion_ids.includes(rowText(row, "建议 ID"))),
    [projectUpdateRequest.selected_suggestion_ids, visibleSuggestionRows],
  );
  const selectedProjectUpdateCount = selectedProjectUpdateRows.length;
  const selectedCreateCount = selectedCreateRows.length;
  const hasSelectedSuggestions = selectedProjectUpdateCount > 0 || selectedCreateCount > 0;
  const suggestedSourceLabels = useMemo(() => {
    const values = [
      ...new Set(
        suggestionRows
          .map((row) => rowText(row, "数据来源"))
          .filter(Boolean),
      ),
    ];
    return values.length ? values.join("、") : "暂无建议来源";
  }, [suggestionRows]);
  const suggestionGeneratedAt = summaryItemValue(suggestions.data, "建议生成时间");
  const suggestionPatrolDate = summaryItemValue(suggestions.data, "今日巡检日期");
  const suggestionSpentAccountCount = summaryItemValue(suggestions.data, "今日巡检有消耗账户");
  const suggestionTargetAccountCount = summaryItemValue(suggestions.data, "建议对象账户");
  const lockedSelectedCreateSuggestionCount = useMemo(
    () =>
      suggestionRows.filter(
        (row) =>
          createPlanRequest.selected_suggestion_ids.includes(String(row["建议 ID"] ?? "")) &&
          Boolean(row["创建建议锁定"]),
      ).length,
    [createPlanRequest.selected_suggestion_ids, suggestionRows],
  );
  const suggestionColumns = useMemo<ColumnsType<SuggestionRow>>(
    () => [
      {
        title: "建议内容",
        dataIndex: "建议内容",
        key: "建议内容",
        width: 360,
        render: (_, row) => (
          <Space direction="vertical" size={2}>
            <Typography.Text strong>{rowText(row, "建议内容") || rowText(row, "中文解释")}</Typography.Text>
            <Space size={[4, 4]} wrap>
              <Tag color={suggestionPriorityColor(rowText(row, "优先级"))}>{rowText(row, "优先级") || "中"}</Tag>
              <Tag>{rowText(row, "建议类型") || rowText(row, "建议动作")}</Tag>
              {rowText(row, "数据来源") ? <Tag>{rowText(row, "数据来源")}</Tag> : null}
            </Space>
          </Space>
        ),
      },
      { title: "建议对象", dataIndex: "建议对象", key: "建议对象", width: 260, ellipsis: true },
      { title: "证据摘要", dataIndex: "证据摘要", key: "证据摘要", width: 300, ellipsis: true },
      {
        title: "状态 / 下一步",
        key: "next",
        width: 220,
        render: (_, row) => (
          <Space direction="vertical" size={2}>
            <Tag color={suggestionNextStepColor(rowText(row, "下一步"))}>{rowText(row, "下一步") || "只读观察"}</Tag>
            <Typography.Text type="secondary">{rowText(row, "创建状态") || "未处理"}</Typography.Text>
          </Space>
        ),
      },
      {
        title: "操作",
        key: "actions",
        width: 170,
        render: (_, row) => {
          const disabled = !isSelectableSuggestionRow(row);
          const buttonText = isCreateSuggestionRow(row) ? "选入创建计划" : "选入管理配置";
          return (
            <Button
              size="small"
              disabled={disabled}
              onClick={() => selectSuggestionForNextStep(row)}
            >
              {disabled ? "只读" : buttonText}
            </Button>
          );
        },
      },
    ],
    [],
  );
  const hasProjectUpdateScope =
    projectUpdateRequest.selected_suggestion_ids.length > 0 || projectUpdateRequest.suggested_actions.length > 0;
  const canPreviewProjectUpdate = Boolean(projectUpdateRequest.suggestions_artifact_path) && hasProjectUpdateScope;
  const canPreviewCreatePlan = Boolean(
    createPlanRequest.suggestions_artifact_path &&
      createPlanRequest.selected_suggestion_ids.length > 0 &&
      createPlanRequest.owner.trim() &&
      lockedSelectedCreateSuggestionCount === 0,
  );
  const refreshStatus = taskStatus(refreshTaskDetail.data, refreshResult);
  const refreshIsActive = isTaskActive(refreshStatus);
  const createPlanPreviewPath = createPlanPreviewResult?.artifact_path ?? "";
  const createPlanPreviewReady = createPlanPreviewResult?.summary.status === "planned" && Boolean(createPlanPreviewPath);
  const createPlanGroups = useMemo(() => createPlanGroupsFromResult(createPlanPreviewResult), [createPlanPreviewResult]);
  const returnToSuggestionsPath = useMemo(() => {
    const params = new URLSearchParams();
    if (productKey) {
      params.set("product_key", productKey);
    }
    if (effectiveSuggestionTypeFilter) {
      params.set("suggestion_type", effectiveSuggestionTypeFilter);
    }
    params.set("focus", "list");
    return `/suggestions?${params.toString()}`;
  }, [effectiveSuggestionTypeFilter, productKey]);

  function updateSuggestionSearch(patch: Record<string, string | null>) {
    const next = new URLSearchParams(searchParams);
    Object.entries(patch).forEach(([key, value]) => {
      if (value) {
        next.set(key, value);
      } else {
        next.delete(key);
      }
    });
    setSearchParams(next);
  }

  useEffect(() => {
    writeSuggestionsWorkbenchCache({
      version: 1,
      productKey,
      lifecycleFilter,
      suggestionTypeFilter,
      projectUpdateRequest,
      createPlanRequest,
      tablePagination: suggestionsPagination,
      activeLane,
    });
  }, [
    activeLane,
    createPlanRequest,
    lifecycleFilter,
    productKey,
    projectUpdateRequest,
    suggestionTypeFilter,
    suggestionsPagination,
  ]);

  useEffect(() => {
    const nextProductKey = searchParams.get("product_key")?.trim() ?? "";
    if (nextProductKey && nextProductKey !== productKey) {
      setProductKey(nextProductKey);
    }
    const nextSuggestionType = parseSuggestionType(searchParams.get("suggestion_type"));
    if (nextSuggestionType && nextSuggestionType !== suggestionTypeFilter) {
      setSuggestionTypeFilter(nextSuggestionType);
    }
  }, [searchParams, productKey, suggestionTypeFilter]);

  useEffect(() => {
    const option = productOptions.find((item) => item.value === productKey);
    const productName = option?.label ?? "";
    setProjectUpdateRequest((current) =>
      current.product_key === productKey && current.product_name === productName
        ? current
        : { ...current, product_key: productKey, product_name: productName },
    );
    setCreatePlanRequest((current) =>
      current.product_key === productKey && current.product_name === productName
        ? current
        : { ...current, product_key: productKey, product_name: productName },
    );
  }, [productKey, productOptions]);

  useEffect(() => {
    if (searchParams.get("focus") !== "list") {
      return undefined;
    }
    const timer = window.setTimeout(() => {
      suggestionListRef.current?.scrollIntoView({ block: "start", behavior: "smooth" });
    }, 120);
    return () => window.clearTimeout(timer);
  }, [searchParams, suggestions.isLoading]);

  useEffect(() => {
    const artifactPath = suggestions.data?.artifact_path ?? "";
    if (!artifactPath) {
      return;
    }
    const projectArtifactChanged = Boolean(
      projectUpdateRequest.suggestions_artifact_path && projectUpdateRequest.suggestions_artifact_path !== artifactPath,
    );
    const createArtifactChanged = Boolean(
      createPlanRequest.suggestions_artifact_path && createPlanRequest.suggestions_artifact_path !== artifactPath,
    );
    if (artifactPath !== projectUpdateRequest.suggestions_artifact_path) {
      setProjectUpdateRequest((current) => ({
        ...current,
        suggestions_artifact_path: artifactPath,
        selected_suggestion_ids: projectArtifactChanged ? [] : current.selected_suggestion_ids,
        suggested_actions: projectArtifactChanged ? [] : current.suggested_actions,
      }));
    }
    if (artifactPath !== createPlanRequest.suggestions_artifact_path) {
      setCreatePlanRequest((current) => ({
        ...current,
        suggestions_artifact_path: artifactPath,
        selected_suggestion_ids: createArtifactChanged ? [] : current.selected_suggestion_ids,
      }));
    }
    if (projectArtifactChanged || createArtifactChanged) {
      setPreviewResult(undefined);
      setGenerateResult(undefined);
      setCreatePlanPreviewResult(undefined);
      setCreatePlanGroupPreviewResults({});
      setActiveLane("");
      antdMessage.info("建议来源已更新，已清空旧选择；请重新选择本次建议。");
    }
  }, [suggestions.data?.artifact_path, projectUpdateRequest.suggestions_artifact_path, createPlanRequest.suggestions_artifact_path]);

  const preview = useMutation({
    mutationFn: () => apiPost<ChineseResult>("/suggestions/project-update/preview", projectUpdateRequest),
    onSuccess: (result) => {
      setPreviewResult(result);
      setGenerateResult(undefined);
    },
  });
  const generate = useMutation({
    mutationFn: () => apiPost<TaskResponse>("/suggestions/project-update/generate", projectUpdateRequest),
    onSuccess: async (result) => {
      setGenerateResult(result);
      await queryClient.invalidateQueries({ queryKey: ["tasks"] });
      antdMessage.success("项目管理配置生成任务已提交，没有执行真实业务动作");
    },
  });
  const createPlanPreview = useMutation({
    mutationFn: () => apiPost<ChineseResult>("/suggestions/create-plan/preview", createPlanRequest),
    onSuccess: (result) => {
      setCreatePlanPreviewResult(result);
      setCreatePlanGroupPreviewResults({});
      antdMessage.success("创建计划预览已生成，没有执行真实创建");
    },
  });
  const createPlanGroupPreview = useMutation({
    mutationFn: (group: CreatePlanGroupRow) =>
      apiPost<ChineseResult>("/suggestions/create-plan/preview", {
        ...createPlanRequest,
        selected_suggestion_ids: group.sourceSuggestionIds,
      }),
    onSuccess: (result, group) => {
      setCreatePlanGroupPreviewResults((current) => ({ ...current, [group.groupId]: result }));
      antdMessage.success("该批创建计划预览已生成，没有执行真实创建");
    },
    onSettled: () => {
      setActiveCreatePlanGroupId("");
    },
  });
  const createPlanGroupColumns = useMemo<ColumnsType<CreatePlanGroupRow>>(
    () => [
      { title: "批次", dataIndex: "groupId", key: "groupId", width: 170, ellipsis: true },
      { title: "产品", dataIndex: "product", key: "product", width: 140, ellipsis: true },
      { title: "推荐模式", dataIndex: "mode", key: "mode", width: 180, ellipsis: true },
      { title: "账户数", dataIndex: "accountCount", key: "accountCount", width: 90 },
      { title: "来源建议", dataIndex: "sourceSuggestionCount", key: "sourceSuggestionCount", width: 100 },
      { title: "命中策略", dataIndex: "strategyIds", key: "strategyIds", width: 180, ellipsis: true },
      { title: "证据", dataIndex: "evidence", key: "evidence", width: 220, ellipsis: true },
      { title: "状态", dataIndex: "status", key: "status", width: 150 },
      {
        title: "操作",
        key: "actions",
        width: 260,
        render: (_, row) => {
          const groupResult = createPlanGroupPreviewResults[row.groupId];
          const groupPath = groupResult?.artifact_path ?? "";
          const ready = groupResult?.summary.status === "planned" && Boolean(groupPath);
          return (
            <Space wrap>
              <Button
                size="small"
                loading={createPlanGroupPreview.isPending && activeCreatePlanGroupId === row.groupId}
                disabled={!row.sourceSuggestionIds.length}
                onClick={() => {
                  setActiveCreatePlanGroupId(row.groupId);
                  createPlanGroupPreview.mutate(row);
                }}
              >
                检查该批创建计划
              </Button>
              {ready ? (
                <Link
                  to={`/create-plans?create_plan_preview_path=${encodeURIComponent(groupPath)}&return_to=${encodeURIComponent(returnToSuggestionsPath)}`}
                >
                  <Button size="small" type="primary">
                    去创建计划页确认
                  </Button>
                </Link>
              ) : null}
            </Space>
          );
        },
      },
    ],
    [activeCreatePlanGroupId, createPlanGroupPreview, createPlanGroupPreviewResults, returnToSuggestionsPath],
  );
  const refresh = useMutation({
    mutationFn: () => apiPost<TaskResponse>("/suggestions/refresh", { product_key: productKey, target_date: "today" }),
    onSuccess: async (result) => {
      setRefreshResult(result);
      await queryClient.invalidateQueries({ queryKey: ["tasks"] });
      antdMessage.success("同步数据并重算建议任务已提交，只做只读同步和本地重算");
    },
  });
  const aiDraft = useMutation({
    mutationFn: () =>
      apiPost<ChineseResult>("/suggestions/ai-draft", {
        ...projectUpdateRequest,
        product_key: productKey || projectUpdateRequest.product_key,
      }),
    onSuccess: (result) => {
      setAiDraftResult(result);
      antdMessage.success("AI 建议草稿已生成，没有执行真实业务动作");
    },
  });
  const backtest = useMutation({
    mutationFn: () =>
      apiPost<ChineseResult>("/suggestions/backtest", {
        suggestions_artifact_path: projectUpdateRequest.suggestions_artifact_path,
        product_key: productKey,
        lookahead_days: backtestLookaheadDays,
    }),
    onSuccess: (result) => {
      setBacktestResult(result);
      antdMessage.success("建议复盘已刷新，没有执行真实业务动作");
    },
  });

  function updateProjectRequest(patch: Partial<ProjectUpdateRequest>) {
    setProjectUpdateRequest((current) => ({ ...current, ...patch }));
    setAiDraftResult(undefined);
    setPreviewResult(undefined);
    setGenerateResult(undefined);
  }

  function updateCreatePlanRequest(patch: Partial<CreatePlanFromSuggestionRequest>) {
    setCreatePlanRequest((current) => ({ ...current, ...patch }));
    setCreatePlanPreviewResult(undefined);
    setCreatePlanGroupPreviewResults({});
  }

  function focusWorkbenchLane(lane: WorkbenchLane) {
    setActiveLane(lane);
    window.setTimeout(() => {
      const target = lane === "create-plan" ? createPlanPanelRef.current : projectUpdatePanelRef.current;
      target?.scrollIntoView({ block: "start", behavior: "smooth" });
    }, 80);
  }

  function clearSelectedSuggestions() {
    updateCreatePlanRequest({ selected_suggestion_ids: [] });
    updateProjectRequest({ selected_suggestion_ids: [], suggested_actions: [] });
    setActiveLane("");
  }

  function selectSuggestionForNextStep(row: SuggestionRow) {
    const id = rowText(row, "建议 ID");
    if (!id) {
      return;
    }
    if (isCreateSuggestionRow(row)) {
      updateCreatePlanRequest({ selected_suggestion_ids: [id] });
      updateProjectRequest({ selected_suggestion_ids: [] });
      focusWorkbenchLane("create-plan");
    } else if (isProjectUpdateSuggestionRow(row)) {
      updateProjectRequest({ selected_suggestion_ids: [id] });
      updateCreatePlanRequest({ selected_suggestion_ids: [] });
      focusWorkbenchLane("project-update");
    }
  }

  useEffect(() => {
    if (!isTaskCompleted(refreshStatus)) {
      return;
    }
    void queryClient.invalidateQueries({ queryKey: ["suggestions"] });
  }, [queryClient, refreshStatus]);

  return (
    <main className="page">
      <Space direction="vertical" size="large" className="full-width">
        <Typography.Title level={2}>投放建议工作台</Typography.Title>
        <WorkflowSteps current={currentStep} items={["查看建议", "生成计划或配置", "去页面确认"]} />
        <Alert
          type="info"
          showIcon
          message="这里按产品汇总扩量、止损和诊断建议；工作台只生成计划或配置预览，真实执行必须去对应页面人工确认。"
        />
        <Form layout="inline" className="filter-bar">
          <Form.Item label="产品">
            <Select
              allowClear
              className="dashboard-filter-select"
              loading={filterCatalog.isLoading}
              value={productKey || undefined}
              onChange={(value) => {
                const nextProductKey = value ?? "";
                const option = productOptions.find((item) => item.value === nextProductKey);
                setProductKey(nextProductKey);
                updateSuggestionSearch({ product_key: nextProductKey || null });
                setLifecycleFilter("");
                setSuggestionTypeFilter("");
                setSuggestionsPagination((current) => ({ ...current, current: 1 }));
                setActiveLane("");
                setProjectUpdateRequest((current) => ({
                  ...current,
                  product_key: nextProductKey,
                  product_name: option?.label ?? "",
                  selected_suggestion_ids: [],
                }));
                setCreatePlanRequest((current) => ({
                  ...current,
                  product_key: nextProductKey,
                  product_name: option?.label ?? "",
                  selected_suggestion_ids: [],
                }));
                setPreviewResult(undefined);
                setGenerateResult(undefined);
                setCreatePlanPreviewResult(undefined);
                setCreatePlanGroupPreviewResults({});
                setAiDraftResult(undefined);
                setBacktestResult(undefined);
              }}
              options={productOptions}
            />
          </Form.Item>
          <Form.Item label="创建状态">
            <Select
              allowClear
              className="dashboard-filter-select"
              value={lifecycleFilter || undefined}
              onChange={(value) => {
                setLifecycleFilter(value ?? "");
                setSuggestionTypeFilter("");
                setSuggestionsPagination((current) => ({ ...current, current: 1 }));
              }}
              options={lifecycleOptions}
              placeholder="全部状态"
            />
          </Form.Item>
          <Form.Item>
            <Button
              icon={<ReloadOutlined />}
              type="primary"
              loading={refresh.isPending || refreshIsActive}
              disabled={refresh.isPending || refreshIsActive}
              onClick={() => refresh.mutate()}
            >
              同步数据并重算建议
            </Button>
          </Form.Item>
        </Form>

        {refresh.error ? <Alert type="error" showIcon message={(refresh.error as Error).message} /> : null}
        <InlineTaskStatus
          title="同步并重算建议结果"
          taskId={refreshTaskId}
          workflow="suggestions_refresh"
          result={refreshResult}
          detail={refreshTaskDetail.data}
          loading={refresh.isPending || refreshTaskDetail.isFetching}
          returnTo={returnToSuggestionsPath}
        />

        <Card size="small" title="数据更新与建议状态">
          <Space direction="vertical" size="middle" className="full-width">
            <Alert
              type="info"
              showIcon
              message="这里汇总数据是否更新、建议是否生成、扩量机会是否可用和复盘是否完成；只读展示，不执行真实业务动作。"
            />
            <Space wrap className="workflow-actions">
              <Button
                icon={<ReloadOutlined />}
                loading={dailyOperations.isFetching}
                onClick={() => {
                  void dailyOperations.refetch();
                }}
              >
                刷新状态
              </Button>
            </Space>
            {dailyOperations.error ? <Alert type="error" showIcon message={(dailyOperations.error as Error).message} /> : null}
            <SummaryPanel
              result={dailyOperations.data}
              loading={dailyOperations.isLoading}
              detailsCollapsed
              showArtifactPath={false}
              showRawJson={false}
            />
          </Space>
        </Card>

        {overview.error ? <Alert type="error" showIcon message={(overview.error as Error).message} /> : null}
        <SummaryPanel result={overview.data} loading={overview.isLoading} detailsCollapsed showArtifactPath={false} showRawJson={false} />

        <Card size="small" title="扩量机会扫描">
          <Space direction="vertical" size="middle" className="full-width">
            <Alert
              type="info"
              showIcon
              message="这里只读扫描哪些账户还有项目容量、素材是否够、转化/ROI 是否达标；不生成创建计划、不执行真实创建。"
            />
            <Space wrap className="workflow-actions">
              <Button
                icon={<ReloadOutlined />}
                loading={createStrategies.isFetching}
                onClick={() => {
                  void createStrategies.refetch();
                }}
              >
                重新扫描扩量机会
              </Button>
            </Space>
            {createStrategies.error ? <Alert type="error" showIcon message={(createStrategies.error as Error).message} /> : null}
            <SummaryPanel
              result={createStrategies.data}
              loading={createStrategies.isLoading}
              detailsCollapsed
              showArtifactPath={false}
              showRawJson={false}
            />
          </Space>
        </Card>

        {suggestions.error ? <Alert type="error" showIcon message={(suggestions.error as Error).message} /> : null}
        <SummaryPanel result={suggestions.data} loading={suggestions.isLoading} detailsCollapsed showArtifactPath={false} showRawJson={false} />

        <div ref={suggestionListRef}>
        <Card size="small" title="建议处理区">
          <Space direction="vertical" size="middle" className="full-width">
            <Alert
              type="info"
              showIcon
              message="当前建议快照"
              description={
                <Space size={[8, 8]} wrap>
                  <Tag>生成时间：{suggestionGeneratedAt || "未提供"}</Tag>
                  <Tag>实时巡检日期：{suggestionPatrolDate || "未找到"}</Tag>
                  <Tag>有消耗账户：{suggestionSpentAccountCount || "0"}</Tag>
                  <Tag>建议对象账户：{suggestionTargetAccountCount || "0"}</Tag>
                  <Tag>来源：{suggestedSourceLabels}</Tag>
                </Space>
              }
            />
            <Alert
              type="info"
              showIcon
              message={`当前 ${createSuggestionRows.length} 条扩量机会、${convertibleSuggestionRows.length} 条项目管理建议、${Math.max(readonlySuggestionCount, 0)} 条只读诊断；正在显示 ${effectiveSuggestionTypeFilter} ${visibleSuggestionRows.length} 条。`}
            />
            <Space wrap align="center">
              <Typography.Text strong>建议类型</Typography.Text>
              <Segmented
                value={effectiveSuggestionTypeFilter}
                options={suggestionTypeOptions}
                onChange={(value) => {
                  setSuggestionTypeFilter(value as SuggestionTypeFilter);
                  updateSuggestionSearch({ suggestion_type: String(value) });
                  setSuggestionsPagination((current) => ({ ...current, current: 1 }));
                  setActiveLane("");
                  updateCreatePlanRequest({ selected_suggestion_ids: [] });
                  updateProjectRequest({ selected_suggestion_ids: [] });
                }}
              />
            </Space>
            {!suggestions.isLoading && visibleSuggestionRows.length === 0 ? (
              <Alert
                type="info"
                showIcon
                message="当前分组没有建议；可以切换建议类型、同步数据并重算建议，或换一个产品查看。"
              />
            ) : null}
            <Table
              rowKey={(row) => String(row["建议 ID"] ?? "")}
              loading={suggestions.isLoading}
              columns={suggestionColumns}
              dataSource={visibleSuggestionRows}
              pagination={{
                current: suggestionsPagination.current,
                pageSize: suggestionsPagination.pageSize,
                showSizeChanger: true,
                pageSizeOptions: ["8", "10", "20", "50", "100"],
                onChange: (current, pageSize) => setSuggestionsPagination({ current, pageSize }),
                onShowSizeChange: (_current, pageSize) => setSuggestionsPagination({ current: 1, pageSize }),
              }}
              size="small"
              scroll={{ x: "max-content" }}
              expandable={{
                expandedRowRender: (row) => (
                  <Descriptions size="small" column={{ xs: 1, md: 2 }} bordered>
                    <Descriptions.Item label="原始建议 ID">{rowText(row, "建议 ID")}</Descriptions.Item>
                    <Descriptions.Item label="来源文件">{rowText(row, "来源文件")}</Descriptions.Item>
                    <Descriptions.Item label="命中策略">{rowText(row, "命中策略") || "未提供"}</Descriptions.Item>
                    <Descriptions.Item label="学习依据">{rowText(row, "学习依据") || "未提供"}</Descriptions.Item>
                    <Descriptions.Item label="动作取舍">{rowText(row, "动作取舍") || "未提供"}</Descriptions.Item>
                    <Descriptions.Item label="推荐模式">{rowText(row, "推荐模式") || "不涉及"}</Descriptions.Item>
                    <Descriptions.Item label="计划预览">{rowText(row, "计划预览") || "未生成"}</Descriptions.Item>
                    <Descriptions.Item label="执行前复核">{rowText(row, "执行前复核") || "未进入"}</Descriptions.Item>
                    <Descriptions.Item label="执行任务">{rowText(row, "执行任务") || "未提交"}</Descriptions.Item>
                    <Descriptions.Item label="完整说明">{rowText(row, "中文解释")}</Descriptions.Item>
                  </Descriptions>
                ),
              }}
              rowSelection={{
                selectedRowKeys: selectedSuggestionIds,
                onChange: (keys) => {
                  const keySet = new Set(keys.map(String));
                  const selectedRows = visibleSuggestionRows.filter((row) => keySet.has(rowText(row, "建议 ID")));
                  const nextCreateIds = selectedRows.filter(isCreateSuggestionRow).map((row) => rowText(row, "建议 ID"));
                  const nextProjectUpdateIds = selectedRows.filter(isProjectUpdateSuggestionRow).map((row) => rowText(row, "建议 ID"));
                  updateCreatePlanRequest({
                    selected_suggestion_ids: nextCreateIds,
                  });
                  updateProjectRequest({
                    selected_suggestion_ids: nextProjectUpdateIds,
                  });
                  setActiveLane(nextProjectUpdateIds.length ? "project-update" : nextCreateIds.length ? "create-plan" : "");
                },
                preserveSelectedRowKeys: false,
                getCheckboxProps: (row) => ({
                  disabled: !isSelectableSuggestionRow(row),
                }),
              }}
            />
            <Typography.Text type="secondary">
              已选择 {selectedCreateRows.length} 条扩量机会、{selectedProjectUpdateRows.length} 条项目管理建议；只读诊断不进入执行链路。
            </Typography.Text>
            {hasSelectedSuggestions ? (
              <div className="suggestion-action-bar">
                <Space wrap align="center">
                  <Typography.Text strong>
                    已选 {selectedCreateCount} 条扩量机会、{selectedProjectUpdateCount} 条项目管理建议
                  </Typography.Text>
                  {selectedProjectUpdateCount > 0 ? (
                    <Button
                      type="primary"
                      loading={preview.isPending}
                      disabled={!canPreviewProjectUpdate}
                      onClick={() => {
                        focusWorkbenchLane("project-update");
                        preview.mutate();
                      }}
                    >
                      检查项目管理配置
                    </Button>
                  ) : null}
                  {selectedCreateCount > 0 ? (
                    <Button
                      type="primary"
                      loading={createPlanPreview.isPending}
                      disabled={!canPreviewCreatePlan}
                      onClick={() => {
                        focusWorkbenchLane("create-plan");
                        createPlanPreview.mutate();
                      }}
                    >
                      检查创建计划
                    </Button>
                  ) : null}
                  <Button onClick={clearSelectedSuggestions}>清空选择</Button>
                </Space>
              </div>
            ) : null}
            {selectedProjectUpdateRows.length > 0 ? (
              <Alert
                type={activeLane === "project-update" ? "success" : "info"}
                showIcon
                message={`已选 ${selectedProjectUpdateRows.length} 条项目管理建议`}
                description="下一步检查项目管理配置，确认动作明细无误后再生成配置；真实执行仍在项目管理页输入确认。"
                action={
                  <Space wrap>
                    <Button onClick={() => focusWorkbenchLane("project-update")}>查看管理配置区</Button>
                    <Button
                      type="primary"
                      loading={preview.isPending}
                      disabled={!canPreviewProjectUpdate}
                      onClick={() => preview.mutate()}
                    >
                      检查项目管理配置
                    </Button>
                  </Space>
                }
              />
            ) : null}
            {selectedCreateRows.length > 0 ? (
              <Alert
                type={activeLane === "create-plan" ? "success" : "info"}
                showIcon
                message={`已选 ${selectedCreateRows.length} 条扩量机会`}
                description={
                  createPlanRequest.owner.trim()
                    ? "下一步检查创建计划预览，再进入创建计划页人工确认。"
                    : "请先填写负责人，再检查创建计划预览。"
                }
                action={
                  <Space wrap>
                    <Button onClick={() => focusWorkbenchLane("create-plan")}>查看创建计划区</Button>
                    <Button
                      type="primary"
                      loading={createPlanPreview.isPending}
                      disabled={!canPreviewCreatePlan}
                      onClick={() => createPlanPreview.mutate()}
                    >
                      检查创建计划
                    </Button>
                  </Space>
                }
              />
            ) : null}
            {lockedSelectedCreateSuggestionCount > 0 ? (
              <Alert
                type="warning"
                showIcon
                message={`已选择 ${lockedSelectedCreateSuggestionCount} 条已进入执行链路的创建建议，不能重复生成创建计划。`}
              />
            ) : null}
            <Row gutter={[24, 16]}>
              <Col xs={24} xl={12}>
                <div ref={createPlanPanelRef}>
                <Space direction="vertical" size="small" className="full-width">
                  <Typography.Title level={4}>生成创建项目计划</Typography.Title>
                  <Alert
                    type={selectedCreateRows.length ? "info" : "warning"}
                    showIcon
                    message={
                      selectedCreateRows.length
                        ? `已选 ${selectedCreateRows.length} 条扩量机会；这里只把策略建议转成创建计划预览，不真实创建项目。`
                        : "选择“扩量机会”后，先检查创建计划，再去创建计划页人工确认。"
                    }
                    description="扩量门槛、素材资格、预算、项目数和单元数来自创建建议策略与固定创建模式；页面只负责选择建议、填写负责人和发起预览。"
                  />
                  <Form layout="vertical" className="filter-bar">
                    <Row gutter={[16, 0]}>
                      <Col xs={24} lg={12}>
                        <Form.Item label="负责人（必填）">
                          <Input
                            value={createPlanRequest.owner}
                            onChange={(event) => updateCreatePlanRequest({ owner: event.target.value })}
                            placeholder="创建计划页会继续复核"
                          />
                        </Form.Item>
                      </Col>
                      <Col xs={24} lg={12}>
                        <Form.Item label="计划日期（可空，默认用建议日期）">
                          <Input
                            value={createPlanRequest.target_date}
                            onChange={(event) => updateCreatePlanRequest({ target_date: event.target.value })}
                            placeholder="例如 2026-05-31"
                          />
                        </Form.Item>
                      </Col>
                      <Col xs={24}>
                        <Form.Item label="创建模板（可空，后端按产品匹配）">
                          <Input
                            value={createPlanRequest.template_catalog}
                            onChange={(event) => updateCreatePlanRequest({ template_catalog: event.target.value })}
                            placeholder="例如 configs/create-templates/xxx.local.json"
                          />
                        </Form.Item>
                      </Col>
                      <Col xs={24}>
                        <Collapse
                          className="advanced-fields"
                          items={[
                            {
                              key: "create-plan-overrides",
                              label: "高级信息：人工覆盖出价和 ROI 系数",
                              children: (
                                <Row gutter={[16, 0]}>
                                  <Col xs={24}>
                                    <Alert
                                      type="warning"
                                      showIcon
                                      message="默认不要填写这里；只有人工已经确认本次要覆盖固定创建模式时才填写。"
                                    />
                                  </Col>
                                  <Col xs={24} lg={12}>
                                    <Form.Item label="本次项目出价（可空）">
                                      <Input
                                        value={createPlanRequest.cpa_bid}
                                        onChange={(event) => updateCreatePlanRequest({ cpa_bid: event.target.value })}
                                      />
                                    </Form.Item>
                                  </Col>
                                  <Col xs={24} lg={12}>
                                    <Form.Item label="本次 ROI 系数（可空）">
                                      <Input
                                        value={createPlanRequest.roi_coefficient}
                                        onChange={(event) => updateCreatePlanRequest({ roi_coefficient: event.target.value })}
                                      />
                                    </Form.Item>
                                  </Col>
                                </Row>
                              ),
                            },
                          ]}
                        />
                      </Col>
                    </Row>
                  </Form>
                  <Space wrap className="workflow-actions">
                    <Button
                      icon={<FileSearchOutlined />}
                      type="primary"
                      loading={createPlanPreview.isPending}
                      disabled={!canPreviewCreatePlan}
                      onClick={() => createPlanPreview.mutate()}
                    >
                      检查创建计划
                    </Button>
                    {createPlanPreviewReady ? (
                      <Link
                        to={`/create-plans?create_plan_preview_path=${encodeURIComponent(createPlanPreviewPath)}&return_to=${encodeURIComponent(returnToSuggestionsPath)}`}
                      >
                        <Button type="primary">去创建计划页确认</Button>
                      </Link>
                    ) : null}
                  </Space>
                  {createPlanPreview.error ? <Alert type="error" showIcon message={(createPlanPreview.error as Error).message} /> : null}
                  <SummaryPanel
                    result={createPlanPreviewResult}
                    loading={createPlanPreview.isPending}
                    detailsCollapsed
                    showArtifactPath={false}
                    showRawJson={false}
                  />
                </Space>
                </div>
              </Col>
              <Col xs={24} xl={12}>
                <div ref={projectUpdatePanelRef}>
                <Space direction="vertical" size="small" className="full-width">
                  <Typography.Title level={4}>生成项目管理配置</Typography.Title>
                  <Alert
                    type={selectedProjectUpdateRows.length || projectUpdateRequest.suggested_actions.length ? "info" : "warning"}
                    showIcon
                    message={
                      selectedProjectUpdateRows.length
                        ? `已选 ${selectedProjectUpdateRows.length} 条项目管理建议；这里只生成项目管理配置，再去项目管理页确认执行。`
                        : "选择删除、暂停、调预算、调出价等项目管理建议后，先检查配置，再去项目管理页确认。"
                    }
                    description="只读诊断和扩量机会不会进入项目管理配置；删除、暂停、预算、出价和时段动作仍必须在项目管理页预览并输入确认。"
                  />
                  <Form layout="vertical" className="filter-bar">
                    <Row gutter={[16, 0]}>
                      <Col xs={24} lg={12}>
                        <Form.Item label="操作人（可空）">
                          <Input
                            value={projectUpdateRequest.operator}
                            onChange={(event) => updateProjectRequest({ operator: event.target.value })}
                          />
                        </Form.Item>
                      </Col>
                      <Col xs={24} lg={12}>
                        <Collapse
                          className="advanced-fields"
                          items={[
                            {
                              key: "project-update-batch-actions",
                              label: "高级信息：未选建议时按动作批量生成",
                              children: (
                                <Form.Item label="批量生成动作类型">
                                  <Select
                                    mode="multiple"
                                    allowClear
                                    value={projectUpdateRequest.suggested_actions}
                                    onChange={(values) => updateProjectRequest({ suggested_actions: values })}
                                    options={actionOptions}
                                  />
                                </Form.Item>
                              ),
                            },
                          ]}
                        />
                      </Col>
                      <Col xs={24}>
                        <Collapse
                          className="advanced-fields"
                          items={[
                            {
                              key: "project-update-json",
                              label: "高级信息：配置来源和输出位置",
                              children: (
                                <Row gutter={[16, 0]}>
                                  <Col xs={24} lg={12}>
                                    <Form.Item label="建议来源文件（自动读取，可手动替换）">
                                      <Input
                                        value={projectUpdateRequest.suggestions_artifact_path}
                                        onChange={(event) => updateProjectRequest({ suggestions_artifact_path: event.target.value })}
                                      />
                                    </Form.Item>
                                  </Col>
                                  <Col xs={24} lg={12}>
                                    <Form.Item label="配置 ID（可空，系统自动生成）">
                                      <Input
                                        value={projectUpdateRequest.project_update_id}
                                        onChange={(event) => updateProjectRequest({ project_update_id: event.target.value })}
                                        placeholder="不填则自动生成"
                                      />
                                    </Form.Item>
                                  </Col>
                                  <Col xs={24} lg={12}>
                                    <Form.Item label="允许账户名单路径（可空）">
                                      <Input
                                        value={projectUpdateRequest.allowed_target_accounts_path}
                                        onChange={(event) => updateProjectRequest({ allowed_target_accounts_path: event.target.value })}
                                        placeholder="可空；生成配置时写入来源"
                                      />
                                    </Form.Item>
                                  </Col>
                                  <Col xs={24} lg={12}>
                                    <Form.Item label="配置文件路径（可空，系统自动生成）">
                                      <Input
                                        value={projectUpdateRequest.output_path}
                                        onChange={(event) => updateProjectRequest({ output_path: event.target.value })}
                                        placeholder="不填则保存到 configs/project-updates/"
                                      />
                                    </Form.Item>
                                  </Col>
                                </Row>
                              ),
                            },
                          ]}
                        />
                      </Col>
                    </Row>
                  </Form>
                  <Space wrap className="workflow-actions">
                    <Button
                      icon={<FileSearchOutlined />}
                      type="primary"
                      loading={preview.isPending}
                      disabled={!canPreviewProjectUpdate}
                      onClick={() => preview.mutate()}
                    >
                      检查项目管理配置
                    </Button>
                    <Button disabled={previewResult?.summary.status !== "planned"} loading={generate.isPending} onClick={() => generate.mutate()}>
                      生成项目管理配置
                    </Button>
                  </Space>
                  <Collapse
                    className="advanced-fields"
                    items={[
                      {
                        key: "ai-draft",
                        label: "辅助复核：生成 AI 建议草稿",
                        children: (
                          <Space direction="vertical" size="small" className="full-width">
                            <Alert
                              type="info"
                              showIcon
                              message="AI 草稿只整理解释和复核点，不执行真实业务动作，也不替代项目管理页确认。"
                            />
                            <Button
                              icon={<FileSearchOutlined />}
                              loading={aiDraft.isPending}
                              onClick={() => aiDraft.mutate()}
                              disabled={!projectUpdateRequest.suggestions_artifact_path}
                            >
                              生成 AI 建议草稿
                            </Button>
                            {aiDraft.error ? <Alert type="error" showIcon message={(aiDraft.error as Error).message} /> : null}
                            {aiDraftResult || aiDraft.isPending ? (
                              <SummaryPanel result={aiDraftResult} loading={aiDraft.isPending} detailsCollapsed showArtifactPath showRawJson />
                            ) : null}
                          </Space>
                        ),
                      },
                    ]}
                  />
                  {preview.error ? <Alert type="error" showIcon message={(preview.error as Error).message} /> : null}
                  {generate.error ? <Alert type="error" showIcon message={(generate.error as Error).message} /> : null}
                  <SummaryPanel result={previewResult} loading={preview.isPending} detailsCollapsed showArtifactPath={false} showRawJson={false} />
                </Space>
                </div>
              </Col>
            </Row>
            {createPlanGroups.length > 1 ? (
              <Space direction="vertical" size="small" className="full-width">
                <Typography.Title level={4}>创建计划拆分批次</Typography.Title>
                <Alert
                  type="warning"
                  showIcon
                  message="所选扩量机会需要拆分批次；请按批次检查，再进入创建计划页确认。"
                />
                <Table
                  rowKey="groupId"
                  columns={createPlanGroupColumns}
                  dataSource={createPlanGroups}
                  pagination={false}
                  size="small"
                  scroll={{ x: "max-content" }}
                />
                {createPlanGroupPreview.error ? (
                  <Alert type="error" showIcon message={(createPlanGroupPreview.error as Error).message} />
                ) : null}
              </Space>
            ) : null}
          </Space>
        </Card>
        </div>

        <InlineTaskStatus
          title="项目管理配置生成结果"
          taskId={taskId}
          workflow="project_update_from_suggestions"
          result={generateResult}
          detail={taskDetail.data}
          loading={taskDetail.isFetching || generate.isPending}
          returnTo={returnToSuggestionsPath}
        />
        {generatedProjectUpdatePath ? (
          <Alert
            type="success"
            showIcon
            message="项目管理配置已生成，可以进入项目管理页核对并人工确认执行。"
            description={
              <Space direction="vertical" size="small">
                <Typography.Text>{generatedProjectUpdatePath}</Typography.Text>
                <Link
                  to={`/project-management?project_update_path=${encodeURIComponent(generatedProjectUpdatePath)}&config_source=suggestions_generated&return_to=${encodeURIComponent(returnToSuggestionsPath)}`}
                >
                  <Button type="primary">去项目管理页确认执行</Button>
                </Link>
              </Space>
            }
          />
        ) : expectedProjectUpdatePath ? (
          <Alert
            type="info"
            showIcon
            message="项目管理配置生成任务已提交，完成后再进入项目管理页确认执行。"
            description={expectedProjectUpdatePath}
          />
        ) : null}

        <Card size="small" title="建议效果复盘">
          <Space direction="vertical" size="middle" className="full-width">
            <Alert
              type="info"
              showIcon
              message="这里自动复盘建议采纳、执行和后续表现；只读取本地历史数据，不会执行真实业务动作。"
            />
            <Form layout="inline" className="filter-bar">
              <Form.Item label="后续观察天数">
                <InputNumber
                  min={1}
                  max={7}
                  value={backtestLookaheadDays}
                  onChange={(value) => {
                    setBacktestLookaheadDays(Number(value || 1));
                    setBacktestResult(undefined);
                  }}
                />
              </Form.Item>
              <Form.Item>
                <Button
                  icon={<FileSearchOutlined />}
                  type="primary"
                  loading={backtest.isPending}
                  onClick={() => backtest.mutate()}
                >
                  刷新只读复盘
                </Button>
              </Form.Item>
            </Form>
            {effectReview.error ? <Alert type="error" showIcon message={(effectReview.error as Error).message} /> : null}
            {backtest.error ? <Alert type="error" showIcon message={(backtest.error as Error).message} /> : null}
            <SummaryPanel
              result={backtestResult ?? effectReview.data}
              loading={backtest.isPending || effectReview.isLoading}
              detailsCollapsed
              showArtifactPath
              showRawJson={false}
            />
          </Space>
        </Card>
      </Space>
    </main>
  );
}

function rowsToProductOptions(result?: ChineseResult) {
  return (result?.table.rows ?? [])
    .filter((row) => row["类型"] === "产品")
    .map((row) => ({
      label: String(row["显示名称"] ?? row["值"] ?? ""),
      value: String(row["值"] ?? ""),
    }));
}

function parseSuggestionType(value: string | null): SuggestionTypeFilter | "" {
  if (value === "扩量机会" || value === "项目管理建议" || value === "只读诊断" || value === "全部") {
    return value;
  }
  return "";
}
