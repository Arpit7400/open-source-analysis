"use client";

import { useEffect } from "react";
import { motion, useReducedMotion } from "framer-motion";
import {
  CheckCircle2,
  CircleSlash,
  Clock,
  FileDiff,
  Layers,
  XCircle,
} from "lucide-react";
import type { Candidate, CandidateVerdict, RiskLevel } from "@/lib/types";
import { cn } from "@/lib/cn";
import { Badge, type BadgeTone } from "@/components/ui/Badge";

/* ------------------------------------------------------------------ */
/* Verdict + risk mappings                                            */
/* ------------------------------------------------------------------ */

interface VerdictMeta {
  tone: BadgeTone;
  icon: typeof CheckCircle2;
  accent: string;
}

const VERDICT_META: Record<CandidateVerdict, VerdictMeta> = {
  ACCEPTED: {
    tone: "completed",
    icon: CheckCircle2,
    accent: "var(--accent-emerald)",
  },
  REJECTED: { tone: "failed", icon: XCircle, accent: "var(--accent-rose)" },
  NO_SUBMISSION: {
    tone: "neutral",
    icon: CircleSlash,
    accent: "var(--text-muted)",
  },
  PENDING: { tone: "amber", icon: Clock, accent: "var(--accent-amber)" },
};

const RISK_TONE: Record<RiskLevel, BadgeTone> = {
  SAFE: "emerald",
  LOW: "cyan",
  MEDIUM: "amber",
  HIGH: "rose",
  BLOCKED: "rose",
};

/** Order candidates deterministically so the tab strip is stable. */
function orderCandidates(candidates: Candidate[]): Candidate[] {
  return [...candidates].sort((a, b) =>
    a.candidate_id.localeCompare(b.candidate_id),
  );
}

export interface CandidateComparisonProps {
  candidates: Candidate[];
  selectedCandidateId: string | null;
  onSelect: (candidateId: string) => void;
  className?: string;
}

/**
 * A tab strip of candidate fixes plus a detail card for the selected one.
 * Each tab is a real button (keyboard + ARIA `aria-pressed`). Selecting a tab
 * calls `onSelect`, which the page wires to `store.selectCandidateId` so the
 * DiffViewer / VerificationMatrix / RiskPanel all follow the same selection.
 * A REJECTED candidate is visibly marked as gated by verification.
 */
export function CandidateComparison({
  candidates,
  selectedCandidateId,
  onSelect,
  className,
}: CandidateComparisonProps) {
  const reduceMotion = useReducedMotion();
  const ordered = orderCandidates(candidates);

  // Ensure a selection exists once candidates arrive.
  const hasSelection =
    selectedCandidateId != null &&
    ordered.some((c) => c.candidate_id === selectedCandidateId);
  const firstId = ordered[0]?.candidate_id ?? null;

  useEffect(() => {
    if (!hasSelection && firstId) {
      onSelect(firstId);
    }
  }, [hasSelection, firstId, onSelect]);

  if (ordered.length === 0) {
    return (
      <div
        className={cn(
          "flex flex-1 flex-col items-center justify-center gap-2 rounded-[var(--radius-sm)] p-8 text-center hairline",
          className,
        )}
      >
        <FileDiff
          className="h-6 w-6 text-[color:var(--text-muted)]"
          aria-hidden="true"
        />
        <p className="text-sm text-[color:var(--text-secondary)]">
          No candidate fixes yet.
        </p>
        <p className="text-xs text-[color:var(--text-muted)]">
          Fix-author agents will submit candidates as the mission progresses.
        </p>
      </div>
    );
  }

  const activeId =
    hasSelection && selectedCandidateId ? selectedCandidateId : firstId;
  const active =
    ordered.find((c) => c.candidate_id === activeId) ?? ordered[0] ?? null;

  return (
    <div className={cn("flex min-h-0 flex-col gap-3", className)}>
      {/* Tab strip */}
      <div
        role="tablist"
        aria-label="Candidate fixes"
        className="flex flex-wrap gap-2"
      >
        {ordered.map((candidate, i) => {
          const meta = VERDICT_META[candidate.verdict];
          const Icon = meta.icon;
          const selected = candidate.candidate_id === activeId;
          const rejected = candidate.verdict === "REJECTED";
          return (
            <motion.button
              key={candidate.candidate_id}
              type="button"
              role="tab"
              aria-selected={selected}
              onClick={() => onSelect(candidate.candidate_id)}
              initial={reduceMotion ? false : { opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{
                type: "spring",
                stiffness: 240,
                damping: 26,
                delay: Math.min(i, 8) * 0.05,
              }}
              className={cn(
                "group flex min-w-0 max-w-[15rem] items-center gap-2 rounded-lg px-3 py-2 text-left text-xs transition-colors hairline",
                selected
                  ? "text-[color:var(--text-primary)]"
                  : "text-[color:var(--text-secondary)] hover:text-[color:var(--text-primary)]",
                rejected && "opacity-90",
              )}
              style={{
                background: selected
                  ? `color-mix(in srgb, ${meta.accent} 14%, transparent)`
                  : "color-mix(in srgb, var(--bg-elevated) 55%, transparent)",
                borderColor: selected
                  ? `color-mix(in srgb, ${meta.accent} 42%, transparent)`
                  : undefined,
                boxShadow: selected
                  ? `0 0 18px -8px ${meta.accent}`
                  : undefined,
              }}
            >
              <Icon
                className="h-3.5 w-3.5 shrink-0"
                style={{ color: meta.accent }}
                aria-hidden="true"
              />
              <span
                className={cn(
                  "truncate font-medium",
                  rejected && "line-through decoration-1",
                )}
              >
                {candidate.title}
              </span>
            </motion.button>
          );
        })}
      </div>

      {/* Active candidate detail */}
      {active ? (
        <CandidateDetail candidate={active} reduceMotion={Boolean(reduceMotion)} />
      ) : null}
    </div>
  );
}

function CandidateDetail({
  candidate,
  reduceMotion,
}: {
  candidate: Candidate;
  reduceMotion: boolean;
}) {
  const meta = VERDICT_META[candidate.verdict];
  const Icon = meta.icon;
  const rejected = candidate.verdict === "REJECTED";

  return (
    <motion.div
      key={candidate.candidate_id}
      initial={reduceMotion ? false : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: "spring", stiffness: 240, damping: 26 }}
      className="flex flex-col gap-3 rounded-[var(--radius-sm)] p-3.5 hairline"
      style={{
        background: "color-mix(in srgb, var(--bg-panel) 82%, transparent)",
        borderColor: rejected
          ? "color-mix(in srgb, var(--accent-rose) 32%, transparent)"
          : undefined,
      }}
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="flex min-w-0 flex-col gap-1">
          <h3 className="text-sm font-semibold leading-snug text-[color:var(--text-primary)]">
            {candidate.title}
          </h3>
          <span className="mono text-[0.625rem] text-[color:var(--text-muted)]">
            author {candidate.author_agent} · {candidate.candidate_id}
          </span>
        </div>
        <Badge tone={meta.tone} dot>
          <Icon className="h-3 w-3" aria-hidden="true" />
          {candidate.verdict}
        </Badge>
      </div>

      {/* Rejected banner — makes it unmistakable that verification gated it. */}
      {rejected ? (
        <div
          className="flex items-start gap-2 rounded-md px-2.5 py-2"
          style={{
            background:
              "color-mix(in srgb, var(--accent-rose) 12%, transparent)",
            border:
              "1px solid color-mix(in srgb, var(--accent-rose) 34%, transparent)",
          }}
          role="note"
        >
          <XCircle
            className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[color:var(--accent-rose)]"
            aria-hidden="true"
          />
          <p className="text-xs leading-relaxed text-[color:var(--text-secondary)]">
            <span className="font-semibold text-[color:var(--accent-rose)]">
              Rejected by independent verification.
            </span>{" "}
            {candidate.verification_summary}
          </p>
        </div>
      ) : null}

      {/* Root cause */}
      <div className="flex flex-col gap-1">
        <span className="eyebrow text-[0.5625rem]">Root cause</span>
        <p className="text-xs leading-relaxed text-[color:var(--text-secondary)]">
          {candidate.root_cause}
        </p>
      </div>

      {/* Meta row: risk / scope / unrelated */}
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={RISK_TONE[candidate.risk_level]} dot>
          RISK {candidate.risk_level}
        </Badge>
        <span
          className="mono inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[0.6875rem] font-semibold text-[color:var(--text-secondary)] hairline"
          title="Files changed by this candidate"
        >
          <Layers className="h-3 w-3" aria-hidden="true" />
          {candidate.scope_files_changed}{" "}
          {candidate.scope_files_changed === 1 ? "file" : "files"}
        </span>
        {candidate.unrelated_changes ? (
          <Badge tone="amber">UNRELATED CHANGES</Badge>
        ) : (
          <Badge tone="emerald">IN SCOPE</Badge>
        )}
      </div>

      {/* Verification summary (non-rejected shows it here too) */}
      {!rejected ? (
        <p className="mono text-[0.6875rem] leading-relaxed text-[color:var(--text-muted)]">
          {candidate.verification_summary}
        </p>
      ) : null}
    </motion.div>
  );
}

export default CandidateComparison;
