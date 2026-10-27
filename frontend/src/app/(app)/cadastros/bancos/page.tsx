"use client";

import { RegistryPage } from "@/components/shared/registry-page";

export default function Page() {
  return (
    <RegistryPage
      config={{
        module: "cadastros.bancos", endpoint: "banks", title: "Bancos", singular: "Banco", breadcrumb: "Gestão de Cadastros",
        description: "Bancos (código COMPE). Os principais bancos já vêm cadastrados.",
        searchPlaceholder: "Código ou nome",
        columns: [
          { label: "Código", render: (r) => <span className="font-mono text-xs font-semibold">{String(r.code)}</span> },
          { label: "Banco", render: (r) => <span className="font-medium">{String(r.name)}</span> },
        ],
        fields: [
          { name: "code", label: "Código COMPE", type: "digits", maxLength: 3, required: true },
          { name: "name", label: "Nome", required: true },
        ],
      }}
    />
  );
}
