import path from "node:path";
import { fileURLToPath } from "node:url";

// Caminho explícito: o Tailwind procura o config a partir do diretório de execução,
// o que falha quando o Next é iniciado fora da pasta frontend.
const tailwindConfig = path.join(path.dirname(fileURLToPath(import.meta.url)), "tailwind.config.ts");

const config = {
  plugins: {
    tailwindcss: { config: tailwindConfig },
    autoprefixer: {},
  },
};

export default config;
