"use client";

import { useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { Loader2, Pencil } from "lucide-react";

import { useSession } from "@/components/providers/session-provider";
import { ErrorState } from "@/components/shared/data-states";
import { FormField } from "@/components/shared/form-field";
import { PageHeader } from "@/components/shared/page-header";
import { RequirePermission } from "@/components/shared/require-permission";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Dialog, DialogBody, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Checkbox, Textarea } from "@/components/ui/input";
import { api, fetcher } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { RetirementRuleRow } from "@/lib/types";

const GROUPS: [string, string][] = [
  ["PERMANENTE", "Regra permanente"], ["TRANSICAO", "Transição"], ["DIREITO_ADQUIRIDO", "Direito adquirido"],
  ["COMPULSORIA", "Compulsória"],
];

const LABELS: Record<string, string> = {
  idade: "Idade mínima", idade_desde: "Idade a partir de", contribuicao: "Contribuição (anos)",
  contribuicao_tipo: "Tipo de tempo", servico_publico: "Serviço público (anos)", carreira: "Carreira (anos)",
  cargo: "Cargo (anos)", pontos: "Pontuação", pedagio: "Pedágio", reducao_ec47: "Redução de idade (EC 47)",
  ingresso_servico_publico_ate: "Ingresso no serviço público até", ingresso_ente_antes_de: "Ingresso no ente antes de",
};

function describe(key: string, v: unknown): string {
  if (v && typeof v === "object" && !Array.isArray(v)) {
    const o = v as Record<string, unknown>;
    if ("F" in o && "M" in o && Object.keys(o).length === 2) return `Mulher ${o.F} · Homem ${o.M}`;
    if (key === "pontos") return `Mulher ${o.F} · Homem ${o.M}${o.ano_base ? ` em ${o.ano_base}, +1/ano até ${o.max_F}/${o.max_M}` : ""}`;
    if (key === "pedagio") return `${o.percentual}% do tempo que faltava em ${formatDate(String(o.referencia))}`;
  }
  if (Array.isArray(v)) return v.map((s) => `desde ${formatDate(s.desde)}: M ${s.F} · H ${s.M}`).join("; ");
  if (typeof v === "string" && /^\d{4}-\d{2}-\d{2}$/.test(v)) return formatDate(v);
  if (typeof v === "boolean") return v ? "Sim" : "Não";
  return String(v);
}

export default function RulesPage() {
  return (
    <RequirePermission module="previdenciaria.regras">
      <Rules />
    </RequirePermission>
  );
}

function Rules() {
  const { can } = useSession();
  const { data, error, mutate } = useSWR<RetirementRuleRow[]>("previdencia/regras", fetcher);
  const [editing, setEditing] = useState<RetirementRuleRow | null>(null);

  return (
    <>
      <PageHeader
        title="Regras de Aposentadoria"
        description="Regras do RPPS conforme a Emenda à Lei Orgânica nº 28/2025 (vigente com a LC 106/2025, a partir de 15/06/2025), EC 103/2019 e direito adquirido."
        breadcrumb={[{ label: "Gestão Previdenciária" }, { label: "Regras de Aposentadoria" }]}
      />
      {error && <ErrorState error={error} />}
      {data?.length === 0 && (
        <Card><CardContent className="p-6 text-center text-xs text-muted-foreground">Nenhuma regra cadastrada para esta instituição.</CardContent></Card>
      )}
      {GROUPS.map(([g, title]) => {
        const rules = data?.filter((r) => r.group === g) ?? [];
        if (!rules.length) return null;
        return (
          <div key={g} className="mb-5">
            <div className="section-label mb-2">{title}</div>
            <div className="grid gap-3 xl:grid-cols-2">
              {rules.map((r) => (
                <Card key={r.id} className={r.active ? "" : "opacity-60"}>
                  <div className="flex items-start justify-between gap-2 border-b px-4 py-2.5">
                    <div>
                      <div className="text-sm font-semibold">{r.name} {r.for_teacher && <Badge className="ml-1">Professor</Badge>} {!r.active && <Badge variant="neutral">Inativa</Badge>}</div>
                      <div className="text-2xs text-muted-foreground">{r.legal_basis}</div>
                    </div>
                    {can("previdenciaria.regras", "editar") && <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => setEditing(r)} aria-label="Editar"><Pencil /></Button>}
                  </div>
                  <CardContent className="space-y-1 p-4 text-xs">
                    {(r.valid_from || r.valid_to) && (
                      <div className="mb-1"><Badge variant="info">{r.valid_from ? `Requisitos a partir de ${formatDate(r.valid_from)}` : `Requisitos até ${formatDate(r.valid_to)}`}</Badge></div>
                    )}
                    {Object.entries(r.params).map(([k, v]) => (
                      <div key={k} className="grid grid-cols-5 gap-2"><span className="col-span-2 text-muted-foreground">{LABELS[k] ?? k}</span><span className="col-span-3">{describe(k, v)}</span></div>
                    ))}
                    <div className="border-t pt-1.5"><span className="text-muted-foreground">Proventos: </span>{r.proventos}</div>
                    <div><span className="text-muted-foreground">Paridade: </span>{r.paridade || "—"}</div>
                    {r.notes && <div className="text-warning">{r.notes}</div>}
                  </CardContent>
                </Card>
              ))}
            </div>
          </div>
        );
      })}
      {editing && <EditRule rule={editing} onClose={() => setEditing(null)} onSaved={() => mutate()} />}
    </>
  );
}

function EditRule({ rule, onClose, onSaved }: { rule: RetirementRuleRow; onClose: () => void; onSaved: () => void }) {
  const [params, setParams] = useState(JSON.stringify(rule.params, null, 2));
  const [active, setActive] = useState(rule.active);
  const [notes, setNotes] = useState(rule.notes);
  const [justification, setJustification] = useState("");
  const [busy, setBusy] = useState(false);

  const save = async () => {
    let parsed: unknown;
    try { parsed = JSON.parse(params); } catch { toast.error("Parâmetros com formato inválido."); return; }
    setBusy(true);
    try {
      await api(`previdencia/regras/${rule.id}`, { method: "PATCH", body: { params: parsed, active, notes }, justification });
      toast.success("Regra atualizada (registrada na auditoria).");
      onSaved();
      onClose();
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent size="lg">
        <DialogHeader>
          <DialogTitle>{rule.name}</DialogTitle>
          <DialogDescription>Altere apenas se a legislação mudar. Toda alteração exige justificativa e fica na auditoria.</DialogDescription>
        </DialogHeader>
        <DialogBody className="space-y-3">
          <FormField label="Parâmetros (avançado)" htmlFor="r-params" hint="Idades e tempos em anos; F = mulher, M = homem.">
            <Textarea id="r-params" value={params} onChange={(e) => setParams(e.target.value)} className="min-h-[220px] font-mono text-2xs" />
          </FormField>
          <FormField label="Observações" htmlFor="r-notes"><Textarea id="r-notes" value={notes} onChange={(e) => setNotes(e.target.value)} /></FormField>
          <label className="flex items-center gap-2 text-xs"><Checkbox checked={active} onChange={(e) => setActive(e.target.checked)} /> Regra ativa</label>
          <FormField label="Justificativa (obrigatória)" htmlFor="r-just" required>
            <Textarea id="r-just" value={justification} onChange={(e) => setJustification(e.target.value)} placeholder="Ex.: Lei Complementar nº ... alterou a idade mínima" />
          </FormField>
        </DialogBody>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancelar</Button>
          <Button onClick={save} disabled={busy || justification.trim().length < 10}>{busy && <Loader2 className="animate-spin" />} Salvar</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
