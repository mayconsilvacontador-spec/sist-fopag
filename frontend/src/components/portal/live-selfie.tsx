"use client";

/**
 * Selfie da prova de vida SOMENTE pela câmera ao vivo (sem galeria / sem arquivo).
 *
 * Vivacidade (anti-fraude): o segurado cumpre 2 gestos sorteados; em cada um o navegador registra uma foto e mede o
 * movimento entre elas (diferença média em escala de cinza). Foto ou tela parada diante da câmera não passa. A selfie
 * final é com o documento ao lado do rosto. Não é biometria facial: a conferência do rosto é da equipe do instituto.
 * Exige conexão segura (HTTPS) ou localhost — é o navegador que impõe isso para liberar a câmera.
 */
import { useEffect, useRef, useState } from "react";
import { Camera, Loader2, RefreshCw, VideoOff } from "lucide-react";

import { Button } from "@/components/ui/button";

export type LiveResult = {
  selfie: Blob; frames: Blob[];
  liveness: { desafios: string[]; movimento: number; camera: string; navegador: string };
};
export type CameraProblem = "permissao" | "sem_camera" | "sem_suporte" | "ocupada" | "movimento";

const CHALLENGES = [
  "Vire o rosto devagar para a sua esquerda",
  "Vire o rosto devagar para a sua direita",
  "Aproxime o rosto da câmera",
  "Afaste um pouco o rosto da câmera",
  "Incline a cabeça para cima, olhando para o teto",
];
const FINAL = "Segure o documento ao lado do rosto e olhe para a câmera";
const SECONDS = 3;
const MIN_MOTION = 4;

function shuffle<T>(a: T[]): T[] {
  const r = [...a];
  for (let i = r.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [r[i], r[j]] = [r[j], r[i]];
  }
  return r;
}

function grab(video: HTMLVideoElement): { blob: Promise<Blob>; thumb: Uint8ClampedArray } {
  const c = document.createElement("canvas");
  c.width = video.videoWidth || 640;
  c.height = video.videoHeight || 480;
  const ctx = c.getContext("2d")!;
  ctx.drawImage(video, 0, 0, c.width, c.height);
  const t = document.createElement("canvas");
  t.width = 64;
  t.height = 48;
  const tctx = t.getContext("2d")!;
  tctx.drawImage(video, 0, 0, 64, 48);
  const px = tctx.getImageData(0, 0, 64, 48).data;
  const gray = new Uint8ClampedArray(64 * 48);
  for (let i = 0; i < gray.length; i++) gray[i] = 0.299 * px[i * 4] + 0.587 * px[i * 4 + 1] + 0.114 * px[i * 4 + 2];
  return { blob: new Promise((res) => c.toBlob((b) => res(b!), "image/jpeg", 0.88)), thumb: gray };
}

function diff(a: Uint8ClampedArray, b: Uint8ClampedArray) {
  let s = 0;
  for (let i = 0; i < a.length; i++) s += Math.abs(a[i] - b[i]);
  return s / a.length;
}

export function LiveSelfie({ onDone, onProblem }: { onDone: (r: LiveResult) => void; onProblem: (p: CameraProblem) => void }) {
  const video = useRef<HTMLVideoElement>(null);
  const stream = useRef<MediaStream | null>(null);
  const [phase, setPhase] = useState<"intro" | "abrindo" | "gestos" | "revisao">("intro");
  const [instruction, setInstruction] = useState("");
  const [count, setCount] = useState(0);
  const [preview, setPreview] = useState<string | null>(null);
  const [result, setResult] = useState<LiveResult | null>(null);

  const stop = () => { stream.current?.getTracks().forEach((t) => t.stop()); stream.current = null; };
  useEffect(() => () => { stop(); if (preview) URL.revokeObjectURL(preview); }, [preview]);

  const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));
  const countdown = async (text: string) => {
    setInstruction(text);
    for (let s = SECONDS; s > 0; s--) { setCount(s); await wait(1000); }
    setCount(0);
  };

  const start = async () => {
    if (typeof window === "undefined" || !window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
      onProblem("sem_suporte");
      return;
    }
    setPhase("abrindo");
    try {
      stream.current = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "user", width: { ideal: 960 } }, audio: false });
    } catch (err) {
      const name = (err as DOMException)?.name;
      setPhase("intro");
      onProblem(name === "NotAllowedError" || name === "SecurityError" ? "permissao" : name === "NotReadableError" ? "ocupada" : "sem_camera");
      return;
    }
    setPhase("gestos");
    await wait(50);
    const v = video.current!;
    v.srcObject = stream.current;
    await v.play().catch(() => undefined);
    await wait(900); // câmera estabilizar a exposição
    const steps = [...shuffle(CHALLENGES).slice(0, 2), FINAL];
    const frames: Blob[] = [];
    const thumbs: Uint8ClampedArray[] = [];
    let selfie: Blob | null = null;
    await countdown("Olhe de frente para a câmera");
    const base = grab(v);
    thumbs.push(base.thumb);
    for (const step of steps) {
      await countdown(step);
      const g = grab(v);
      thumbs.push(g.thumb);
      if (step === FINAL) selfie = await g.blob;
      else frames.push(await g.blob);
    }
    frames.unshift(await base.blob);
    let motion = 0;
    for (let i = 1; i < thumbs.length; i++) motion = Math.max(motion, diff(thumbs[i - 1], thumbs[i]));
    const camera = stream.current?.getVideoTracks()[0]?.label ?? "";
    stop();
    if (motion < MIN_MOTION || !selfie) {
      setPhase("intro");
      onProblem("movimento");
      return;
    }
    const r: LiveResult = { selfie, frames, liveness: { desafios: ["Olhe de frente para a câmera", ...steps], movimento: Math.round(motion * 10) / 10, camera, navegador: navigator.userAgent } };
    setResult(r);
    setPreview(URL.createObjectURL(selfie));
    setPhase("revisao");
  };

  if (phase === "revisao" && preview && result) return (
    <div className="space-y-3">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={preview} alt="Sua selfie" className="mx-auto max-h-80 rounded-xl border object-contain" />
      <p className="text-center text-sm text-muted-foreground">Seu rosto e o documento aparecem bem? Se não, tire de novo.</p>
      <div className="flex flex-wrap justify-center gap-2">
        <Button variant="outline" size="lg" onClick={() => { setResult(null); setPreview(null); setPhase("intro"); }}><RefreshCw /> Tirar de novo</Button>
        <Button size="lg" className="text-base" onClick={() => onDone(result)}>Usar esta foto</Button>
      </div>
    </div>
  );

  if (phase === "gestos" || phase === "abrindo") return (
    <div className="space-y-3">
      <div className="relative mx-auto aspect-[3/4] w-full max-w-sm overflow-hidden rounded-2xl bg-black">
        <video ref={video} playsInline muted className="h-full w-full -scale-x-100 object-cover" />
        <div className="pointer-events-none absolute inset-[12%] rounded-[50%] border-4 border-white/80" />
        {phase === "abrindo" && <div className="absolute inset-0 flex items-center justify-center text-white"><Loader2 className="h-8 w-8 animate-spin" /></div>}
        {count > 0 && <div className="absolute right-3 top-3 flex h-12 w-12 items-center justify-center rounded-full bg-black/60 text-2xl font-bold text-white">{count}</div>}
      </div>
      <div className="rounded-xl bg-primary-soft px-4 py-3 text-center text-lg font-semibold text-primary-strong" aria-live="assertive">
        {phase === "abrindo" ? "Abrindo a câmera…" : instruction}
      </div>
      <p className="text-center text-xs text-muted-foreground">Siga as instruções. A câmera tira as fotos sozinha.</p>
    </div>
  );

  return (
    <div className="space-y-3 text-center">
      <div className="mx-auto flex h-24 w-24 items-center justify-center rounded-full bg-primary-soft text-primary"><Camera className="h-12 w-12" /></div>
      <p className="text-sm text-muted-foreground">A câmera vai abrir e pedir alguns gestos simples (como virar o rosto). No final, segure seu documento ao lado do rosto.</p>
      <Button size="lg" className="h-12 w-full max-w-sm text-base" onClick={start}><Camera /> Abrir câmera e tirar selfie</Button>
    </div>
  );
}

const PROBLEM_TEXT: Record<CameraProblem, { title: string; text: string }> = {
  permissao: { title: "A câmera não foi liberada", text: "Quando o aparelho perguntar, toque em “Permitir” para usar a câmera. Se você negou sem querer, libere a câmera nas configurações do navegador e tente de novo." },
  sem_camera: { title: "Não encontramos uma câmera neste aparelho", text: "Use um celular com câmera ou peça atendimento alternativo abaixo." },
  sem_suporte: { title: "Este navegador não libera a câmera", text: "Atualize o navegador (Chrome, Safari ou Edge) ou use outro aparelho. Se não for possível, peça atendimento alternativo." },
  ocupada: { title: "A câmera está sendo usada por outro aplicativo", text: "Feche outros aplicativos que usem a câmera (como videochamadas) e tente de novo." },
  movimento: { title: "Não percebemos os gestos", text: "Faça os movimentos pedidos na tela com calma, em um lugar bem iluminado. Fotos, vídeos ou telas não são aceitos." },
};

export function CameraProblemBox({ problem, onRetry, onAlternative }: { problem: CameraProblem; onRetry: () => void; onAlternative: () => void }) {
  const p = PROBLEM_TEXT[problem];
  return (
    <div className="space-y-3 rounded-xl border-2 border-warning bg-warning-soft p-4">
      <div className="flex items-start gap-3">
        <VideoOff className="mt-0.5 h-6 w-6 shrink-0 text-warning" />
        <div><div className="text-base font-bold">{p.title}</div><p className="text-sm text-foreground/80">{p.text}</p></div>
      </div>
      <div className="flex flex-wrap gap-2">
        <Button size="lg" onClick={onRetry}><RefreshCw /> Tentar de novo</Button>
        <Button size="lg" variant="outline" onClick={onAlternative}>Pedir atendimento</Button>
      </div>
    </div>
  );
}
