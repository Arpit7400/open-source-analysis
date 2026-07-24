"use client";

import { Suspense, useMemo, useState } from "react";
import dynamic from "next/dynamic";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import {
  AlertTriangle,
  Boxes,
  Gauge,
  Loader2,
  Orbit,
  Sparkles,
  Table2,
} from "lucide-react";
import * as api from "@/lib/api";
import type { Skill, SkillsResponse } from "@/lib/types";
import { cn } from "@/lib/cn";
import { Eyebrow } from "@/components/ui/Eyebrow";
import { Panel } from "@/components/ui/Panel";
import { StatPill } from "@/components/ui/StatPill";
import { MonoValue } from "@/components/ui/MonoValue";
import { SkillTableFallback } from "@/components/skills/SkillTableFallback";
import {
  WebGLGate,
  type FallbackReason,
  setPerformanceMode,
} from "@/components/skills/WebGLGate";

/**
 * The 3D scene is heavy (three.js + drei). Load it only on the client, only
 * when actually needed, and never during SSR.
 */
const Constellation = dynamic(
  () => import("@/components/skills/Constellation").then((m) => m.Constellation),
  {
    ssr: false,
    loading: () => <CanvasLoading />,
  },
);

type ViewMode = "constellation" | "table";

const REASON_COPY: Record<FallbackReason, string | null> = {
  none: null,
  probing: "Detecting graphics capabilities…",
  "no-webgl":
    "WebGL is unavailable in this browser, so the accessible table view is shown.",
  "reduced-motion":
    "Reduced-motion is enabled, so the animated 3D view is replaced by the table.",
  "performance-mode":
    "Performance Mode is on, so the 3D view is disabled. You can re-enable it below.",
};

export default function SkillsPage() {
  const [view, setView] = useState<ViewMode>("constellation");

  const skillsQuery = useQuery<SkillsResponse>({
    queryKey: ["skills"],
    queryFn: ({ signal }) => api.getSkills(signal),
  });

  const skills: Skill[] = useMemo(
    () => skillsQuery.data?.skills ?? [],
    [skillsQuery.data],
  );

  const summary = useMemo(() => computeSummary(skills), [skills]);

  return (
    <div className="mx-auto flex w-full max-w-[1400px] flex-col gap-5 px-4 py-6 md:px-6">
      {/* ---- Header ------------------------------------------------------- */}
      <header className="flex flex-col gap-3">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div className="flex flex-col gap-1.5">
            <Eyebrow className="flex items-center gap-2">
              <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
              Profile Brain
            </Eyebrow>
            <h1 className="text-2xl font-semibold tracking-tight text-[color:var(--text-primary)]">
              Skill Constellation
            </h1>
            <p className="max-w-2xl text-sm text-[color:var(--text-secondary)]">
              Every node is a skill. Size scales with evidence strength, glow
              with confidence, and pulse with recency. Lines connect related
              skills. Tinted by how strongly each skill is verified.
            </p>
          </div>

          <ViewToggle view={view} onChange={setView} />
        </div>

        {/* Summary stats */}
        <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3 lg:grid-cols-5">
          <StatPill
            label="Skills"
            icon={<Boxes className="h-3 w-3" aria-hidden="true" />}
            value={<MonoValue value={summary.total} />}
            accent="var(--accent-cyan)"
          />
          <StatPill
            label="Verified"
            icon={<Sparkles className="h-3 w-3" aria-hidden="true" />}
            value={<MonoValue value={summary.verified} />}
            accent="var(--accent-emerald)"
          />
          <StatPill
            label="Avg confidence"
            icon={<Gauge className="h-3 w-3" aria-hidden="true" />}
            value={<MonoValue value={summary.avgConfidence} suffix="%" />}
            accent="var(--accent-violet)"
          />
          <StatPill
            label="Evidence"
            value={<MonoValue value={summary.evidence} />}
            accent="var(--accent-blue)"
          />
          <StatPill
            label="Relationships"
            value={<MonoValue value={summary.relationships} />}
            accent="var(--accent-amber)"
          />
        </div>
      </header>

      {/* ---- Body --------------------------------------------------------- */}
      <Panel flush className="min-h-[560px]">
        {skillsQuery.isLoading ? (
          <CanvasLoading />
        ) : skillsQuery.isError ? (
          <ErrorState
            message={
              skillsQuery.error instanceof Error
                ? skillsQuery.error.message
                : "Failed to load skills."
            }
            onRetry={() => skillsQuery.refetch()}
          />
        ) : skills.length === 0 ? (
          <EmptyState />
        ) : view === "table" ? (
          <div className="p-4">
            <SkillTableFallback skills={skills} />
          </div>
        ) : (
          <WebGLGate
            fallback={
              <div className="p-4">
                <SkillTableFallback skills={skills} />
              </div>
            }
            renderFallbackNotice={({ reason, canOverride, enableThreeD }) => {
              const copy = REASON_COPY[reason];
              if (!copy) return null;
              return (
                <div
                  className="mx-4 mt-4 flex items-center gap-2.5 rounded-lg px-3 py-2 text-[0.8125rem] hairline"
                  style={{
                    background:
                      "color-mix(in srgb, var(--accent-amber) 8%, transparent)",
                    color: "var(--text-secondary)",
                  }}
                  role="status"
                >
                  <AlertTriangle
                    className="h-4 w-4 shrink-0"
                    style={{ color: "var(--accent-amber)" }}
                    aria-hidden="true"
                  />
                  <span>{copy}</span>
                  {canOverride ? (
                    <button
                      type="button"
                      onClick={enableThreeD}
                      className="mono ml-auto shrink-0 rounded-md px-2 py-1 text-[0.6875rem] font-semibold transition-colors hover:brightness-125"
                      style={{
                        color: "var(--accent-cyan)",
                        background:
                          "color-mix(in srgb, var(--accent-cyan) 12%, transparent)",
                        border:
                          "1px solid color-mix(in srgb, var(--accent-cyan) 30%, transparent)",
                      }}
                    >
                      Enable 3D
                    </button>
                  ) : null}
                </div>
              );
            }}
          >
            <Suspense fallback={<CanvasLoading />}>
              <Constellation skills={skills} height={560} />
            </Suspense>
          </WebGLGate>
        )}
      </Panel>

      {/* Performance-mode hint when in the 3D view */}
      {view === "constellation" && skills.length > 0 ? (
        <p className="text-center text-[0.75rem] text-[color:var(--text-muted)]">
          Drag to orbit · scroll to zoom · hover a node for detail. Prefer a
          static view?{" "}
          <button
            type="button"
            onClick={() => {
              setPerformanceMode(true);
              setView("table");
            }}
            className="mono underline decoration-dotted underline-offset-2 hover:text-[color:var(--text-secondary)]"
          >
            Enable Performance Mode
          </button>
          .
        </p>
      ) : null}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* View toggle                                                        */
/* ------------------------------------------------------------------ */

function ViewToggle({
  view,
  onChange,
}: {
  view: ViewMode;
  onChange: (v: ViewMode) => void;
}) {
  const options: { value: ViewMode; label: string; Icon: typeof Orbit }[] = [
    { value: "constellation", label: "Constellation", Icon: Orbit },
    { value: "table", label: "Table", Icon: Table2 },
  ];

  return (
    <div
      className="relative inline-flex items-center gap-1 rounded-lg p-1 hairline"
      role="group"
      aria-label="Skill view mode"
      style={{
        background: "color-mix(in srgb, var(--bg-elevated) 60%, transparent)",
      }}
    >
      {options.map(({ value, label, Icon }) => {
        const active = view === value;
        return (
          <button
            key={value}
            type="button"
            onClick={() => onChange(value)}
            aria-pressed={active}
            className={cn(
              "relative flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
              active
                ? "text-[color:var(--text-primary)]"
                : "text-[color:var(--text-secondary)] hover:text-[color:var(--text-primary)]",
            )}
          >
            {active ? (
              <motion.span
                layoutId="skill-view-toggle"
                className="absolute inset-0 rounded-md"
                style={{
                  background:
                    "color-mix(in srgb, var(--accent-cyan) 14%, transparent)",
                  border:
                    "1px solid color-mix(in srgb, var(--accent-cyan) 30%, transparent)",
                }}
                transition={{ type: "spring", stiffness: 320, damping: 30 }}
                aria-hidden="true"
              />
            ) : null}
            <Icon className="relative h-4 w-4" aria-hidden="true" />
            <span className="relative">{label}</span>
          </button>
        );
      })}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* States                                                             */
/* ------------------------------------------------------------------ */

function CanvasLoading() {
  return (
    <div className="flex min-h-[560px] flex-1 flex-col items-center justify-center gap-3 text-center">
      <Loader2
        className="h-6 w-6 animate-spin"
        style={{ color: "var(--accent-cyan)" }}
        aria-hidden="true"
      />
      <p className="mono text-xs text-[color:var(--text-secondary)]">
        Assembling constellation…
      </p>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="flex min-h-[560px] flex-1 flex-col items-center justify-center gap-3 p-8 text-center">
      <Orbit
        className="h-8 w-8"
        style={{ color: "var(--text-muted)" }}
        aria-hidden="true"
      />
      <p className="max-w-md text-sm text-[color:var(--text-secondary)]">
        No skills yet. Run a repository analysis in the Command Center or ingest
        a resume, and verified skills will populate this constellation.
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
    <div className="flex min-h-[560px] flex-1 flex-col items-center justify-center gap-3 p-8 text-center">
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

/* ------------------------------------------------------------------ */
/* Summary                                                            */
/* ------------------------------------------------------------------ */

interface SkillSummary {
  total: number;
  verified: number;
  avgConfidence: number;
  evidence: number;
  relationships: number;
}

const VERIFIED_LEVELS = new Set([
  "TOOL_VERIFIED",
  "HUMAN_REVIEWED",
  "EXTERNALLY_VALIDATED",
]);

function computeSummary(skills: Skill[]): SkillSummary {
  if (skills.length === 0) {
    return {
      total: 0,
      verified: 0,
      avgConfidence: 0,
      evidence: 0,
      relationships: 0,
    };
  }

  let confidenceSum = 0;
  let verified = 0;
  let evidence = 0;
  const edgeKeys = new Set<string>();
  const ids = new Set(skills.map((s) => s.id));

  for (const skill of skills) {
    confidenceSum += Number.isFinite(skill.confidence) ? skill.confidence : 0;
    if (VERIFIED_LEVELS.has(skill.verification_level)) verified += 1;
    evidence += skill.evidence_ids.length;
    for (const relatedId of skill.related_skill_ids) {
      if (!ids.has(relatedId)) continue;
      const key =
        skill.id < relatedId
          ? `${skill.id}|${relatedId}`
          : `${relatedId}|${skill.id}`;
      edgeKeys.add(key);
    }
  }

  return {
    total: skills.length,
    verified,
    avgConfidence: Math.round((confidenceSum / skills.length) * 100),
    evidence,
    relationships: edgeKeys.size,
  };
}
