"use client";

import { RegistryPage } from "@/components/shared/registry-page";
import { TIPO_CARGO } from "@/lib/options";

export default function Page() {
  return (
    <RegistryPage
      config={{
        module: "cadastros.cargos", endpoint: "positions", title: "Cargos", singular: "Cargo", breadcrumb: "Gestão de Cadastros",
        description: "Cargos efetivos e suas carreiras. O tipo de cargo segue o leiaute SPREV (avaliação atuarial).",
        searchPlaceholder: "Cargo, carreira ou CBO",
        columns: [
          { label: "Cargo", render: (r) => <><div className="font-medium">{String(r.name)}</div><div className="text-2xs text-muted-foreground">{String(r.career || "")}</div></> },
          { label: "Tipo (SPREV)", render: (r) => String(r.cargo_type_display) },
          { label: "CBO", render: (r) => String(r.cbo || "—") },
          { label: "Carga horária", render: (r) => (r.weekly_hours ? `${r.weekly_hours}h` : "—") },
        ],
        fields: [
          { name: "name", label: "Cargo", required: true, wide: true },
          { name: "career", label: "Carreira", wide: true },
          { name: "cargo_type", label: "Tipo de cargo (SPREV)", type: "select", required: true, options: TIPO_CARGO, wide: true },
          { name: "cbo", label: "CBO", type: "digits", maxLength: 6 },
          { name: "weekly_hours", label: "Carga horária semanal", type: "number" },
          { name: "education", label: "Escolaridade exigida" },
          { name: "legal_basis", label: "Lei de criação" },
        ],
        defaults: { cargo_type: 7 },
      }}
    />
  );
}
