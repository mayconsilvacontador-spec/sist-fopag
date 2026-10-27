"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { AlertCircle, Loader2, Lock, User } from "lucide-react";

import { Crest } from "@/components/layout/logo";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/input";
import { useBranding } from "@/lib/branding";
import { cn } from "@/lib/utils";

function LoginForm() {
  const params = useSearchParams();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setError(data.detail || "Não foi possível entrar.");
        return;
      }
      const next = params.get("next");
      const safeNext = next && next.startsWith("/") && !next.startsWith("//") ? next : "/";
      // Navegação completa: descarta qualquer cache de dados de uma sessão anterior
      window.location.assign(data.must_change_password ? "/perfil?trocar=1" : safeNext);
    } catch {
      setError("Falha de comunicação com o servidor.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} className="space-y-3.5">
      <div className="space-y-1">
        <Label htmlFor="username">Usuário</Label>
        <div className="relative">
          <User className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            id="username"
            autoComplete="username"
            autoFocus
            required
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            className="h-9 pl-8"
          />
        </div>
      </div>
      <div className="space-y-1">
        <Label htmlFor="password">Senha</Label>
        <div className="relative">
          <Lock className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            id="password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="h-9 pl-8"
          />
        </div>
      </div>
      {error && (
        <div className="flex items-start gap-2 rounded-md border border-critical-border bg-critical-soft px-3 py-2 text-xs text-critical" role="alert">
          <AlertCircle className="mt-px h-4 w-4 shrink-0" /> {error}
        </div>
      )}
      <Button type="submit" size="lg" className="w-full" disabled={busy}>
        {busy && <Loader2 className="animate-spin" />} Entrar
      </Button>
    </form>
  );
}

export default function LoginPage() {
  const { branding, brasaoUrl, fundoUrl } = useBranding();
  // No login a imagem aparece mais forte que dentro do sistema, com um véu escuro para o quadro ficar legível
  const bg = fundoUrl ? {
    backgroundImage: `linear-gradient(hsl(var(--primary-strong) / 0.55), hsl(var(--primary-strong) / 0.70)), url("${fundoUrl}")`,
    backgroundSize: "cover", backgroundPosition: "center",
  } : undefined;
  return (
    <main className={cn("flex min-h-screen flex-col", fundoUrl ? "" : "bg-background")} style={bg}>
      <div className="flex flex-1 items-center justify-center px-4 py-10">
        <div className="w-full max-w-[400px]">
          <div className="mb-5 flex flex-col items-center text-center">
            <Crest url={brasaoUrl} className="h-16 w-16" />
            <h1 className={cn("mt-3 text-xl font-bold tracking-wide", fundoUrl ? "text-white" : "text-primary-strong")}>SIST FOPAG</h1>
            <p className={cn("text-xs", fundoUrl ? "text-white/85" : "text-muted-foreground")}>
              {branding?.name || "Sistema Integrado de Gestão de RPPS"}
            </p>
          </div>
          <div className="rounded-xl border bg-card p-6 shadow-lg">
            <h2 className="mb-1 text-sm font-semibold text-primary-strong">Acesso ao sistema</h2>
            <p className="mb-4 text-xs text-muted-foreground">Informe suas credenciais institucionais.</p>
            <Suspense>
              <LoginForm />
            </Suspense>
          </div>
          <p className={cn("mt-4 text-center text-2xs", fundoUrl ? "text-white/80" : "text-muted-foreground")}>
            Acesso restrito. Todas as operações são registradas em trilha de auditoria.
          </p>
        </div>
      </div>
      <footer className={cn("py-2.5 text-center text-2xs", fundoUrl ? "text-white/70" : "border-t bg-card text-muted-foreground")}>
        SIST FOPAG · Sistema Integrado de Gestão de RPPS
      </footer>
    </main>
  );
}