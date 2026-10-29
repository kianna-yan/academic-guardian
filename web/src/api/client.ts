import axios, { type AxiosRequestConfig } from "axios";
import type {
  AccountRow,
  AgentBriefing,
  AppealItem,
  AuthProfile,
  ChatAnswer,
  ChatTrace,
  Citation,
  CurriculumImportResult,
  CurriculumPayload,
  ImportResult,
  Intervention,
  Letter,
  LoginResult,
  Meta,
  NoticeItem,
  NoticePayload,
  Overview,
  Role,
  RosterRow,
  StudentDetail,
  TeacherClassroom,
  TeacherView,
  TodoItem,
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

/* ------------------------------------------------------------------
 * 大模型健康状态（顶部黄条用）
 * ok=false 意味着后端已经回落规则引擎：数据照常查，但回答是模板句。
 * probe=true 会真发一次几个 token 的请求探活，用于「重试连接」。
 * ---------------------------------------------------------------- */
export interface LlmStatus {
  enabled: boolean;
  ok: boolean;
  reason: string;
  model: string;
  route_model: string;
  checked_at: string;
  fails: number;
}

export function fetchLlmStatus(probe = false): Promise<LlmStatus> {
  return http
    .get<LlmStatus>("/llm/status", probe ? { params: { probe: 1 } } : undefined)
    .then((r) => r.data);
}

/* ------------------------------------------------------------------
 * 登录态
 * token 放 localStorage（关掉页面再回来还在），每次请求带 Bearer。
 * 过期由后端判 401，前端收到 401 就清掉并踢回登录页。
 * ---------------------------------------------------------------- */
const TOKEN_KEY = "ag.token";

export function getToken(): string {
  return localStorage.getItem(TOKEN_KEY) || "";
}
export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}
export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

http.interceptors.request.use((config) => {
  const token = getToken();
  if (SHARE_CODE) {
    config.params = { ...(config.params || {}), sharecode: SHARE_CODE };
  }
  if (token) {
    // 线上托管网关会用自己的 JWT 覆写 Authorization 头，所以另走自定义头；
    // 再附一个 query 参数兜底（网关对 query 是透传的），本地直连两种都认。
    config.headers.set("X-Ag-Token", token);
    config.headers.set("Authorization", `Bearer ${token}`);
    config.params = { ...(config.params || {}), ag_token: token };
  }
  return config;
});

http.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err?.response?.status === 401) {
      clearToken();
      if (!location.pathname.startsWith("/login")) {
        // 线上是按 sharecode 放行的，跳登录页也得把分享码带上，否则会被网关 403
        const q = SHARE_CODE ? `?sharecode=${encodeURIComponent(SHARE_CODE)}` : "";
        location.replace(`/login${q}`);
      }
    }
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
  login: (body: { role: Role; account: string; password: string }) =>
    post<LoginResult>("/auth/login", body),
  me: () =>
    get<{
      profile: AuthProfile;
      stats: Record<string, number>;
      defaults: Record<string, string>;
      staff_accounts: Record<string, string>;
    }>("/auth/me"),
  changePassword: (body: { old_password: string; new_password: string }) =>
    post<{ ok: boolean; profile: AuthProfile }>("/auth/change-password", body),
  accounts: (limit = 200) =>
    get<{ rows: AccountRow[]; stats: Record<string, number> }>("/auth/accounts", {
      params: { limit },
    }),
  importStudents: (text: string) => post<ImportResult>("/auth/import-students", { text }),
  meta: () => get<Meta>("/meta"),
  overview: () => get<Overview>("/overview"),
  students: (params: { class_name?: string; level?: string; limit?: number } = {}) =>
    get<{ total: number; rows: RosterRow[] }>("/students", { params }),
  student: (sid: string) => get<StudentDetail>(`/students/${sid}`),
  teacherView: () => get<TeacherView>("/teacher/view"),
  /** 课堂学情：以「我教的这门课」为统计单位 */
  teacherClassroom: () => get<TeacherClassroom>("/teacher/classroom"),
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
  briefing: () => get<AgentBriefing>("/agent/briefing"),
  resetAgent: () => post<{ ok: boolean }>("/agent/reset", {}),
  dailyReport: () =>
    get<{
      date: string;
      week: number | string;
      generated_at: string;
      scheduled_at: string | null;
      runs: number;
      summary: string;
      body: string;
      red_top: { name: string; class_name: string; score: number }[];
      rising: { name: string; class_name: string; delta: number; score: number }[];
      docx_url: string;
      smtp_configured: boolean;
    }>("/agent/daily-report"),
  curriculum: () => get<CurriculumPayload>("/curriculum"),
  importCurriculum: (text: string) => post<CurriculumImportResult>("/curriculum/import", { text }),
  /* ---- 消息中心：通知 / 待办 / 异议 ---- */
  notifications: () => get<NoticePayload>("/notifications"),
  markNoticesRead: (ids: string[]) => post<{ ok: boolean; marked: number }>("/notifications/read", { ids }),
  finishTodo: (id: string) => post<{ ok: boolean; todo: TodoItem }>(`/todos/${id}/finish`, {}),
  submitAppeal: (body: { kind: "attendance" | "homework"; record_id: string; course: string; reason: string }) =>
    post<{ ok: boolean; appeal: AppealItem }>("/appeals", body),
  appeals: () => get<{ items: AppealItem[] }>("/appeals"),
  resolveAppeal: (id: string, body: { action: "accept" | "reject"; reply: string }) =>
    post<{ ok: boolean; appeal: AppealItem }>(`/appeals/${id}/resolve`, body),
};

/* ------------------------------------------------------------------
 * 文书下载：/api/export/* 的 <a>/window.open 直接触发，token 走 ag_token query。
 * ---------------------------------------------------------------- */
export function downloadDoc(path: string): void {
  const token = localStorage.getItem(TOKEN_KEY) || "";
  const joiner = path.includes("?") ? "&" : "?";
  window.open(`${path}${joiner}ag_token=${encodeURIComponent(token)}`, "_blank", "noopener");
}

/* ------------------------------------------------------------------
 * 流式对话（SSE over POST）
 * 原生 EventSource 不支持 POST，所以用 fetch + ReadableStream 手工解析。
 * ---------------------------------------------------------------- */
export type StreamEvent =
  | { type: "meta"; intent: string }
  | { type: "thought"; text: string }
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
  const token = getToken();
  const params = new URLSearchParams();
  if (SHARE_CODE) params.set("sharecode", SHARE_CODE);
  if (token) params.set("ag_token", token);
  const qs = params.toString() ? `?${params.toString()}` : "";
  const res = await fetch(`/api/chat/stream${qs}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
      ...(token ? { "X-Ag-Token": token, Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
    signal,
  });

  if (res.status === 401) {
    clearToken();
    throw new Error("登录已过期，请重新登录");
  }
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
    case "thought":
      return { type: "thought", text: String(payload.text ?? "") };
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
