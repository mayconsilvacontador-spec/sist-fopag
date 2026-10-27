"use client";

import { useEffect, useState } from "react";
import useSWR from "swr";
import { Search, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { fetcher, qs, type Paginated } from "@/lib/api";
import type { PersonRow } from "@/lib/types";

/** Busca uma pessoa do Cadastro Único por nome, CPF ou matrícula. */
export function PersonPicker({
  value, onChange, tipo,
}: {
  value: PersonRow | null;
  onChange: (p: PersonRow | null) => void;
  tipo?: string;
}) {
  const [term, setTerm] = useState("");
  const [debounced, setDebounced] = useState("");
  useEffect(() => {
    const t = setTimeout(() => setDebounced(term), 300);
    return () => clearTimeout(t);
  }, [term]);
  const { data } = useSWR<Paginated<PersonRow>>(
    debounced.length >= 3 ? `people${qs({ search: debounced, tipo, page_size: 8 })}` : null, fetcher,
  );

  if (value) {
    return (
      <div className="flex items-center gap-3 rounded-md border bg-muted/40 px-3 py-2">
        <div className="min-w-0 flex-1">
          <div className="font-medium">{value.name || "Nome não informado"}</div>
          <div className="text-2xs text-muted-foreground">CPF {value.cpf_formatado} · {value.idade} anos{value.situacao ? ` · ${value.situacao}` : ""}</div>
        </div>
        <Button size="sm" variant="ghost" onClick={() => onChange(null)}><X /> Trocar</Button>
      </div>
    );
  }
  return (
    <div className="relative">
      <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
      <Input value={term} onChange={(e) => setTerm(e.target.value)} placeholder="Digite nome, CPF ou matrícula (mín. 3 caracteres)" className="pl-8" autoFocus />
      {data && debounced.length >= 3 && (
        <ul className="absolute z-20 mt-1 max-h-72 w-full overflow-auto rounded-md border bg-popover shadow-md">
          {data.results.map((p) => (
            <li key={p.id}>
              <button type="button" className="w-full px-3 py-2 text-left text-xs hover:bg-muted" onClick={() => { onChange(p); setTerm(""); }}>
                <div className="font-medium">{p.name || "Nome não informado"}</div>
                <div className="text-2xs text-muted-foreground">CPF {p.cpf_formatado}{p.situacao ? ` · ${p.situacao}` : ""}</div>
              </button>
            </li>
          ))}
          {data.results.length === 0 && <li className="px-3 py-2 text-xs text-muted-foreground">Nenhuma pessoa encontrada.</li>}
        </ul>
      )}
    </div>
  );
}
