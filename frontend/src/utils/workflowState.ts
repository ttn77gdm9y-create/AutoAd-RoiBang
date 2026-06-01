import type { ChineseResult, TaskDetailResponse } from "../types/api";

const activeTaskStatuses = new Set(["queued", "running", "running_post_1", "running_post_2", "running_post_3"]);

function taskPayloadStatus(result?: ChineseResult): string {
  const task = (result as (ChineseResult & { task?: Record<string, unknown> }) | undefined)?.task;
  return String(task?.status ?? "").trim();
}

export function summaryItemValue(result: ChineseResult | undefined, label: string): string {
  return String(result?.summary.items.find((item) => item.label === label)?.value ?? "").trim();
}

export function summaryItemNumber(result: ChineseResult | undefined, label: string): number | undefined {
  const value = summaryItemValue(result, label);
  if (!value) {
    return undefined;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : undefined;
}

export function taskStatus(detail?: TaskDetailResponse, result?: ChineseResult): string {
  return String(taskPayloadStatus(detail) || detail?.summary.status || taskPayloadStatus(result) || result?.summary.status || "").trim();
}

export function isTaskActive(status: string): boolean {
  const normalized = status.trim();
  return normalized.startsWith("running") || activeTaskStatuses.has(normalized);
}

export function isTaskCompleted(status: string): boolean {
  return status.trim() === "completed";
}
