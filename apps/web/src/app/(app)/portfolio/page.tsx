"use client";

/**
 * Public Evidence Portfolio (Phase 15).
 *
 * A user-approved public view of verified skills, projects, merged
 * contributions, and evidence — with EVERY claim labelled by its verification
 * level (declared -> inferred -> tool-verified -> human-reviewed ->
 * externally-validated) so nothing overstates what the evidence supports.
 *
 * Read-only and static-first: it renders the real profile/skills the backend
 * exposes; a "verified-only" toggle models the user's approval control over
 * what is public.
 */

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { motion, useReducedMotion } from "framer-motion";
import {
  BadgeCheck,
  GitMerge,
  ShieldCheck,
  Sparkles,
  Trophy,
} from "lucide-react";
import * as api from "@/lib/api";
import type { Profile, Skill, SkillsResponse, VerificationLevel } from "@/lib/types";
import { Eyebrow } from "@/components/ui/Eyebrow";
import { Panel } from "@/components/ui/Panel";
import { StatPill } from "@/components/ui/StatPill";
import { MonoValue } from "@/components/ui/MonoValue";
import { EvidenceSkillCard } from "@/components/portfolio/EvidenceSkillCard";
import { VerificationLegend } from "@/components/portfolio/VerificationLegend";

/** Verification levels that count as "verified" for the public toggle. */
const VERIFIED_LEVELS: ReadonlySet<VerificationLevel> = new Set([
  "TOOL_VERIFIED",
  "HUMAN_REVIEWED",
  "EXTERNALLY_VALIDATED",
]);

/** Rank used to sort strongest evidence first. */
const LEVEL_RANK: Record<VerificationLevel, number> = {
  EXTERNALLY_VALIDATED: 5,
  HUMAN_REVIEWED: 4,
  TOOL_VERIFIED: 3,
  AI_INFERRED: 2,
  SELF_DECLARED: 1,
};

export default function PortfolioPage() {
  const reduceMotion = useReducedMotion();
  const [verifiedOnly, setVerifiedOnly] = useState(false);

  const profileQuery = useQuery<Profile>({
    queryKey: ["profile"],
    queryFn: ({ signal }) => api.getProfile(signal),
  });
  const skillsQuery = useQuery<SkillsResponse>({
    queryKey: ["skills"],
    queryFn: ({ signal }) => api.getSkills(signal),
  });

  const profile = profileQuery.data;
  const skills = useMemo(() => {
    const all: Skill[] = skillsQuery.data?.skills ?? [];
    const filtered = verifiedOnly
      ? all.filter((s) => VERIFIED_LEVELS.has(s.verification_level))
      : all;
    return [...filtered].sort(
      (a, b) =>
        (LEVEL_RANK[b.verification_level] ?? 0) - (LEVEL_RANK[a.verification_level] ?? 0) ||
        b.confidence - a.confidence,
    );
  }, [skillsQuery.data, verifiedOnly]);

  const externallyValidated = skills.filter(
    (s) => s.verification_level === "EXTERNALLY_VALIDATED",
  ).length;

  const enter = reduceMotion
    ? {}
    : { initial: { opacity: 0, y: 12 }, animate: { opacity: 1, y: 0 } };

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6 px-4 py-8">
      {/* ---- Header / identity ------------------------------------------- */}
      <motion.header {...enter} className="glass flex flex-col gap-4 rounded-2xl p-6">
        <Eyebrow>Public Evidence Portfolio</Eyebrow>
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="text-3xl font-semibold tracking-tight text-[var(--text-primary)]">
              {profile?.name ?? "…"}
            </h1>
            <p className="mt-1 text-[var(--text-secondary)]">
              {profile?.headline ?? "Evidence-backed engineering profile"}
            </p>
          </div>
          <div className="flex flex-wrap gap-3">
            <StatPill
              label="Verified skills"
              icon={<ShieldCheck className="h-4 w-4" />}
              value={<MonoValue value={profile?.verified_skill_count ?? 0} />}
            />
            <StatPill
              label="Merged PRs"
              icon={<GitMerge className="h-4 w-4" />}
              value={<MonoValue value={profile?.merged_prs ?? 0} />}
            />
            <StatPill
              label="Evidence items"
              icon={<BadgeCheck className="h-4 w-4" />}
              value={<MonoValue value={profile?.evidence_count ?? 0} />}
            />
            <StatPill
              label="Externally validated"
              icon={<Trophy className="h-4 w-4" />}
              value={<MonoValue value={externallyValidated} />}
            />
          </div>
        </div>

        {profile?.goals?.length ? (
          <div className="flex flex-wrap items-center gap-2 pt-2">
            <Sparkles className="h-4 w-4 text-[var(--accent-cyan)]" aria-hidden />
            {profile.goals.map((g) => (
              <span
                key={g}
                className="rounded-full border border-[var(--border-hair)] bg-[var(--bg-elevated)] px-3 py-1 text-xs text-[var(--text-secondary)]"
              >
                {g}
              </span>
            ))}
          </div>
        ) : null}
      </motion.header>

      {/* ---- Verification legend + approval toggle ----------------------- */}
      <Panel
        eyebrow="Trust model"
        title="How each claim is verified"
        index={1}
        actions={
          <label className="flex cursor-pointer items-center gap-2 text-xs text-[var(--text-secondary)]">
            <input
              type="checkbox"
              className="accent-[var(--accent-cyan)]"
              checked={verifiedOnly}
              onChange={(e) => setVerifiedOnly(e.target.checked)}
            />
            Show verified-only (public view)
          </label>
        }
      >
        <VerificationLegend />
      </Panel>

      {/* ---- Skills with evidence ---------------------------------------- */}
      <Panel eyebrow="Evidence" title="Verified skills" index={2} flush>
        {skillsQuery.isLoading ? (
          <p className="p-6 text-sm text-[var(--text-muted)]">Loading evidence…</p>
        ) : skills.length === 0 ? (
          <p className="p-6 text-sm text-[var(--text-muted)]">
            No skills to show at this verification level yet.
          </p>
        ) : (
          <ul className="grid gap-3 p-4 sm:grid-cols-2 lg:grid-cols-3">
            {skills.map((s, i) => (
              <EvidenceSkillCard key={s.id} skill={s} index={i} />
            ))}
          </ul>
        )}
      </Panel>

      <p className="pb-4 text-center text-xs text-[var(--text-muted)]">
        This portfolio only shows information the user has approved for public display.
        Verification labels distinguish declared claims from externally validated evidence.
      </p>
    </div>
  );
}
