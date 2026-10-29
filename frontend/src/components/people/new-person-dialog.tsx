"use client";

import { useState } from "react";
import { Loader2 } from "lucide-react";

import { type FormState, PersonForm, receitaToForm } from "@/components/people/person-form";
import { useSession } from "@/components/providers/session-provider";
import { FormField } from "@/components/shared/form-field";
import { Button } from "@/components/ui/button";
import {
  Dialog, DialogBody, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { api, qs } from "@/lib/api";
import { isValidCPF, maskCPF } from "@/lib/format";
import type { PersonRow, ReceitaPerson } from "@/lib/types";

/**
 * Inclusão em 2 passos: primeiro o CPF (reaproveita o cadastro existente —
 * princípio do cadastro), depois os dados. onPicked recebe a pessoa
 * existente ou a recém-criada.
 */
export function NewPersonDialog({
  title = "Nova pessoa", onClose, onPicked,
}: {
  title?: string;
  onClose: () => void;
  onPicked: (p: { id: string; name: string }, existing: boolean) => void;
}) {
  const { me } = useSession();
  const [cpf, setCpf] = useState("");
  const [step, setStep] = useState<"cpf" | "form">("cpf");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [prefill, setPrefill] = useState<Partial<FormState> | undefined>();
  const [receitaInfo, setReceitaInfo] = useState<{ ok: boolean; text: string } | null>(null);

  const checkCpf = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!isValidCPF(cpf)) { setError("CPF inválido."); return; }
    setBusy(true);
    try {
      const found = await api<PersonRow | null>(`people/by-cpf${qs({ cpf })}`);
      if (found) { onPicked(found, true); return; }
      if (me?.integracoes?.receita) {
        try {
          const r = await api<ReceitaPerson>(`people/receita${qs({ cpf })}`);
          setPrefill(receitaToForm(r));
          setReceitaInfo({ ok: true, text: `Dados preenchidos pela Receita Federal (situação: ${r.situacao_cadastral || "—"}${r.ano_obito ? `, óbito em ${r.ano_obito}` : ""}). Confira antes de salvar.` });
        } catch (err) {
          setReceitaInfo({ ok: false, text: `Receita Federal: ${(err as Error).message} Preencha manualmente.` });
        }
      }
      setStep("form");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent size={step === "cpf" ? "sm" : "lg"}>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>
            {step === "cpf"
              ? `Informe o CPF. Se a pessoa já estiver cadastrada, o cadastro existente será usado.${me?.integracoes?.receita ? " Se não estiver, os dados são buscados na Receita Federal." : ""}`
              : "CPF ainda não cadastrado. Preencha os dados."}
          </DialogDescription>
        </DialogHeader>
        {step === "cpf" ? (
          <form onSubmit={checkCpf}>
            <DialogBody>
              <FormField label="CPF" htmlFor="new-cpf" required error={error}>
                <Input id="new-cpf" value={cpf} onChange={(e) => { setCpf(maskCPF(e.target.value)); setError(""); }}
                  placeholder="000.000.000-00" autoFocus inputMode="numeric" />
              </FormField>
            </DialogBody>
            <DialogFooter>
              <Button variant="outline" onClick={onClose}>Cancelar</Button>
              <Button type="submit" disabled={busy}>{busy && <Loader2 className="animate-spin" />} Continuar</Button>
            </DialogFooter>
          </form>
        ) : (
          <DialogBody>
            {receitaInfo && (
              <div className={`mb-3 rounded-md border px-3 py-2 text-xs ${receitaInfo.ok ? "border-success-border bg-success-soft text-success" : "border-warning-border bg-warning-soft text-warning"}`}>
                {receitaInfo.text}
              </div>
            )}
            <PersonForm initialCpf={cpf} prefill={prefill} onSaved={(p) => onPicked(p, false)} onCancel={onClose} />
          </DialogBody>
        )}
      </DialogContent>
    </Dialog>
  );
}
