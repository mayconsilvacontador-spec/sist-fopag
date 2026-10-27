import { NextRequest, NextResponse } from "next/server";

/**
 * Redireciona para /login quem não possui sessão (cookie de refresh).
 * A validação real do token acontece no backend a cada requisição.
 */
const PUBLIC_PATHS = ["/login", "/api/auth/login", "/segurado/login"];

export function middleware(req: NextRequest) {
  const { pathname, search } = req.nextUrl;
  if (PUBLIC_PATHS.some((p) => pathname.startsWith(p))) return NextResponse.next();
  if (pathname.startsWith("/api/")) return NextResponse.next(); // o BFF responde 401 por conta própria

  const hasSession = Boolean(req.cookies.get("sist_refresh")?.value);
  if (!hasSession) {
    const url = req.nextUrl.clone();
    url.pathname = pathname.startsWith("/segurado") ? "/segurado/login" : "/login";
    url.search = pathname !== "/" ? `?next=${encodeURIComponent(pathname + search)}` : "";
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|icon.svg|robots.txt).*)"],
};
