"use client";

import { RegistryPage } from "@/components/shared/registry-page";

export default function Page() {
  return (
    <RegistryPage
      config={{
        module: "cadastros.lotacao", endpoint: "workplaces", title: "Lotação", singular: "Lotação", breadcrumb: "Gestão de Cadastros",
        description: "Setores, secretarias e unidades onde os servidores trabalham.",
        searchPlaceholder: "Nome ou código",
        columns: [
          { label: "Lotação", render: (r) => <span className="font-medium">{String(r.name)}</span> },
          { label: "Código", render: (r) => String(r.code || "—") },
          { label: "Órgão", render: (r) => String(r.organ_name) },
        ],
        fields: [
          { name: "organ", label: "Órgão", type: "ref", required: true, wide: true, ref: { endpoint: "organs", label: (r) => String(r.name) } },
          { name: "name", label: "Nome", required: true, wide: true },
          { name: "code", label: "Código" },
        ],
      }}
    />
  );
}
