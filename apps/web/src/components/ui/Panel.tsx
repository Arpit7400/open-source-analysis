"use client";

import { type ReactNode } from "react";
import { motion, type HTMLMotionProps } from "framer-motion";
import { cn } from "@/lib/cn";
import { Eyebrow } from "./Eyebrow";

type PanelProps = {
  children: ReactNode;
  /** Section title rendered as a heading. */
  title?: ReactNode;
  /** Uppercase micro-label above the title. */
  eyebrow?: ReactNode;
  /** Right-aligned header content (actions, badges, live indicators). */
  actions?: ReactNode;
  /** Remove inner padding on the body (for edge-to-edge content like graphs). */
  flush?: boolean;
  /** Stagger index — multiplies the entrance delay so siblings cascade. */
  index?: number;
  /** Add an active cyan inner glow. */
  active?: boolean;
  className?: string;
  bodyClassName?: string;
  headerClassName?: string;
} & Omit<HTMLMotionProps<"section">, "title" | "children">;

/**
 * The core glass surface. Enters with a staggered fade+rise spring and lays
 * out an optional header (eyebrow + title + actions) over a body region.
 * `index` cascades the entrance so a column of panels resolves top-to-bottom.
 */
export function Panel({
  children,
  title,
  eyebrow,
  actions,
  flush = false,
  index = 0,
  active = false,
  className,
  bodyClassName,
  headerClassName,
  ...rest
}: PanelProps) {
  const hasHeader = Boolean(title || eyebrow || actions);

  return (
    <motion.section
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{
        type: "spring",
        stiffness: 220,
        damping: 26,
        mass: 0.7,
        delay: Math.min(index, 12) * 0.04,
      }}
      className={cn(
        "glass relative flex min-h-0 flex-col overflow-hidden",
        active && "glow-cyan",
        className,
      )}
      {...rest}
    >
      {hasHeader ? (
        <header
          className={cn(
            "flex items-start justify-between gap-3 px-4 pt-3.5 pb-3 hairline-b",
            headerClassName,
          )}
        >
          <div className="flex min-w-0 flex-col gap-1.5">
            {eyebrow ? <Eyebrow>{eyebrow}</Eyebrow> : null}
            {title ? (
              <h2 className="truncate text-sm font-semibold text-[color:var(--text-primary)]">
                {title}
              </h2>
            ) : null}
          </div>
          {actions ? (
            <div className="flex shrink-0 items-center gap-2">{actions}</div>
          ) : null}
        </header>
      ) : null}

      <div
        className={cn(
          "flex min-h-0 flex-1 flex-col",
          !flush && "p-4",
          bodyClassName,
        )}
      >
        {children}
      </div>
    </motion.section>
  );
}

export default Panel;
