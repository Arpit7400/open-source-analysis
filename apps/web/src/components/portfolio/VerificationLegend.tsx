"use client";

/**
 * A compact legend explaining the five verification levels, ordered from
 * weakest (declared) to strongest (externally validated). Reuses the shared
 * VerificationBadge so the colors match everywhere in the app.
 */

import type { VerificationLevel } from "@/lib/types";
import { VerificationBadge } from "@/components/skills/VerificationBadge";

const LEVELS: { level: VerificationLevel; meaning: string }[] = [
  { level: "SELF_DECLARED", meaning: "The user stated it. No supporting evidence yet." },
  { level: "AI_INFERRED", meaning: "Inferred by the system from context — not yet checked." },
  { level: "TOOL_VERIFIED", meaning: "Backed by a deterministic tool: tests, linters, parsers." },
  { level: "HUMAN_REVIEWED", meaning: "A human reviewed and confirmed the evidence." },
  {
    level: "EXTERNALLY_VALIDATED",
    meaning: "Validated outside the system — e.g. a merged open-source contribution.",
  },
];

export function VerificationLegend() {
  return (
    <ol className="grid gap-2 sm:grid-cols-2 lg:grid-cols-1">
      {LEVELS.map(({ level, meaning }) => (
        <li key={level} className="flex items-start gap-3 text-sm">
          <span className="mt-0.5 shrink-0">
            <VerificationBadge level={level} />
          </span>
          <span className="text-[var(--text-secondary)]">{meaning}</span>
        </li>
      ))}
    </ol>
  );
}

export default VerificationLegend;
