"use client";

import useSWR from "swr";
import { Printer } from "lucide-react";

import { useSession } from "@/components/providers/session-provider";
import { ErrorState } from "@/components/shared/data-states";
import { Button } from "@/components/ui/button";
import {
  Dialog, DialogBody, DialogContent, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { fetcher } from "@/lib/api";
import { formatCPF, formatCurrency, formatDate } from "@/lib/format";
import type { Payslip } from "@/lib/types";

const MONTHS = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"];

/** Contracheque (demonstrativo de pagamento) — imprimível. */
export function PayslipView({ p }: { p: Payslip }) {
  const { me } = useSession();
  return <PayslipBody p={p} institutionName={me?.institution?.name} />;
}

/** Corpo do contracheque sem depender da sessão interna (usado também no Portal do Segurado). */
export function PayslipBody({ p, institutionName }: { p: Payslip; institutionName?: string }) {
  const prov = p.items.filter((i) => i.kind === "PROVENTO");
  const desc = p.items.filter((i) => i.kind === "DESCONTO");
  const ir = (p.memory?.irrf ?? p.memory?.irrf_13) as Record<string, string> | undefined;
  const bank = p.bank ?? {};
  return (
    <div className="space-y-3 text-xs print:text-[11px]">
      <div className="flex flex-wrap justify-between gap-2 border-b pb-2">
        <div>
          <div className="text-sm font-semibold">{institutionName ?? "Demonstrativo de pagamento"}</div>
          <div className="text-muted-foreground">{p.run.folha_name} · {p.run.kind_display}</div>
        </div>
        <div className="text-right">
          <div className="font-semibold">{MONTHS[p.run.month - 1]}/{p.run.year}</div>
          <div className="text-muted-foreground">Situação da folha: {p.run.status_display}</div>
        </div>
      </div>
      <div className="grid gap-1 sm:grid-cols-2">
        <div><span className="text-muted-foreground">Beneficiário: </span><b>{p.beneficiary_name}</b></div>
        <div><span className="text-muted-foreground">CPF: </span>{formatCPF(p.beneficiary_cpf)}</div>
        <div><span className="text-muted-foreground">Benefício: </span>{p.kind_display}{p.registration ? ` · matrícula ${p.registration}` : ""}</div>
        <div><span className="text-muted-foreground">Início: </span>{formatDate(p.start_date)}</div>
        {p.instituidor_name && <div><span className="text-muted-foreground">Instituidor: </span>{p.instituidor_name}</div>}
        <div><span className="text-muted-foreground">Crédito: </span>{bank.banco ? `Banco ${bank.banco} · ag. ${bank.agencia}${bank.agencia_dv ? "-" + bank.agencia_dv : ""} · conta ${bank.conta}${bank.conta_dv ? "-" + bank.conta_dv : ""}` : <span className="text-warning">sem conta bancária</span>}</div>
      </div>
      <table className="w-full border text-xs">
        <thead className="bg-muted/50">
          <tr><th className="px-2 py-1 text-left">Cód.</th><th className="px-2 py-1 text-left">Descrição</th><th className="px-2 py-1 text-left">Ref.</th><th className="px-2 py-1 text-right">Proventos</th><th className="px-2 py-1 text-right">Descontos</th></tr>
        </thead>
        <tbody>
          {[...prov, ...desc].map((i) => (
            <tr key={i.id} className="border-t">
              <td className="px-2 py-1 font-mono">{i.code}</td>
              <td className="px-2 py-1">{i.name}</td>
              <td className="px-2 py-1">{i.reference}</td>
              <td className="px-2 py-1 text-right tabular">{i.kind === "PROVENTO" ? formatCurrency(i.amount) : ""}</td>
              <td className="px-2 py-1 text-right tabular">{i.kind === "DESCONTO" ? formatCurrency(i.amount) : ""}</td>
            </tr>
          ))}
        </tbody>
        <tfoot className="border-t-2 font-semibold">
          <tr><td colSpan={3} className="px-2 py-1 text-right">Totais</td><td className="px-2 py-1 text-right tabular">{formatCurrency(p.gross)}</td><td className="px-2 py-1 text-right tabular">{formatCurrency(p.discounts)}</td></tr>
          <tr><td colSpan={3} className="px-2 py-1 text-right">Valor líquido</td><td colSpan={2} className="px-2 py-1 text-right tabular text-sm">{formatCurrency(p.net)}</td></tr>
        </tfoot>
      </table>
      <div className="grid gap-1 text-2xs text-muted-foreground sm:grid-cols-3">
        <div>Base da contribuição: {formatCurrency(p.rpps_base)}</div>
        <div>Base do IRRF: {formatCurrency(p.ir_base)}{ir?.metodo === "SIMPLIFICADO" ? " (desconto simplificado)" : ir?.metodo === "ISENTO_MOLESTIA" ? " (isento — moléstia grave)" : ""}</div>
        {ir?.parcela_isenta_65 && ir.parcela_isenta_65 !== "0" && <div>Parcela isenta 65 anos: {formatCurrency(ir.parcela_isenta_65)}</div>}
        {ir?.reducao_lei_15270 && ir.reducao_lei_15270 !== "0" && <div>Redução do IR (Lei 15.270/2025): {formatCurrency(ir.reducao_lei_15270)}</div>}
      </div>
      {(p.warnings ?? []).length > 0 && (
        <ul className="list-disc rounded border border-warning/40 bg-warning/5 py-1.5 pl-6 pr-2 text-2xs print:hidden">
          {p.warnings.map((w) => <li key={w}>{w}</li>)}
        </ul>
      )}
    </div>
  );
}

export function PayslipDialog({ id, onClose }: { id: string; onClose: () => void }) {
  const { data, error } = useSWR<Payslip>(`folha/contracheques/${id}`, fetcher);
  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent size="lg">
        <DialogHeader>
          <DialogTitle className="flex items-center justify-between gap-2 pr-6">
            Contracheque
            {data && <Button size="sm" variant="outline" onClick={() => window.open(`/folha/contracheques/${id}`, "_blank")}><Printer /> Imprimir</Button>}
          </DialogTitle>
        </DialogHeader>
        <DialogBody>
          {error && <ErrorState error={error} />}
          {data && <PayslipView p={data} />}
        </DialogBody>
      </DialogContent>
    </Dialog>
  );
}
