"use client";

import { motion, useReducedMotion } from "framer-motion";
import { AlertTriangle, FileStack, ShieldCheck, ShieldX } from "lucide-react";
import type { Candidate, RiskLevel } from "@/lib/types";
import { cn } from "@/lib/cn";

/* ------------------------------------------------------------------ */
/* Risk mapping                                                       */
/* ------------------------------------------------------------------ */

interface RiskMeta {
  accent: string;
  /** Fill fraction of the meter (0..1). */
  fraction: number;
  label: string;
}

const RISK_META: Record<RiskLevel, RiskMeta> = {
  SAFE: { accent: "var(--accent-emerald)", fraction: 0.12, label: "Safe" },
  LOW: { accent: "var(--accent-cyan)", fraction: 0.32, label: "Low" },
  MEDIUM: { accent: "var(--accent-amber)", fraction: 0.58, label: "Medium" },
  HIGH: { accent: "var(--accent-rose)", fraction: 0.82, label: "High" },
  BLOCKED: { accent: "var(--accent-rose)", fraction: 1, label: "Blocked" },
};

const RISK_ORDER: readonly RiskLevel[] = [
  "SAFE",
  "LOW",
  "MEDIUM",
  "HIGH",
  "BLOCKED",
] as const;

export interface RiskPanelProps {
  candidate: Candidate | null;
  className?: string;
}

/**
 * Risk readout for the selected candidate: a segmented risk meter, an
 * unrelated-changes flag, and the scope (files changed) count.
 */
export function RiskPanel({ candidate, className }: RiskPanelProps) {
  const reduceMotion = useReducedMotion();

  if (!candidate) {
    return (
      <div
        className={cn(
          "flex flex-col items-center justify-center gap-2 rounded-[var(--radius-sm)] p-6 text-center hairline",
          className,
        )}
      >
        <ShieldCheck
          className="h-5 w-5 text-[color:var(--text-muted)]"
          aria-hidden="true"
        />
        <p className="text-xs text-[color:var(--text-secondary)]">
          Select a candidate to assess risk.
        </p>
      </div>
    );
  }

  const meta = RISK_META[candidate.risk_level];
  const activeIndex = RISK_ORDER.indexOf(candidate.risk_level);

  return (
    <div className={cn("flex flex-col gap-3.5", className)}>
      {/* Risk level headline */}
      <div className="flex items-center justify-between gap-2">
        <span className="eyebrow text-[0.5625rem]">Risk level</span>
        <span
          className="mono text-sm font-bold uppercase tracking-wide"
          style={{ color: meta.accent }}
        >
          {candidate.risk_level}
        </span>
      </div>

      {/* Segmented meter */}
      <div
        className="flex gap-1"
        role="meter"
        aria-valuenow={activeIndex + 1}
        aria-valuemin={1}
        aria-valuemax={RISK_ORDER.length}
        aria-label={`Risk level ${meta.label}`}
      >
        {RISK_ORDER.map((level, i) => {
          const on = i <= activeIndex;
          const segMeta = RISK_META[level];
          return (
            <motion.span
              key={level}
              className="h-2 flex-1 rounded-full"
              style={{
                background: on
                  ? segMeta.accent
                  : "color-mix(in srgb, var(--bg-void) 60%, transparent)",
                border: on
                  ? "none"
                  : "1px solid var(--border-hair)",
              }}
              initial={reduceMotion ? false : { opacity: 0, scaleX: 0.4 }}
              animate={{ opacity: on ? 1 : 0.5, scaleX: 1 }}
              transition={{
                type: "spring",
                stiffness: 300,
                damping: 26,
                delay: reduceMotion ? 0 : Math.min(i, 5) * 0.05,
              }}
            />
          );
        })}
      </div>
      <div className="flex justify-between">
        <span className="mono text-[0.5625rem] text-[color:var(--text-muted)]">
          SAFE
        </span>
        <span className="mono text-[0.5625rem] text-[color:var(--text-muted)]">
          BLOCKED
        </span>
      </div>

      {/* Scope + unrelated changes */}
      <div className="grid grid-cols-2 gap-2">
        <div
          className="flex flex-col gap-1 rounded-md px-2.5 py-2 hairline"
          style={{
            background:
              "color-mix(in srgb, var(--bg-elevated) 55%, transparent)",
          }}
        >
          <span className="eyebrow flex items-center gap-1 text-[0.5625rem]">
            <FileStack className="h-3 w-3" aria-hidden="true" />
            Scope
          </span>
          <span className="mono text-lg font-semibold leading-none text-[color:var(--text-primary)]">
            {candidate.scope_files_changed}
            <span className="ml-1 text-[0.625rem] font-normal text-[color:var(--text-muted)]">
              {candidate.scope_files_changed === 1 ? "file" : "files"}
            </span>
          </span>
        </div>

        <div
          className="flex flex-col gap-1 rounded-md px-2.5 py-2 hairline"
          style={{
            background: candidate.unrelated_changes
              ? "color-mix(in srgb, var(--accent-amber) 10%, transparent)"
              : "color-mix(in srgb, var(--accent-emerald) 8%, transparent)",
            borderColor: candidate.unrelated_changes
              ? "color-mix(in srgb, var(--accent-amber) 34%, transparent)"
              : "color-mix(in srgb, var(--accent-emerald) 30%, transparent)",
          }}
        >
          <span className="eyebrow flex items-center gap-1 text-[0.5625rem]">
            {candidate.unrelated_changes ? (
              <ShieldX className="h-3 w-3" aria-hidden="true" />
            ) : (
              <ShieldCheck className="h-3 w-3" aria-hidden="true" />
            )}
            Unrelated
          </span>
          <span
            className="mono text-sm font-semibold leading-none"
            style={{
              color: candidate.unrelated_changes
                ? "var(--accent-amber)"
                : "var(--accent-emerald)",
            }}
          >
            {candidate.unrelated_changes ? "DETECTED" : "NONE"}
          </span>
        </div>
      </div>

      {candidate.unrelated_changes ? (
        <div
          className="flex items-start gap-2 rounded-md px-2.5 py-2"
          style={{
            background:
              "color-mix(in srgb, var(--accent-amber) 10%, transparent)",
            border:
              "1px solid color-mix(in srgb, var(--accent-amber) 32%, transparent)",
          }}
          role="note"
        >
          <AlertTriangle
            className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[color:var(--accent-amber)]"
            aria-hidden="true"
          />
          <p className="text-[0.6875rem] leading-relaxed text-[color:var(--text-secondary)]">
            This candidate touches files unrelated to the target finding, which
            widens the blast radius and typically fails scope verification.
          </p>
        </div>
      ) : null}
    </div>
  );
}

export default RiskPanel;
