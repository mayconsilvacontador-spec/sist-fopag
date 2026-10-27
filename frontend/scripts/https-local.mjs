/**
 * Acesso seguro (HTTPS) de TESTE pela rede Wi-Fi local — para abrir o sistema/Portal no celular.
 *
 * O celular só libera a câmera em endereço https. Este script atende em https://<IP-do-computador>:3443 com um
 * certificado autoassinado (frontend/certs/*.pem) e repassa tudo para o Next.js em http://127.0.0.1:3000.
 * O celular vai mostrar "conexão não particular": é esperado (certificado de teste) — toque em Avançado › Continuar.
 *
 * NÃO é para produção: em produção o servidor terá certificado válido (ex.: Let's Encrypt) e domínio próprio.
 * Uso: node scripts/https-local.mjs   (com o "frontend" já rodando na porta 3000)
 */
import { readFileSync } from "node:fs";
import http from "node:http";
import https from "node:https";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const PORT = Number(process.env.HTTPS_PORT || 3443);
const TARGET = { host: "127.0.0.1", port: Number(process.env.TARGET_PORT || 3000) };

const server = https.createServer(
  { key: readFileSync(join(here, "..", "certs", "sist-key.pem")), cert: readFileSync(join(here, "..", "certs", "sist-cert.pem")) },
  (req, res) => {
    const upstream = http.request(
      { ...TARGET, method: req.method, path: req.url, headers: { ...req.headers, "x-forwarded-proto": "https" } },
      (up) => {
        res.writeHead(up.statusCode || 502, up.headers);
        up.pipe(res);
      },
    );
    upstream.on("error", () => {
      if (!res.headersSent) res.writeHead(502, { "content-type": "text/plain; charset=utf-8" });
      res.end("SIST FOPAG: o sistema (porta 3000) não está rodando neste computador.");
    });
    req.pipe(upstream);
  },
);

server.listen(PORT, "0.0.0.0", () => {
  console.log(`Acesso seguro de teste em https://<IP-deste-computador>:${PORT} (repassando para a porta ${TARGET.port})`);
});
