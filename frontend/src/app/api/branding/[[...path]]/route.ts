/**
 * Identidade visual pública (brasão e imagem de fundo), usada também na tela de login — sem sessão.
 * /api/branding?inst=SIGLA            -> BACKEND/api/v1/branding/?inst=SIGLA
 * /api/branding/brasao|fundo?inst=... -> BACKEND/api/v1/branding/<tipo>/?inst=...
 */
import { NextRequest, NextResponse } from "next/server";

import { BACKEND_URL } from "@/lib/server/bff";

export const dynamic = "force-dynamic";

export async function GET(req: NextRequest, ctx: { params: Promise<{ path?: string[] }> }) {
  const { path = [] } = await ctx.params;
  if (path.length > 1 || (path[0] && !["brasao", "fundo"].includes(path[0]))) {
    return NextResponse.json({ detail: "Caminho inválido." }, { status: 400 });
  }
  const target = `${BACKEND_URL}/api/v1/branding/${path[0] ? `${path[0]}/` : ""}${req.nextUrl.search}`;
  try {
    const upstream = await fetch(target, { cache: "no-store" });
    const headers = new Headers();
    for (const h of ["content-type", "cache-control", "x-content-type-options"]) {
      const v = upstream.headers.get(h);
      if (v) headers.set(h, v);
    }
    return new NextResponse(await upstream.arrayBuffer(), { status: upstream.status, headers });
  } catch {
    return NextResponse.json({ detail: "Servidor indisponível." }, { status: 502 });
  }
}
