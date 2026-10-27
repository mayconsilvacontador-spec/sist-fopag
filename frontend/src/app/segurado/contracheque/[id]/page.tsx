"use client";

import { useParams } from "next/navigation";

import { PortalPayslip } from "@/components/portal/segurado";

export default function Page() {
  const { id } = useParams<{ id: string }>();
  return <PortalPayslip id={id} />;
}
