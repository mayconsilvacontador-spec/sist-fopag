"use client";

import { ShieldAlert } from "lucide-react";

import { useSession } from "@/components/providers/session-provider";

/** Bloqueia a renderização da tela quando o usuário não possui a permissão. */
export function RequirePermission({
  module, action = "visualizar", children,
}: {
  module: string;
  action?: string;
  children: React.ReactNode;
}) {
  const { can } = useSession();
  if (!can(module, action)) {
    return (
      <div className="mx-auto mt-16 max-w-md rounded-lg border bg-card p-6 text-center shadow-card">
        <ShieldAlert className="mx-auto h-8 w-8 text-warning" />
        <h2 className="mt-2 text-sm font-semibold">Acesso não autorizado</h2>
        <p className="mt-1 text-xs text-muted-foreground">
          Seu perfil não possui a permissão <code className="rounded bg-muted px-1">{module}:{action}</code>.
          Solicite ao administrador do sistema.
        </p>
      </div>
    );
  }
  return <>{children}</>;
}
