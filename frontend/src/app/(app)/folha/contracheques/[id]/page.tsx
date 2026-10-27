"use client";

import { useParams } from "next/navigation";
import useSWR from "swr";
import { Printer } from "lucide-react";

import { PayslipView } from "@/components/folha/payslip";
import { ErrorState } from "@/components/shared/data-states";
import { RequirePermission } from "@/components/shared/require-permission";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { fetcher } from "@/lib/api";
import type { Payslip } from "@/lib/types";

export default function Page() {
  const { id } = useParams<{ id: string }>();
  const { data, error } = useSWR<Payslip>(`folha/contracheques/${id}`, fetcher);
  return (
    <RequirePermission module="folha.contracheques">
      <div className="mb-3 flex justify-end print:hidden"><Button variant="outline" onClick={() => window.print()} disabled={!data}><Printer /> Imprimir</Button></div>
      {error && <ErrorState error={error} />}
      {data && <Card className="mx-auto max-w-3xl p-6 print:border-0 print:p-0 print:shadow-none"><PayslipView p={data} /></Card>}
    </RequirePermission>
  );
}