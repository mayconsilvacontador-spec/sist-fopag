"use client";

import { useEffect, useState } from "react";
import useSWR from "swr";
import { Search, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { fetcher, qs, type Paginated } from "@/lib/api";
import { formatCurrency } from "@/lib/format";
import type { BenefitRow } from "@/lib/types";

/** Busca um benefício implantado (ativo ou suspenso) por beneficiário, CPF ou matrícula. */
export function BenefitPicker({ value, onChange }: { value: BenefitRow | null; onChange: (b: BenefitRow | null) => void }) {
  const [term, setTerm] = useState("");
  const [debounced, setDebounced] = useState("");
  useEffect(() => {
    const t = setTimeout(() => setDebounced(term), 300);
    return () => clearTimeout(t);
  }, [term]);
  const { data } = useSWR<Paginated<BenefitRow>>(
    debounced.length >= 3 ? `beneficios${qs({ search: debounced, page_size: 8 })}` : null, fetcher);

  if (value) {
    return (
      <div className="flex items-center justify-between rounded-md border bg-muted/40 px-3 py-2 text-xs">
        <div>
          <div className="font-medium">{value.beneficiary_name}</div>
          <div className="text-muted-foreground">{value.kind_display} · {value.folha} · {formatCurrency(value.amount)} · {value.status_display}</div>
        </div>
        <Button type="button" variant="ghost" size="icon" className="h-7 w-7" onClick={() => onChange(null)} aria-label="Trocar"><X /></Button>
      </div>
    );
  }
  return (
    <div>
      <div className="relative">
        <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input value={term} onChange={(e) => setTerm(e.target.value)} placeholder="Beneficiário, CPF ou matrícula (mín. 3 letras)" className="pl-8" />
      </div>
      {data && (
        <ul className="mt-1 max-h-56 overflow-auto rounded-md border text-xs">
          {data.results.map((b) => (
            <li key={b.id}>
              <button type="button" className="w-full px-3 py-1.5 text-left hover:bg-muted" onClick={() => onChange(b)}>
                <span className="font-medium">{b.beneficiary_name}</span>{" "}
                <span className="text-muted-foreground">— {b.kind_display} · {b.folha} · {formatCurrency(b.amount)} · {b.status_display}</span>
              </button>
            </li>
          ))}
          {data.results.length === 0 && <li className="px-3 py-1.5 text-muted-foreground">Nenhum benefício encontrado.</li>}
        </ul>
      )}
    </div>
  );
}
