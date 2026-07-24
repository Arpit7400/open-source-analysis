"use client";

/**
 * AgentNode — a custom React Flow node renderer for a single mission agent.
 *
 * Visual language (DESIGN_SYSTEM.md § agent-state colors):
 *   WAITING   -> muted, dim
 *   RUNNING   -> cyan, soft pulse
 *   COMPLETED -> emerald
 *   VERIFYING -> violet, dual-ring
 *   BLOCKED   -> amber
 *   FAILED    -> rose, red shake + flash
 *   REJECTED  -> desaturated, strikethrough feel
 *
 * The node shows a per-group lucide icon, its label, a state Badge, a
 * ProgressRing (dual when VERIFYING), and a result_count chip. All motion is
 * transform/opacity only (60fps) and disabled under reduced motion.
 */

import { memo, useMemo } from "react";
import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";
import { motion, useReducedMotion, type Variants } from "framer-motion";
import {
  Cpu,
  FlaskConical,
  Download,
  CopyCheck,
  Wrench,
  ShieldCheck,
  Radio,
  Layers,
  Bot,
  type LucideIcon,
} from "lucide-react";
import type { AgentGroup, AgentNode as AgentNodeData, AgentState } from "@/lib/types";
import { Badge, type BadgeTone } from "@/components/ui/Badge";
import { ProgressRing } from "@/components/ui/ProgressRing";
import { cn } from "@/lib/cn";

/**
 * Data payload carried on each React Flow node (the full AgentNode).
 *
 * React Flow (@xyflow/react) constrains a node's `data` to
 * `Record<string, unknown>`, so we intersect with an index signature to
 * satisfy that generic bound while keeping our concrete fields typed.
 */
export type AgentFlowData = AgentNodeData & {
  /** Whether this node is the currently selected one (drives selected ring). */
  selected?: boolean;
} & Record<string, unknown>;

const GROUP_ICON: Record<AgentGroup, LucideIcon> = {
  CONTROL: Radio,
  INTAKE: Download,
  STATIC: Cpu,
  RUNTIME: FlaskConical,
  DUPLICATE: CopyCheck,
  AGGREGATE: Layers,
  FIX: Wrench,
  VERIFY: ShieldCheck,
};

const STATE_COLOR: Record<AgentState, string> = {
  WAITING: "var(--state-waiting)",
  RUNNING: "var(--state-running)",
  COMPLETED: "var(--state-completed)",
  VERIFYING: "var(--state-verifying)",
  BLOCKED: "var(--state-blocked)",
  FAILED: "var(--state-failed)",
  REJECTED: "var(--state-rejected)",
};

const STATE_TONE: Record<AgentState, BadgeTone> = {
  WAITING: "waiting",
  RUNNING: "running",
  COMPLETED: "completed",
  VERIFYING: "verifying",
  BLOCKED: "blocked",
  FAILED: "failed",
  REJECTED: "rejected",
};

function groupLabel(group: AgentGroup): string {
  return group.charAt(0) + group.slice(1).toLowerCase();
}

function AgentNodeComponent({ data }: NodeProps<Node<AgentFlowData>>) {
  const reduceMotion = useReducedMotion();
  const node = data;

  const color = STATE_COLOR[node.state] ?? "var(--text-muted)";
  const Icon = GROUP_ICON[node.group] ?? Bot;
  const isRunning = node.state === "RUNNING";
  const isVerifying = node.state === "VERIFYING";
  const isFailed = node.state === "FAILED";
  const isRejected = node.state === "REJECTED";
  const isCompleted = node.state === "COMPLETED";
  const isSelected = Boolean(node.selected);

  // FAILED gets a one-shot red shake; RUNNING gets a gentle breathing scale.
  const containerVariants: Variants = useMemo(() => {
    if (reduceMotion) {
      return {
        rest: { scale: 1, x: 0 },
        active: { scale: 1, x: 0 },
      };
    }
    if (isFailed) {
      return {
        rest: { x: 0 },
        active: {
          x: [0, -4, 4, -3, 3, -1.5, 0],
          transition: { duration: 0.5, ease: "easeInOut" },
        },
      };
    }
    if (isRunning) {
      return {
        rest: { scale: 1 },
        active: {
          scale: [1, 1.025, 1],
          transition: { duration: 2, ease: "easeInOut", repeat: Infinity },
        },
      };
    }
    return { rest: { scale: 1 }, active: { scale: 1 } };
  }, [reduceMotion, isFailed, isRunning]);

  const glowShadow = isSelected
    ? `0 0 0 1.5px ${color}, 0 0 22px -4px color-mix(in srgb, ${color} 70%, transparent)`
    : `0 0 0 1px color-mix(in srgb, ${color} 40%, transparent), 0 0 16px -8px color-mix(in srgb, ${color} 60%, transparent)`;

  return (
    <motion.div
      variants={containerVariants}
      initial="rest"
      animate="active"
      className={cn(
        "relative flex w-[230px] select-none items-center gap-3 rounded-xl px-3 py-2.5",
        isRejected && "opacity-60 saturate-50",
      )}
      style={{
        background: "color-mix(in srgb, var(--bg-elevated) 78%, transparent)",
        backdropFilter: "blur(8px)",
        border: "1px solid var(--border-hair)",
        boxShadow: glowShadow,
      }}
      role="button"
      tabIndex={-1}
      aria-label={`${node.label} — ${node.state.toLowerCase()}, ${Math.round(
        node.progress * 100,
      )} percent`}
    >
      {/* Incoming / outgoing connection handles (kept subtle). */}
      <Handle
        type="target"
        position={Position.Left}
        className="!h-1.5 !w-1.5 !border-0"
        style={{ background: "var(--border-glow)" }}
      />
      <Handle
        type="source"
        position={Position.Right}
        className="!h-1.5 !w-1.5 !border-0"
        style={{ background: "var(--border-glow)" }}
      />

      {/* Progress ring with the group icon in the center. */}
      <div className="relative shrink-0">
        <ProgressRing
          progress={node.progress}
          size={44}
          stroke={4}
          color={color}
          dual={isVerifying}
          dualColor="var(--accent-cyan)"
          glow={isRunning || isVerifying || isSelected}
          aria-label={`${node.label} progress`}
        >
          <Icon
            className="h-4 w-4"
            style={{ color }}
            aria-hidden="true"
          />
        </ProgressRing>
        {/* Soft pulsing halo behind the ring while RUNNING. */}
        {isRunning && !reduceMotion ? (
          <motion.span
            aria-hidden="true"
            className="pointer-events-none absolute inset-0 rounded-full"
            style={{ background: color }}
            initial={{ opacity: 0.32, scale: 0.9 }}
            animate={{ opacity: [0.28, 0, 0.28], scale: [0.9, 1.5, 0.9] }}
            transition={{ duration: 2, repeat: Infinity, ease: "easeOut" }}
          />
        ) : null}
      </div>

      {/* Text column: label + group eyebrow + state badge. */}
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <div className="flex items-center justify-between gap-2">
          <span
            className={cn(
              "truncate text-[0.8125rem] font-semibold leading-tight text-[color:var(--text-primary)]",
              isRejected && "line-through decoration-1",
            )}
            title={node.label}
          >
            {node.label}
          </span>
          {node.result_count > 0 ? (
            <span
              className="mono shrink-0 rounded-md px-1.5 py-0.5 text-[0.625rem] font-semibold leading-none"
              style={{
                color,
                background: `color-mix(in srgb, ${color} 16%, transparent)`,
              }}
              title={`${node.result_count} result(s)`}
            >
              {node.result_count}
            </span>
          ) : null}
        </div>
        <div className="flex items-center gap-2">
          <span className="eyebrow text-[0.5625rem] text-[color:var(--text-muted)]">
            {groupLabel(node.group)}
          </span>
          <Badge tone={STATE_TONE[node.state]} dot className="!px-1.5 !py-0.5 !text-[0.5625rem]">
            {node.state}
          </Badge>
        </div>
      </div>

      {/* COMPLETED gets a draw-on checkmark stamp in the corner. */}
      {isCompleted ? (
        <svg
          className="pointer-events-none absolute -right-1.5 -top-1.5 h-4 w-4"
          viewBox="0 0 24 24"
          fill="none"
          aria-hidden="true"
        >
          <circle cx="12" cy="12" r="11" fill="var(--bg-base)" />
          <motion.path
            d="M6 12.5l4 4 8-9"
            stroke="var(--accent-emerald)"
            strokeWidth={2.5}
            strokeLinecap="round"
            strokeLinejoin="round"
            initial={reduceMotion ? false : { pathLength: 0 }}
            animate={{ pathLength: 1 }}
            transition={{ duration: 0.4, ease: "easeOut" }}
          />
        </svg>
      ) : null}

      {/* FAILED red flash overlay (one-shot). */}
      {isFailed && !reduceMotion ? (
        <motion.span
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 rounded-xl"
          style={{ background: "var(--accent-rose)" }}
          initial={{ opacity: 0.32 }}
          animate={{ opacity: 0 }}
          transition={{ duration: 0.6, ease: "easeOut" }}
        />
      ) : null}
    </motion.div>
  );
}

export const AgentNode = memo(AgentNodeComponent);

export default AgentNode;
