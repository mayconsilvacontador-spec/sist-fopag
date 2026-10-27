import { NextRequest, NextResponse } from "next/server";

import {
  BACKEND_URL, REFRESH_COOKIE, clearAuthCookies, forwardHeaders, isAllowedOrigin,
} from "@/lib/server/bff";

export async function POST(req: NextRequest) {
  if (!isAllowedOrigin(req)) {
    return NextResponse.json({ detail: "Origem não autorizada." }, { status: 403 });
  }
  const refresh = req.cookies.get(REFRESH_COOKIE)?.value;
  if (refresh) {
    // Invalida o refresh token no backend (blacklist) e registra o logout
    await fetch(`${BACKEND_URL}/api/v1/auth/logout/`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...forwardHeaders(req) },
      body: JSON.stringify({ refresh }),
      cache: "no-store",
    }).catch(() => undefined);
  }
  const res = NextResponse.json({ ok: true });
  clearAuthCookies(res);
  return res;
}
