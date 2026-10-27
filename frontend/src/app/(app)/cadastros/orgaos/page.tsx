"use client";

import { RegistryPage } from "@/components/shared/registry-page";
import { PODER, TIPO_PODER } from "@/lib/options";

export default function Page() {
  return (
    <RegistryPage
      config={{
        module: "cadastros.orgaos", endpoint: "organs", title: "Órgãos", singular: "Órgão", breadcrumb: "Gestão de Cadastros",
        description: "Órgãos e entidades (Prefeitura, Câmara, autarquias). O código SIGFIS é usado na Deliberação 260 do TCE-RJ.",
        searchPlaceholder: "Nome, sigla, CNPJ ou código SIGFIS",
        columns: [
          { label: "Órgão", render: (r) => <><div className="font-medium">{String(r.name)}</div><div className="text-2xs text-muted-foreground">{String(r.ente_name)}</div></> },
          { label: "Sigla", render: (r) => String(r.short_name || "—") },
          { label: "CNPJ", render: (r) => String(r.cnpj_formatado || "—"), className: "tabular" },
          { label: "Poder", render: (r) => `${r.poder_display} · ${r.tipo_poder_display}` },
          { label: "SIGFIS", render: (r) => <span className="font-mono text-xs">{String(r.sigfis_code || "—")}</span> },
        ],
        fields: [
          { name: "ente", label: "Ente", type: "ref", required: true, wide: true, ref: { endpoint: "entes", label: (r) => String(r.name) } },
          { name: "name", label: "Nome", required: true, wide: true },
          { name: "short_name", label: "Sigla" },
          { name: "cnpj", label: "CNPJ", type: "cnpj" },
          { name: "poder", label: "Poder", type: "select", required: true, options: PODER },
          { name: "tipo_poder", label: "Administração", type: "select", required: true, options: TIPO_PODER },
          { name: "sigfis_code", label: "Código SIGFIS (TCE-RJ)", type: "digits", maxLength: 4, hint: "4 dígitos — Deliberação 260." },
        ],
        defaults: { poder: 1, tipo_poder: 1 },
      }}
    />
  );
}
