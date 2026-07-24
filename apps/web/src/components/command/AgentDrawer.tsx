"use client";

/**
 * AgentDrawer — a right-anchored side drawer showing the full detail of the
 * agent currently selected in the mission store (`selectedAgentId`). Slides in
 * with a spring, traps nothing (never steals focus permanently), closes on the
 * Escape key, backdrop click, or the close button. Reduced-motion swaps the
 * slide for an instant fade.
 */

import { useEffect } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { X, Clock, Link2, Activity } from "lucide-react";
import type { AgentNode, AgentState } from "@/lib/types";
import { useMissionStore } from "@/lib/store";
import { Badge, type BadgeTone } from "@/components/ui/Badge";
import { Eyebrow } from "@/components/ui/Eyebrow";
import { ProgressRing } from "@/components/ui/ProgressRing";
import { MonoValue } from "@/components/ui/MonoValue";

const STATE_TONE: Record<AgentState, BadgeTone> = {
  WAITING: "waiting",
  RUNNING: "running",
  COMPLETED: "completed",
  VERIFYING: "verifying",
  BLOCKED: "blocked",
  FAILED: "failed",
  REJECTED: "rejected",
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

function formatTs(iso: string | null): string {
  if (!iso) return "—";
  const parsed = Date.parse(iso);
  if (Number.isNaN(parsed)) return iso;
  try {
    return new Date(parsed).toLocaleTimeString(undefined, {
      hour12: false,
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return iso;
  }
}

function DetailRow({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1 py-2.5 hairline-b last:border-b-0">
      <Eyebrow className="text-[0.5625rem] text-[color:var(--text-muted)]">
        {label}
      </Eyebrow>
      <div className="text-sm text-[color:var(--text-primary)]">{children}</div>
    </div>
  );
}

export function AgentDrawer() {
  const reduceMotion = useReducedMotion();
  const selectedAgentId = useMissionStore((s) => s.selectedAgentId);
  const agents = useMissionStore((s) => s.agents);
  const selectAgentId = useMissionStore((s) => s.selectAgentId);

  const agent: AgentNode | null = selectedAgentId
    ? agents[selectedAgentId] ?? null
    : null;
  const open = agent !== null;

  const close = () => selectAgentId(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        close();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const color = agent ? STATE_COLOR[agent.state] : "var(--accent-cyan)";

  return (
    <AnimatePresence>
      {open && agent ? (
        <motion.div
          className="fixed inset-0 z-50 flex justify-end"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: reduceMotion ? 0 : 0.18 }}
        >
          {/* Backdrop */}
          <button
            type="button"
            aria-label="Close agent detail"
            onClick={close}
            className="absolute inset-0 h-full w-full cursor-default"
            style={{ background: "rgba(5,7,13,0.55)", backdropFilter: "blur(3px)" }}
          />

          {/* Panel */}
          <motion.aside
            role="dialog"
            aria-modal="false"
            aria-label={`Agent detail: ${agent.label}`}
            className="glass relative z-10 flex h-full w-full max-w-[380px] flex-col rounded-none border-y-0 border-r-0"
            initial={
              reduceMotion ? { opacity: 0 } : { x: "100%", opacity: 0.6 }
            }
            animate={reduceMotion ? { opacity: 1 } : { x: 0, opacity: 1 }}
            exit={reduceMotion ? { opacity: 0 } : { x: "100%", opacity: 0.4 }}
            transition={
              reduceMotion
                ? { duration: 0 }
                : { type: "spring", stiffness: 260, damping: 30 }
            }
          >
            {/* Header */}
            <header className="flex items-start gap-3 px-4 pb-3 pt-4 hairline-b">
              <ProgressRing
                progress={agent.progress}
                size={46}
                stroke={4}
                color={color}
                dual={agent.state === "VERIFYING"}
                glow
                aria-label={`${agent.label} progress`}
              >
                <span className="mono text-[0.625rem] font-semibold" style={{ color }}>
                  {Math.round(agent.progress * 100)}
                </span>
              </ProgressRing>
              <div className="flex min-w-0 flex-1 flex-col gap-1.5">
                <Eyebrow className="text-[0.5625rem]" style={{ color }}>
                  {agent.group}
                </Eyebrow>
                <h2 className="truncate text-base font-semibold text-[color:var(--text-primary)]">
                  {agent.label}
                </h2>
                <div className="flex items-center gap-2">
                  <Badge tone={STATE_TONE[agent.state]} dot>
                    {agent.state}
                  </Badge>
                  <span className="mono text-[0.625rem] text-[color:var(--text-muted)]">
                    {agent.id}
                  </span>
                </div>
              </div>
              <button
                type="button"
                onClick={close}
                aria-label="Close"
                className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-[color:var(--text-secondary)] transition-colors hover:bg-[color:var(--bg-elevated)] hover:text-[color:var(--text-primary)]"
              >
                <X className="h-4 w-4" aria-hidden="true" />
              </button>
            </header>

            {/* Body */}
            <div className="flex min-h-0 flex-1 flex-col overflow-y-auto px-4 py-3">
              <DetailRow label="Current detail">
                <span className="flex items-start gap-2">
                  <Activity
                    className="mt-0.5 h-3.5 w-3.5 shrink-0"
                    style={{ color }}
                    aria-hidden="true"
                  />
                  <span className="text-[color:var(--text-secondary)]">
                    {agent.detail || "—"}
                  </span>
                </span>
              </DetailRow>

              <DetailRow label="Progress">
                <span className="mono text-sm" style={{ color }}>
                  <MonoValue value={agent.progress * 100} decimals={0} suffix="%" />
                </span>
              </DetailRow>

              <DetailRow label="Results emitted">
                <span className="mono text-sm">
                  <MonoValue value={agent.result_count} decimals={0} />
                </span>
              </DetailRow>

              <DetailRow label="Verifier of">
                {agent.verifier_of ? (
                  <button
                    type="button"
                    onClick={() => selectAgentId(agent.verifier_of)}
                    className="mono inline-flex items-center gap-1.5 text-sm text-[color:var(--accent-cyan)] transition-colors hover:text-[color:var(--text-primary)]"
                  >
                    <Link2 className="h-3.5 w-3.5" aria-hidden="true" />
                    {agent.verifier_of}
                  </button>
                ) : (
                  <span className="text-[color:var(--text-muted)]">
                    Not a verifier
                  </span>
                )}
              </DetailRow>

              <DetailRow label="Started at">
                <span className="mono inline-flex items-center gap-1.5 text-sm text-[color:var(--text-secondary)]">
                  <Clock className="h-3.5 w-3.5" aria-hidden="true" />
                  {formatTs(agent.started_at)}
                </span>
              </DetailRow>

              <DetailRow label="Group">
                <span className="text-[color:var(--text-secondary)]">
                  {agent.group}
                </span>
              </DetailRow>
            </div>
          </motion.aside>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}

export default AgentDrawer;
