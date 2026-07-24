import type { HTMLAttributes, ReactNode } from "react";
import { cn } from "@/lib/cn";

/**
 * Tones map to the accent ramps in DESIGN_SYSTEM.md. The semantic aliases
 * (running/completed/…) line up with the AgentState / Severity color mapping
 * so callers can pass a state directly without re-deriving a color.
 */
export type BadgeTone =
  | "neutral"
  | "cyan"
  | "violet"
  | "amber"
  | "emerald"
  | "rose"
  | "blue"
  // agent-state aliases
  | "waiting"
  | "running"
  | "completed"
  | "verifying"
  | "blocked"
  | "failed"
  | "rejected"
  // severity aliases
  | "info"
  | "low"
  | "medium"
  | "high"
  | "critical";

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  children: ReactNode;
  tone?: BadgeTone;
  /** A small leading dot for at-a-glance status reading. */
  dot?: boolean;
  className?: string;
}

/**
 * Each tone renders as a tinted-glass chip: a low-alpha fill, a matching
 * hairline border, and full-strength text. Colors are inline (from CSS custom
 * properties) so they stay in lockstep with the token file.
 */
const TONE_COLOR: Record<BadgeTone, string> = {
  neutral: "var(--text-secondary)",
  cyan: "var(--accent-cyan)",
  violet: "var(--accent-violet)",
  amber: "var(--accent-amber)",
  emerald: "var(--accent-emerald)",
  rose: "var(--accent-rose)",
  blue: "var(--accent-blue)",

  waiting: "var(--text-muted)",
  running: "var(--accent-cyan)",
  completed: "var(--accent-emerald)",
  verifying: "var(--accent-violet)",
  blocked: "var(--accent-amber)",
  failed: "var(--accent-rose)",
  rejected: "var(--text-muted)",

  info: "var(--accent-blue)",
  low: "var(--accent-cyan)",
  medium: "var(--accent-amber)",
  high: "var(--accent-rose)",
  critical: "var(--accent-rose)",
};

export function Badge({
  children,
  tone = "neutral",
  dot = false,
  className,
  style,
  ...rest
}: BadgeProps) {
  const color = TONE_COLOR[tone];
  const strikethrough = tone === "rejected";

  return (
    <span
      className={cn(
        "mono inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-0.5 text-[0.6875rem] font-semibold leading-none",
        strikethrough && "line-through decoration-1",
        className,
      )}
      style={{
        color,
        backgroundColor: `color-mix(in srgb, ${color} 14%, transparent)`,
        border: `1px solid color-mix(in srgb, ${color} 32%, transparent)`,
        ...style,
      }}
      {...rest}
    >
      {dot ? (
        <span
          aria-hidden="true"
          className="h-1.5 w-1.5 shrink-0 rounded-full"
          style={{ backgroundColor: color }}
        />
      ) : null}
      {children}
    </span>
  );
}

export default Badge;
