"use client";

/**
 * Command Center — the flagship hero screen.
 *
 * Flow:
 *   1. The operator enters a GitHub repo URL (a demo URL is pre-filled) and
 *      hits "Analyze". That calls `api.analyzeRepo`, which returns a
 *      `mission_id`.
 *   2. We `reset()` the mission store, seed the mission id, and subscribe with
 *      `useMissionStream(missionId)` — which mirrors the backend SSE stream
 *      (or the bundled mock, if the backend is unreachable) into the store.
 *   3. The dashboard renders live from the store:
 *        - top:    MissionPipeline (phase progress)
 *        - left:   ResourceGauges  (CPU / RAM / active agents)
 *        - center: AgentGraph      (React Flow live graph)
 *        - right:  EventLog        (streaming mono log)
 *      Selecting a node opens the AgentDrawer.
 *
 * Before the first run an empty state explains the console. Everything honors
 * reduced motion and is keyboard accessible.
 */

import { useCallback, useMemo, useState } from "react";
import Link from "next/link";
import { ReactFlowProvider } from "@xyflow/react";
import { motion, useReducedMotion } from "framer-motion";
import {
  Play,
  Loader2,
  Github,
  RadioTower,
  Waypoints,
  ScrollText,
  Gauge as GaugeIcon,
  ShieldAlert,
  ArrowRight,
} from "lucide-react";
import * as api from "@/lib/api";
import { ApiError } from "@/lib/api";
import { useMissionStore } from "@/lib/store";
import { useMissionStream, type StreamMode } from "@/lib/useMissionStream";
import type { MissionStatus } from "@/lib/types";
import { Panel } from "@/components/ui/Panel";
import { Eyebrow } from "@/components/ui/Eyebrow";
import { Badge, type BadgeTone } from "@/components/ui/Badge";
import { cn } from "@/lib/cn";
import { MissionPipeline } from "@/components/command/MissionPipeline";
import { AgentGraph } from "@/components/command/AgentGraph";
import { EventLog } from "@/components/command/EventLog";
import { ResourceGauges } from "@/components/command/ResourceGauges";
import { AgentDrawer } from "@/components/command/AgentDrawer";

const DEMO_REPO_URL = "https://github.com/octo-labs/fastwidget";

const STATUS_TONE: Record<MissionStatus, BadgeTone> = {
  QUEUED: "neutral",
  PLANNING: "blue",
  RUNNING: "running",
  AWAITING_APPROVAL: "blocked",
  COMPLETED: "completed",
  FAILED: "failed",
  CANCELLED: "rejected",
};

const MODE_LABEL: Record<StreamMode, string> = {
  idle: "idle",
  connecting: "connecting",
  live: "live",
  mock: "simulated",
  closed: "closed",
};

const MODE_TONE: Record<StreamMode, BadgeTone> = {
  idle: "neutral",
  connecting: "amber",
  live: "emerald",
  mock: "violet",
  closed: "neutral",
};

function isLikelyRepoUrl(value: string): boolean {
  const trimmed = value.trim();
  if (trimmed.length === 0) return false;
  try {
    const url = new URL(trimmed);
    return (
      (url.protocol === "https:" || url.protocol === "http:") &&
      url.pathname.split("/").filter(Boolean).length >= 2
    );
  } catch {
    return false;
  }
}

export default function CommandCenterPage() {
  const reduceMotion = useReducedMotion();

  const [repoUrl, setRepoUrl] = useState<string>(DEMO_REPO_URL);
  const [launching, setLaunching] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const missionId = useMissionStore((s) => s.missionId);
  const status = useMissionStore((s) => s.status);
  const storeRepoUrl = useMissionStore((s) => s.repoUrl);
  const plan = useMissionStore((s) => s.plan);
  const findingsCount = useMissionStore((s) => s.findings.length);
  const candidateCount = useMissionStore(
    (s) => Object.keys(s.candidates).length,
  );
  const agentCount = useMissionStore((s) => Object.keys(s.agents).length);
  const approval = useMissionStore((s) => s.approval);

  const reset = useMissionStore((s) => s.reset);
  const setMissionId = useMissionStore((s) => s.setMissionId);
  const setStatus = useMissionStore((s) => s.setStatus);
  const setStoreRepoUrl = useMissionStore.setState;

  const { mode } = useMissionStream(missionId);

  const started = missionId !== null;
  const valid = useMemo(() => isLikelyRepoUrl(repoUrl), [repoUrl]);
  const inFlight =
    launching ||
    status === "QUEUED" ||
    status === "PLANNING" ||
    status === "RUNNING";

  const launch = useCallback(async () => {
    if (!valid || launching) return;
    setError(null);
    setLaunching(true);
    const url = repoUrl.trim();
    try {
      const response = await api.analyzeRepo(url);
      // Fresh mission: clear the store, seed id + repo + status, then subscribe.
      reset();
      setStoreRepoUrl({ repoUrl: url });
      setMissionId(response.mission_id);
      setStatus(response.status);
    } catch (cause) {
      const message =
        cause instanceof ApiError
          ? `${cause.code}: ${cause.message}`
          : cause instanceof Error
            ? cause.message
            : "Failed to launch mission.";
      setError(message);
    } finally {
      setLaunching(false);
    }
  }, [
    valid,
    launching,
    repoUrl,
    reset,
    setStoreRepoUrl,
    setMissionId,
    setStatus,
  ]);

  const onKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter") {
      event.preventDefault();
      void launch();
    }
  };

  const activeRepo = storeRepoUrl ?? repoUrl;

  return (
    <div className="flex h-[calc(100vh-var(--shell-nav-h))] min-h-0 flex-col gap-3 p-3 sm:p-4">
      {/* ---- Launch bar ---------------------------------------------------- */}
      <Panel
        index={0}
        flush
        className="shrink-0"
        active={inFlight}
      >
        <div className="flex flex-col gap-3 p-4">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div className="flex min-w-0 flex-col gap-1.5">
              <Eyebrow className="text-[color:var(--accent-cyan)]">
                Mission Control
              </Eyebrow>
              <h1 className="text-lg font-semibold tracking-tight text-[color:var(--text-primary)]">
                Repository Analysis Console
              </h1>
            </div>
            <div className="flex items-center gap-2">
              <Badge tone={MODE_TONE[mode]} dot>
                stream · {MODE_LABEL[mode]}
              </Badge>
              {status ? (
                <Badge tone={STATUS_TONE[status]} dot>
                  {status}
                </Badge>
              ) : (
                <Badge tone="neutral" dot>
                  IDLE
                </Badge>
              )}
            </div>
          </div>

          <form
            className="flex flex-col gap-2 sm:flex-row sm:items-center"
            onSubmit={(event) => {
              event.preventDefault();
              void launch();
            }}
          >
            <label className="sr-only" htmlFor="repo-url">
              GitHub repository URL
            </label>
            <div
              className="flex min-w-0 flex-1 items-center gap-2 rounded-lg px-3 py-2 hairline"
              style={{
                background: "color-mix(in srgb, var(--bg-elevated) 70%, transparent)",
              }}
            >
              <Github
                className="h-4 w-4 shrink-0 text-[color:var(--text-muted)]"
                aria-hidden="true"
              />
              <input
                id="repo-url"
                name="repo-url"
                type="url"
                inputMode="url"
                autoComplete="off"
                spellCheck={false}
                value={repoUrl}
                onChange={(event) => setRepoUrl(event.target.value)}
                onKeyDown={onKeyDown}
                placeholder="https://github.com/owner/name"
                aria-invalid={!valid}
                aria-describedby={error ? "repo-error" : undefined}
                className="mono min-w-0 flex-1 bg-transparent text-sm text-[color:var(--text-primary)] placeholder:text-[color:var(--text-muted)] focus:outline-none"
              />
            </div>
            <button
              type="submit"
              disabled={!valid || launching}
              className={cn(
                "group inline-flex shrink-0 items-center justify-center gap-2 rounded-lg px-5 py-2 text-sm font-semibold transition-all",
                valid && !launching
                  ? "text-[#04121a] hover:scale-[1.02]"
                  : "cursor-not-allowed opacity-50",
              )}
              style={{
                background: valid
                  ? "linear-gradient(135deg, var(--accent-cyan), var(--accent-violet))"
                  : "var(--bg-elevated)",
                color: valid ? "#04121a" : "var(--text-muted)",
              }}
              aria-label="Analyze repository"
            >
              {launching ? (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              ) : (
                <Play className="h-4 w-4" aria-hidden="true" />
              )}
              {launching ? "Launching…" : started ? "Re-run" : "Analyze"}
            </button>
          </form>

          {error ? (
            <p
              id="repo-error"
              role="alert"
              className="flex items-center gap-2 text-[0.75rem] text-[color:var(--accent-rose)]"
            >
              <ShieldAlert className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
              {error}
            </p>
          ) : null}

          {/* Phase pipeline */}
          <div className="pt-1">
            <MissionPipeline />
          </div>
        </div>
      </Panel>

      {/* ---- Dashboard grid ------------------------------------------------ */}
      {started ? (
        <div className="grid min-h-0 flex-1 grid-cols-1 gap-3 lg:grid-cols-[280px_minmax(0,1fr)_320px]">
          {/* Left rail: resources + mission meta */}
          <div className="flex min-h-0 flex-col gap-3 lg:overflow-y-auto">
            <Panel
              index={1}
              eyebrow="Telemetry"
              title="Resource Gauges"
              actions={
                <GaugeIcon
                  className="h-4 w-4 text-[color:var(--text-muted)]"
                  aria-hidden="true"
                />
              }
            >
              <ResourceGauges />
            </Panel>

            <Panel index={2} eyebrow="Mission" title="Overview" className="shrink-0">
              <dl className="flex flex-col gap-2.5">
                <MetaRow label="Repository">
                  <span className="mono truncate text-xs text-[color:var(--text-secondary)]">
                    {activeRepo.replace(/^https?:\/\//, "")}
                  </span>
                </MetaRow>
                <MetaRow label="Mission ID">
                  <span className="mono truncate text-xs text-[color:var(--text-secondary)]">
                    {missionId ?? "—"}
                  </span>
                </MetaRow>
                <div className="grid grid-cols-3 gap-2 pt-1">
                  <MiniCount label="Agents" value={agentCount} accent="var(--accent-cyan)" />
                  <MiniCount label="Findings" value={findingsCount} accent="var(--accent-amber)" />
                  <MiniCount label="Fixes" value={candidateCount} accent="var(--accent-violet)" />
                </div>
                {plan?.goal ? (
                  <div className="pt-1">
                    <Eyebrow className="text-[0.5625rem] text-[color:var(--text-muted)]">
                      Goal
                    </Eyebrow>
                    <p className="mt-1 text-xs leading-relaxed text-[color:var(--text-secondary)]">
                      {plan.goal}
                    </p>
                  </div>
                ) : null}
                {approval?.required && !approval.granted ? (
                  <Link
                    href="/lab"
                    className="group mt-1 flex flex-col gap-1.5 rounded-lg px-2.5 py-2.5 text-[0.6875rem] no-underline transition-colors"
                    style={{
                      color: "var(--accent-amber)",
                      background:
                        "color-mix(in srgb, var(--accent-amber) 12%, transparent)",
                      border:
                        "1px solid color-mix(in srgb, var(--accent-amber) 40%, transparent)",
                    }}
                    role="status"
                    aria-label="Human approval required — go to the Contribution Lab to review and approve"
                  >
                    <span className="flex items-center gap-2 font-semibold">
                      <ShieldAlert className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                      Human approval required
                    </span>
                    <span className="leading-relaxed text-[color:var(--text-secondary)]">
                      A fix passed independent verification. Review the diff and
                      approve it in the Contribution Lab.
                    </span>
                    <span
                      className="mt-0.5 inline-flex items-center gap-1 self-start rounded-md px-2 py-1 font-semibold"
                      style={{
                        color: "var(--bg-void)",
                        background: "var(--accent-amber)",
                      }}
                    >
                      Review &amp; approve
                      <ArrowRight
                        className="h-3 w-3 transition-transform group-hover:translate-x-0.5"
                        aria-hidden="true"
                      />
                    </span>
                  </Link>
                ) : null}
              </dl>
            </Panel>
          </div>

          {/* Center: agent graph */}
          <Panel
            index={1}
            flush
            eyebrow="Multi-agent"
            title="Live Agent Graph"
            active={inFlight}
            actions={
              <span className="flex items-center gap-1.5 text-[color:var(--text-muted)]">
                <Waypoints className="h-4 w-4" aria-hidden="true" />
              </span>
            }
            className="min-h-[360px]"
            bodyClassName="p-0"
          >
            <div className="relative min-h-0 flex-1">
              <ReactFlowProvider>
                <AgentGraph />
              </ReactFlowProvider>
            </div>
          </Panel>

          {/* Right: event log */}
          <Panel
            index={2}
            flush
            eyebrow="Telemetry"
            title="Event Log"
            actions={
              <span className="flex items-center gap-1.5">
                <RadioTower
                  className={cn(
                    "h-4 w-4",
                    inFlight && !reduceMotion && "animate-pulse",
                  )}
                  style={{ color: inFlight ? "var(--accent-cyan)" : "var(--text-muted)" }}
                  aria-hidden="true"
                />
              </span>
            }
            className="min-h-[360px]"
            bodyClassName="p-0"
          >
            <EventLog />
          </Panel>
        </div>
      ) : (
        <EmptyState valid={valid} onLaunch={() => void launch()} launching={launching} />
      )}

      {/* Node detail drawer (portal-like overlay) */}
      <AgentDrawer />
    </div>
  );
}

function MetaRow({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between gap-3">
      <dt className="eyebrow text-[0.5625rem] text-[color:var(--text-muted)]">
        {label}
      </dt>
      <dd className="min-w-0">{children}</dd>
    </div>
  );
}

function MiniCount({
  label,
  value,
  accent,
}: {
  label: string;
  value: number;
  accent: string;
}) {
  return (
    <div
      className="flex flex-col items-center gap-0.5 rounded-lg px-2 py-1.5 hairline"
      style={{ background: "color-mix(in srgb, var(--bg-elevated) 60%, transparent)" }}
    >
      <span className="mono text-base font-semibold" style={{ color: accent }}>
        {value}
      </span>
      <span className="eyebrow text-[0.5rem] text-[color:var(--text-muted)]">
        {label}
      </span>
    </div>
  );
}

/**
 * Empty state shown before any mission has been launched. It mirrors the
 * dashboard layout as a "dark, ready" console rather than a marketing card.
 */
function EmptyState({
  valid,
  onLaunch,
  launching,
}: {
  valid: boolean;
  onLaunch: () => void;
  launching: boolean;
}) {
  const reduceMotion = useReducedMotion();
  const features = [
    {
      icon: Waypoints,
      title: "Live agent graph",
      body: "Watch the multi-agent fleet fan out, reason, and converge in real time.",
      accent: "var(--accent-cyan)",
    },
    {
      icon: ScrollText,
      title: "Streaming telemetry",
      body: "Every step is logged with level-coded, mono event lines as it happens.",
      accent: "var(--accent-violet)",
    },
    {
      icon: GaugeIcon,
      title: "Resource-aware",
      body: "CPU, RAM, and agent concurrency gauges reflect the local host budget.",
      accent: "var(--accent-emerald)",
    },
  ];

  return (
    <Panel index={1} flush className="min-h-0 flex-1">
      <div className="flex min-h-0 flex-1 flex-col items-center justify-center gap-8 p-6 text-center">
        <motion.div
          initial={reduceMotion ? false : { opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ type: "spring", stiffness: 200, damping: 22 }}
          className="relative flex h-16 w-16 items-center justify-center rounded-2xl"
          style={{
            background: "color-mix(in srgb, var(--accent-cyan) 12%, transparent)",
            border: "1px solid color-mix(in srgb, var(--accent-cyan) 32%, transparent)",
          }}
        >
          <RadioTower
            className="h-7 w-7 text-[color:var(--accent-cyan)]"
            aria-hidden="true"
          />
          {!reduceMotion ? (
            <motion.span
              aria-hidden="true"
              className="absolute inset-0 rounded-2xl"
              style={{ border: "1px solid var(--accent-cyan)" }}
              initial={{ opacity: 0.5, scale: 1 }}
              animate={{ opacity: 0, scale: 1.4 }}
              transition={{ duration: 2.2, repeat: Infinity, ease: "easeOut" }}
            />
          ) : null}
        </motion.div>

        <div className="flex max-w-md flex-col gap-2">
          <Eyebrow className="text-[color:var(--accent-cyan)]">
            Standing by
          </Eyebrow>
          <h2 className="text-xl font-semibold tracking-tight text-[color:var(--text-primary)]">
            Launch a repository mission
          </h2>
          <p className="text-sm leading-relaxed text-[color:var(--text-secondary)]">
            Enter a GitHub repository above and hit{" "}
            <span className="mono text-[color:var(--text-primary)]">Analyze</span>.
            A fleet of reasoning agents will analyze, reproduce, fix, and
            independently verify — streaming every step into this console.
          </p>
        </div>

        <div className="grid w-full max-w-3xl grid-cols-1 gap-3 sm:grid-cols-3">
          {features.map((feature) => {
            const Icon = feature.icon;
            return (
              <div
                key={feature.title}
                className="flex flex-col items-center gap-2 rounded-xl p-4 hairline"
                style={{
                  background:
                    "color-mix(in srgb, var(--bg-elevated) 55%, transparent)",
                }}
              >
                <span
                  className="flex h-9 w-9 items-center justify-center rounded-lg"
                  style={{
                    color: feature.accent,
                    background: `color-mix(in srgb, ${feature.accent} 12%, transparent)`,
                  }}
                >
                  <Icon className="h-4 w-4" aria-hidden="true" />
                </span>
                <span className="text-sm font-semibold text-[color:var(--text-primary)]">
                  {feature.title}
                </span>
                <span className="text-xs leading-relaxed text-[color:var(--text-secondary)]">
                  {feature.body}
                </span>
              </div>
            );
          })}
        </div>

        <button
          type="button"
          onClick={onLaunch}
          disabled={!valid || launching}
          className={cn(
            "inline-flex items-center gap-2 rounded-full px-6 py-3 text-sm font-semibold transition-transform",
            valid && !launching
              ? "hover:scale-[1.02]"
              : "cursor-not-allowed opacity-50",
          )}
          style={{
            background: valid
              ? "linear-gradient(135deg, var(--accent-cyan), var(--accent-violet))"
              : "var(--bg-elevated)",
            color: valid ? "#04121a" : "var(--text-muted)",
          }}
        >
          {launching ? (
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          ) : (
            <Play className="h-4 w-4" aria-hidden="true" />
          )}
          {launching ? "Launching mission…" : "Analyze repository"}
        </button>
      </div>
    </Panel>
  );
}
