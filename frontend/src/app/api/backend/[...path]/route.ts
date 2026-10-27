/**
 * Proxy autenticado: /api/backend/<rota> -> BACKEND_URL/api/v1/<rota>/
 *
 * - Injeta Authorization: Bearer <access> a partir do cookie httpOnly;
 * - Renova o access token automaticamente (uma tentativa) quando expira;
 * - Envia a instituição em operação (X-Institution-Id);
 * - Bloqueia requisições de escrita de origens não autorizadas (CSRF).
 */
import { NextRequest, NextResponse } from "next/server";

import {
  ACCESS_COOKIE, BACKEND_URL, INSTITUTION_COOKIE, REFRESH_COOKIE, clearAuthCookies,
  forwardHeaders, isAllowedOrigin, refreshTokens, setAuthCookies,
} from "@/lib/server/bff";

export const dynamic = "force-dynamic";

const PASS_RESPONSE_HEADERS = ["content-type", "content-disposition", "x-request-id"];

async function handle(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  if (!isAllowedOrigin(req)) {
    return NextResponse.json({ detail: "Origem não autorizada." }, { status: 403 });
  }
  const { path } = await ctx.params;
  if (path.some((p) => p === ".." || p.includes("\\"))) {
    return NextResponse.json({ detail: "Caminho inválido." }, { status: 400 });
  }
  const target = `${BACKEND_URL}/api/v1/${path.map(encodeURIComponent).join("/")}/${req.nextUrl.search}`;

  let access = req.cookies.get(ACCESS_COOKIE)?.value;
  const refresh = req.cookies.get(REFRESH_COOKIE)?.value;
  const institution = req.cookies.get(INSTITUTION_COOKIE)?.value;
  const hasBody = !["GET", "HEAD"].includes(req.method);
  const body = hasBody ? await req.arrayBuffer() : undefined;

  let renewed: { access: string; refresh?: string } | null = null;
  if (!access && refresh) {
    renewed = await refreshTokens(refresh, req);
    access = renewed?.access;
  }
  if (!access) {
    const res = NextResponse.json({ detail: "Sessão expirada." }, { status: 401 });
    clearAuthCookies(res);
    return res;
  }

  const send = (token: string) => {
    const headers: Record<string, string> = {
      Accept: req.headers.get("accept") || "application/json",
      Authorization: `Bearer ${token}`,
      ...forwardHeaders(req),
    };
    const ct = req.headers.get("content-type");
    if (ct && hasBody) headers["Content-Type"] = ct;
    if (institution) headers["X-Institution-Id"] = institution;
    return fetch(target, { method: req.method, headers, body, cache: "no-store", redirect: "manual" });
  };

  let upstream: Response;
  try {
    upstream = await send(access);
    if (upstream.status === 401 && refresh && !renewed) {
      renewed = await refreshTokens(refresh, req);
      if (renewed) upstream = await send(renewed.access);
    }
  } catch {
    return NextResponse.json(
      { detail: "Não foi possível conectar ao servidor do SIST FOPAG." },
      { status: 502 },
    );
  }

  const headers = new Headers();
  for (const name of PASS_RESPONSE_HEADERS) {
    const v = upstream.headers.get(name);
    if (v) headers.set(name, v);
  }
  const payload = upstream.status === 204 ? null : await upstream.arrayBuffer();
  const res = new NextResponse(payload, { status: upstream.status, headers });
  if (renewed) setAuthCookies(res, renewed.access, renewed.refresh);
  if (upstream.status === 401) clearAuthCookies(res);
  return res;
}

export const GET = handle;
export const POST = handle;
export const PUT = handle;
export const PATCH = handle;
export const DELETE = handle;
