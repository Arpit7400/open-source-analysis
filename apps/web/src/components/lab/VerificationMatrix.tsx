"use client";

import { motion, useReducedMotion } from "framer-motion";
import { Check, Minus, ShieldCheck, X } from "lucide-react";
import type {
  Candidate,
  VerificationCheck,
  VerificationStatus,
} from "@/lib/types";
import { cn } from "@/lib/cn";

/* ------------------------------------------------------------------ */
/* Status mapping                                                     */
/* ------------------------------------------------------------------ */

interface StatusMeta {
  accent: string;
  icon: typeof Check;
  label: string;
}

const STATUS_META: Record<VerificationStatus, StatusMeta> = {
  PASS: { accent: "var(--accent-emerald)", icon: Check, label: "PASS" },
  FAIL: { accent: "var(--accent-rose)", icon: X, label: "FAIL" },
  SKIP: { accent: "var(--text-muted)", icon: Minus, label: "SKIP" },
};

/** Humanize a snake_case check id into a Title Case label. */
function humanizeCheck(check: string): string {
  return check
    .split(/[_\s]+/)
    .filter(Boolean)
    .map((w) => (w.length > 0 ? w[0]!.toUpperCase() + w.slice(1) : w))
    .join(" ");
}

export interface VerificationMatrixProps {
  candidate: Candidate | null;
  className?: string;
}

/**
 * Grid of verification checks × status with animated draw-on stamps. Also
 * surfaces `verification_summary` and explicitly notes that each verifier is
 * an agent independent of the fix author (verifier != author).
 */
export function VerificationMatrix({
  candidate,
  className,
}: VerificationMatrixProps) {
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
          Select a candidate to see its verification matrix.
        </p>
      </div>
    );
  }

  const checks = candidate.verification;
  const passCount = checks.filter((c) => c.status === "PASS").length;
  const failCount = checks.filter((c) => c.status === "FAIL").length;

  return (
    <div className={cn("flex flex-col gap-3", className)}>
      {/* Summary line */}
      <div
        className="flex flex-wrap items-center gap-2 rounded-md px-2.5 py-2 hairline"
        style={{
          background:
            failCount > 0
              ? "color-mix(in srgb, var(--accent-rose) 9%, transparent)"
              : "color-mix(in srgb, var(--accent-emerald) 8%, transparent)",
        }}
      >
        <ShieldCheck
          className="h-3.5 w-3.5 shrink-0"
          style={{
            color:
              failCount > 0
                ? "var(--accent-rose)"
                : "var(--accent-emerald)",
          }}
          aria-hidden="true"
        />
        <p className="text-xs leading-snug text-[color:var(--text-secondary)]">
          {candidate.verification_summary}
        </p>
      </div>

      {/* Matrix header */}
      {checks.length > 0 ? (
        <div
          className="grid items-center gap-2 px-1"
          style={{ gridTemplateColumns: "1fr auto" }}
        >
          <span className="eyebrow text-[0.5625rem]">Check</span>
          <span className="eyebrow justify-self-end text-[0.5625rem]">
            Status
          </span>
        </div>
      ) : (
        <p className="px-1 text-xs text-[color:var(--text-muted)]">
          No verification checks recorded for this candidate.
        </p>
      )}

      {/* Rows */}
      <ul className="flex flex-col gap-1.5">
        {checks.map((check, i) => (
          <VerificationRow
            key={`${candidate.candidate_id}-${check.check}-${i}`}
            check={check}
            index={i}
            reduceMotion={Boolean(reduceMotion)}
          />
        ))}
      </ul>

      {/* Tally + independence note */}
      {checks.length > 0 ? (
        <div className="flex flex-col gap-1.5 pt-0.5">
          <div className="flex items-center gap-3">
            <span className="mono text-[0.625rem] text-[color:var(--accent-emerald)]">
              {passCount} PASS
            </span>
            {failCount > 0 ? (
              <span className="mono text-[0.625rem] text-[color:var(--accent-rose)]">
                {failCount} FAIL
              </span>
            ) : null}
            <span className="mono ml-auto text-[0.625rem] text-[color:var(--text-muted)]">
              {checks.length} total
            </span>
          </div>
          <p className="text-[0.625rem] leading-relaxed text-[color:var(--text-muted)]">
            Each check is run by an independent verifier agent — never the fix
            author ({candidate.author_agent}).
          </p>
        </div>
      ) : null}
    </div>
  );
}

function VerificationRow({
  check,
  index,
  reduceMotion,
}: {
  check: VerificationCheck;
  index: number;
  reduceMotion: boolean;
}) {
  const meta = STATUS_META[check.status];
  const Icon = meta.icon;

  return (
    <motion.li
      initial={reduceMotion ? false : { opacity: 0, x: -8 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{
        type: "spring",
        stiffness: 260,
        damping: 28,
        delay: Math.min(index, 8) * 0.06,
      }}
      className="flex items-center gap-3 rounded-md px-2.5 py-2 hairline"
      style={{
        background: "color-mix(in srgb, var(--bg-elevated) 45%, transparent)",
      }}
    >
      <div className="flex min-w-0 flex-col gap-0.5">
        <span className="truncate text-xs font-medium text-[color:var(--text-primary)]">
          {humanizeCheck(check.check)}
        </span>
        <span className="truncate text-[0.625rem] text-[color:var(--text-muted)]">
          {check.detail}
        </span>
        <span className="mono text-[0.5625rem] text-[color:var(--text-muted)]">
          {check.verifier_agent}
        </span>
      </div>

      {/* Draw-on stamp */}
      <motion.span
        initial={reduceMotion ? false : { scale: 0.4, opacity: 0, rotate: -8 }}
        animate={{ scale: 1, opacity: 1, rotate: 0 }}
        transition={
          reduceMotion
            ? { duration: 0 }
            : {
                type: "spring",
                stiffness: 480,
                damping: 18,
                delay: 0.12 + Math.min(index, 8) * 0.06,
              }
        }
        className="mono ml-auto inline-flex shrink-0 items-center gap-1 rounded-md px-2 py-1 text-[0.625rem] font-bold uppercase tracking-wider"
        style={{
          color: meta.accent,
          background: `color-mix(in srgb, ${meta.accent} 14%, transparent)`,
          border: `1.5px solid color-mix(in srgb, ${meta.accent} 55%, transparent)`,
          boxShadow:
            check.status === "FAIL"
              ? `0 0 14px -6px ${meta.accent}`
              : undefined,
        }}
        aria-label={`${humanizeCheck(check.check)}: ${meta.label}`}
      >
        <Icon className="h-3 w-3" aria-hidden="true" />
        {meta.label}
      </motion.span>
    </motion.li>
  );
}

export default VerificationMatrix;
