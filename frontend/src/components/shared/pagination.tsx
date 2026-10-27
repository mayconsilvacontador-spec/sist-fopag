import { ChevronLeft, ChevronRight } from "lucide-react";

import { Button } from "@/components/ui/button";
import { formatInt } from "@/lib/format";

export function Pagination({
  page,
  numPages,
  count,
  onChange,
}: {
  page: number;
  numPages: number;
  count: number;
  onChange: (page: number) => void;
}) {
  return (
    <div className="flex items-center justify-between border-t px-3 py-2 text-xs text-muted-foreground">
      <span>{formatInt(count)} registro(s)</span>
      <div className="flex items-center gap-2">
        <span>
          Página {page} de {Math.max(numPages, 1)}
        </span>
        <Button variant="outline" size="icon" className="h-7 w-7" disabled={page <= 1} onClick={() => onChange(page - 1)} aria-label="Página anterior">
          <ChevronLeft />
        </Button>
        <Button variant="outline" size="icon" className="h-7 w-7" disabled={page >= numPages} onClick={() => onChange(page + 1)} aria-label="Próxima página">
          <ChevronRight />
        </Button>
      </div>
    </div>
  );
}
