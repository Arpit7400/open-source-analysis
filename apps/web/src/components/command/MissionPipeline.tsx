"use client";

/**
 * MissionPipeline — the horizontal phase pipeline across the top of the
 * Command Center:
 *
 *   Intake → Static → Runtime → Aggregate → Duplicate → Fix → Verify → Approval
 *
 * Each segment reflects one phase of the mission. A phase is:
 *   - "done"    when its agent group(s) have all COMPLETED (or the mission is),
 *   - "active"  when any of its agents is RUNNING / VERIFYING (pulsing),
 *   - "pending" otherwise.
 *
 * The Approval segment is driven by the mission status / approval gate rather
 * than an agent group. An animated fill bar sweeps across as phases resolve.
 * Reduced-motion collapses the pulse/fill animation to instant state changes.
 */

import { useMemo } from "react";
import { motion, useReducedMotion } from "framer-motion";
import {
  Download,
  Cpu,
  FlaskConical,
  Layers,
  CopyCheck,
  Wrench,
  ShieldCheck,
  GitPullRequestArrow,
  type LucideIcon,
} from "lucide-react";
import type { AgentGroup, AgentState } from "@/lib/types";
import { selectAgentList, useMissionStore } from "@/lib/store";
import { cn } from "@/lib/cn";

type PhaseStatus = "pending" | "active" | "done";

interface PhaseDef {
  key: string;
  label: string;
  icon: LucideIcon;
  /** Agent groups that constitute this phase (empty => status-driven). */
  groups: AgentGroup[];
}

const PHASES: PhaseDef[] = [
  { key: "intake", label: "Intake", icon: Download, groups: ["INTAKE"] },
  { key: "static", label: "Static", icon: Cpu, groups: ["STATIC"] },
  { key: "runtime", label: "Runtime", icon: FlaskConical, groups: ["RUNTIME"] },
  { key: "aggregate", label: "Aggregate", icon: Layers, groups: ["AGGREGATE"] },
  { key: "duplicate", label: "Duplicate", icon: CopyCheck, groups: ["DUPLICATE"] },
  { key: "fix", label: "Fix", icon: Wrench, groups: ["FIX"] },
  { key: "verify", label: "Verify", icon: ShieldCheck, groups: ["VERIFY"] },
  { key: "approval", label: "Approval", icon: GitPullRequestArrow, groups: [] },
];

const ACTIVE_STATES: ReadonlySet<AgentState> = new Set<AgentState>([
  "RUNNING",
  "VERIFYING",
  "BLOCKED",
]);
const DONE_STATES: ReadonlySet<AgentState> = new Set<AgentState>([
  "COMPLETED",
  "REJECTED",
  "FAILED",
]);

const STATUS_COLOR: Record<PhaseStatus, string> = {
  pending: "var(--text-muted)",
  active: "var(--accent-cyan)",
  done: "var(--accent-emerald)",
};

export function MissionPipeline() {
  const reduceMotion = useReducedMotion();
  const agents = useMissionStore(selectAgentList);
  const status = useMissionStore((s) => s.status);
  const approval = useMissionStore((s) => s.approval);

  const phases = useMemo<Array<{ def: PhaseDef; status: PhaseStatus }>>(() => {
    const inGroup = (groups: AgentGroup[]) =>
      agents.filter((a) => groups.includes(a.group));

    return PHASES.map((def) => {
      if (def.key === "approval") {
        let phaseStatus: PhaseStatus = "pending";
        if (status === "COMPLETED") {
          phaseStatus = "done";
        } else if (
          status === "AWAITING_APPROVAL" ||
          (approval?.required && !approval.granted)
        ) {
          phaseStatus = "active";
        } else if (approval?.granted) {
          phaseStatus = "done";
        }
        return { def, status: phaseStatus };
      }

      const members = inGroup(def.groups);
      if (members.length === 0) {
        return { def, status: "pending" as PhaseStatus };
      }
      const anyActive = members.some((m) => ACTIVE_STATES.has(m.state));
      const allDone = members.every((m) => DONE_STATES.has(m.state));
      const phaseStatus: PhaseStatus = anyActive
        ? "active"
        : allDone
          ? "done"
          : "pending";
      return { def, status: phaseStatus };
    });
  }, [agents, status, approval]);

  // Overall completion fraction drives the sweeping fill bar under the rail.
  const fill = useMemo(() => {
    if (phases.length === 0) return 0;
    const score = phases.reduce((acc, p) => {
      if (p.status === "done") return acc + 1;
      if (p.status === "active") return acc + 0.5;
      return acc;
    }, 0);
    return score / phases.length;
  }, [phases]);

  return (
    <div
      className="relative w-full"
      role="group"
      aria-label="Mission phase pipeline"
    >
      {/* The connecting rail + animated fill sits behind the segments. */}
      <div
        className="pointer-events-none absolute left-4 right-4 top-[26px] h-0.5 rounded-full"
        style={{ background: "var(--border-hair)" }}
        aria-hidden="true"
      >
        <motion.div
          className="h-full rounded-full"
          style={{
            background:
              "linear-gradient(90deg, var(--accent-cyan), var(--accent-violet))",
            transformOrigin: "left center",
          }}
          initial={false}
          animate={{ scaleX: fill }}
          transition={
            reduceMotion
              ? { duration: 0 }
              : { type: "spring", stiffness: 120, damping: 26 }
          }
        />
      </div>

      <ol className="relative flex items-start justify-between gap-1">
        {phases.map(({ def, status: phaseStatus }, index) => {
          const Icon = def.icon;
          const color = STATUS_COLOR[phaseStatus];
          const isActive = phaseStatus === "active";
          const isDone = phaseStatus === "done";
          return (
            <li
              key={def.key}
              className="flex min-w-0 flex-1 flex-col items-center gap-1.5"
              aria-current={isActive ? "step" : undefined}
            >
              <motion.span
                className={cn(
                  "relative flex h-[52px] w-[52px] items-center justify-center rounded-xl",
                )}
                style={{
                  color,
                  background:
                    phaseStatus === "pending"
                      ? "color-mix(in srgb, var(--bg-elevated) 60%, transparent)"
                      : `color-mix(in srgb, ${color} 14%, transparent)`,
                  border: `1px solid ${
                    phaseStatus === "pending"
                      ? "var(--border-hair)"
                      : `color-mix(in srgb, ${color} 44%, transparent)`
                  }`,
                }}
                initial={false}
                animate={{
                  boxShadow:
                    isActive && !reduceMotion
                      ? [
                          `0 0 0 0 color-mix(in srgb, ${color} 40%, transparent)`,
                          `0 0 16px 2px color-mix(in srgb, ${color} 34%, transparent)`,
                          `0 0 0 0 color-mix(in srgb, ${color} 40%, transparent)`,
                        ]
                      : isDone
                        ? `0 0 12px -4px color-mix(in srgb, ${color} 60%, transparent)`
                        : "0 0 0 0 transparent",
                }}
                transition={
                  reduceMotion
                    ? { duration: 0 }
                    : isActive
                      ? { duration: 1.8, repeat: Infinity, ease: "easeInOut" }
                      : { duration: 0.3 }
                }
              >
                <Icon className="h-5 w-5" aria-hidden="true" />
                {/* Active scanning ring. */}
                {isActive && !reduceMotion ? (
                  <motion.span
                    aria-hidden="true"
                    className="absolute inset-0 rounded-xl"
                    style={{ border: `1px solid ${color}` }}
                    initial={{ opacity: 0.6, scale: 1 }}
                    animate={{ opacity: 0, scale: 1.3 }}
                    transition={{ duration: 1.6, repeat: Infinity, ease: "easeOut" }}
                  />
                ) : null}
              </motion.span>

              <div className="flex flex-col items-center gap-0.5 text-center">
                <span
                  className={cn(
                    "eyebrow text-[0.5625rem] leading-none transition-colors",
                  )}
                  style={{
                    color:
                      phaseStatus === "pending"
                        ? "var(--text-muted)"
                        : "var(--text-secondary)",
                  }}
                >
                  {def.label}
                </span>
                <span
                  className="mono text-[0.5rem] leading-none"
                  style={{ color }}
                >
                  {String(index + 1).padStart(2, "0")}
                  {isDone ? " ·done" : isActive ? " ·live" : ""}
                </span>
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

export default MissionPipeline;
