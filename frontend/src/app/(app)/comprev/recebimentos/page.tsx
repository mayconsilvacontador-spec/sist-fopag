import { Suspense } from "react";

import { ComprevMovementsPage } from "@/components/comprev/pages";

export default function Page() {
  return <Suspense><ComprevMovementsPage direction="RECEBER" /></Suspense>;
}
