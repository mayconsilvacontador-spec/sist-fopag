"use client";

import { useState } from "react";
import { Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog, DialogBody, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Label, Textarea } from "@/components/ui/input";

type Props = {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  title: string;
  description?: React.ReactNode;
  confirmLabel?: string;
  destructive?: boolean;
  /** Exige justificativa (mín. 10 caracteres) — usada em reaberturas e alterações sensíveis */
  requireJustification?: boolean;
  onConfirm: (justification: string) => Promise<void> | void;
};

export function ConfirmDialog({
  open, onOpenChange, title, description, confirmLabel = "Confirmar", destructive,
  requireJustification, onConfirm,
}: Props) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const invalid = requireJustification && text.trim().length < 10;

  const submit = async () => {
    setBusy(true);
    try {
      await onConfirm(text.trim());
      setText("");
      onOpenChange(false);
    } catch {
      /* o chamador já exibiu a mensagem de erro; o diálogo permanece aberto */
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(v) => !busy && onOpenChange(v)}>
      <DialogContent size="sm">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          {description && <DialogDescription asChild><div>{description}</div></DialogDescription>}
        </DialogHeader>
        {requireJustification && (
          <DialogBody>
            <Label htmlFor="justificativa">Justificativa (obrigatória, registrada na auditoria)</Label>
            <Textarea
              id="justificativa"
              className="mt-1"
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Descreva o motivo (mínimo de 10 caracteres)"
              autoFocus
            />
          </DialogBody>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Cancelar</Button>
          <Button variant={destructive ? "destructive" : "default"} onClick={submit} disabled={busy || invalid}>
            {busy && <Loader2 className="animate-spin" />} {confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
