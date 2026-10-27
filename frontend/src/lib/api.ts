/**
 * Cliente HTTP do navegador. Todas as chamadas passam pelo BFF do Next.js
 * (/api/backend/...), que injeta o token JWT guardado em cookie httpOnly.
 */
export class ApiError extends Error {
  status: number;
  data: unknown;
  code?: string;

  constructor(status: number, data: unknown) {
    super(extractMessage(data) || `Erro ${status}`);
    this.status = status;
    this.data = data;
    if (data && typeof data === "object" && "code" in data) {
      this.code = String((data as Record<string, unknown>).code);
    }
  }

  /** Erros por campo (validação do DRF) */
  get fieldErrors(): Record<string, string> {
    const out: Record<string, string> = {};
    if (this.data && typeof this.data === "object" && !Array.isArray(this.data)) {
      for (const [k, v] of Object.entries(this.data as Record<string, unknown>)) {
        if (k === "detail" || k === "code") continue;
        out[k] = Array.isArray(v) ? v.map(String).join(" ") : String(v);
      }
    }
    return out;
  }
}

function extractMessage(data: unknown): string {
  if (!data) return "";
  if (typeof data === "string") return data;
  if (typeof data === "object") {
    const d = data as Record<string, unknown>;
    if (typeof d.detail === "string") return d.detail;
    if (d.detail && typeof d.detail === "object") return extractMessage(d.detail);
    const first = Object.entries(d)[0];
    if (first) {
      const [field, value] = first;
      const msg = Array.isArray(value) ? value.join(" ") : String(value);
      return field === "non_field_errors" ? msg : `${field}: ${msg}`;
    }
  }
  return "";
}

type Options = {
  method?: string;
  body?: unknown;
  justification?: string;
  signal?: AbortSignal;
};

function handleAuthFailure(status: number, data: unknown) {
  if (typeof window === "undefined") return;
  const portal = window.location.pathname.startsWith("/segurado");
  if (status === 401) {
    const next = encodeURIComponent(window.location.pathname + window.location.search);
    window.location.href = portal ? "/segurado/login" : `/login?next=${next}`;
  }
  if (status === 403 && data && typeof data === "object" && (data as { code?: string }).code === "troca_senha_obrigatoria") {
    if (portal) return; // o portal mostra a troca de senha na própria página inicial
    if (!window.location.pathname.startsWith("/perfil")) window.location.href = "/perfil?trocar=1";
  }
}

export async function api<T = unknown>(path: string, opts: Options = {}): Promise<T> {
  const clean = path.replace(/^\/+/, "");
  const headers: Record<string, string> = { Accept: "application/json" };
  if (opts.body !== undefined) headers["Content-Type"] = "application/json";
  if (opts.justification) headers["X-Justification"] = encodeURIComponent(opts.justification);
  const res = await fetch(`/api/backend/${clean}`, {
    method: opts.method || "GET",
    headers,
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
    credentials: "same-origin",
    signal: opts.signal,
  });
  if (res.status === 204) return undefined as T;
  const isJson = (res.headers.get("content-type") || "").includes("application/json");
  const data = isJson ? await res.json() : await res.text();
  if (!res.ok) {
    handleAuthFailure(res.status, data);
    throw new ApiError(res.status, data);
  }
  return data as T;
}

/** Fetcher para SWR */
export const fetcher = <T,>(path: string) => api<T>(path);

/** Download de arquivo (exportações CSV/XLSX) preservando o nome sugerido. */
export async function download(path: string, fallbackName: string, body?: unknown) {
  const res = await fetch(`/api/backend/${path.replace(/^\/+/, "")}`, {
    credentials: "same-origin",
    ...(body !== undefined
      ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }
      : {}),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => null);
    handleAuthFailure(res.status, data);
    throw new ApiError(res.status, data);
  }
  const blob = await res.blob();
  const cd = res.headers.get("content-disposition") || "";
  const match = /filename="?([^";]+)"?/.exec(cd);
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = match?.[1] || fallbackName;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export type Paginated<T> = {
  count: number;
  page: number;
  page_size: number;
  num_pages: number;
  results: T[];
};

export function qs(params: Record<string, string | number | boolean | undefined | null>): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "") sp.set(k, String(v));
  }
  const s = sp.toString();
  return s ? `?${s}` : "";
}
