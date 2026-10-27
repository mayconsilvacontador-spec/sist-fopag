import type { Metadata } from "next";
import { Toaster } from "sonner";

import "./globals.css";

export const metadata: Metadata = {
  title: { default: "SIST FOPAG · Gestão de RPPS", template: "%s · SIST FOPAG" },
  description: "SIST FOPAG - Sistema Integrado de Gestão de RPPS",
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR">
      <body>
        {children}
        <Toaster position="top-right" richColors closeButton toastOptions={{ className: "text-[13px]" }} />
      </body>
    </html>
  );
}
