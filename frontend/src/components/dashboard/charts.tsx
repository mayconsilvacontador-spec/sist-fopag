"use client";

import {
  Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";

import { formatCompactCurrency, formatCurrency, formatInt } from "@/lib/format";

/**
 * Paleta validada (scripts de acessibilidade de cor): azul institucional e
 * azul-petróleo, ambos com contraste >= 3:1 sobre o fundo e distinguíveis
 * por daltônicos. Ordem fixa: série 1 = chart-1, série 2 = chart-2.
 */
const C1 = "hsl(var(--chart-1))";
const C2 = "hsl(var(--chart-2))";
const C3 = "hsl(var(--chart-3))"; // 3ª folha (Compra de Vidas)
const GRID = "hsl(var(--border))";
const AXIS = "hsl(var(--muted-foreground))";

const axisProps = {
  tick: { fontSize: 11, fill: AXIS },
  tickLine: false,
  axisLine: { stroke: GRID },
};

function TooltipBox({
  active, payload, label, money,
}: {
  active?: boolean;
  payload?: { name: string; value: number | string; color: string }[];
  label?: string;
  money?: boolean;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-md border bg-popover px-3 py-2 text-xs shadow-md">
      <div className="mb-1 font-semibold">{label}</div>
      {payload.map((p) => (
        <div key={p.name} className="flex items-center gap-2">
          <span className="h-2 w-2 rounded-full" style={{ background: p.color }} />
          <span className="text-muted-foreground">{p.name}</span>
          <span className="ml-auto pl-3 font-semibold tabular">{money ? formatCurrency(p.value) : formatInt(p.value)}</span>
        </div>
      ))}
    </div>
  );
}

const legendStyle = { fontSize: 11, paddingTop: 4 };

export function PayrollEvolutionChart({
  data,
}: {
  data: { rotulo: string; bruta: string; liquida: string; descontos: string }[];
}) {
  const rows = data.map((d) => ({ rotulo: d.rotulo, bruta: Number(d.bruta), liquida: Number(d.liquida) }));
  return (
    <ResponsiveContainer width="100%" height={230}>
      <LineChart data={rows} margin={{ top: 8, right: 12, left: 4, bottom: 0 }}>
        <CartesianGrid vertical={false} stroke={GRID} strokeDasharray="0" />
        <XAxis dataKey="rotulo" {...axisProps} />
        <YAxis {...axisProps} axisLine={false} width={72} tickFormatter={(v) => formatCompactCurrency(v)} />
        <Tooltip content={<TooltipBox money />} cursor={{ stroke: AXIS, strokeDasharray: "3 3" }} />
        <Legend iconType="plainline" wrapperStyle={legendStyle} />
        <Line type="monotone" dataKey="bruta" name="Folha bruta" stroke={C1} strokeWidth={2} dot={false} activeDot={{ r: 4, strokeWidth: 2, stroke: "#fff" }} />
        <Line type="monotone" dataKey="liquida" name="Folha líquida" stroke={C2} strokeWidth={2} dot={false} activeDot={{ r: 4, strokeWidth: 2, stroke: "#fff" }} />
      </LineChart>
    </ResponsiveContainer>
  );
}

export function BeneficiariesChart({
  data,
}: {
  data: { rotulo: string; aposentados: number; pensionistas: number }[];
}) {
  return (
    <ResponsiveContainer width="100%" height={230}>
      <BarChart data={data} margin={{ top: 8, right: 12, left: 4, bottom: 0 }} barCategoryGap="28%">
        <CartesianGrid vertical={false} stroke={GRID} />
        <XAxis dataKey="rotulo" {...axisProps} />
        <YAxis {...axisProps} axisLine={false} width={48} tickFormatter={(v) => formatInt(v)} />
        <Tooltip content={<TooltipBox />} cursor={{ fill: "hsl(var(--muted))" }} />
        <Legend iconType="square" wrapperStyle={legendStyle} />
        <Bar dataKey="aposentados" name="Aposentados" stackId="a" fill={C1} stroke="#fff" strokeWidth={1} />
        <Bar dataKey="pensionistas" name="Pensionistas" stackId="a" fill={C2} stroke="#fff" strokeWidth={1} radius={[3, 3, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

/** Barra de composição (parte/todo) com rótulos diretos — sem gráfico de pizza. */
export function SplitBars({
  items, format = "int",
}: {
  items: { label: string; value: number }[];
  format?: "int" | "currency";
}) {
  const total = items.reduce((s, i) => s + i.value, 0) || 1;
  const colors = [C1, C2, C3];
  return (
    <div className="space-y-3">
      <div className="flex h-3 w-full gap-0.5 overflow-hidden rounded">
        {items.map((it, i) => (
          <div
            key={it.label}
            style={{ width: `${(it.value / total) * 100}%`, background: colors[i % colors.length] }}
            title={`${it.label}: ${format === "currency" ? formatCurrency(it.value) : formatInt(it.value)}`}
          />
        ))}
      </div>
      <ul className="space-y-1.5">
        {items.map((it, i) => (
          <li key={it.label} className="flex items-center gap-2 text-xs">
            <span className="h-2.5 w-2.5 rounded-sm" style={{ background: colors[i % colors.length] }} />
            <span className="text-foreground/80">{it.label}</span>
            <span className="ml-auto font-semibold tabular">
              {format === "currency" ? formatCurrency(it.value) : formatInt(it.value)}
            </span>
            <span className="w-12 text-right text-muted-foreground tabular">
              {((it.value / total) * 100).toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
