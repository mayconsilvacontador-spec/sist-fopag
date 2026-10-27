"use client";

import { useRef, useState } from "react";
import { toast } from "sonner";
import { ImageIcon, Loader2, Trash2, Upload } from "lucide-react";

import { Crest } from "@/components/layout/logo";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";
import { useBranding } from "@/lib/branding";

/**
 * Identidade visual: brasão do município contratante (menu lateral e tela de login) e imagem de fundo das telas,
 * com a intensidade com que aparece. PNG, JPG ou WEBP.
 */
export function BrandingSection({ shortName, intensity, canEdit, onChanged }: {
  shortName: string; intensity: number; canEdit: boolean; onChanged: () => void;
}) {
  const { brasaoUrl, fundoUrl, refresh } = useBranding(shortName);
  const [level, setLevel] = useState(intensity);
  const [saving, setSaving] = useState(false);
  const done = () => { refresh(); onChanged(); };

  return (
    <Card className="self-start xl:col-span-2">
      <CardHeader><CardTitle>Identidade visual</CardTitle></CardHeader>
      <CardContent className="grid gap-6 md:grid-cols-2">
        <ImageSlot kind="brasao" title="Brasão do município" canEdit={canEdit} url={brasaoUrl} onDone={done}
          hint="Aparece no menu lateral e na tela de login. Prefira PNG com fundo transparente, até 2 MB."
          preview={<div className="flex h-28 items-center justify-center rounded-lg border bg-sidebar"><Crest url={brasaoUrl} className="h-20 w-20" /></div>} />
        <div className="space-y-3">
          <ImageSlot kind="fundo" title="Imagem de fundo" canEdit={canEdit} url={fundoUrl} onDone={done}
            hint="Aparece suavizada atrás das telas e no login (ex.: foto da cidade ou da sede). JPG ou PNG, até 6 MB."
            preview={
              <div className="h-28 rounded-lg border bg-cover bg-center"
                style={fundoUrl ? { backgroundImage: `linear-gradient(hsl(var(--background) / ${1 - level / 100}), hsl(var(--background) / ${1 - level / 100})), url("${fundoUrl}")` } : undefined}>
                {!fundoUrl && <div className="flex h-full items-center justify-center text-xs text-muted-foreground"><ImageIcon className="mr-1.5 h-4 w-4" /> Sem imagem</div>}
              </div>
            } />
          {fundoUrl && (
            <div className="space-y-1.5 text-xs">
              <label htmlFor="intensidade" className="font-medium">Intensidade da imagem: {level}%</label>
              <input id="intensidade" type="range" min={5} max={60} step={5} value={level} disabled={!canEdit}
                onChange={(e) => setLevel(Number(e.target.value))} className="w-full accent-[hsl(var(--primary))]" />
              <p className="text-muted-foreground">Quanto menor, mais suave (melhor leitura). Recomendado: 10% a 20%.</p>
              {canEdit && level !== intensity && (
                <Button size="sm" disabled={saving} onClick={async () => {
                  setSaving(true);
                  try {
                    await api("institution/current", { method: "PATCH", body: { background_intensity: level } });
                    toast.success("Intensidade salva.");
                    done();
                  } catch (err) {
                    toast.error((err as Error).message);
                  } finally {
                    setSaving(false);
                  }
                }}>{saving && <Loader2 className="animate-spin" />} Salvar intensidade</Button>
              )}
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

function ImageSlot({ kind, title, hint, url, preview, canEdit, onDone }: {
  kind: "brasao" | "fundo"; title: string; hint: string; url: string | null; preview: React.ReactNode; canEdit: boolean; onDone: () => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const send = async (file: File) => {
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const res = await fetch(`/api/backend/institution/current/branding/${kind}`, { method: "POST", body: fd, credentials: "same-origin" });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.detail || "Falha ao enviar a imagem.");
      toast.success(`${title} atualizado.`);
      onDone();
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setBusy(false);
      if (input.current) input.current.value = "";
    }
  };
  const remove = async () => {
    try {
      await api(`institution/current/branding/${kind}`, { method: "DELETE" });
      toast.success(`${title} removido.`);
      onDone();
    } catch (err) {
      toast.error((err as Error).message);
    }
  };
  return (
    <div className="space-y-2">
      <div className="text-[13px] font-semibold text-primary-strong">{title}</div>
      {preview}
      <p className="text-xs text-muted-foreground">{hint}</p>
      {canEdit && (
        <div className="flex gap-2">
          <input ref={input} type="file" accept="image/png,image/jpeg,image/webp" className="hidden"
            onChange={(e) => e.target.files?.[0] && send(e.target.files[0])} />
          <Button size="sm" variant="outline" disabled={busy} onClick={() => input.current?.click()}>
            {busy ? <Loader2 className="animate-spin" /> : <Upload />} {url ? "Trocar" : "Enviar imagem"}
          </Button>
          {url && <Button size="sm" variant="ghost" onClick={remove}><Trash2 /> Remover</Button>}
        </div>
      )}
    </div>
  );
}
