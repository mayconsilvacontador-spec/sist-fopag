/**
 * Utilitários do BFF (Backend For Frontend). Executa SOMENTE no servidor
 * Next.js. Os tokens JWT ficam em cookies httpOnly e nunca chegam ao
 * JavaScript do navegador.
 */
import "server-only";

import type { NextRequest, NextResponse } from "next/server";

export const BACKEND_URL = (process.env.BACKEND_URL || "http://127.0.0.1:8000").replace(/\/+$/, "");
export const ACCESS_COOKIE = "sist_access";
export const REFRESH_COOKIE = "sist_refresh";
export const INSTITUTION_COOKIE = "sist_inst";

const ACCESS_MAX_AGE = 15 * 60;
const REFRESH_MAX_AGE = 10 * 60 * 60;
const secure = process.env.COOKIE_SECURE === "true";

const cookieBase = { httpOnly: true, secure, sameSite: "lax" as const, path: "/" };

export function setAuthCookies(res: NextResponse, access: string, refresh?: string) {
  res.cookies.set(ACCESS_COOKIE, access, { ...cookieBase, maxAge: ACCESS_MAX_AGE });
  if (refresh) res.cookies.set(REFRESH_COOKIE, refresh, { ...cookieBase, maxAge: REFRESH_MAX_AGE });
}

export function setInstitutionCookie(res: NextResponse, id: string) {
  res.cookies.set(INSTITUTION_COOKIE, id, { ...cookieBase, maxAge: 365 * 24 * 60 * 60 });
}

export function clearAuthCookies(res: NextResponse) {
  for (const name of [ACCESS_COOKIE, REFRESH_COOKIE]) {
    res.cookies.set(name, "", { ...cookieBase, maxAge: 0 });
  }
}

/**
 * Proteção CSRF: requisições que alteram estado precisam vir de uma origem
 * autorizada. Combinada com SameSite=Lax nos cookies.
 */
export function isAllowedOrigin(req: NextRequest): boolean {
  const method = req.method.toUpperCase();
  if (["GET", "HEAD", "OPTIONS"].includes(method)) return true;
  const allowed = (process.env.ALLOWED_ORIGINS || "http://localhost:3000,http://127.0.0.1:3000")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
  // Mesmo endereço da página que fez o pedido (ex.: acesso pelo IP da rede ou por outra porta): seguro contra CSRF,
  // porque um site de terceiros sempre envia a própria origem, diferente do Host deste servidor.
  const host = req.headers.get("host");
  const ok = (value: string) => {
    try {
      const u = new URL(value);
      return allowed.includes(u.origin) || (!!host && u.host === host);
    } catch {
      return false;
    }
  };
  const origin = req.headers.get("origin");
  if (origin) return ok(origin);
  const referer = req.headers.get("referer");
  if (referer) return ok(referer);
  return false;
}

/** IP do cliente, somente se houver proxy reverso confiável configurado. */
export function clientIp(req: NextRequest): string | null {
  if (process.env.TRUST_PROXY_HEADERS !== "true") return null;
  const real = req.headers.get("x-real-ip");
  if (real) return real.trim();
  const xff = req.headers.get("x-forwarded-for");
  return xff ? xff.split(",")[0].trim() : null;
}

export function forwardHeaders(req: NextRequest): Record<string, string> {
  const h: Record<string, string> = {};
  const ip = clientIp(req);
  if (ip) h["X-Forwarded-For"] = ip;
  const ua = req.headers.get("user-agent");
  if (ua) h["User-Agent"] = ua;
  const just = req.headers.get("x-justification");
  if (just) h["X-Justification"] = just;
  return h;
}

export async function refreshTokens(refresh: string, req: NextRequest) {
  const res = await fetch(`${BACKEND_URL}/api/v1/auth/token/refresh/`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...forwardHeaders(req) },
    body: JSON.stringify({ refresh }),
    cache: "no-store",
  });
  if (!res.ok) return null;
  return (await res.json()) as { access: string; refresh?: string };
}
