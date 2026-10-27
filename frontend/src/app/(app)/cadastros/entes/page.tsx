"use client";

import { RegistryPage } from "@/components/shared/registry-page";
import { ENTE_KIND, UF_OPTIONS } from "@/lib/options";

export default function Page() {
  return (
    <RegistryPage
      config={{
        module: "cadastros.entes", endpoint: "entes", title: "Entes", singular: "Ente", breadcrumb: "Gestão de Cadastros",
        description: "Entes federativos aos quais os órgãos e servidores estão vinculados.",
        searchPlaceholder: "Nome ou CNPJ",
        columns: [
          { label: "Nome", render: (r) => <span className="font-medium">{String(r.name)}</span> },
          { label: "Tipo", render: (r) => String(r.kind_display) },
          { label: "CNPJ", render: (r) => String(r.cnpj_formatado || "—"), className: "tabular" },
          { label: "IBGE / UF", render: (r) => `${r.ibge_code || "—"} · ${r.uf || "—"}` },
        ],
        fields: [
          { name: "name", label: "Nome", required: true, wide: true },
          { name: "kind", label: "Tipo", type: "select", required: true, options: ENTE_KIND },
          { name: "cnpj", label: "CNPJ", type: "cnpj" },
          { name: "ibge_code", label: "Código IBGE", type: "digits", maxLength: 7 },
          { name: "uf", label: "UF", type: "select", options: UF_OPTIONS },
        ],
        defaults: { kind: "MUNICIPIO" },
      }}
    />
  );
}
