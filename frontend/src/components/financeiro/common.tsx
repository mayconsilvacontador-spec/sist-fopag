"use client";

import useSWR from "swr";
import { toast } from "sonner";

import { FormDialog, type FieldDef } from "@/components/shared/registry-page";
import { Badge } from "@/components/ui/badge";
import { api, fetcher, type Paginated } from "@/lib/api";

export type Plan = { id: string; code: string; name: string; kind: string };
export type TreasuryAccount = {
  id: string; plan: string; plan_code: string; bank: string; bank_label: string; branch: string; branch_digit: string;
  account: string; account_digit: string; purpose: string; purpose_display: string; description: string; label: string;
  agreement: string; active: boolean;
};

export const SITUATION: Record<string, { label: string; variant: "success" | "warning" | "critical" | "neutral" | "info" }> = {
  PAGO: { label: "Pago", variant: "success" }, PARCIAL: { label: "Pago parcialmente", variant: "warning" },
  VENCIDO: { label: "Vencido", variant: "critical" }, A_VENCER: { label: "A vencer", variant: "neutral" },
};

export function SituationBadge({ s }: { s: string }) {
  const x = SITUATION[s] ?? { label: s, variant: "neutral" as const };
  return <Badge variant={x.variant}>{x.label}</Badge>;
}

export function usePlans() {
  return useSWR<Paginated<Plan>>("plans?page_size=50", fetcher);
}

export function useAccounts() {
  return useSWR<Paginated<TreasuryAccount>>("financeiro/contas?ativos=1&page_size=200", fetcher);
}

export const MONTHS = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"];

export const compLabel = (d: string | null | undefined) => (d ? `${d.slice(5, 7)}/${d.slice(0, 4)}` : "—");

/** Diálogo de baixa (pagamento) — contribuição, aporte ou parcela. A conta deve ser do mesmo plano. */
export function PayDialog({ title, path, planId, suggested, onClose, onDone }: {
  title: string; path: string; planId: string; suggested?: string; onClose: () => void; onDone: () => void;
}) {
  const accounts = useAccounts();
  const opts = (accounts.data?.results ?? []).filter((a) => a.plan === planId).map((a) => ({ value: a.id, label: a.label }));
  const fields: FieldDef[] = [
    { name: "amount", label: "Valor principal pago (R$)", type: "money", required: true },
    { name: "date", label: "Data do crédito", type: "date", required: true },
    { name: "fines", label: "Multa / juros / atualização (R$)", type: "money" },
    { name: "document", label: "Documento (guia, aviso, OB)" },
    { name: "account", label: "Conta de crédito (mesmo plano)", type: "select", options: opts, wide: true },
  ];
  return (
    <FormDialog title={title} size="md" fields={fields} onClose={onClose}
      description="A baixa vira receita do plano. Só são aceitas contas do mesmo plano (segregação de massas)."
      initial={{ amount: suggested ? suggested.replace(".", ",") : "", date: new Date().toISOString().slice(0, 10) }}
      submitLabel="Registrar pagamento"
      submit={async (body) => {
        await api(path, { method: "POST", body });
        toast.success("Pagamento registrado.");
        onDone();
      }} />
  );
}
