import { NextRequest, NextResponse } from "next/server";

import { isAllowedOrigin, setInstitutionCookie } from "@/lib/server/bff";

/**
 * Troca a instituição em operação. O backend valida, a cada requisição,
 * se o usuário realmente possui acesso à instituição informada.
 */
export async function POST(req: NextRequest) {
  if (!isAllowedOrigin(req)) {
    return NextResponse.json({ detail: "Origem não autorizada." }, { status: 403 });
  }
  const body = await req.json().catch(() => ({}));
  const id = String(body.id || "");
  if (!/^[0-9a-f-]{36}$/i.test(id)) {
    return NextResponse.json({ detail: "Instituição inválida." }, { status: 400 });
  }
  const res = NextResponse.json({ ok: true });
  setInstitutionCookie(res, id);
  return res;
}
