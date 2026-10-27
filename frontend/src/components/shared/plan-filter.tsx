"use client";

import { useEffect } from "react";

import { useAppState, type PlanFilter as Plan } from "@/components/providers/app-state";
import { useSession } from "@/components/providers/session-provider";
import { cn } from "@/lib/utils";

const MAIN: { value: Plan; label: string }[] = [
  { value: "TODOS", label: "Todos" },
  { value: "FINANCEIRO", label: "Financeiro" },
  { value: "PREVIDENCIARIO", label: "Previdenciário" },
];

// Folhas do fundo em capitalização (só com Compra de Vidas)
const PREV_SUB: { value: Plan; label: string }[] = [
  { value: "PREVIDENCIARIO", label: "Consolidado" },
  { value: "PREVIDENCIARIO_PROPRIO", label: "Massa própria" },
  { value: "COMPRA_VIDAS", label: "Compra de Vidas" },
];
const PREV_FAMILY: Plan[] = ["PREVIDENCIARIO", "PREVIDENCIARIO_PROPRIO", "COMPRA_VIDAS"];

/** Filtro de segregação de massas, compartilhado entre as telas. */
export function PlanFilter({ className }: { className?: string }) {
  const { plan, setPlan } = useAppState();
  const { me } = useSession();
  const hasLifePurchase = !!me?.institution?.life_purchase_enabled;
  const inPrev = PREV_FAMILY.includes(plan);

  // Instituição sem Compra de Vidas: as subdivisões não existem
  useEffect(() => {
    if (me && !hasLifePurchase && (plan === "PREVIDENCIARIO_PROPRIO" || plan === "COMPRA_VIDAS")) setPlan("PREVIDENCIARIO");
  }, [me, hasLifePurchase, plan, setPlan]);

  return (
    <div className={cn("inline-flex flex-wrap items-center gap-2", className)}>
      <span className="section-label">Plano</span>
      <Segmented
        label="Plano"
        options={MAIN}
        isActive={(v) => (v === "PREVIDENCIARIO" ? inPrev : plan === v)}
        onSelect={(v) => setPlan(v === "PREVIDENCIARIO" && inPrev ? plan : v)}
      />
      {hasLifePurchase && inPrev && (
        <Segmented label="Folha do Plano Previdenciário" options={PREV_SUB} isActive={(v) => plan === v} onSelect={setPlan} subtle />
      )}
    </div>
  );
}

function Segmented({
  label, options, isActive, onSelect, subtle,
}: {
  label: string;
  options: { value: Plan; label: string }[];
  isActive: (v: Plan) => boolean;
  onSelect: (v: Plan) => void;
  subtle?: boolean;
}) {
  return (
    <div className="inline-flex rounded-md border bg-card p-0.5" role="radiogroup" aria-label={label}>
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={isActive(o.value)}
          onClick={() => onSelect(o.value)}
          className={cn(
            "rounded px-2.5 py-1 text-xs font-medium transition-colors",
            isActive(o.value)
              ? subtle ? "bg-primary-soft text-primary" : "bg-primary text-primary-foreground"
              : "text-muted-foreground hover:text-foreground",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
