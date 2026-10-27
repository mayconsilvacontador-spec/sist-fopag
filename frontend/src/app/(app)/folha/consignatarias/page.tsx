"use client";

import { RegistryPage } from "@/components/shared/registry-page";

export default function Page() {
  return (
    <RegistryPage
      config={{
        module: "folha.consignacoes", endpoint: "folha/consignatarias", title: "Consignatárias", singular: "Consignatária", breadcrumb: "Folha de Benefícios",
        description: "Bancos, sindicatos e associações autorizados a descontar em folha.",
        searchPlaceholder: "Nome ou CNPJ",
        columns: [
          { label: "Nome", render: (r) => String(r.name) },
          { label: "Tipo", render: (r) => String(r.kind_display) },
          { label: "CNPJ", render: (r) => String(r.cnpj || "—") },
        ],
        fields: [
          { name: "name", label: "Nome", required: true, wide: true },
          { name: "kind", label: "Tipo", type: "select", required: true, options: [
            { value: "BANCO", label: "Instituição financeira" }, { value: "SINDICATO", label: "Sindicato" },
            { value: "ASSOCIACAO", label: "Associação" }, { value: "OUTROS", label: "Outros" }] },
          { name: "cnpj", label: "CNPJ", type: "cnpj" },
        ],
        defaults: { kind: "BANCO" },
      }}
    />
  );
}