"use client";

import useSWR from "swr";

/** Identidade visual da instituição (brasão e imagem de fundo), pública — funciona também no login. */
export type Branding = {
  short_name: string; name: string; city?: string; uf?: string;
  brasao: boolean; fundo: boolean; intensidade?: number; versao?: number;
};

const publicFetcher = (url: string) => fetch(url).then((r) => (r.ok ? r.json() : null));

export function useBranding(inst?: string) {
  const q = inst ? `?inst=${encodeURIComponent(inst)}` : "";
  const { data, mutate } = useSWR<Branding | null>(`/api/branding${q}`, publicFetcher, { revalidateOnFocus: false });
  const v = data?.versao ?? 0;
  const sep = q ? "&" : "?";
  return {
    branding: data ?? null,
    brasaoUrl: data?.brasao ? `/api/branding/brasao${q}${sep}v=${v}` : null,
    fundoUrl: data?.fundo ? `/api/branding/fundo${q}${sep}v=${v}` : null,
    refresh: mutate,
  };
}
