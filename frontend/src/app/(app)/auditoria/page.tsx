"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { FileSpreadsheet, FileText, Loader2, ShieldCheck, ShieldX } from "lucide-react";

import { useSession } from "@/components/providers/session-provider";
import { EmptyRow, ErrorState, LoadingRows } from "@/components/shared/data-states";
import { PageHeader } from "@/components/shared/page-header";
import { Pagination } from "@/components/shared/pagination";
import { RequirePermission } from "@/components/shared/require-permission";
import { Badge, type BadgeProps } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  Dialog, DialogBody, DialogContent, DialogDescription, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Input, Label } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, download, fetcher, qs, type Paginated } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import type { AuditLogRow } from "@/lib/types";
import { cn } from "@/lib/utils";

const CATEGORIES = [
  { value: "", label: "Todos" },
  { value: "alteracoes", label: "Alterações" },
  { value: "calculos", label: "Cálculos" },
  { value: "exclusoes", label: "Exclusões" },
  { value: "usuarios", label: "Usuários" },
  { value: "permissoes", label: "Permissões" },
  { value: "acessos", label: "Acessos" },
  { value: "fechamentos", label: "Fechamentos" },
  { value: "reaberturas", label: "Reaberturas" },
  { value: "exportacoes", label: "Exportações" },
];

const ACTION_VARIANT: Record<string, BadgeProps["variant"]> = {
  CREATE: "success", UPDATE: "info", DELETE: "critical", LOGIN: "neutral", LOGIN_FAILED: "warning",
  LOGOUT: "neutral", PASSWORD_CHANGE: "warning", PERMISSION_CHANGE: "warning", CLOSE: "default",
  REOPEN: "critical", EXPORT: "default", CALCULATE: "default", CANCEL: "critical", APPROVE: "success", SYSTEM: "neutral",
};

export default function AuditPage() {
  return (
    <RequirePermission module="auditoria">
      <Audit />
    </RequirePermission>
  );
}

function Audit() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const { can } = useSession();
  const categoria = params.get("categoria") ?? "";

  const [username, setUsername] = useState("");
  const [search, setSearch] = useState("");
  const [inicio, setInicio] = useState("");
  const [fim, setFim] = useState("");
  const [applied, setApplied] = useState({ username: "", search: "", inicio: "", fim: "" });
  const [page, setPage] = useState(1);
  const [detail, setDetail] = useState<AuditLogRow | null>(null);
  const [exporting, setExporting] = useState<string | null>(null);

  useEffect(() => setPage(1), [categoria]);

  const filters = {
    categoria, username: applied.username, search: applied.search,
    data_inicio: applied.inicio, data_fim: applied.fim,
  };
  const { data, error, isLoading } = useSWR<Paginated<AuditLogRow>>(
    `audit/logs${qs({ ...filters, page })}`,
    fetcher,
    { keepPreviousData: true },
  );

  const doExport = async (formato: "csv" | "xlsx") => {
    setExporting(formato);
    try {
      await download(`audit/logs/export${qs({ ...filters, formato })}`, `auditoria.${formato}`);
      toast.success("Exportação gerada. A própria exportação foi registrada na auditoria.");
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setExporting(null);
    }
  };

  const label = CATEGORIES.find((c) => c.value === categoria)?.label ?? "Todos";

  return (
    <>
      <PageHeader
        title={`Auditoria${categoria ? ` · ${label}` : ""}`}
        description="Trilha imutável: os registros não podem ser alterados nem excluídos, inclusive no banco de dados."
        breadcrumb={[{ label: "Auditoria" }, { label }]}
        actions={can("auditoria", "exportar") && (
          <>
            <Button variant="outline" size="sm" onClick={() => doExport("csv")} disabled={Boolean(exporting)}>
              {exporting === "csv" ? <Loader2 className="animate-spin" /> : <FileText />} CSV
            </Button>
            <Button variant="outline" size="sm" onClick={() => doExport("xlsx")} disabled={Boolean(exporting)}>
              {exporting === "xlsx" ? <Loader2 className="animate-spin" /> : <FileSpreadsheet />} Excel
            </Button>
          </>
        )}
      />

      <div className="mb-3 flex flex-wrap gap-1">
        {CATEGORIES.map((c) => (
          <button
            key={c.value}
            type="button"
            onClick={() => router.replace(c.value ? `${pathname}?categoria=${c.value}` : pathname)}
            className={cn(
              "rounded-md border px-2.5 py-1 text-xs font-medium",
              categoria === c.value ? "border-primary bg-primary text-primary-foreground" : "bg-card text-muted-foreground hover:text-foreground",
            )}
          >
            {c.label}
          </button>
        ))}
      </div>

      <Card>
        <form
          className="flex flex-wrap items-end gap-3 border-b px-4 py-2.5"
          onSubmit={(e) => {
            e.preventDefault();
            setApplied({ username, search, inicio, fim });
            setPage(1);
          }}
        >
          <div className="space-y-1">
            <Label htmlFor="a-user">Usuário</Label>
            <Input id="a-user" className="w-36" value={username} onChange={(e) => setUsername(e.target.value)} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="a-search">Registro / IP / justificativa</Label>
            <Input id="a-search" className="w-56" value={search} onChange={(e) => setSearch(e.target.value)} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="a-ini">De</Label>
            <Input id="a-ini" type="date" className="w-36" value={inicio} onChange={(e) => setInicio(e.target.value)} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="a-fim">Até</Label>
            <Input id="a-fim" type="date" className="w-36" value={fim} onChange={(e) => setFim(e.target.value)} />
          </div>
          <Button type="submit" size="sm">Filtrar</Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => {
              setUsername(""); setSearch(""); setInicio(""); setFim("");
              setApplied({ username: "", search: "", inicio: "", fim: "" });
            }}
          >
            Limpar
          </Button>
        </form>
        {error && <div className="p-4"><ErrorState error={error} /></div>}
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Data/hora</TableHead>
              <TableHead>Usuário</TableHead>
              <TableHead>IP</TableHead>
              <TableHead>Ação</TableHead>
              <TableHead>Módulo</TableHead>
              <TableHead>Registro</TableHead>
              <TableHead>Justificativa</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading && !data && <LoadingRows cols={7} />}
            {data?.results.map((r) => (
              <TableRow key={r.id} className="cursor-pointer" onClick={() => setDetail(r)}>
                <TableCell className="whitespace-nowrap text-xs tabular">{formatDateTime(r.timestamp)}</TableCell>
                <TableCell className="text-xs">{r.username || <span className="text-muted-foreground">sistema</span>}</TableCell>
                <TableCell className="font-mono text-2xs">{r.ip || "—"}</TableCell>
                <TableCell><Badge variant={ACTION_VARIANT[r.action] ?? "neutral"}>{r.action_display}</Badge></TableCell>
                <TableCell className="font-mono text-2xs">{r.module || "—"}</TableCell>
                <TableCell className="max-w-[260px] truncate text-xs">{r.object_repr || r.object_type || "—"}</TableCell>
                <TableCell className="max-w-[200px] truncate text-xs text-muted-foreground">{r.justification || "—"}</TableCell>
              </TableRow>
            ))}
            {data && data.results.length === 0 && <EmptyRow cols={7} />}
          </TableBody>
        </Table>
        {data && <Pagination page={data.page} numPages={data.num_pages} count={data.count} onChange={setPage} />}
      </Card>

      {detail && <DetailDialog row={detail} onClose={() => setDetail(null)} />}
    </>
  );
}

function fmt(v: unknown) {
  if (v === null || v === undefined || v === "") return <span className="text-muted-foreground">vazio</span>;
  if (typeof v === "object") return <code className="text-2xs">{JSON.stringify(v)}</code>;
  return String(v);
}

function DetailDialog({ row, onClose }: { row: AuditLogRow; onClose: () => void }) {
  const [verify, setVerify] = useState<{ integro: boolean; detail: string } | null>(null);
  const [checking, setChecking] = useState(false);
  const keys = Array.from(new Set([...Object.keys(row.old_values ?? {}), ...Object.keys(row.new_values ?? {})])).sort();

  const check = async () => {
    setChecking(true);
    try {
      setVerify(await api(`audit/logs/${row.id}/verify`));
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setChecking(false);
    }
  };

  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent size="lg">
        <DialogHeader>
          <DialogTitle>Registro de auditoria nº {row.id}</DialogTitle>
          <DialogDescription>{row.action_display} · {formatDateTime(row.timestamp)}</DialogDescription>
        </DialogHeader>
        <DialogBody className="space-y-4">
          <dl className="grid grid-cols-[150px_1fr] gap-y-1.5 text-xs">
            <dt className="text-muted-foreground">Usuário</dt><dd>{row.username || "sistema"} {row.user_full_name && `· ${row.user_full_name}`}</dd>
            <dt className="text-muted-foreground">IP / origem</dt><dd>{row.ip || "—"} · {row.source}</dd>
            <dt className="text-muted-foreground">Navegador</dt><dd className="truncate">{row.user_agent || "—"}</dd>
            <dt className="text-muted-foreground">Módulo</dt><dd className="font-mono">{row.module || "—"}</dd>
            <dt className="text-muted-foreground">Registro</dt><dd>{row.object_repr || "—"} <span className="font-mono text-2xs text-muted-foreground">{row.object_type} {row.object_id}</span></dd>
            <dt className="text-muted-foreground">Justificativa</dt><dd>{row.justification || "—"}</dd>
            <dt className="text-muted-foreground">Requisição</dt><dd className="font-mono text-2xs">{row.request_id || "—"}</dd>
          </dl>

          {keys.length > 0 && (
            <div>
              <div className="section-label mb-1.5">Valores</div>
              <Table className="rounded border">
                <TableHeader>
                  <TableRow>
                    <TableHead>Campo</TableHead>
                    <TableHead>Anterior</TableHead>
                    <TableHead>Novo</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {keys.map((k) => (
                    <TableRow key={k}>
                      <TableCell className="font-mono text-2xs">{k}</TableCell>
                      <TableCell className="text-xs">{row.old_values ? fmt(row.old_values[k]) : "—"}</TableCell>
                      <TableCell className="text-xs">{row.new_values ? fmt(row.new_values[k]) : "—"}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}

          {row.extra && (
            <div>
              <div className="section-label mb-1.5">Dados adicionais</div>
              <pre className="overflow-x-auto rounded border bg-muted p-2 text-2xs thin-scroll">{JSON.stringify(row.extra, null, 2)}</pre>
            </div>
          )}

          <div className="rounded-md border bg-muted/50 p-3">
            <div className="section-label">Integridade (SHA-256)</div>
            <code className="mt-1 block break-all text-2xs">{row.record_hash}</code>
            <div className="mt-2 flex items-center gap-2">
              <Button size="sm" variant="outline" onClick={check} disabled={checking}>
                {checking ? <Loader2 className="animate-spin" /> : <ShieldCheck />} Verificar integridade
              </Button>
              {verify && (
                <span className={cn("flex items-center gap-1 text-xs font-medium", verify.integro ? "text-success" : "text-critical")}>
                  {verify.integro ? <ShieldCheck className="h-4 w-4" /> : <ShieldX className="h-4 w-4" />} {verify.detail}
                </span>
              )}
            </div>
          </div>
        </DialogBody>
      </DialogContent>
    </Dialog>
  );
}
