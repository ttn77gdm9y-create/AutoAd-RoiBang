const CONFIGURED_API_BASE = import.meta.env.VITE_API_BASE_URL;
const DEFAULT_API_BASES = ["http://127.0.0.1:8007/api", "http://127.0.0.1:8000/api", "http://127.0.0.1:8006/api"];

function getStoredApiBase(): string | undefined {
  try {
    return window.localStorage.getItem("roibang_api_base") ?? undefined;
  } catch {
    return undefined;
  }
}

function rememberApiBase(apiBase: string): void {
  try {
    window.localStorage.setItem("roibang_api_base", apiBase);
  } catch {
    // localStorage can be unavailable in restricted browser contexts.
  }
}

function getApiBases(): string[] {
  const bases = [CONFIGURED_API_BASE, ...DEFAULT_API_BASES, getStoredApiBase()].filter(Boolean) as string[];
  return [...new Set(bases)];
}

export const API_BASE = getApiBases()[0];

export function apiUrl(path: string): string {
  return `${getApiBases()[0]}${path}`;
}

async function parseResponse<T>(response: Response): Promise<T> {
  const contentType = response.headers.get("content-type") ?? "";
  const payload = contentType.includes("application/json") ? await response.json() : await response.text();
  if (!response.ok) {
    const detail = typeof payload === "object" && payload !== null && "detail" in payload ? String(payload.detail) : String(payload);
    throw new Error(detail || `请求失败：${response.status}`);
  }
  return payload as T;
}

export async function apiGet<T>(path: string): Promise<T> {
  return fetchWithFallback<T>(path, (url) => fetch(url));
}

export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  return fetchWithFallback<T>(path, (url) =>
    fetch(url, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    }),
  );
}

export async function apiUpload<T>(path: string, file: File): Promise<T> {
  const body = new FormData();
  body.append("file", file);
  return fetchWithFallback<T>(path, (url) =>
    fetch(url, {
      method: "POST",
      body,
    }),
  );
}

async function fetchWithFallback<T>(path: string, request: (url: string) => Promise<Response>): Promise<T> {
  let lastError: unknown;
  for (const apiBase of getApiBases()) {
    try {
      const response = await request(`${apiBase}${path}`);
      if (response.ok) {
        rememberApiBase(apiBase);
      }
      return parseResponse<T>(response);
    } catch (error) {
      lastError = error;
      if (!(error instanceof TypeError)) {
        throw error;
      }
    }
  }
  throw lastError instanceof Error ? lastError : new Error("请求失败：无法连接本地后端");
}
