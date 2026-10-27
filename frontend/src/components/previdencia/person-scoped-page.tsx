"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import { PersonPicker } from "@/components/people/person-picker";
import { PageHeader } from "@/components/shared/page-header";
import { RequirePermission } from "@/components/shared/require-permission";
import { Card, CardContent } from "@/components/ui/card";
import { api } from "@/lib/api";
import type { PersonRow } from "@/lib/types";

/** Página da Gestão Previdenciária: escolhe o segurado (ou recebe ?pessoa=<id>) e mostra o painel. */
export function PersonScopedPage({
  module, title, description, children,
}: {
  module: string;
  title: string;
  description: string;
  children: (personId: string) => React.ReactNode;
}) {
  return (
    <RequirePermission module={module}>
      <Inner title={title} description={description}>{children}</Inner>
    </RequirePermission>
  );
}

function Inner({ title, description, children }: { title: string; description: string; children: (id: string) => React.ReactNode }) {
  const [person, setPerson] = useState<PersonRow | null>(null);

  useEffect(() => {
    const id = new URLSearchParams(window.location.search).get("pessoa");
    if (id) api<PersonRow>(`people/${id}`).then(setPerson).catch(() => undefined);
  }, []);

  return (
    <>
      <PageHeader title={title} description={description} breadcrumb={[{ label: "Gestão Previdenciária" }, { label: title }]} />
      <Card>
        <CardContent className="space-y-4 p-4">
          <div className="max-w-xl">
            <PersonPicker value={person} onChange={setPerson} />
            {person && (
              <Link href={`/cadastros/pessoas/${person.id}`} className="mt-1 inline-block text-2xs text-primary hover:underline">
                Abrir cadastro completo
              </Link>
            )}
          </div>
          {person ? children(person.id) : (
            <p className="py-8 text-center text-xs text-muted-foreground">Escolha o segurado para começar.</p>
          )}
        </CardContent>
      </Card>
    </>
  );
}
