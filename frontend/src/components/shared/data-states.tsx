import { AlertCircle, Inbox } from "lucide-react";

import { Skeleton } from "@/components/ui/skeleton";
import { TableCell, TableRow } from "@/components/ui/table";
import { ApiError } from "@/lib/api";

export function LoadingRows({ cols, rows = 5 }: { cols: number; rows?: number }) {
  return (
    <>
      {Array.from({ length: rows }).map((_, r) => (
        <TableRow key={r}>
          {Array.from({ length: cols }).map((__, c) => (
            <TableCell key={c}>
              <Skeleton className="h-3.5 w-full max-w-[160px]" />
            </TableCell>
          ))}
        </TableRow>
      ))}
    </>
  );
}

export function EmptyRow({ cols, text = "Nenhum registro encontrado." }: { cols: number; text?: string }) {
  return (
    <TableRow className="hover:bg-transparent">
      <TableCell colSpan={cols} className="py-10 text-center text-xs text-muted-foreground">
        <Inbox className="mx-auto mb-1.5 h-5 w-5 opacity-60" />
        {text}
      </TableCell>
    </TableRow>
  );
}

export function ErrorState({ error }: { error: unknown }) {
  const msg =
    error instanceof ApiError
      ? error.status === 403
        ? "Você não possui permissão para acessar estas informações."
        : error.message
      : "Não foi possível carregar os dados.";
  return (
    <div className="flex items-center gap-2 rounded-md border border-critical-border bg-critical-soft px-3 py-2.5 text-xs text-critical">
      <AlertCircle className="h-4 w-4 shrink-0" /> {msg}
    </div>
  );
}

export function FieldError({ message }: { message?: string }) {
  if (!message) return null;
  return <p className="mt-1 text-2xs text-destructive">{message}</p>;
}
