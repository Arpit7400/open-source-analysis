"use client";

import { useId, useState } from "react";
import { motion, useReducedMotion } from "framer-motion";
import {
  ChevronDown,
  FileCode2,
  FlaskConical,
  Lightbulb,
  ShieldAlert,
} from "lucide-react";
import type { Finding, ReproductionStatus, Severity } from "@/lib/types";
import { cn } from "@/lib/cn";
import { Badge, type BadgeTone } from "@/components/ui/Badge";

/* ------------------------------------------------------------------ */
/* Severity / category / reproduction mappings                        */
/* ------------------------------------------------------------------ */

/** Severity → accent CSS variable used for the left rail + confidence bar. */
const SEVERITY_COLOR: Record<Severity, string> = {
  INFO: "var(--accent-blue)",
  LOW: "var(--accent-cyan)",
  MEDIUM: "var(--accent-amber)",
  HIGH: "var(--accent-rose)",
  CRITICAL: "var(--accent-rose)",
};

/** Severity → Badge tone (semantic aliases exist on Badge). */
const SEVERITY_TONE: Record<Severity, BadgeTone> = {
  INFO: "info",
  LOW: "low",
  MEDIUM: "medium",
  HIGH: "high",
  CRITICAL: "critical",
};

/** Rank used only for the small ordinal indicator (CRITICAL is highest). */
const SEVERITY_RANK: Record<Severity, number> = {
  INFO: 1,
  LOW: 2,
  MEDIUM: 3,
  HIGH: 4,
  CRITICAL: 5,
};

interface ReproMeta {
  label: string;
  tone: BadgeTone;
}

const REPRODUCTION_META: Record<ReproductionStatus, ReproMeta> = {
  NOT_REQUIRED: { label: "REPRO N/A", tone: "neutral" },
  PENDING: { label: "REPRO PENDING", tone: "amber" },
  REPRODUCED: { label: "REPRODUCED", tone: "emerald" },
  NOT_REPRODUCED: { label: "NOT REPRODUCED", tone: "rose" },
};

export interface FindingCardProps {
  finding: Finding;
  /** Stagger index for the entrance cascade. */
  index?: number;
  className?: string;
}

/**
 * A single severity-coded finding. Shows a colored severity rail, category
 * chip, an animated confidence bar, evidence (file:line + mono snippet), a
 * reproduction badge, an expandable limitations block, and the suggested next
 * step. Fully keyboard-operable: the limitations toggle is a real button.
 */
export function FindingCard({ finding, index = 0, className }: FindingCardProps) {
  const reduceMotion = useReducedMotion();
  const [expanded, setExpanded] = useState(false);
  const limitationsId = useId();

  const color = SEVERITY_COLOR[finding.severity];
  const repro = REPRODUCTION_META[finding.reproduction_status];
  const confidencePct = Math.round(
    Math.max(0, Math.min(1, finding.confidence)) * 100,
  );
  const hasLimitations = finding.limitations.length > 0;

  return (
    <motion.article
      initial={reduceMotion ? false : { opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{
        type: "spring",
        stiffness: 240,
        damping: 26,
        mass: 0.7,
        delay: Math.min(index, 12) * 0.04,
      }}
      className={cn(
        "relative overflow-hidden rounded-[var(--radius-sm)] hairline",
        className,
      )}
      style={{
        background: "color-mix(in srgb, var(--bg-panel) 82%, transparent)",
      }}
      aria-label={`${finding.severity} finding: ${finding.summary}`}
    >
      {/* Severity rail */}
      <span
        aria-hidden="true"
        className="absolute inset-y-0 left-0 w-[3px]"
        style={{ background: color }}
      />

      <div className="flex flex-col gap-3 p-3.5 pl-4">
        {/* Header: severity + category + confidence */}
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone={SEVERITY_TONE[finding.severity]} dot>
            {finding.severity}
          </Badge>
          <Badge tone="neutral">{finding.category}</Badge>
          <span
            className="mono ml-auto shrink-0 text-[0.625rem] text-[color:var(--text-muted)]"
            title="Severity rank (1 = INFO … 5 = CRITICAL)"
          >
            SEV {SEVERITY_RANK[finding.severity]}/5
          </span>
        </div>

        {/* Summary */}
        <h3 className="text-sm font-semibold leading-snug text-[color:var(--text-primary)]">
          {finding.summary}
        </h3>

        {/* Confidence bar */}
        <div className="flex flex-col gap-1">
          <div className="flex items-center justify-between">
            <span className="eyebrow text-[0.5625rem]">Confidence</span>
            <span
              className="mono text-[0.6875rem] font-semibold"
              style={{ color }}
            >
              {confidencePct}%
            </span>
          </div>
          <div
            className="h-1.5 w-full overflow-hidden rounded-full"
            style={{
              background: "color-mix(in srgb, var(--bg-void) 70%, transparent)",
            }}
            role="meter"
            aria-valuenow={confidencePct}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label={`Confidence ${confidencePct} percent`}
          >
            <motion.span
              className="block h-full rounded-full"
              style={{ background: color }}
              initial={reduceMotion ? false : { width: 0 }}
              animate={{ width: `${confidencePct}%` }}
              transition={{
                type: "spring",
                stiffness: 120,
                damping: 22,
                delay: reduceMotion ? 0 : 0.12 + Math.min(index, 12) * 0.03,
              }}
            />
          </div>
        </div>

        {/* Evidence */}
        {finding.evidence.length > 0 ? (
          <div className="flex flex-col gap-2">
            <span className="eyebrow flex items-center gap-1.5 text-[0.5625rem]">
              <FileCode2 className="h-3 w-3" aria-hidden="true" />
              Evidence
            </span>
            {finding.evidence.map((ev, i) => (
              <figure
                key={`${finding.finding_id}-ev-${i}`}
                className="overflow-hidden rounded-md hairline"
                style={{ background: "var(--bg-void)" }}
              >
                <figcaption className="mono flex flex-wrap items-center gap-x-2 gap-y-0.5 px-2.5 py-1.5 text-[0.625rem] text-[color:var(--text-secondary)] hairline-b">
                  <span className="truncate text-[color:var(--text-primary)]">
                    {ev.path}
                  </span>
                  <span className="text-[color:var(--accent-cyan)]">
                    :{ev.start_line}
                    {ev.end_line !== ev.start_line ? `-${ev.end_line}` : ""}
                  </span>
                  {ev.commit ? (
                    <span
                      className="ml-auto text-[color:var(--text-muted)]"
                      title={`Commit ${ev.commit}`}
                    >
                      @{ev.commit.slice(0, 7)}
                    </span>
                  ) : null}
                </figcaption>
                <pre className="mono overflow-x-auto px-2.5 py-2 text-[0.6875rem] leading-relaxed text-[color:var(--text-secondary)]">
                  <code>{ev.snippet}</code>
                </pre>
              </figure>
            ))}
          </div>
        ) : null}

        {/* Reproduction + suggested next step */}
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone={repro.tone}>
            <FlaskConical className="h-3 w-3" aria-hidden="true" />
            {repro.label}
          </Badge>
          {finding.reproduction_required ? (
            <span className="mono text-[0.5625rem] uppercase tracking-wider text-[color:var(--text-muted)]">
              repro required
            </span>
          ) : null}
        </div>

        <div
          className="flex items-start gap-2 rounded-md px-2.5 py-2 hairline"
          style={{
            background:
              "color-mix(in srgb, var(--accent-cyan) 7%, transparent)",
          }}
        >
          <Lightbulb
            className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[color:var(--accent-cyan)]"
            aria-hidden="true"
          />
          <p className="text-xs leading-relaxed text-[color:var(--text-secondary)]">
            <span className="eyebrow mr-1.5 text-[0.5625rem] text-[color:var(--accent-cyan)]">
              Next
            </span>
            {finding.suggested_next_step}
          </p>
        </div>

        {/* Expandable limitations */}
        {hasLimitations ? (
          <div className="flex flex-col">
            <button
              type="button"
              onClick={() => setExpanded((v) => !v)}
              aria-expanded={expanded}
              aria-controls={limitationsId}
              className="mono flex items-center gap-1.5 self-start rounded-md px-1.5 py-1 text-[0.625rem] text-[color:var(--text-secondary)] transition-colors hover:text-[color:var(--text-primary)]"
            >
              <ShieldAlert className="h-3 w-3" aria-hidden="true" />
              <span>
                Limitations ({finding.limitations.length})
              </span>
              <ChevronDown
                className={cn(
                  "h-3 w-3 transition-transform",
                  expanded && "rotate-180",
                )}
                aria-hidden="true"
              />
            </button>
            <motion.div
              id={limitationsId}
              initial={false}
              animate={{
                height: expanded ? "auto" : 0,
                opacity: expanded ? 1 : 0,
              }}
              transition={
                reduceMotion
                  ? { duration: 0 }
                  : { type: "spring", stiffness: 260, damping: 30 }
              }
              className="overflow-hidden"
            >
              <ul className="mt-1.5 flex flex-col gap-1 pl-1">
                {finding.limitations.map((lim, i) => (
                  <li
                    key={`${finding.finding_id}-lim-${i}`}
                    className="flex gap-1.5 text-[0.6875rem] leading-relaxed text-[color:var(--text-muted)]"
                  >
                    <span
                      aria-hidden="true"
                      className="mt-1.5 h-1 w-1 shrink-0 rounded-full"
                      style={{ background: "var(--accent-amber)" }}
                    />
                    {lim}
                  </li>
                ))}
              </ul>
            </motion.div>
          </div>
        ) : null}

        {/* Footer: source agent */}
        <div className="flex items-center justify-between pt-0.5">
          <span className="mono text-[0.5625rem] text-[color:var(--text-muted)]">
            {finding.agent_id}
          </span>
          <span className="mono text-[0.5625rem] text-[color:var(--text-muted)]">
            {finding.finding_id}
          </span>
        </div>
      </div>
    </motion.article>
  );
}

export default FindingCard;
