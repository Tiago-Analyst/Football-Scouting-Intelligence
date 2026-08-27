import Link from "next/link";
import type { ComponentProps, ReactNode } from "react";

import { cn } from "@/lib/cn";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md" | "lg";

const VARIANTS: Record<Variant, string> = {
  primary: "bg-accent text-accent-fg hover:bg-accent-hover border-transparent",
  secondary: "bg-surface text-text border-border hover:bg-surface-2 hover:border-border-strong",
  ghost: "bg-transparent text-muted border-transparent hover:bg-surface-2 hover:text-text",
  danger: "bg-transparent text-danger border-danger/40 hover:bg-danger/10",
};

const SIZES: Record<Size, string> = {
  sm: "h-8 px-3 text-xs gap-1.5",
  md: "h-9.5 px-4 text-sm gap-2",
  lg: "h-11 px-5 text-sm gap-2",
};

const BASE =
  "inline-flex items-center justify-center rounded-md border font-medium " +
  "transition-colors disabled:pointer-events-none disabled:opacity-50 " +
  "whitespace-nowrap select-none";

export function buttonStyles(variant: Variant = "primary", size: Size = "md", className?: string) {
  return cn(BASE, VARIANTS[variant], SIZES[size], className);
}

interface ButtonProps extends Omit<ComponentProps<"button">, "children"> {
  variant?: Variant;
  size?: Size;
  children: ReactNode;
}

export function Button({ variant, size, className, children, ...rest }: ButtonProps) {
  return (
    <button className={buttonStyles(variant, size, className)} {...rest}>
      {children}
    </button>
  );
}

interface ButtonLinkProps extends Omit<ComponentProps<typeof Link>, "children"> {
  variant?: Variant;
  size?: Size;
  children: ReactNode;
}

/** A link styled as a button. Navigation is a link, never a button with onClick. */
export function ButtonLink({ variant, size, className, children, ...rest }: ButtonLinkProps) {
  return (
    <Link className={buttonStyles(variant, size, className)} {...rest}>
      {children}
    </Link>
  );
}
