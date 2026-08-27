import type { ComponentProps, ReactNode } from "react";

import { cn } from "@/lib/cn";

const CONTROL =
  "h-9 w-full rounded-md border border-border bg-surface px-2.5 text-sm text-text " +
  "placeholder:text-subtle transition-colors hover:border-border-strong " +
  "disabled:cursor-not-allowed disabled:opacity-50";

export function Field({
  label,
  hint,
  htmlFor,
  children,
  className,
}: {
  label: ReactNode;
  hint?: ReactNode;
  htmlFor?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("space-y-1.5", className)}>
      <label
        htmlFor={htmlFor}
        className="flex items-center gap-1.5 text-xs font-medium text-muted"
      >
        {label}
      </label>
      {children}
      {hint ? <p className="text-[11px] text-subtle">{hint}</p> : null}
    </div>
  );
}

export function TextInput({ className, ...rest }: ComponentProps<"input">) {
  return <input className={cn(CONTROL, className)} {...rest} />;
}

export function Select({ className, children, ...rest }: ComponentProps<"select">) {
  return (
    <select className={cn(CONTROL, "cursor-pointer pr-8", className)} {...rest}>
      {children}
    </select>
  );
}

/**
 * Paired min/max inputs.
 *
 * Age, market value, minutes and contract length are all range filters, and a
 * single component keeps their labelling and spacing identical across the app.
 */
export function NumberRange({
  name,
  minPlaceholder = "Min",
  maxPlaceholder = "Max",
  unit,
  ...rest
}: {
  name: string;
  minPlaceholder?: string;
  maxPlaceholder?: string;
  unit?: string;
} & Pick<ComponentProps<"input">, "min" | "max" | "step" | "disabled">) {
  return (
    <div className="flex items-center gap-2">
      <TextInput
        type="number"
        inputMode="numeric"
        name={`${name}_min`}
        aria-label={`${name} minimum`}
        placeholder={minPlaceholder}
        className="tabular"
        {...rest}
      />
      <span aria-hidden className="text-xs text-subtle">
        –
      </span>
      <TextInput
        type="number"
        inputMode="numeric"
        name={`${name}_max`}
        aria-label={`${name} maximum`}
        placeholder={maxPlaceholder}
        className="tabular"
        {...rest}
      />
      {unit ? <span className="shrink-0 text-xs text-subtle">{unit}</span> : null}
    </div>
  );
}
