"use client";

import Link from "next/link";

import { TabTitle } from "@/components/layout/page-tabs";
import { cn } from "@/lib/utils";

type Crumb = { label: string; href?: string };

/** Cabeçalho das telas: caminho discreto, título grande, descrição e ações à direita. */
export function PageHeader({
  title,
  description,
  breadcrumb = [],
  actions,
  className,
}: {
  title: string;
  description?: React.ReactNode;
  breadcrumb?: Crumb[];
  actions?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("mb-5 flex flex-wrap items-end justify-between gap-3", className)}>
      <TabTitle title={title} />
      <div className="min-w-0">
        {breadcrumb.length > 0 && (
          <nav className="mb-1 flex flex-wrap items-center gap-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground" aria-label="Navegação">
            {breadcrumb.map((c, i) => (
              <span key={`${c.label}-${i}`} className="flex items-center gap-1">
                {i > 0 && <span aria-hidden="true">·</span>}
                {c.href ? <Link href={c.href} className="hover:text-primary hover:underline">{c.label}</Link> : <span>{c.label}</span>}
              </span>
            ))}
          </nav>
        )}
        <h1 className="text-[26px] font-bold leading-tight tracking-tight text-primary-strong">{title}</h1>
        {description && <p className="mt-0.5 text-[14px] text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}
