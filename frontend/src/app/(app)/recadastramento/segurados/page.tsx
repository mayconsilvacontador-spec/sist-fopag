import { Suspense } from "react";

import { RecadItemsPage } from "@/components/recadastramento/pages";

export default function Page() {
  return <Suspense><RecadItemsPage kind="segurados" /></Suspense>;
}
