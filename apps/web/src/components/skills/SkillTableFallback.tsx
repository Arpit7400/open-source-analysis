"use client";

import { useMemo } from "react";
import type { Skill } from "@/lib/types";
import { cn } from "@/lib/cn";
import { VerificationBadge } from "./VerificationBadge";

interface SkillTableFallbackProps {
  skills: Skill[];
  className?: string;
}

/**
 * Confidence meter — a small labeled bar. Purely decorative bar plus a mono
 * percentage so it is legible without color perception.
 */
function ConfidenceMeter({ value }: { value: number }) {
  const clamped = Math.max(0, Math.min(1, Number.isFinite(value) ? value : 0));
  const pct = Math.round(clamped * 100);
  // Ramp the accent from blue (low) → cyan → emerald (high) for a quick read.
  const color =
    clamped >= 0.75
      ? "var(--accent-emerald)"
      : clamped >= 0.5
        ? "var(--accent-cyan)"
        : "var(--accent-blue)";

  return (
    <div className="flex items-center gap-2">
      <div
        className="relative h-1.5 w-24 overflow-hidden rounded-full"
        style={{
          background: "color-mix(in srgb, var(--bg-elevated) 80%, transparent)",
        }}
        role="progressbar"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={`Confidence ${pct} percent`}
      >
        <span
          className="absolute inset-y-0 left-0 rounded-full"
          style={{ width: `${pct}%`, background: color }}
          aria-hidden="true"
        />
      </div>
      <span
        className="mono w-9 text-right text-[0.6875rem] tabular-nums text-[color:var(--text-secondary)]"
        aria-hidden="true"
      >
        {pct}%
      </span>
    </div>
  );
}

/**
 * The required non-WebGL / reduced-motion fallback for the Skill Constellation.
 * A semantic, keyboard-navigable, screen-reader-friendly table that surfaces
 * every signal the 3D scene encodes — name, verification level, confidence,
 * evidence count, and the reason the skill last changed.
 */
export function SkillTableFallback({
  skills,
  className,
}: SkillTableFallbackProps) {
  const rows = useMemo(
    () =>
      [...skills].sort((a, b) => {
        // Strongest, most-corroborated skills first.
        if (b.confidence !== a.confidence) return b.confidence - a.confidence;
        return b.evidence_strength - a.evidence_strength;
      }),
    [skills],
  );

  if (rows.length === 0) {
    return (
      <div
        className={cn(
          "flex min-h-40 items-center justify-center rounded-lg p-8 text-center hairline",
          className,
        )}
      >
        <p className="text-sm text-[color:var(--text-secondary)]">
          No skills have been extracted yet. Analyze a repository or ingest a
          resume to populate your skill graph.
        </p>
      </div>
    );
  }

  return (
    <div className={cn("w-full overflow-x-auto rounded-lg hairline", className)}>
      <table className="w-full border-collapse text-left text-sm">
        <caption className="sr-only">
          Skill inventory: name, verification level, confidence, evidence count,
          and the reason each skill last changed.
        </caption>
        <thead>
          <tr className="hairline-b">
            <th
              scope="col"
              className="eyebrow px-4 py-2.5 text-[0.625rem] font-semibold text-[color:var(--text-secondary)]"
            >
              Skill
            </th>
            <th
              scope="col"
              className="eyebrow px-4 py-2.5 text-[0.625rem] font-semibold text-[color:var(--text-secondary)]"
            >
              Verification
            </th>
            <th
              scope="col"
              className="eyebrow px-4 py-2.5 text-[0.625rem] font-semibold text-[color:var(--text-secondary)]"
            >
              Confidence
            </th>
            <th
              scope="col"
              className="eyebrow px-4 py-2.5 text-right text-[0.625rem] font-semibold text-[color:var(--text-secondary)]"
            >
              Evidence
            </th>
            <th
              scope="col"
              className="eyebrow px-4 py-2.5 text-[0.625rem] font-semibold text-[color:var(--text-secondary)]"
            >
              Last change
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((skill) => (
            <tr
              key={skill.id}
              className="align-top transition-colors hairline-b last:border-b-0 hover:bg-[color:color-mix(in_srgb,var(--accent-cyan)_5%,transparent)]"
            >
              <th
                scope="row"
                className="px-4 py-3 font-medium text-[color:var(--text-primary)]"
              >
                <span className="flex flex-col gap-0.5">
                  <span>{skill.name}</span>
                  <span className="eyebrow text-[0.5625rem] text-[color:var(--text-muted)]">
                    {skill.category}
                  </span>
                </span>
              </th>
              <td className="px-4 py-3">
                <VerificationBadge level={skill.verification_level} />
              </td>
              <td className="px-4 py-3">
                <ConfidenceMeter value={skill.confidence} />
              </td>
              <td className="px-4 py-3 text-right">
                <span className="mono tabular-nums text-[color:var(--text-secondary)]">
                  {skill.evidence_ids.length}
                </span>
              </td>
              <td className="px-4 py-3">
                <span className="text-[0.8125rem] text-[color:var(--text-secondary)]">
                  {skill.last_change_reason || "—"}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default SkillTableFallback;
