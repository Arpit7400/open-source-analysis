import type { HTMLAttributes, ReactNode } from "react";
import { cn } from "@/lib/cn";

interface StatPillProps extends HTMLAttributes<HTMLDivElement> {
  /** Uppercase micro-label describing the metric. */
  label: ReactNode;
  /** The value — rendered mono (numbers/IDs are always mono per the DS). */
  value: ReactNode;
  /** Optional leading icon or accent glyph. */
  icon?: ReactNode;
  /** Optional trailing unit (e.g. "%", "MB"). */
  unit?: ReactNode;
  /** Accent color for the value, as a CSS color / custom-property string. */
  accent?: string;
  className?: string;
}

/**
 * A compact labeled statistic: eyebrow label on top, mono value below.
 * Used across resource readouts, mission summaries, and profile stats.
 */
export function StatPill({
  label,
  value,
  icon,
  unit,
  accent,
  className,
  ...rest
}: StatPillProps) {
  return (
    <div
      className={cn(
        "flex min-w-0 flex-col gap-1 rounded-lg px-3 py-2 hairline",
        className,
      )}
      style={{ background: "color-mix(in srgb, var(--bg-elevated) 60%, transparent)" }}
      {...rest}
    >
      <span className="eyebrow flex items-center gap-1.5 text-[0.625rem]">
        {icon ? (
          <span aria-hidden="true" className="flex items-center">
            {icon}
          </span>
        ) : null}
        {label}
      </span>
      <span
        className="mono flex items-baseline gap-1 truncate text-lg font-semibold leading-none"
        style={accent ? { color: accent } : undefined}
      >
        {value}
        {unit ? (
          <span className="text-xs font-normal text-[color:var(--text-muted)]">
            {unit}
          </span>
        ) : null}
      </span>
    </div>
  );
}

export default StatPill;
