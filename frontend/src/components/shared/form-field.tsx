import { Label } from "@/components/ui/input";
import { cn } from "@/lib/utils";

import { FieldError } from "./data-states";

export function FormField({
  label, htmlFor, error, required, hint, className, children,
}: {
  label: string;
  htmlFor?: string;
  error?: string;
  required?: boolean;
  hint?: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div className={cn("space-y-1", className)}>
      <Label htmlFor={htmlFor}>
        {label}
        {required && <span className="ml-0.5 text-destructive">*</span>}
      </Label>
      {children}
      {hint && !error && <p className="text-2xs text-muted-foreground">{hint}</p>}
      <FieldError message={error} />
    </div>
  );
}
