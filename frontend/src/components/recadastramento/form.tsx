"use client";

/** Formulário do recadastramento (o mesmo no Portal do Segurado e no atendimento presencial). */
import { useRef, useState } from "react";
import { FileUp } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input, Select, Textarea } from "@/components/ui/input";
import { cn } from "@/lib/utils";

export type RecadData = {
  pessoa: { social_name: string; marital_status: number | string; education: string; race: number | string; phone: string; mobile: string; email: string };
  endereco: { cep: string; street: string; number: string; complement: string; district: string; city: string; uf: string };
};
export type RecadDecl = {
  veracidade: boolean; dependentes_alteracoes: string; conta_alteracao: string;
  acumula_cargo: boolean; acumula_cargo_descricao: string; outro_beneficio: boolean; outro_beneficio_descricao: string;
};
export const EMPTY_DECL: RecadDecl = {
  veracidade: false, dependentes_alteracoes: "", conta_alteracao: "", acumula_cargo: false, acumula_cargo_descricao: "",
  outro_beneficio: false, outro_beneficio_descricao: "",
};

const MARITAL = [[1, "Solteiro(a)"], [2, "Casado(a)"], [3, "Viúvo(a)"], [4, "Separado(a) judicialmente"], [5, "Divorciado(a)"], [6, "União estável"], [9, "Outros"]];
const RACE = [[1, "Branca"], [2, "Preta"], [3, "Parda"], [4, "Amarela"], [5, "Indígena"], [6, "Prefiro não informar"]];
const UFS = "AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO".split(" ");

function F({ label, children, className }: { label: string; children: React.ReactNode; className?: string }) {
  return <label className={cn("block space-y-1", className)}><span className="text-sm font-medium">{label}</span>{children}</label>;
}

export function RecadForm({ data, setData, decl, setDecl, large }: {
  data: RecadData; setData: (d: RecadData) => void; decl: RecadDecl; setDecl: (d: RecadDecl) => void; large?: boolean;
}) {
  const h = large ? "h-11 text-base" : "h-9";
  const p = (k: keyof RecadData["pessoa"]) => ({ value: String(data.pessoa[k] ?? ""), onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setData({ ...data, pessoa: { ...data.pessoa, [k]: e.target.value } }) });
  const a = (k: keyof RecadData["endereco"]) => ({ value: data.endereco[k] ?? "", onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setData({ ...data, endereco: { ...data.endereco, [k]: e.target.value } }) });
  const d = <K extends keyof RecadDecl>(k: K, v: RecadDecl[K]) => setDecl({ ...decl, [k]: v });
  return (
    <div className="space-y-5">
      <section className="space-y-3">
        <h3 className="text-base font-semibold text-primary-strong">Contato e dados pessoais</h3>
        <div className="grid gap-3 sm:grid-cols-2">
          <F label="Celular (com DDD)"><Input className={h} inputMode="tel" placeholder="(24) 99999-9999" {...p("mobile")} /></F>
          <F label="Outro telefone"><Input className={h} inputMode="tel" {...p("phone")} /></F>
          <F label="E-mail" className="sm:col-span-2"><Input className={h} type="email" {...p("email")} /></F>
          <F label="Estado civil"><Select className={h} {...p("marital_status")}><option value="">Selecione</option>{MARITAL.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</Select></F>
          <F label="Escolaridade"><Input className={h} {...p("education")} placeholder="Ex.: Ensino médio completo" /></F>
          <F label="Raça/cor"><Select className={h} {...p("race")}><option value="">Selecione</option>{RACE.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</Select></F>
          <F label="Nome social (se usar)"><Input className={h} {...p("social_name")} /></F>
        </div>
      </section>
      <section className="space-y-3">
        <h3 className="text-base font-semibold text-primary-strong">Endereço</h3>
        <div className="grid gap-3 sm:grid-cols-6">
          <F label="CEP" className="sm:col-span-2"><Input className={h} inputMode="numeric" {...a("cep")} /></F>
          <F label="Rua / avenida" className="sm:col-span-4"><Input className={h} {...a("street")} /></F>
          <F label="Número" className="sm:col-span-1"><Input className={h} {...a("number")} /></F>
          <F label="Complemento" className="sm:col-span-2"><Input className={h} {...a("complement")} /></F>
          <F label="Bairro" className="sm:col-span-3"><Input className={h} {...a("district")} /></F>
          <F label="Cidade" className="sm:col-span-4"><Input className={h} {...a("city")} /></F>
          <F label="UF" className="sm:col-span-2"><Select className={h} {...a("uf")}><option value="">UF</option>{UFS.map((u) => <option key={u} value={u}>{u}</option>)}</Select></F>
        </div>
      </section>
      <section className="space-y-3">
        <h3 className="text-base font-semibold text-primary-strong">Declarações</h3>
        <label className="flex items-start gap-3 text-sm"><input type="checkbox" className="mt-0.5 h-5 w-5" checked={decl.acumula_cargo} onChange={(e) => d("acumula_cargo", e.target.checked)} />
          Tenho outro cargo, emprego ou função pública (acumulação).</label>
        {decl.acumula_cargo && <Input className={h} placeholder="Qual? (órgão e cargo)" value={decl.acumula_cargo_descricao} onChange={(e) => d("acumula_cargo_descricao", e.target.value)} />}
        <label className="flex items-start gap-3 text-sm"><input type="checkbox" className="mt-0.5 h-5 w-5" checked={decl.outro_beneficio} onChange={(e) => d("outro_beneficio", e.target.checked)} />
          Recebo aposentadoria ou pensão de outro regime (INSS ou outro órgão).</label>
        {decl.outro_beneficio && <Input className={h} placeholder="Qual? (órgão e tipo de benefício)" value={decl.outro_beneficio_descricao} onChange={(e) => d("outro_beneficio_descricao", e.target.value)} />}
        <F label="Mudou algo nos seus dependentes? (nascimento, casamento, separação, óbito…)">
          <Textarea value={decl.dependentes_alteracoes} onChange={(e) => d("dependentes_alteracoes", e.target.value)} placeholder="Deixe em branco se não mudou nada" />
        </F>
        <F label="Precisa trocar a conta onde recebe?">
          <Input className={h} value={decl.conta_alteracao} onChange={(e) => d("conta_alteracao", e.target.value)} placeholder="Deixe em branco se não precisa" />
        </F>
        <p className="text-xs text-muted-foreground">Mudanças de dependentes e de conta precisam de documentos: a equipe vai entrar em contato.</p>
      </section>
    </div>
  );
}

export function FilePick({ label, file, setFile, hint }: { label: string; file: File | null; setFile: (f: File | null) => void; hint?: string }) {
  const input = useRef<HTMLInputElement>(null);
  return (
    <div className="space-y-1">
      <div className="text-sm font-medium">{label}</div>
      {hint && <div className="text-xs text-muted-foreground">{hint}</div>}
      <input ref={input} type="file" accept=".pdf,.jpg,.jpeg,.png,image/*" className="hidden" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
      <div className="flex flex-wrap items-center gap-2">
        <Button type="button" variant="outline" onClick={() => input.current?.click()}><FileUp /> {file ? "Trocar arquivo" : "Escolher arquivo ou tirar foto"}</Button>
        {file && <span className="truncate text-sm text-muted-foreground">{file.name}</span>}
      </div>
    </div>
  );
}

export function useRecadState(initial?: Partial<RecadData>) {
  const [data, setData] = useState<RecadData>({
    pessoa: { social_name: "", marital_status: "", education: "", race: "", phone: "", mobile: "", email: "", ...(initial?.pessoa ?? {}) },
    endereco: { cep: "", street: "", number: "", complement: "", district: "", city: "", uf: "", ...(initial?.endereco ?? {}) },
  });
  const [decl, setDecl] = useState<RecadDecl>(EMPTY_DECL);
  return { data, setData, decl, setDecl };
}
