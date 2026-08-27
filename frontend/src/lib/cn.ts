import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * Compose class names, with later Tailwind utilities beating earlier ones.
 *
 * Without the merge step a caller's `className` cannot override a component's
 * own defaults - `px-3` and `px-4` would both survive and the winner would
 * depend on stylesheet order.
 */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
