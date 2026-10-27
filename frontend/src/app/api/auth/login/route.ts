import { NextRequest, NextResponse } from "next/server";

import {
  BACKEND_URL, forwardHeaders, isAllowedOrigin, setAuthCookies, setInstitutionCookie,
} from "@/lib/server/bff";

export async function POST(req: NextRequest) {
  if (!isAllowedOrigin(req)) {
    return NextResponse.json({ detail: "Origem não autorizada." }, { status: 403 });
  }
  let body: { username?: string; password?: string; cpf?: string; portal?: boolean };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ detail: "Requisição inválida." }, { status: 400 });
  }
  let upstream: Response;
  try {
    // Portal do Segurado: login por CPF em rota própria (usuários internos não entram por ela, e vice-versa)
    const url = body.portal ? "portal/auth/token/" : "auth/token/";
    upstream = await fetch(`${BACKEND_URL}/api/v1/${url}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...forwardHeaders(req) },
      body: JSON.stringify(body.portal
        ? { cpf: body.cpf ?? "", password: body.password ?? "" }
        : { username: body.username ?? "", password: body.password ?? "" }),
      cache: "no-store",
    });
  } catch {
    return NextResponse.json(
      { detail: "Não foi possível conectar ao servidor do SIST FOPAG. Verifique se o backend está em execução." },
      { status: 502 },
    );
  }
  const data = await upstream.json().catch(() => ({}));
  if (!upstream.ok) {
    return NextResponse.json(data, { status: upstream.status });
  }
  const res = NextResponse.json({
    ok: true,
    must_change_password: Boolean(data.must_change_password),
  });
  setAuthCookies(res, data.access, data.refresh);
  if (data.institution_id) setInstitutionCookie(res, data.institution_id);
  return res;
}
