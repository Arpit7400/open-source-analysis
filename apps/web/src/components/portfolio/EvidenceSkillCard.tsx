"use client";

/**
 * A single skill in the public portfolio: name, category, verification badge,
 * a confidence meter, and — on expand — the underlying evidence (fetched
 * lazily from the API), each item itself labelled by verification level with a
 * link to its source.
 */

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { ChevronDown, ExternalLink } from "lucide-react";
import * as api from "@/lib/api";
import type { Skill, SkillEvidenceResponse } from "@/lib/types";
import { cn } from "@/lib/cn";
import {
  VerificationBadge,
  verificationColor,
} from "@/components/skills/VerificationBadge";

interface Props {
  skill: Skill;
  index: number;
}

export function EvidenceSkillCard({ skill, index }: Props) {
  const reduceMotion = useReducedMotion();
  const [open, setOpen] = useState(false);
  const accent = verificationColor(skill.verification_level);

  const evidenceQuery = useQuery<SkillEvidenceResponse>({
    queryKey: ["skill-evidence", skill.id],
    queryFn: ({ signal }) => api.getSkillEvidence(skill.id, signal),
    enabled: open, // fetch only when the user expands the card
  });

  const confidencePct = Math.round(skill.confidence * 100);

  return (
    <motion.li
      initial={reduceMotion ? undefined : { opacity: 0, y: 10 }}
      animate={reduceMotion ? undefined : { opacity: 1, y: 0 }}
      transition={reduceMotion ? undefined : { delay: Math.min(index * 0.03, 0.3) }}
      className="glass flex flex-col gap-3 rounded-xl p-4"
      style={{ borderColor: `${accent}33` }}
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <h3 className="font-medium text-[var(--text-primary)]">{skill.name}</h3>
          <p className="text-xs uppercase tracking-wide text-[var(--text-muted)]">
            {skill.category}
          </p>
        </div>
        <VerificationBadge level={skill.verification_level} />
      </div>

      {/* confidence meter */}
      <div className="flex items-center gap-2">
        <div
          className="h-1.5 flex-1 overflow-hidden rounded-full bg-[var(--bg-elevated)]"
          role="progressbar"
          aria-valuenow={confidencePct}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={`${skill.name} confidence`}
        >
          <motion.div
            className="h-full rounded-full"
            style={{ backgroundColor: accent }}
            initial={reduceMotion ? undefined : { width: 0 }}
            animate={{ width: `${confidencePct}%` }}
            transition={reduceMotion ? undefined : { duration: 0.6, ease: "easeOut" }}
          />
        </div>
        <span className="font-mono text-xs text-[var(--text-secondary)]">{confidencePct}%</span>
      </div>

      {skill.last_change_reason ? (
        <p className="text-xs text-[var(--text-muted)]">Why: {skill.last_change_reason}</p>
      ) : null}

      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="flex items-center gap-1 self-start text-xs text-[var(--accent-cyan)] hover:underline"
      >
        <ChevronDown className={cn("h-3.5 w-3.5 transition-transform", open && "rotate-180")} />
        {open ? "Hide evidence" : `Evidence (${skill.evidence_ids.length})`}
      </button>

      <AnimatePresence initial={false}>
        {open ? (
          <motion.div
            initial={reduceMotion ? undefined : { height: 0, opacity: 0 }}
            animate={reduceMotion ? undefined : { height: "auto", opacity: 1 }}
            exit={reduceMotion ? undefined : { height: 0, opacity: 0 }}
            className="overflow-hidden"
          >
            {evidenceQuery.isLoading ? (
              <p className="py-2 text-xs text-[var(--text-muted)]">Loading evidence…</p>
            ) : evidenceQuery.data && evidenceQuery.data.evidence.length > 0 ? (
              <ul className="flex flex-col gap-2 pt-1">
                {evidenceQuery.data.evidence.map((ev) => (
                  <li
                    key={ev.id}
                    className="rounded-lg border border-[var(--border-hair)] bg-[var(--bg-elevated)] p-2"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-[10px] uppercase tracking-wide text-[var(--text-muted)]">
                        {ev.type}
                      </span>
                      <VerificationBadge level={ev.verification_level} />
                    </div>
                    <p className="mt-1 text-xs text-[var(--text-secondary)]">{ev.summary}</p>
                    {ev.source_url ? (
                      <a
                        href={ev.source_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="mt-1 inline-flex items-center gap-1 text-[10px] text-[var(--accent-cyan)] hover:underline"
                      >
                        <ExternalLink className="h-3 w-3" />
                        source
                      </a>
                    ) : null}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="py-2 text-xs text-[var(--text-muted)]">
                No evidence records linked yet.
              </p>
            )}
          </motion.div>
        ) : null}
      </AnimatePresence>
    </motion.li>
  );
}

export default EvidenceSkillCard;
