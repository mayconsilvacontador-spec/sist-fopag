import type { NextConfig } from "next";

const securityHeaders = [
  // SAMEORIGIN: o próprio sistema pode mostrar PDFs ao lado da tela (leitura inteligente); sites de fora continuam bloqueados
  { key: "X-Frame-Options", value: "SAMEORIGIN" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "same-origin" },
  // Câmera liberada só para o próprio site (prova de vida no Portal); microfone e localização continuam bloqueados
  { key: "Permissions-Policy", value: "camera=(self), microphone=(), geolocation=()" },
];

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
};

export default nextConfig;
