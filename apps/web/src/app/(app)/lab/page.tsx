"use client";

import { useCallback, useMemo, useState } from "react";
import Link from "next/link";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { ArrowRight, FlaskConical, Network, SlidersHorizontal } from "lucide-react";
import { useMissionStream } from "@/lib/useMissionStream";
import {
  selectCandidateList,
  useMissionStore,
  type MissionStoreState,
} from "@/lib/store";
import type {
  Candidate,
  Finding,
  FindingCategory,
  Severity,
} from "@/lib/types";
import { cn } from "@/lib/cn";
import { Panel } from "@/components/ui/Panel";
import { Badge } from "@/components/ui/Badge";
import { Eyebrow } from "@/components/ui/Eyebrow";
import { FindingCard } from "@/components/lab/FindingCard";
import { CandidateComparison } from "@/components/lab/CandidateComparison";
import { DiffViewer } from "@/components/lab/DiffViewer";
import { VerificationMatrix } from "@/components/lab/VerificationMatrix";
import { RiskPanel } from "@/components/lab/RiskPanel";
import { ApprovalPanel } from "@/components/lab/ApprovalPanel";

const ALL_CATEGORIES: readonly FindingCategory[] = [
  "ARCHITECTURE",
  "CODE_QUALITY",
  "DOCS_DRIFT",
  "DEPENDENCY",
  "TEST_QUALITY",
  "TYPING",
  "API_CONSISTENCY",
  "SECURITY_SMELL",
  "DEPRECATION",
  "RUNTIME",
] as const;

const SEVERITY_ORDER: readonly Severity[] = [
  "CRITICAL",
  "HIGH",
  "MEDIUM",
  "LOW",
  "INFO",
] as const;

const SEVERITY_RANK: Record<Severity, number> = {
  CRITICAL: 5,
  HIGH: 4,
  MEDIUM: 3,
  LOW: 2,
  INFO: 1,
};

/* ------------------------------------------------------------------ */
/* Store selectors                                                    */
/* ------------------------------------------------------------------ */

const selectMissionId = (s: MissionStoreState) => s.missionId;
const selectRepoUrl = (s: MissionStoreState) => s.repoUrl;
const selectFindings = (s: MissionStoreState) => s.findings;
const selectApproval = (s: MissionStoreState) => s.approval;
const selectSelectedCandidateId = (s: MissionStoreState) =>
  s.selectedCandidateId;
const selectSelect = (s: MissionStoreState) => s.selectCandidateId;

export default function LabPage() {
  const reduceMotion = useReducedMotion();

  const missionId = useMissionStore(selectMissionId);
  const repoUrl = useMissionStore(selectRepoUrl);
  const findings = useMissionStore(selectFindings);
  const candidates = useMissionStore(selectCandidateList);
  const approval = useMissionStore(selectApproval);
  const selectedCandidateId = useMissionStore(selectSelectedCandidateId);
  const selectCandidateId = useMissionStore(selectSelect);

  // Keep the mission stream alive if the user navigates straight here.
  useMissionStream(missionId);

  const [activeCategories, setActiveCategories] = useState<
    Set<FindingCategory>
  >(new Set());
  const [activeSeverities, setActiveSeverities] = useState<Set<Severity>>(
    new Set(),
  );

  const toggleCategory = useCallback((category: FindingCategory) => {
    setActiveCategories((prev) => {
      const next = new Set(prev);
      if (next.has(category)) {
        next.delete(category);
      } else {
        next.add(category);
      }
      return next;
    });
  }, []);

  const toggleSeverity = useCallback((severity: Severity) => {
    setActiveSeverities((prev) => {
      const next = new Set(prev);
      if (next.has(severity)) {
        next.delete(severity);
      } else {
        next.add(severity);
      }
      return next;
    });
  }, []);

  const clearFilters = useCallback(() => {
    setActiveCategories(new Set());
    setActiveSeverities(new Set());
  }, []);

  // Categories actually present in the current mission's findings.
  const presentCategories = useMemo(() => {
    const present = new Set<FindingCategory>();
    for (const f of findings) present.add(f.category);
    return ALL_CATEGORIES.filter((c) => present.has(c));
  }, [findings]);

  const filteredFindings = useMemo(() => {
    const list = findings.filter((f) => {
      const catOk =
        activeCategories.size === 0 || activeCategories.has(f.category);
      const sevOk =
        activeSeverities.size === 0 || activeSeverities.has(f.severity);
      return catOk && sevOk;
    });
    // Sort by severity desc, then confidence desc for a stable, useful order.
    return [...list].sort((a, b) => {
      const sev = SEVERITY_RANK[b.severity] - SEVERITY_RANK[a.severity];
      if (sev !== 0) return sev;
      return b.confidence - a.confidence;
    });
  }, [findings, activeCategories, activeSeverities]);

  const activeCandidate = useMemo<Candidate | null>(() => {
    if (candidates.length === 0) return null;
    const ordered = [...candidates].sort((a, b) =>
      a.candidate_id.localeCompare(b.candidate_id),
    );
    const found =
      selectedCandidateId != null
        ? ordered.find((c) => c.candidate_id === selectedCandidateId)
        : undefined;
    return found ?? ordered[0] ?? null;
  }, [candidates, selectedCandidateId]);

  const filtersActive =
    activeCategories.size > 0 || activeSeverities.size > 0;

  if (!missionId) {
    return <EmptyState reduceMotion={Boolean(reduceMotion)} />;
  }

  return (
    <div className="mx-auto flex w-full max-w-[112rem] flex-col gap-3 p-3 lg:p-4">
      {/* Page header */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-col gap-1">
          <Eyebrow className="text-[color:var(--accent-violet)]">
            Contribution Laboratory
          </Eyebrow>
          <div className="flex items-center gap-2">
            <FlaskConical
              className="h-4 w-4 text-[color:var(--accent-violet)]"
              aria-hidden="true"
            />
            <h1 className="text-base font-semibold text-[color:var(--text-primary)]">
              Findings, candidates &amp; verification
            </h1>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {repoUrl ? (
            <span className="mono hidden text-xs text-[color:var(--text-muted)] sm:inline">
              {repoUrl.replace(/^https?:\/\//, "")}
            </span>
          ) : null}
          <span className="mono rounded-md px-2 py-1 text-[0.625rem] text-[color:var(--text-secondary)] hairline">
            {missionId}
          </span>
        </div>
      </div>

      {/* Three-column workspace */}
      <div className="grid grid-cols-1 gap-3 xl:grid-cols-[minmax(0,20rem)_minmax(0,1fr)_minmax(0,22rem)]">
        {/* LEFT — findings list */}
        <Panel
          eyebrow="Repo X-Ray"
          title={`Findings (${filteredFindings.length}/${findings.length})`}
          index={0}
          className="min-h-[24rem] xl:max-h-[calc(100vh-9rem)]"
          bodyClassName="gap-3 overflow-hidden"
          actions={
            filtersActive ? (
              <button
                type="button"
                onClick={clearFilters}
                className="mono text-[0.625rem] text-[color:var(--accent-cyan)] hover:underline"
              >
                clear
              </button>
            ) : null
          }
        >
          <FindingFilters
            categories={presentCategories}
            activeCategories={activeCategories}
            activeSeverities={activeSeverities}
            onToggleCategory={toggleCategory}
            onToggleSeverity={toggleSeverity}
            findings={findings}
          />

          <div className="flex min-h-0 flex-1 flex-col gap-2.5 overflow-y-auto pr-1">
            {findings.length === 0 ? (
              <FindingsEmpty />
            ) : filteredFindings.length === 0 ? (
              <p className="px-1 py-6 text-center text-xs text-[color:var(--text-muted)]">
                No findings match the active filters.
              </p>
            ) : (
              filteredFindings.map((finding, i) => (
                <FindingCard
                  key={finding.finding_id}
                  finding={finding}
                  index={i}
                />
              ))
            )}
          </div>
        </Panel>

        {/* CENTER — candidate comparison + diff */}
        <div className="flex min-h-0 flex-col gap-3">
          <Panel
            eyebrow="Fix candidates"
            title="Candidate comparison"
            index={1}
            bodyClassName="gap-3"
          >
            <CandidateComparison
              candidates={candidates}
              selectedCandidateId={selectedCandidateId}
              onSelect={selectCandidateId}
            />
          </Panel>

          <Panel
            eyebrow="Candidate diff (Monaco)"
            title="Side-by-side changes"
            index={2}
            flush
            className="min-h-[22rem] flex-1"
            bodyClassName="p-3"
          >
            <DiffViewer candidate={activeCandidate} className="flex-1" />
          </Panel>
        </div>

        {/* RIGHT — verification + risk + approval */}
        <div className="flex min-h-0 flex-col gap-3">
          <Panel
            eyebrow="Independent verification"
            title="Verification matrix"
            index={2}
          >
            <VerificationMatrix candidate={activeCandidate} />
          </Panel>

          <Panel eyebrow="Blast radius" title="Risk panel" index={3}>
            <RiskPanel candidate={activeCandidate} />
          </Panel>

          <Panel
            eyebrow="Human-in-the-loop"
            title="Approval gate"
            index={4}
            active={Boolean(approval?.required && !approval.granted)}
          >
            <ApprovalPanel missionId={missionId} approval={approval} />
          </Panel>
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Filters                                                            */
/* ------------------------------------------------------------------ */

function FindingFilters({
  categories,
  activeCategories,
  activeSeverities,
  onToggleCategory,
  onToggleSeverity,
  findings,
}: {
  categories: readonly FindingCategory[];
  activeCategories: Set<FindingCategory>;
  activeSeverities: Set<Severity>;
  onToggleCategory: (category: FindingCategory) => void;
  onToggleSeverity: (severity: Severity) => void;
  findings: Finding[];
}) {
  const severityCounts = useMemo(() => {
    const counts: Record<Severity, number> = {
      CRITICAL: 0,
      HIGH: 0,
      MEDIUM: 0,
      LOW: 0,
      INFO: 0,
    };
    for (const f of findings) counts[f.severity] += 1;
    return counts;
  }, [findings]);

  const presentSeverities = SEVERITY_ORDER.filter(
    (s) => severityCounts[s] > 0,
  );

  if (findings.length === 0) return null;

  return (
    <div className="flex flex-col gap-2.5">
      <div className="flex flex-col gap-1.5">
        <span className="eyebrow flex items-center gap-1.5 text-[0.5625rem]">
          <SlidersHorizontal className="h-3 w-3" aria-hidden="true" />
          Severity
        </span>
        <div
          className="flex flex-wrap gap-1.5"
          role="group"
          aria-label="Filter findings by severity"
        >
          {presentSeverities.map((sev) => {
            const active = activeSeverities.has(sev);
            return (
              <FilterChip
                key={sev}
                active={active}
                onClick={() => onToggleSeverity(sev)}
                label={`${sev} ${severityCounts[sev]}`}
                ariaLabel={`Severity ${sev}, ${severityCounts[sev]} findings`}
              />
            );
          })}
        </div>
      </div>

      <div className="flex flex-col gap-1.5">
        <span className="eyebrow text-[0.5625rem]">Category</span>
        <div
          className="flex flex-wrap gap-1.5"
          role="group"
          aria-label="Filter findings by category"
        >
          {categories.map((cat) => {
            const active = activeCategories.has(cat);
            return (
              <FilterChip
                key={cat}
                active={active}
                onClick={() => onToggleCategory(cat)}
                label={cat}
                ariaLabel={`Category ${cat}`}
              />
            );
          })}
        </div>
      </div>
    </div>
  );
}

function FilterChip({
  active,
  onClick,
  label,
  ariaLabel,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
  ariaLabel: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      aria-label={ariaLabel}
      className={cn(
        "mono rounded-full px-2 py-0.5 text-[0.5625rem] font-semibold uppercase tracking-wider transition-colors hairline",
        active
          ? "text-[color:var(--text-primary)]"
          : "text-[color:var(--text-muted)] hover:text-[color:var(--text-secondary)]",
      )}
      style={{
        background: active
          ? "color-mix(in srgb, var(--accent-cyan) 16%, transparent)"
          : "transparent",
        borderColor: active
          ? "color-mix(in srgb, var(--accent-cyan) 40%, transparent)"
          : undefined,
      }}
    >
      {label}
    </button>
  );
}

/* ------------------------------------------------------------------ */
/* Empty states                                                       */
/* ------------------------------------------------------------------ */

function FindingsEmpty() {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-2 p-6 text-center">
      <div className="cf-dot-pulse h-2 w-2 rounded-full bg-[color:var(--accent-cyan)]" />
      <p className="text-xs text-[color:var(--text-secondary)]">
        Waiting for findings…
      </p>
      <p className="text-[0.625rem] text-[color:var(--text-muted)]">
        Static and runtime agents stream findings as the mission runs.
      </p>
    </div>
  );
}

function EmptyState({ reduceMotion }: { reduceMotion: boolean }) {
  return (
    <div className="mx-auto flex min-h-[70vh] w-full max-w-2xl flex-col items-center justify-center px-6 text-center">
      <AnimatePresence>
        <motion.div
          initial={reduceMotion ? false : { opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ type: "spring", stiffness: 220, damping: 26 }}
          className="glass flex w-full flex-col items-center gap-4 p-8"
        >
          <span
            className="inline-flex h-12 w-12 items-center justify-center rounded-xl hairline"
            style={{
              color: "var(--accent-violet)",
              background:
                "color-mix(in srgb, var(--accent-violet) 12%, transparent)",
              borderColor:
                "color-mix(in srgb, var(--accent-violet) 30%, transparent)",
            }}
          >
            <FlaskConical className="h-6 w-6" aria-hidden="true" />
          </span>

          <Eyebrow className="text-[color:var(--accent-violet)]">
            Contribution Laboratory
          </Eyebrow>

          <h1 className="text-xl font-semibold text-[color:var(--text-primary)]">
            No active mission
          </h1>
          <p className="max-w-md text-sm leading-relaxed text-[color:var(--text-secondary)]">
            The lab inspects the findings, candidate fixes, and independent
            verification for a running mission. Launch one from the Command
            Center, then return here to review candidates and gate the draft.
          </p>

          <Link
            href="/command"
            className="group mt-1 inline-flex items-center gap-2 rounded-full px-5 py-2.5 text-sm font-semibold text-[#04121a] transition-transform hover:scale-[1.02] focus-visible:scale-[1.02]"
            style={{ background: "var(--accent-cyan)" }}
          >
            <Network className="h-4 w-4" aria-hidden="true" />
            Go to Command Center
            <ArrowRight
              className="h-4 w-4 transition-transform group-hover:translate-x-0.5"
              aria-hidden="true"
            />
          </Link>

          <div className="mt-2 flex flex-wrap items-center justify-center gap-2">
            <Badge tone="amber" dot>
              GitHub writes disabled
            </Badge>
            <Badge tone="violet">Human-gated drafts</Badge>
          </div>
        </motion.div>
      </AnimatePresence>
    </div>
  );
}
