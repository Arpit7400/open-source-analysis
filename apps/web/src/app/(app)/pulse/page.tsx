"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  AlertTriangle,
  BookOpen,
  FileCode2,
  Github,
  Loader2,
  Radio,
  ShieldAlert,
} from "lucide-react";
import * as api from "@/lib/api";
import type { PulseItem, PulseResponse, PulseSource } from "@/lib/types";
import { cn } from "@/lib/cn";
import { Eyebrow } from "@/components/ui/Eyebrow";
import { Panel } from "@/components/ui/Panel";
import { StatPill } from "@/components/ui/StatPill";
import { MonoValue } from "@/components/ui/MonoValue";
import { MomentumChart } from "@/components/pulse/MomentumChart";
import { GapCard } from "@/components/pulse/GapCard";

const SOURCES: readonly PulseSource[] = ["arXiv", "GitHub", "Blog", "Advisory"];

const SOURCE_ICON: Record<PulseSource, typeof Github> = {
  arXiv: BookOpen,
  GitHub: Github,
  Blog: FileCode2,
  Advisory: ShieldAlert,
};

const SOURCE_ACCENT: Record<PulseSource, string> = {
  arXiv: "var(--accent-violet)",
  GitHub: "var(--accent-cyan)",
  Blog: "var(--accent-blue)",
  Advisory: "var(--accent-rose)",
};

type SortMode = "relevance" | "momentum" | "recent";

const SORTS: { value: SortMode; label: string }[] = [
  { value: "relevance", label: "Relevance" },
  { value: "momentum", label: "Momentum" },
  { value: "recent", label: "Newest" },
];

export default function PulsePage() {
  const [active, setActive] = useState<Set<PulseSource>>(new Set());
  const [sort, setSort] = useState<SortMode>("relevance");

  const pulseQuery = useQuery<PulseResponse>({
    queryKey: ["pulse"],
    queryFn: ({ signal }) => api.getPulse(signal),
  });

  const items: PulseItem[] = useMemo(
    () => pulseQuery.data?.items ?? [],
    [pulseQuery.data],
  );

  // Per-source counts for the filter chips.
  const counts = useMemo(() => {
    const map = new Map<PulseSource, number>();
    for (const item of items) {
      map.set(item.source, (map.get(item.source) ?? 0) + 1);
    }
    return map;
  }, [items]);

  const filtered = useMemo(() => {
    const base =
      active.size === 0 ? items : items.filter((i) => active.has(i.source));
    const sorted = [...base];
    sorted.sort((a, b) => {
      if (sort === "relevance") return b.personal_relevance - a.personal_relevance;
      if (sort === "momentum") return b.momentum - a.momentum;
      return (
        new Date(b.published_at).getTime() - new Date(a.published_at).getTime()
      );
    });
    return sorted;
  }, [items, active, sort]);

  const summary = useMemo(() => {
    if (items.length === 0) {
      return { total: 0, avgMomentum: 0, avgRelevance: 0, highAction: 0 };
    }
    let m = 0;
    let r = 0;
    let highAction = 0;
    for (const i of items) {
      m += i.momentum;
      r += i.personal_relevance;
      if (i.actionability >= 0.6) highAction += 1;
    }
    return {
      total: items.length,
      avgMomentum: Math.round((m / items.length) * 100),
      avgRelevance: Math.round((r / items.length) * 100),
      highAction,
    };
  }, [items]);

  const toggleSource = (source: PulseSource) => {
    setActive((prev) => {
      const next = new Set(prev);
      if (next.has(source)) next.delete(source);
      else next.add(source);
      return next;
    });
  };

  return (
    <div className="mx-auto flex w-full max-w-[1400px] flex-col gap-5 px-4 py-6 md:px-6">
      {/* ---- Header ------------------------------------------------------- */}
      <header className="flex flex-col gap-3">
        <div className="flex flex-col gap-1.5">
          <Eyebrow className="flex items-center gap-2">
            <Radio className="h-3.5 w-3.5" aria-hidden="true" />
            Industry Pulse
          </Eyebrow>
          <h1 className="text-2xl font-semibold tracking-tight text-[color:var(--text-primary)]">
            Momentum &amp; Skill Gaps
          </h1>
          <p className="max-w-2xl text-sm text-[color:var(--text-secondary)]">
            A momentum timeline of what is accelerating across research, open
            source, and advisories — mapped to your personal relevance and the
            gaps worth closing. Signals only; never job postings.
          </p>
        </div>

        <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
          <StatPill
            label="Signals"
            icon={<Activity className="h-3 w-3" aria-hidden="true" />}
            value={<MonoValue value={summary.total} />}
            accent="var(--accent-cyan)"
          />
          <StatPill
            label="Avg momentum"
            value={<MonoValue value={summary.avgMomentum} suffix="%" />}
            accent="var(--accent-violet)"
          />
          <StatPill
            label="Avg relevance"
            value={<MonoValue value={summary.avgRelevance} suffix="%" />}
            accent="var(--accent-blue)"
          />
          <StatPill
            label="High-action"
            value={<MonoValue value={summary.highAction} />}
            accent="var(--accent-emerald)"
          />
        </div>
      </header>

      {/* ---- Chart -------------------------------------------------------- */}
      <Panel
        eyebrow="Momentum timeline"
        title="Signal momentum over time"
        index={0}
      >
        {pulseQuery.isLoading ? (
          <ChartLoading />
        ) : pulseQuery.isError ? (
          <ErrorState
            message={
              pulseQuery.error instanceof Error
                ? pulseQuery.error.message
                : "Failed to load the Industry Pulse."
            }
            onRetry={() => pulseQuery.refetch()}
          />
        ) : (
          <MomentumChart items={filtered} height={360} />
        )}
      </Panel>

      {/* ---- Filters ------------------------------------------------------ */}
      {!pulseQuery.isLoading && !pulseQuery.isError && items.length > 0 ? (
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div
            className="flex flex-wrap items-center gap-2"
            role="group"
            aria-label="Filter signals by source"
          >
            {SOURCES.map((source) => {
              const Icon = SOURCE_ICON[source];
              const accent = SOURCE_ACCENT[source];
              const count = counts.get(source) ?? 0;
              const isActive = active.has(source);
              const disabled = count === 0;
              return (
                <button
                  key={source}
                  type="button"
                  onClick={() => toggleSource(source)}
                  disabled={disabled}
                  aria-pressed={isActive}
                  className={cn(
                    "mono inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-[0.75rem] font-semibold transition-colors",
                    disabled && "cursor-not-allowed opacity-40",
                  )}
                  style={{
                    color: isActive ? accent : "var(--text-secondary)",
                    background: isActive
                      ? `color-mix(in srgb, ${accent} 16%, transparent)`
                      : "color-mix(in srgb, var(--bg-elevated) 60%, transparent)",
                    border: `1px solid ${
                      isActive
                        ? `color-mix(in srgb, ${accent} 40%, transparent)`
                        : "var(--border-hair)"
                    }`,
                  }}
                >
                  <Icon className="h-3 w-3" aria-hidden="true" />
                  {source}
                  <span className="text-[color:var(--text-muted)]">{count}</span>
                </button>
              );
            })}
            {active.size > 0 ? (
              <button
                type="button"
                onClick={() => setActive(new Set())}
                className="mono rounded-full px-2.5 py-1 text-[0.6875rem] text-[color:var(--text-muted)] underline decoration-dotted underline-offset-2 transition-colors hover:text-[color:var(--text-secondary)]"
              >
                Clear
              </button>
            ) : null}
          </div>

          {/* Sort */}
          <div
            className="inline-flex items-center gap-1 rounded-lg p-1 hairline"
            role="group"
            aria-label="Sort signals"
            style={{
              background:
                "color-mix(in srgb, var(--bg-elevated) 60%, transparent)",
            }}
          >
            {SORTS.map((option) => {
              const isActive = sort === option.value;
              return (
                <button
                  key={option.value}
                  type="button"
                  onClick={() => setSort(option.value)}
                  aria-pressed={isActive}
                  className={cn(
                    "mono rounded-md px-2.5 py-1 text-[0.6875rem] font-semibold transition-colors",
                    isActive
                      ? "text-[color:var(--text-primary)]"
                      : "text-[color:var(--text-secondary)] hover:text-[color:var(--text-primary)]",
                  )}
                  style={
                    isActive
                      ? {
                          background:
                            "color-mix(in srgb, var(--accent-cyan) 14%, transparent)",
                          border:
                            "1px solid color-mix(in srgb, var(--accent-cyan) 30%, transparent)",
                        }
                      : { border: "1px solid transparent" }
                  }
                >
                  {option.label}
                </button>
              );
            })}
          </div>
        </div>
      ) : null}

      {/* ---- Gap cards ---------------------------------------------------- */}
      {pulseQuery.isLoading ? (
        <ListLoading />
      ) : pulseQuery.isError ? null : items.length === 0 ? (
        <EmptyState />
      ) : filtered.length === 0 ? (
        <div className="flex min-h-32 items-center justify-center rounded-lg p-8 text-center hairline">
          <p className="text-sm text-[color:var(--text-secondary)]">
            No signals match the selected sources.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {filtered.map((item, i) => (
            <GapCard key={item.id} item={item} index={i} />
          ))}
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* States                                                             */
/* ------------------------------------------------------------------ */

function ChartLoading() {
  return (
    <div className="flex h-[360px] flex-col items-center justify-center gap-3">
      <Loader2
        className="h-6 w-6 animate-spin"
        style={{ color: "var(--accent-cyan)" }}
        aria-hidden="true"
      />
      <p className="mono text-xs text-[color:var(--text-secondary)]">
        Tuning the pulse…
      </p>
    </div>
  );
}

function ListLoading() {
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
      {Array.from({ length: 6 }).map((_, i) => (
        <div
          key={i}
          className="glass h-56 animate-pulse p-4"
          aria-hidden="true"
          style={{ opacity: 0.5 }}
        />
      ))}
    </div>
  );
}

function EmptyState() {
  return (
    <div className="flex min-h-40 flex-col items-center justify-center gap-3 p-8 text-center">
      <Radio
        className="h-8 w-8"
        style={{ color: "var(--text-muted)" }}
        aria-hidden="true"
      />
      <p className="max-w-md text-sm text-[color:var(--text-secondary)]">
        The pulse is quiet right now. New research, releases, and advisories
        will appear here as they gain momentum.
      </p>
    </div>
  );
}

function ErrorState({
  message,
  onRetry,
}: {
  message: string;
  onRetry: () => void;
}) {
  return (
    <div className="flex h-[360px] flex-col items-center justify-center gap-3 p-8 text-center">
      <AlertTriangle
        className="h-8 w-8"
        style={{ color: "var(--accent-rose)" }}
        aria-hidden="true"
      />
      <p className="max-w-md text-sm text-[color:var(--text-secondary)]">
        {message}
      </p>
      <button
        type="button"
        onClick={onRetry}
        className="mono rounded-md px-3 py-1.5 text-[0.6875rem] font-semibold transition-colors hover:brightness-125"
        style={{
          color: "var(--accent-cyan)",
          background: "color-mix(in srgb, var(--accent-cyan) 12%, transparent)",
          border: "1px solid color-mix(in srgb, var(--accent-cyan) 30%, transparent)",
        }}
      >
        Retry
      </button>
    </div>
  );
}
