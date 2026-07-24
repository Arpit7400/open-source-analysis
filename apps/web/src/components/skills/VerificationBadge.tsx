"use client";

import type { CSSProperties } from "react";
import {
  BadgeCheck,
  BrainCircuit,
  CheckCircle2,
  ShieldCheck,
  UserCheck,
} from "lucide-react";
import type { VerificationLevel } from "@/lib/types";
import { cn } from "@/lib/cn";

/**
 * Shared verification-level chip. Maps a {@link VerificationLevel} to a short
 * label, an accent color (drawn from the design-system ramps), and a glyph so
 * the same visual language is used in the constellation hover card and the
 * accessible skill table.
 *
 * The ladder deliberately climbs from a dim, self-asserted claim
 * (`SELF_DECLARED`) up to the strongest signal (`EXTERNALLY_VALIDATED`), so a
 * denser color reads as "more trustworthy" at a glance.
 */

type VerificationMeta = {
  label: string;
  /** CSS color / custom-property string used for text, border, and fill. */
  color: string;
  Icon: typeof ShieldCheck;
  /** Short screen-reader / tooltip description of what this level means. */
  description: string;
};

const META: Record<VerificationLevel, VerificationMeta> = {
  SELF_DECLARED: {
    label: "Self-declared",
    color: "var(--text-muted)",
    Icon: UserCheck,
    description: "Claimed by the user; not yet corroborated by evidence.",
  },
  AI_INFERRED: {
    label: "AI-inferred",
    color: "var(--accent-blue)",
    Icon: BrainCircuit,
    description: "Inferred by an agent from linked artifacts.",
  },
  TOOL_VERIFIED: {
    label: "Tool-verified",
    color: "var(--accent-cyan)",
    Icon: CheckCircle2,
    description: "Confirmed by an automated tool (tests, linters, builds).",
  },
  HUMAN_REVIEWED: {
    label: "Human-reviewed",
    color: "var(--accent-violet)",
    Icon: BadgeCheck,
    description: "Reviewed and confirmed by a human.",
  },
  EXTERNALLY_VALIDATED: {
    label: "Externally validated",
    color: "var(--accent-emerald)",
    Icon: ShieldCheck,
    description: "Validated by an external source (merged PR, publication).",
  },
};

/** Accent color for a verification level — exported for the 3D node tinting. */
export function verificationColor(level: VerificationLevel): string {
  return (META[level] ?? META.SELF_DECLARED).color;
}

/** Human-readable label for a verification level. */
export function verificationLabel(level: VerificationLevel): string {
  return (META[level] ?? META.SELF_DECLARED).label;
}

interface VerificationBadgeProps {
  level: VerificationLevel;
  /** Hide the leading icon (compact contexts). */
  hideIcon?: boolean;
  className?: string;
}

export function VerificationBadge({
  level,
  hideIcon = false,
  className,
}: VerificationBadgeProps) {
  const meta = META[level] ?? META.SELF_DECLARED;
  const { label, color, Icon, description } = meta;

  const style: CSSProperties = {
    color,
    backgroundColor: `color-mix(in srgb, ${color} 14%, transparent)`,
    border: `1px solid color-mix(in srgb, ${color} 32%, transparent)`,
  };

  return (
    <span
      className={cn(
        "mono inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-0.5 text-[0.6875rem] font-semibold leading-none",
        className,
      )}
      style={style}
      title={description}
    >
      {hideIcon ? null : <Icon className="h-3 w-3 shrink-0" aria-hidden="true" />}
      {label}
    </span>
  );
}

export default VerificationBadge;
