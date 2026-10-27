"use client";

import { FichaImport, RubricClassification } from "@/components/ativos/ficha";
import { PageHeader } from "@/components/shared/page-header";
import { RequirePermission } from "@/components/shared/require-permission";
import { Card, CardContent } from "@/components/ui/card";
import { useSWRConfig } from "swr";

export default function FichaFinanceiraPage() {
  const { mutate } = useSWRConfig();
  return (
    <RequirePermission module="ativos.ficha_financeira">
      <PageHeader title="Ficha financeira" description="Importe as fichas financeiras de todos os servidores (sistema anterior) e diga qual rubrica é a contribuição ao RPPS."
        breadcrumb={[{ label: "Folha de Ativos" }, { label: "Ficha financeira" }]} />
      <Card className="mb-4">
        <CardContent className="p-4">
          <FichaImport onDone={() => mutate((k) => typeof k === "string" && k.startsWith("ativos/ficha-financeira/rubricas"))} />
          <p className="mt-2 text-xs text-muted-foreground">
            A ficha de cada servidor aparece na Pasta do Servidor › Remuneração, junto com o controle da contribuição
            (quanto foi descontado, quanto deveria ser e se o órgão repassou ao RPPS).
          </p>
        </CardContent>
      </Card>
      <Card>
        <CardContent className="p-4">
          <h2 className="mb-1 text-sm font-bold text-primary-strong">Classificação das rubricas importadas</h2>
          <p className="mb-3 text-xs text-muted-foreground">
            Cada sistema usa códigos próprios. Marque qual rubrica é o desconto previdenciário do servidor e qual é a base —
            é isso que alimenta o controle da contribuição. A sugestão automática é feita pelo nome e deve ser conferida.
          </p>
          <RubricClassification />
        </CardContent>
      </Card>
    </RequirePermission>
  );
}
