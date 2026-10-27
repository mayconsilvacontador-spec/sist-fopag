"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import useSWR from "swr";
import { toast } from "sonner";
import { Loader2, Search, UserCheck } from "lucide-react";

import { useSession } from "@/components/providers/session-provider";
import { FormField } from "@/components/shared/form-field";
import { PageHeader } from "@/components/shared/page-header";
import { RequirePermission } from "@/components/shared/require-permission";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input, Select } from "@/components/ui/input";
import { api, fetcher, type Paginated } from "@/lib/api";
import { ACCOUNT_TYPE, ADMISSION_FORM, LINK_TYPE, MARITAL, REGIME, SEGMENT, SEX, UF_OPTIONS } from "@/lib/options";

type Row = { id: string; name: string; code?: string };
type Found = { id: string; name: string } | null;
type Form = Record<string, string | boolean>;

export default function AdmissaoPage() {
  return (
    <RequirePermission module="cadastros.segurados" action="incluir">
      <Admissao />
    </RequirePermission>
  );
}

function Admissao() {
  const router = useRouter();
  const { can } = useSession();
  const organs = useSWR<Paginated<Row>>("organs?page_size=500", fetcher);
  const positions = useSWR<Paginated<Row>>("positions?page_size=1000", fetcher);
  const banks = useSWR<Paginated<Row>>("banks?page_size=500", fetcher);
  const [cpf, setCpf] = useState("");
  const [found, setFound] = useState<Found | undefined>(undefined);
  const [f, setF] = useState<Form>({
    sex: "", marital_status: "", link_type: "1", regime: "ESTATUTARIO", admission_form: "3", segment: "PREVIDENCIARIO",
    account_type: "CORRENTE", complementary_pension: false,
  });
  const [busy, setBusy] = useState(false);
  const [missing, setMissing] = useState<string[]>([]);
  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setF((x) => ({ ...x, [k]: e.target.type === "checkbox" ? (e.target as HTMLInputElement).checked : e.target.value }));
  const v = (k: string) => String(f[k] ?? "");

  const lookup = async () => {
    const digits = cpf.replace(/\D/g, "");
    if (digits.length !== 11) { toast.error("Digite os 11 números do CPF."); return; }
    try {
      const r = await api<Found | "">(`people/by-cpf?cpf=${digits}`);
      setFound(r && typeof r === "object" && r.id ? r : null);
    } catch (err) {
      toast.error((err as Error).message);
    }
  };

  const save = async () => {
    const need: [string, string][] = [
      ...(found === null ? [["name", "nome"], ["birth_date", "data de nascimento"], ["sex", "sexo"]] as [string, string][] : []),
      ["organ", "órgão"], ["position", "cargo"], ["registration", "matrícula"], ["nomeacao", "data da nomeação"],
    ];
    const missing = need.filter(([k]) => !v(k).trim());
    setMissing(missing.map(([k]) => k));
    if (missing.length) {
      toast.error(`Preencha: ${missing.map(([, l]) => l).join(", ")}.`);
      document.getElementById(`ad-${missing[0][0]}`)?.focus();
      return;
    }
    setBusy(true);
    try {
      const r = await api<{ pessoa: string }>("people/admissao", {
        method: "POST",
        body: {
          pessoa: { cpf: cpf.replace(/\D/g, ""), name: v("name"), birth_date: v("birth_date"), sex: v("sex"),
            marital_status: v("marital_status"), mother_name: v("mother_name"), father_name: v("father_name"),
            rg_number: v("rg_number"), rg_issuer: v("rg_issuer"), pis_pasep: v("pis_pasep"), education: v("education"),
            mobile: v("mobile"), email: v("email") },
          vinculo: { organ: v("organ"), position: v("position"), registration: v("registration"), link_type: v("link_type"),
            regime: v("regime"), admission_form: v("admission_form"), nomeacao: v("nomeacao"), exercicio: v("exercicio"),
            servico_publico: v("servico_publico"), class_level: v("class_level"), base_salary: v("base_salary"),
            weekly_hours: v("weekly_hours"),
            segment: v("segment"), complementary_pension: f.complementary_pension, act_type: "PORTARIA",
            act_number: v("act_number"), act_date: v("act_date"), publication: v("publication") },
          endereco: { cep: v("cep"), street: v("street"), number: v("number"), complement: v("complement"),
            district: v("district"), city: v("city"), uf: v("uf") },
          conta: { bank: v("bank"), branch: v("branch"), account: v("account"), account_digit: v("account_digit"),
            account_type: v("account_type") },
        },
      });
      toast.success("Admissão registrada. Agora anexe a foto e os documentos na Pasta do Servidor.");
      router.push(`/cadastros/pessoas/${r.pessoa}`);
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const T = (k: string, label: string, props: React.InputHTMLAttributes<HTMLInputElement> = {}) => (
    <FormField label={label} htmlFor={`ad-${k}`}><Input id={`ad-${k}`} value={v(k)} onChange={set(k)} {...props}
      className={missing.includes(k) && !v(k) ? "border-critical ring-1 ring-critical" : undefined} /></FormField>
  );
  const S = (k: string, label: string, opts: { value: string | number; label: string }[], placeholder = true) => (
    <FormField label={label} htmlFor={`ad-${k}`}>
      <Select id={`ad-${k}`} value={v(k)} onChange={set(k)}
        className={missing.includes(k) && !v(k) ? "border-critical ring-1 ring-critical" : undefined}>
        {placeholder && <option value="">Selecione…</option>}
        {opts.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </Select>
    </FormField>
  );
  const rows = (d?: Paginated<Row>, withCode = false) =>
    (d?.results ?? []).map((r) => ({ value: r.id, label: withCode && r.code ? `${r.code} - ${r.name}` : r.name }));

  return (
    <>
      <PageHeader title="Admissão" description="Porta de entrada do servidor: cadastro, cargo, vencimento, nomeação e posse, de uma só vez."
        breadcrumb={[{ label: "Gestão de Cadastros" }, { label: "Servidores", href: "/cadastros/servidores" }, { label: "Admissão" }]} />
      <Card className="mb-4">
        <CardContent className="flex flex-wrap items-end gap-3 p-4">
          <FormField label="1. CPF do servidor" htmlFor="ad-cpf">
            <Input id="ad-cpf" value={cpf} onChange={(e) => { setCpf(e.target.value); setFound(undefined); }}
              onKeyDown={(e) => e.key === "Enter" && lookup()} placeholder="000.000.000-00" className="w-48" />
          </FormField>
          <Button variant="outline" onClick={lookup}><Search /> Conferir</Button>
          {found === null && <span className="text-sm text-muted-foreground">CPF novo — preencha os dados pessoais.</span>}
          {found && (
            <span className="flex items-center gap-1 text-sm text-success">
              <UserCheck className="h-4 w-4" /> Já cadastrado: {found.name}. Os dados pessoais serão mantidos; preencha só o novo vínculo.
            </span>
          )}
        </CardContent>
      </Card>

      {found !== undefined && (
        <Card>
          <CardContent className="space-y-6 p-4">
            {found === null && (
              <Block title="2. Dados pessoais">
                {T("name", "Nome completo *")}
                {T("birth_date", "Nascimento *", { type: "date" })}
                {S("sex", "Sexo *", SEX)}
                {S("marital_status", "Estado civil", MARITAL)}
                {T("mother_name", "Nome da mãe")}
                {T("father_name", "Nome do pai")}
                {T("rg_number", "RG")}
                {T("rg_issuer", "Órgão expedidor")}
                {T("pis_pasep", "PIS/PASEP")}
                {T("education", "Escolaridade")}
                {T("mobile", "Celular")}
                {T("email", "E-mail", { type: "email" })}
              </Block>
            )}
            <Block title={found === null ? "3. Cargo e vínculo" : "2. Cargo e vínculo"}>
              {S("organ", "Órgão *", rows(organs.data))}
              {S("position", "Cargo *", rows(positions.data))}
              {T("registration", "Matrícula *")}
              {T("class_level", "Classe / nível")}
              {T("base_salary", "Vencimento base (R$)", { type: "number", step: "0.01", min: "0" })}
              {T("weekly_hours", "Carga horária (horas semanais)", { type: "number", min: "1", max: "60" })}
              {S("link_type", "Tipo de vínculo", LINK_TYPE, false)}
              {S("regime", "Regime", REGIME, false)}
              {S("admission_form", "Forma de admissão", ADMISSION_FORM, false)}
              {S("segment", "Massa (fundo)", SEGMENT.filter((s) => s.value !== "COMPRA_VIDAS"), false)}
              {T("nomeacao", "Data da nomeação *", { type: "date" })}
              {T("exercicio", "Início do exercício (posse)", { type: "date" })}
              {T("servico_publico", "Ingresso no serviço público", { type: "date" })}
              {T("act_number", "Nº da portaria de nomeação")}
              {T("act_date", "Data da portaria", { type: "date" })}
              {T("publication", "Publicação (D.O. / data)")}
              <label className="flex items-center gap-2 self-end pb-2 text-sm">
                <input type="checkbox" checked={!!f.complementary_pension} onChange={set("complementary_pension")} />
                Sujeito à previdência complementar
              </label>
            </Block>
            <p className="-mt-3 text-2xs text-muted-foreground">
              Sem vencimento informado, a folha usa a Tabela de vencimentos do cargo/nível. Se o exercício ficar em branco, vale a data da nomeação.
            </p>
            <Block title="Endereço (opcional)">
              {T("cep", "CEP")}
              {T("street", "Logradouro")}
              {T("number", "Número")}
              {T("complement", "Complemento")}
              {T("district", "Bairro")}
              {T("city", "Cidade")}
              {S("uf", "UF", UF_OPTIONS)}
            </Block>
            <Block title="Conta para crédito do salário (opcional)">
              {S("bank", "Banco", rows(banks.data, true))}
              {T("branch", "Agência")}
              {T("account", "Conta")}
              {T("account_digit", "Dígito")}
              {S("account_type", "Tipo", ACCOUNT_TYPE, false)}
            </Block>
            <div className="flex justify-end">
              <Button onClick={save} disabled={busy || !can("cadastros.vinculos", "incluir")}>
                {busy ? <Loader2 className="animate-spin" /> : <UserCheck />} Registrar admissão
              </Button>
            </div>
          </CardContent>
        </Card>
      )}
    </>
  );
}

function Block({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h3 className="mb-2 border-b pb-1 text-sm font-semibold text-primary-strong">{title}</h3>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">{children}</div>
    </section>
  );
}
