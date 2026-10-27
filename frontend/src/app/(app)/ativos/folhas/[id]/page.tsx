"use client";

import { use } from "react";

import { ActiveRunDetailPage } from "@/components/ativos/pages";

export default function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  return <ActiveRunDetailPage id={id} />;
}
