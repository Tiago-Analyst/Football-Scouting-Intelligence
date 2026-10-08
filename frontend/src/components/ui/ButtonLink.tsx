import Link from "next/link";
import type { ComponentProps, ReactNode } from "react";

import { AppLink } from "./AppLink";
import { buttonStyles, type Size, type Variant } from "./Button";

/**
 * A link styled as a button, in its own module on purpose.
 *
 * It renders through `AppLink`, which reads the locale from
 * `next/root-params` and is therefore server-only. While this lived beside
 * `Button`, every Client Component importing a plain `Button` - the error
 * boundary among them - pulled that import in with it, and the build
 * refused: "this API is only available in Server Components".
 *
 * Splitting the file is the whole fix. Navigation is a link, never a button
 * with onClick, and a link in this application always carries its language.
 */
interface ButtonLinkProps extends Omit<ComponentProps<typeof Link>, "children"> {
  variant?: Variant;
  size?: Size;
  children: ReactNode;
}

/**
 * A link styled as a button. Navigation is a link, never a button with onClick.
 *
 * Routed through `AppLink` so an href written as `/players` picks up the
 * current language. See the reasoning there.
 */
export function ButtonLink({ variant, size, className, children, ...rest }: ButtonLinkProps) {
  return (
    <AppLink className={buttonStyles(variant, size, className)} {...rest}>
      {children}
    </AppLink>
  );
}
