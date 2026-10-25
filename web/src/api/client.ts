import axios, { type AxiosRequestConfig } from "axios";
import type {
  ChatAnswer,
  ChatTrace,
  Citation,
  Intervention,
  Letter,
  Meta,
  Overview,
  RosterRow,
  StudentDetail,
} from "@/types";

/* ------------------------------------------------------------------
 * 分享码
 * 网关要求每个请求都带 sharecode，否则一律 403。
 * 首次从地址栏取，之后写进 sessionStorage，刷新深层路由也不会丢。
 * ---------------------------------------------------------------- */
const SHARE_KEY = "ag.sharecode";

function resolveShareCode(): string {
  const fromUrl = new URLSearchParams(location.search).get("sharecode") || "";
  if (fromUrl) {
    sessionStorage.setItem(SHARE_KEY, fromUrl);
    return fromUrl;
  }
  return sessionStorage.getItem(SHARE_KEY) || "";
}

export const SHARE_CODE = resolveShareCode();

// 刷新到 /counselor 这类深层路径时，把分享码补回地址栏，保证再次刷新仍可访问
if (SHARE_CODE && !new URLSearchParams(location.search).get("sharecode")) {
  const url = new URL(location.href);
  url.searchParams.set("sharecode", SHARE_CODE);
  history.replaceState(null, "", url.toString());
}

export const http = axios.create({ baseURL: "/api", timeout: 25000 });

http.interceptors.request.use((config) => {
  if (SHARE_CODE) {
    config.params = { ...(config.params || {}), sharecode: SHARE_CODE };
  }
  return config;
});

http.interceptors.response.use(
  (res) => res,
  (err) => {
    const detail =
      err?.response?.data?.detail ||
      err?.response?.statusText ||
      err?.message ||
      "请求失败";
    return Promise.reject(new Error(String(detail)));
  },
);

async function get<T>(url: string, config?: AxiosRequestConfig): Promise<T> {
  const { data } = await http.get<T>(url, config);
  return data;
}

async function post<T>(url: string, body?: unknown, config?: AxiosRequestConfig): Promise<T> {
  const { data } = await http.post<T>(url, body, config);
  return data;
}

/* ------------------------------------------------------------------
 * REST
 * ---------------------------------------------------------------- */
export const api = {
  meta: () => get<Meta>("/meta"),
  overview: () => get<Overview>("/overview"),
  students: (params: { class_name?: string; level?: string; limit?: number } = {}) =>
    get<{ total: number; rows: RosterRow[] }>("/students", { params }),
  student: (sid: string) => get<StudentDetail>(`/students/${sid}`),
  letter: (sid: string, type: "student" | "parent" | "counselor") =>
    get<Letter>(`/letters/${sid}`, { params: { type } }),
  report: (className: string) => get<Letter>(`/reports/${className}`),
  policy: (q: string, school?: string) =>
    get<{ query: string; hits: Citation[] }>("/policy", { params: { q, school } }),
  config: () => get<Meta["config"]>("/config"),
  saveConfig: (body: { red_line: number; yellow_line: number; absence_warn_ratio: number }) =>
    post<{ ok: boolean; config: Meta["config"]; overview: Overview }>("/config", body),
  interventions: (sid: string) => get<{ items: Intervention[] }>(`/interventions/${sid}`),
  addIntervention: (sid: string, body: { title: string; note: string; status?: string }) =>
    post<{ ok: boolean; item: Intervention }>(`/interventions/${sid}`, body),
  chat: (body: { role: string; sid: string | null; message: string }) =>
    post<ChatAnswer>("/chat", body),
};

/* ------------------------------------------------------------------
 * 流式对话（SSE over POST）
 * 原生 EventSource 不支持 POST，所以用 fetch + ReadableStream 手工解析。
 * ---------------------------------------------------------------- */
export type StreamEvent =
  | { type: "meta"; intent: string }
  | { type: "tool"; trace: ChatTrace }
  | { type: "delta"; text: string }
  | { type: "citations"; citations: Citation[] }
  | { type: "suggestions"; suggestions: string[] }
  | { type: "done"; elapsed_ms: number }
  | { type: "error"; message: string };

export async function chatStream(
  body: { role: string; sid: string | null; message: string },
  onEvent: (ev: StreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const qs = SHARE_CODE ? `?sharecode=${encodeURIComponent(SHARE_CODE)}` : "";
  const res = await fetch(`/api/chat/stream${qs}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify(body),
    signal,
  });

  if (!res.ok || !res.body) {
    const text = await res.text().catch(() => "");
    throw new Error(text || `HTTP ${res.status}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let idx: number;
    while ((idx = buffer.indexOf("\n\n")) >= 0) {
      const raw = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      const ev = parseBlock(raw);
      if (ev) onEvent(ev);
    }
  }
  if (buffer.trim()) {
    const ev = parseBlock(buffer);
    if (ev) onEvent(ev);
  }
}

function parseBlock(raw: string): StreamEvent | null {
  let name = "message";
  const dataLines: string[] = [];
  for (const line of raw.split("\n")) {
    if (line.startsWith("event:")) name = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
  }
  if (!dataLines.length) return null;

  let payload: any;
  try {
    payload = JSON.parse(dataLines.join("\n"));
  } catch {
    return null;
  }

  switch (name) {
    case "meta":
      return { type: "meta", intent: payload.intent };
    case "tool":
      return { type: "tool", trace: payload as ChatTrace };
    case "delta":
      return { type: "delta", text: String(payload.text ?? "") };
    case "citations":
      return { type: "citations", citations: payload as Citation[] };
    case "suggestions":
      return { type: "suggestions", suggestions: payload as string[] };
    case "done":
      return { type: "done", elapsed_ms: Number(payload.elapsed_ms ?? 0) };
    case "error":
      return { type: "error", message: String(payload.message ?? "对话失败") };
    default:
      return null;
  }
}
