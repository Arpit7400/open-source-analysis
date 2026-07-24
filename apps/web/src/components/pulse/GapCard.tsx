"use client";

import { useEffect, useRef, useState } from "react";
import { motion, useReducedMotion } from "framer-motion";
import {
  ArrowUpRight,
  BookOpen,
  Check,
  ExternalLink,
  FileCode2,
  Github,
  Lightbulb,
  ShieldAlert,
  Target,
  TrendingUp,
} from "lucide-react";
import type { PulseItem, PulseSource } from "@/lib/types";
import { cn } from "@/lib/cn";
import { Badge } from "@/components/ui/Badge";

const SOURCE_META: Record<
  PulseSource,
  { icon: typeof Github; tone: "violet" | "cyan" | "blue" | "rose" }
> = {
  arXiv: { icon: BookOpen, tone: "violet" },
  GitHub: { icon: Github, tone: "cyan" },
  Blog: { icon: FileCode2, tone: "blue" },
  Advisory: { icon: ShieldAlert, tone: "rose" },
};

function clamp01(n: number): number {
  return Math.max(0, Math.min(1, Number.isFinite(n) ? n : 0));
}

/** Small horizontal meter with a mono percentage. */
function Meter({
  label,
  value,
  color,
  icon,
}: {
  label: string;
  value: number;
  color: string;
  icon: React.ReactNode;
}) {
  const pct = Math.round(clamp01(value) * 100);
  return (
    <div className="flex flex-col gap-1">
      <span className="eyebrow flex items-center gap-1 text-[0.5625rem] text-[color:var(--text-muted)]">
        <span aria-hidden="true" style={{ color }} className="flex items-center">
          {icon}
        </span>
        {label}
      </span>
      <div className="flex items-center gap-2">
        <div
          className="relative h-1.5 flex-1 overflow-hidden rounded-full"
          style={{
            background:
              "color-mix(in srgb, var(--bg-elevated) 80%, transparent)",
          }}
          role="progressbar"
          aria-valuenow={pct}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={`${label} ${pct} percent`}
        >
          <span
            className="absolute inset-y-0 left-0 rounded-full"
            style={{ width: `${pct}%`, background: color }}
            aria-hidden="true"
          />
        </div>
        <span
          className="mono w-8 text-right text-[0.625rem] tabular-nums text-[color:var(--text-secondary)]"
          aria-hidden="true"
        >
          {pct}%
        </span>
      </div>
    </div>
  );
}

interface GapCardProps {
  item: PulseItem;
  /** Stagger index for the entrance cascade. */
  index?: number;
}

/**
 * A single Industry Pulse signal rendered as an actionable "gap" card. It shows
 * why the signal matters, the skill gap it exposes, and a suggested action —
 * plus an actionability meter and a link to the canonical source. The
 * "Create Artifact" button is a local stub that shows an inline confirmation
 * (no network writes; GitHub/side-effects stay disabled per the safety model).
 *
 * Strictly a knowledge/skill signal — never a job posting.
 */
export function GapCard({ item, index = 0 }: GapCardProps) {
  const reduceMotion = useReducedMotion();
  const [created, setCreated] = useState(false);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(
    () => () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
    },
    [],
  );

  const meta = SOURCE_META[item.source] ?? SOURCE_META.Blog;
  const SourceIcon = meta.icon;

  const published = (() => {
    const d = new Date(item.published_at);
    if (Number.isNaN(d.getTime())) return item.published_at;
    return d.toLocaleDateString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  })();

  const handleCreate = () => {
    setCreated(true);
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
    timeoutRef.current = setTimeout(() => setCreated(false), 2600);
  };

  return (
    <motion.article
      initial={reduceMotion ? false : { opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{
        type: "spring",
        stiffness: 220,
        damping: 26,
        delay: Math.min(index, 10) * 0.04,
      }}
      className="glass flex flex-col gap-3 p-4"
      aria-label={`${item.source} signal: ${item.title}`}
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 flex-col gap-1.5">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={meta.tone} dot>
              <SourceIcon className="h-3 w-3" aria-hidden="true" />
              {item.source}
            </Badge>
            <span className="mono text-[0.625rem] text-[color:var(--text-muted)]">
              {item.technology}
            </span>
            <span className="mono text-[0.625rem] text-[color:var(--text-muted)]">
              {published}
            </span>
          </div>
          <h3 className="text-sm font-semibold leading-snug text-[color:var(--text-primary)]">
            {item.title}
          </h3>
        </div>
      </div>

      {/* Narrative */}
      <dl className="flex flex-col gap-2.5 text-[0.8125rem]">
        <div className="flex gap-2">
          <dt className="flex shrink-0 items-center gap-1.5 pt-0.5">
            <TrendingUp
              className="h-3.5 w-3.5"
              style={{ color: "var(--accent-cyan)" }}
              aria-hidden="true"
            />
            <span className="eyebrow text-[0.5625rem]">Why</span>
          </dt>
          <dd className="text-[color:var(--text-secondary)]">
            {item.why_it_matters}
          </dd>
        </div>
        <div className="flex gap-2">
          <dt className="flex shrink-0 items-center gap-1.5 pt-0.5">
            <Target
              className="h-3.5 w-3.5"
              style={{ color: "var(--accent-amber)" }}
              aria-hidden="true"
            />
            <span className="eyebrow text-[0.5625rem]">Gap</span>
          </dt>
          <dd className="text-[color:var(--text-secondary)]">
            {item.skill_gap}
          </dd>
        </div>
        <div className="flex gap-2">
          <dt className="flex shrink-0 items-center gap-1.5 pt-0.5">
            <Lightbulb
              className="h-3.5 w-3.5"
              style={{ color: "var(--accent-emerald)" }}
              aria-hidden="true"
            />
            <span className="eyebrow text-[0.5625rem]">Do</span>
          </dt>
          <dd className="text-[color:var(--text-secondary)]">
            {item.suggested_action}
          </dd>
        </div>
      </dl>

      {/* Meters */}
      <div className="grid grid-cols-3 gap-3 pt-1">
        <Meter
          label="Actionability"
          value={item.actionability}
          color="var(--accent-emerald)"
          icon={<Lightbulb className="h-2.5 w-2.5" aria-hidden="true" />}
        />
        <Meter
          label="Relevance"
          value={item.personal_relevance}
          color="var(--accent-violet)"
          icon={<Target className="h-2.5 w-2.5" aria-hidden="true" />}
        />
        <Meter
          label="Momentum"
          value={item.momentum}
          color="var(--accent-cyan)"
          icon={<TrendingUp className="h-2.5 w-2.5" aria-hidden="true" />}
        />
      </div>

      {/* Actions */}
      <div className="mt-1 flex items-center justify-between gap-3 pt-2 hairline-t">
        <a
          href={item.canonical_url}
          target="_blank"
          rel="noopener noreferrer"
          className="mono inline-flex items-center gap-1.5 text-[0.75rem] font-medium text-[color:var(--text-secondary)] transition-colors hover:text-[color:var(--accent-cyan)]"
        >
          <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
          Source
        </a>

        <button
          type="button"
          onClick={handleCreate}
          className={cn(
            "mono inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-[0.75rem] font-semibold transition-colors",
          )}
          style={
            created
              ? {
                  color: "var(--accent-emerald)",
                  background:
                    "color-mix(in srgb, var(--accent-emerald) 14%, transparent)",
                  border:
                    "1px solid color-mix(in srgb, var(--accent-emerald) 34%, transparent)",
                }
              : {
                  color: "var(--accent-cyan)",
                  background:
                    "color-mix(in srgb, var(--accent-cyan) 12%, transparent)",
                  border:
                    "1px solid color-mix(in srgb, var(--accent-cyan) 30%, transparent)",
                }
          }
          aria-live="polite"
        >
          {created ? (
            <>
              <Check className="h-3.5 w-3.5" aria-hidden="true" />
              Draft saved locally
            </>
          ) : (
            <>
              <ArrowUpRight className="h-3.5 w-3.5" aria-hidden="true" />
              Create Artifact
            </>
          )}
        </button>
      </div>
    </motion.article>
  );
}

export default GapCard;
