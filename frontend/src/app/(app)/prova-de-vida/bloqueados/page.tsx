import { Suspense } from "react";

import { ProofsPage } from "@/components/provadevida/pages";

export default function Page() {
  return <Suspense><ProofsPage kind="bloqueados" /></Suspense>;
}
