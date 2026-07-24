import type { ElementType, HTMLAttributes, ReactNode } from "react";
import { cn } from "@/lib/cn";

interface EyebrowProps extends HTMLAttributes<HTMLElement> {
  children: ReactNode;
  /** Render element (default span). Use "h2"/"p" when the eyebrow is semantic. */
  as?: ElementType;
  className?: string;
}

/**
 * Uppercase, letter-spaced micro-label used above section titles.
 * Mono face + wide tracking per the design system's "section eyebrow" spec.
 */
export function Eyebrow({
  children,
  as,
  className,
  ...rest
}: EyebrowProps) {
  const Tag = (as ?? "span") as ElementType;
  return (
    <Tag className={cn("eyebrow", className)} {...rest}>
      {children}
    </Tag>
  );
}

export default Eyebrow;
