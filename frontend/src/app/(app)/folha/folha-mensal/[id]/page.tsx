"use client";

import { useParams } from "next/navigation";

import { RunDetail } from "@/components/folha/run-detail";

export default function Page() {
  const { id } = useParams<{ id: string }>();
  return <RunDetail id={id} />;
}
