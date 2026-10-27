"use client";

import { RegistryPage } from "@/components/shared/registry-page";
import { UF_OPTIONS } from "@/lib/options";

export default function Page() {
  return (
    <RegistryPage
      config={{
        module: "cadastros.agencias", endpoint: "bank-branches", title: "Agências", singular: "Agência", breadcrumb: "Gestão de Cadastros",
        description: "Agências bancárias usadas no pagamento de benefícios.",
        searchPlaceholder: "Número, nome, cidade ou banco",
        columns: [
          { label: "Banco", render: (r) => String(r.bank_label) },
          { label: "Agência", render: (r) => <span className="font-mono text-xs">{`${r.number}${r.digit ? "-" + r.digit : ""}`}</span> },
          { label: "Nome", render: (r) => String(r.name || "—") },
          { label: "Cidade", render: (r) => `${r.city || "—"}${r.uf ? "/" + r.uf : ""}` },
        ],
        fields: [
          { name: "bank", label: "Banco", type: "ref", required: true, wide: true, ref: { endpoint: "banks", label: (r) => `${r.code} - ${r.name}` } },
          { name: "number", label: "Agência", type: "digits", maxLength: 5, required: true },
          { name: "digit", label: "Dígito", maxLength: 1 },
          { name: "name", label: "Nome", wide: true },
          { name: "city", label: "Cidade" },
          { name: "uf", label: "UF", type: "select", options: UF_OPTIONS },
        ],
      }}
    />
  );
}
