"use client";

/**
 * Estado de interface compartilhado: menu recolhido, exercício selecionado e
 * filtro de plano (segregação de massas). Preferências guardadas apenas no
 * navegador do usuário, com fallback seguro quando o armazenamento não está
 * disponível.
 */
import { createContext, useContext, useEffect, useMemo, useState } from "react";

/**
 * Filtro de plano/folha. PREVIDENCIARIO = fundo em capitalização consolidado
 * (massa própria + Compra de Vidas); os dois últimos separam as folhas do fundo.
 */
export type PlanFilter = "TODOS" | "FINANCEIRO" | "PREVIDENCIARIO" | "PREVIDENCIARIO_PROPRIO" | "COMPRA_VIDAS";
const PLAN_VALUES: PlanFilter[] = ["TODOS", "FINANCEIRO", "PREVIDENCIARIO", "PREVIDENCIARIO_PROPRIO", "COMPRA_VIDAS"];

type AppState = {
  collapsed: boolean;
  setCollapsed: (v: boolean) => void;
  exercise: number;
  setExercise: (y: number) => void;
  plan: PlanFilter;
  setPlan: (p: PlanFilter) => void;
};

const Ctx = createContext<AppState | null>(null);

function read(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function write(key: string, value: string) {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    /* armazenamento indisponível: mantém apenas em memória */
  }
}

export function AppStateProvider({ children }: { children: React.ReactNode }) {
  const [collapsed, setCollapsedState] = useState(false);
  const [exercise, setExerciseState] = useState<number>(new Date().getFullYear());
  const [plan, setPlanState] = useState<PlanFilter>("TODOS");

  useEffect(() => {
    if (read("sist.sidebar") === "1") setCollapsedState(true);
    const ex = Number(read("sist.exercicio"));
    if (ex >= 1990 && ex <= 2100) setExerciseState(ex);
    const p = read("sist.plano");
    if (PLAN_VALUES.includes(p as PlanFilter)) setPlanState(p as PlanFilter);
  }, []);

  const value = useMemo<AppState>(
    () => ({
      collapsed,
      setCollapsed: (v) => {
        setCollapsedState(v);
        write("sist.sidebar", v ? "1" : "0");
      },
      exercise,
      setExercise: (y) => {
        setExerciseState(y);
        write("sist.exercicio", String(y));
      },
      plan,
      setPlan: (p) => {
        setPlanState(p);
        write("sist.plano", p);
      },
    }),
    [collapsed, exercise, plan],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAppState() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useAppState deve ser usado dentro de AppStateProvider");
  return ctx;
}
