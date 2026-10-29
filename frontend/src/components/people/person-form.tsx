"use client";

import { useState } from "react";
import { toast } from "sonner";
import { Landmark, Loader2, Save } from "lucide-react";

import { useSession } from "@/components/providers/session-provider";
import { FormField } from "@/components/shared/form-field";
import { Button } from "@/components/ui/button";
import { Checkbox, Input, Select, Textarea } from "@/components/ui/input";
import { ApiError, api } from "@/lib/api";
import { isValidCPF, maskCPF, onlyDigits } from "@/lib/format";
import { MARITAL, SEX, UF_OPTIONS } from "@/lib/options";
import type { Person, ReceitaPerson } from "@/lib/types";

const EMPTY = {
  cpf: "", name: "", social_name: "", birth_date: "", sex: "", marital_status: "", mother_name: "", father_name: "",
  nationality: "Brasileira", birthplace_city: "", birthplace_uf: "", rg_number: "", rg_issuer: "", rg_uf: "",
  rg_date: "", pis_pasep: "", voter_id: "", education: "", phone: "", mobile: "", email: "", race: "", has_disability: false,
  disability_type: "", is_invalid: false, invalidity_date: "", death_date: "", death_certificate: "", notes: "",
};
export type FormState = typeof EMPTY;
const RACE = [{ value: 1, label: "Branca" }, { value: 2, label: "Preta" }, { value: 3, label: "Parda" }, { value: 4, label: "Amarela" }, { value: 5, label: "Indígena" }, { value: 6, label: "Não informado" }];
// Nomes completos: o Tailwind não reconhece classes montadas dinamicamente
const SPAN: Record<number, string> = { 2: "sm:col-span-2", 3: "sm:col-span-3", 4: "sm:col-span-4", 6: "sm:col-span-6" };

function fromPerson(p: Person): FormState {
  const out = { ...EMPTY } as Record<string, unknown>;
  for (const k of Object.keys(EMPTY)) {
    const v = (p as unknown as Record<string, unknown>)[k];
    out[k] = v === null || v === undefined ? (typeof EMPTY[k as keyof FormState] === "boolean" ? false : "") : v;
  }
  out.cpf = maskCPF(p.cpf);
  return out as FormState;
}

/** Converte a resposta da Receita em campos do formulário (somente os preenchidos). */
export function receitaToForm(r: ReceitaPerson): Partial<FormState> {
  const out: Partial<FormState> = {};
  if (r.name) out.name = r.name;
  if (r.social_name) out.social_name = r.social_name;
  if (r.birth_date) out.birth_date = r.birth_date;
  if (r.sex) out.sex = String(r.sex);
  if (r.mother_name) out.mother_name = r.mother_name;
  if (r.birthplace_city) out.birthplace_city = r.birthplace_city;
  if (r.birthplace_uf) out.birthplace_uf = r.birthplace_uf;
  if (r.nationality) out.nationality = r.nationality;
  return out;
}

/** Formulário do cadastro (inclusão e edição). */
export function PersonForm({
  person, initialCpf, prefill, disabled, onSaved, onCancel,
}: {
  person?: Person;
  initialCpf?: string;
  /** Dados vindos da Receita para pré-preencher a inclusão */
  prefill?: Partial<FormState>;
  disabled?: boolean;
  onSaved: (p: Person) => void;
  onCancel?: () => void;
}) {
  const { me } = useSession();
  const receitaOn = !!me?.integracoes?.receita;
  const [f, setF] = useState<FormState>(person ? fromPerson(person) : { ...EMPTY, ...prefill, cpf: initialCpf ?? "" });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [consulting, setConsulting] = useState(false);

  /** Edição: completa pela Receita apenas os campos vazios (nada é sobrescrito). */
  const fillFromReceita = async () => {
    setConsulting(true);
    try {
      const r = await api<ReceitaPerson>(`people/receita?cpf=${onlyDigits(f.cpf)}`);
      const data = receitaToForm(r);
      setF((s) => {
        const next = { ...s } as Record<string, unknown>;
        for (const [k, v] of Object.entries(data)) if (!next[k]) next[k] = v;
        return next as FormState;
      });
      toast.success(`Receita: ${r.situacao_cadastral || "consulta realizada"}. Campos vazios completados — confira e salve.`);
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setConsulting(false);
    }
  };

  const set = (k: keyof FormState) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
    setF((s) => ({ ...s, [k]: k === "cpf" ? maskCPF(e.target.value) : e.target.value }));
  const check = (k: keyof FormState) => (e: React.ChangeEvent<HTMLInputElement>) => setF((s) => ({ ...s, [k]: e.target.checked }));

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!isValidCPF(f.cpf)) { setErrors({ cpf: "CPF inválido." }); return; }
    setBusy(true);
    setErrors({});
    try {
      const body: Record<string, unknown> = { ...f };
      for (const k of ["marital_status", "race", "rg_date", "invalidity_date", "death_date"]) if (body[k] === "") body[k] = null;
      const saved = person
        ? await api<Person>(`people/${person.id}`, { method: "PATCH", body })
        : await api<Person>("people", { method: "POST", body });
      toast.success(person ? "Cadastro atualizado." : "Pessoa cadastrada.");
      onSaved(saved);
    } catch (err) {
      if (err instanceof ApiError) setErrors(err.fieldErrors);
      toast.error((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const fld = (k: keyof FormState, label: string, props: { required?: boolean; type?: string; span?: number; hint?: string } = {}) => (
    <FormField label={label} htmlFor={`p-${k}`} required={props.required} error={errors[k]} hint={props.hint}
      className={props.span ? SPAN[props.span] : undefined}>
      <Input id={`p-${k}`} type={props.type ?? "text"} value={String(f[k] ?? "")} onChange={set(k)} required={props.required} disabled={disabled} />
    </FormField>
  );
  const sel = (k: keyof FormState, label: string, options: { value: string | number; label: string }[], required = false) => (
    <FormField label={label} htmlFor={`p-${k}`} required={required} error={errors[k]}>
      <Select id={`p-${k}`} value={String(f[k] ?? "")} onChange={set(k)} required={required} disabled={disabled}>
        <option value="">{required ? "Selecione" : "—"}</option>
        {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </Select>
    </FormField>
  );

  return (
    <form onSubmit={submit}>
      <div className="grid gap-3 sm:grid-cols-6">
        <div className="flex items-center justify-between sm:col-span-6">
          <span className="section-label">Identificação</span>
          {person && !disabled && receitaOn && (
            <Button type="button" size="sm" variant="outline" onClick={fillFromReceita} disabled={consulting}>
              {consulting ? <Loader2 className="animate-spin" /> : <Landmark />} Completar pela Receita
            </Button>
          )}
        </div>
        {fld("cpf", "CPF", { required: true, span: 2 })}
        {fld("name", "Nome completo", { required: true, span: 4 })}
        {fld("social_name", "Nome social", { span: 2 })}
        {fld("birth_date", "Data de nascimento", { required: true, type: "date" })}
        {sel("sex", "Sexo", SEX, true)}
        {sel("marital_status", "Estado civil", MARITAL)}
        {sel("race", "Raça/cor", RACE)}
        {fld("pis_pasep", "PIS/PASEP/NIT")}
        {fld("mother_name", "Nome da mãe", { span: 3 })}
        {fld("father_name", "Nome do pai", { span: 3 })}
        {fld("nationality", "Nacionalidade")}
        {fld("birthplace_city", "Naturalidade", { span: 2 })}
        {sel("birthplace_uf", "UF", UF_OPTIONS)}
        {fld("education", "Escolaridade", { span: 2 })}

        <div className="section-label mt-2 sm:col-span-6">Documentos</div>
        {fld("rg_number", "RG")}
        {fld("rg_issuer", "Órgão expedidor")}
        {sel("rg_uf", "UF do RG", UF_OPTIONS)}
        {fld("rg_date", "Expedição", { type: "date" })}
        {fld("voter_id", "Título de eleitor", { span: 2 })}

        <div className="section-label mt-2 sm:col-span-6">Contato</div>
        {fld("phone", "Telefone", { span: 2 })}
        {fld("mobile", "Celular", { span: 2 })}
        {fld("email", "E-mail", { type: "email", span: 2 })}

        <div className="section-label mt-2 sm:col-span-6">Condições</div>
        <label className="flex items-center gap-2 text-xs sm:col-span-2">
          <Checkbox checked={f.has_disability} onChange={check("has_disability")} disabled={disabled} /> Pessoa com deficiência
        </label>
        {f.has_disability ? fld("disability_type", "Tipo de deficiência", { span: 4 }) : <div className="sm:col-span-4" />}
        <label className="flex items-center gap-2 text-xs sm:col-span-2">
          <Checkbox checked={f.is_invalid} onChange={check("is_invalid")} disabled={disabled} /> Inválido(a)
        </label>
        {f.is_invalid ? fld("invalidity_date", "Data da invalidez", { type: "date", required: true }) : <div />}
        <div className="sm:col-span-3" />
        {person && (
          <>
            {fld("death_date", "Data do óbito", { type: "date" })}
            {fld("death_certificate", "Certidão de óbito", { span: 2 })}
            <div className="sm:col-span-3" />
          </>
        )}
        <FormField label="Observações" htmlFor="p-notes" error={errors.notes} className="sm:col-span-6">
          <Textarea id="p-notes" value={f.notes} onChange={set("notes")} disabled={disabled} />
        </FormField>
      </div>
      {!disabled && (
        <div className="mt-4 flex justify-end gap-2 border-t pt-3">
          {onCancel && <Button variant="outline" onClick={onCancel}>Cancelar</Button>}
          <Button type="submit" disabled={busy}>{busy ? <Loader2 className="animate-spin" /> : <Save />} Salvar</Button>
        </div>
      )}
    </form>
  );
}
