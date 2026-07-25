"use client";

import { type ReactNode } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { motion, useReducedMotion } from "framer-motion";
import {
  Network,
  FlaskConical,
  Radar,
  Activity,
  Cpu,
  MemoryStick,
  Bot,
  ShieldAlert,
  ShieldCheck,
  BadgeCheck,
} from "lucide-react";
import * as api from "@/lib/api";
import type { Health, Resources } from "@/lib/types";
import { cn } from "@/lib/cn";
import { MonoValue } from "@/components/ui/MonoValue";

interface NavItem {
  href: string;
  label: string;
  icon: typeof Network;
}

/** Fixed copyright year (constant so SSR and client render identically). */
const COPYRIGHT_YEAR = 2026;

const NAV: readonly NavItem[] = [
  { href: "/command", label: "Command Center", icon: Network },
  { href: "/lab", label: "Contribution Lab", icon: FlaskConical },
  { href: "/skills", label: "Skills", icon: Radar },
  { href: "/pulse", label: "Pulse", icon: Activity },
  { href: "/portfolio", label: "Portfolio", icon: BadgeCheck },
] as const;

type HealthTone = "green" | "amber" | "red";

/**
 * Derive the health dot color. A hard failure (query error / missing payload)
 * is red; any degraded/down service is amber; otherwise green. Mock services
 * are treated as healthy since demo mode is the default runnable mode.
 */
function healthTone(health: Health | undefined, isError: boolean): HealthTone {
  if (isError || !health) return "red";
  if (health.status && health.status.toLowerCase() !== "ok") return "amber";
  const services = Object.values(health.services ?? {});
  if (services.some((s) => s === "down")) return "amber";
  return "green";
}

const TONE_COLOR: Record<HealthTone, string> = {
  green: "var(--accent-emerald)",
  amber: "var(--accent-amber)",
  red: "var(--accent-rose)",
};

const TONE_LABEL: Record<HealthTone, string> = {
  green: "operational",
  amber: "degraded",
  red: "offline",
};

export default function AppLayout({ children }: { children: ReactNode }) {
  const reduceMotion = useReducedMotion();
  const pathname = usePathname();

  const healthQuery = useQuery<Health>({
    queryKey: ["system", "health"],
    queryFn: ({ signal }) => api.getHealth(signal),
    refetchInterval: 5_000,
    refetchIntervalInBackground: true,
    retry: false,
    staleTime: 0,
  });

  const resourcesQuery = useQuery<Resources>({
    queryKey: ["system", "resources"],
    queryFn: ({ signal }) => api.getResources(signal),
    refetchInterval: 5_000,
    refetchIntervalInBackground: true,
    retry: false,
    staleTime: 0,
  });

  const tone = healthTone(healthQuery.data, healthQuery.isError);
  const health = healthQuery.data;
  const resources = resourcesQuery.data;

  // "demo" whenever any service is mock or writes are disabled — the default.
  const isDemo =
    !health ||
    Object.values(health.services ?? {}).some((s) => s === "mock") ||
    health.flags?.github_writes === false;

  const ramPct =
    resources && resources.ram_total_mb > 0
      ? (resources.ram_used_mb / resources.ram_total_mb) * 100
      : 0;

  return (
    <div className="flex min-h-screen flex-col">
      {/* ---- Top command bar ---------------------------------------------- */}
      <motion.header
        initial={reduceMotion ? false : { opacity: 0, y: -12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ type: "spring", stiffness: 240, damping: 26 }}
        className="glass sticky top-0 z-40 flex h-[var(--shell-nav-h)] items-center gap-4 rounded-none border-x-0 border-t-0 px-4"
        style={{ backdropFilter: "blur(16px)" }}
      >
        {/* Logo mark */}
        <Link
          href="/"
          className="flex shrink-0 items-center gap-2.5"
          aria-label="CareerForge AI home"
        >
          <span className="relative inline-flex h-7 w-7 items-center justify-center">
            <span
              className="absolute inset-0 rounded-[7px]"
              style={{
                background:
                  "linear-gradient(135deg, var(--accent-cyan), var(--accent-violet))",
                opacity: 0.9,
              }}
              aria-hidden="true"
            />
            <span className="mono relative text-sm font-bold text-[#04121a]">
              CF
            </span>
          </span>
          <span className="hidden flex-col leading-none sm:flex">
            <span className="text-sm font-semibold tracking-tight text-[color:var(--text-primary)]">
              CareerForge
            </span>
            <span className="eyebrow text-[0.5625rem] text-[color:var(--text-muted)]">
              Command Center
            </span>
          </span>
        </Link>

        {/* Primary nav */}
        <nav
          className="ml-2 flex items-center gap-1"
          aria-label="Primary navigation"
        >
          {NAV.map((item) => {
            const Icon = item.icon;
            const active =
              pathname === item.href || pathname.startsWith(`${item.href}/`);
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "relative flex items-center gap-2 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors",
                  active
                    ? "text-[color:var(--text-primary)]"
                    : "text-[color:var(--text-secondary)] hover:text-[color:var(--text-primary)]",
                )}
              >
                {active ? (
                  <motion.span
                    layoutId={reduceMotion ? undefined : "nav-active"}
                    className="glow-cyan absolute inset-0 rounded-lg"
                    style={{
                      background:
                        "color-mix(in srgb, var(--accent-cyan) 12%, transparent)",
                    }}
                    transition={{ type: "spring", stiffness: 320, damping: 30 }}
                    aria-hidden="true"
                  />
                ) : null}
                <Icon className="relative h-4 w-4" aria-hidden="true" />
                <span className="relative hidden md:inline">{item.label}</span>
              </Link>
            );
          })}
        </nav>

        {/* Right cluster: resource mini-readout + env flags + health dot */}
        <div className="ml-auto flex items-center gap-3">
          <ResourceMiniReadout resources={resources} ramPct={ramPct} />

          {/* Env + flags */}
          <div className="hidden items-center gap-1.5 lg:flex">
            <span
              className="mono rounded-md px-2 py-1 text-[0.625rem] font-semibold uppercase tracking-wider"
              style={{
                color: "var(--accent-blue)",
                background:
                  "color-mix(in srgb, var(--accent-blue) 12%, transparent)",
                border:
                  "1px solid color-mix(in srgb, var(--accent-blue) 30%, transparent)",
              }}
              title="Application environment"
            >
              {isDemo ? "demo" : "live"}
            </span>
            {health ? (
              <span
                className="mono inline-flex items-center gap-1 rounded-md px-2 py-1 text-[0.625rem] font-semibold"
                style={{
                  color: health.flags.github_writes
                    ? "var(--accent-emerald)"
                    : "var(--accent-amber)",
                  background: health.flags.github_writes
                    ? "color-mix(in srgb, var(--accent-emerald) 12%, transparent)"
                    : "color-mix(in srgb, var(--accent-amber) 12%, transparent)",
                  border: health.flags.github_writes
                    ? "1px solid color-mix(in srgb, var(--accent-emerald) 30%, transparent)"
                    : "1px solid color-mix(in srgb, var(--accent-amber) 30%, transparent)",
                }}
                title={
                  health.flags.github_writes
                    ? "GitHub writes enabled"
                    : "GitHub writes disabled (safe mode)"
                }
              >
                {health.flags.github_writes ? (
                  <ShieldCheck className="h-3 w-3" aria-hidden="true" />
                ) : (
                  <ShieldAlert className="h-3 w-3" aria-hidden="true" />
                )}
                writes {health.flags.github_writes ? "on" : "off"}
              </span>
            ) : null}
          </div>

          {/* Health dot */}
          <div
            className="flex items-center gap-2 rounded-lg px-2.5 py-1.5 hairline"
            role="status"
            aria-live="polite"
            aria-label={`System status: ${TONE_LABEL[tone]}`}
            title={
              health
                ? `${health.status} · v${health.version} · ${health.hardware_profile}`
                : "Connecting to backend…"
            }
          >
            <span className="relative flex h-2.5 w-2.5">
              {tone === "green" && !reduceMotion ? (
                <span
                  className="absolute inline-flex h-full w-full animate-ping rounded-full opacity-60"
                  style={{ background: TONE_COLOR[tone] }}
                  aria-hidden="true"
                />
              ) : null}
              <span
                className="relative inline-flex h-2.5 w-2.5 rounded-full"
                style={{ background: TONE_COLOR[tone] }}
                aria-hidden="true"
              />
            </span>
            <span className="mono hidden text-[0.6875rem] text-[color:var(--text-secondary)] sm:inline">
              {health ? `v${health.version}` : "···"}
            </span>
          </div>
        </div>
      </motion.header>

      {/* ---- Page content ------------------------------------------------- */}
      <motion.main
        initial={reduceMotion ? false : { opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{
          type: "spring",
          stiffness: 220,
          damping: 26,
          delay: reduceMotion ? 0 : 0.08,
        }}
        className="min-h-0 flex-1"
      >
        {children}
      </motion.main>

      {/* ---- Global footer: ownership / copyright ------------------------ */}
      <footer className="hairline border-x-0 border-b-0 px-4 py-3 text-center text-xs text-[var(--text-muted)]">
        © {COPYRIGHT_YEAR} CareerForge AI — All rights reserved by Arpit Sahu.
      </footer>
    </div>
  );
}

/**
 * Compact CPU / RAM / active-agent readout for the top bar. Numbers count up
 * via MonoValue and are hidden on small screens to keep the bar uncluttered.
 */
function ResourceMiniReadout({
  resources,
  ramPct,
}: {
  resources: Resources | undefined;
  ramPct: number;
}) {
  return (
    <div className="hidden items-center gap-3 xl:flex">
      <MiniStat
        icon={<Cpu className="h-3.5 w-3.5" aria-hidden="true" />}
        label="CPU"
        accent="var(--accent-cyan)"
      >
        <MonoValue value={resources?.cpu_percent ?? 0} decimals={0} suffix="%" />
      </MiniStat>
      <MiniStat
        icon={<MemoryStick className="h-3.5 w-3.5" aria-hidden="true" />}
        label="RAM"
        accent="var(--accent-violet)"
      >
        <MonoValue value={ramPct} decimals={0} suffix="%" />
      </MiniStat>
      <MiniStat
        icon={<Bot className="h-3.5 w-3.5" aria-hidden="true" />}
        label="Agents"
        accent="var(--accent-emerald)"
      >
        <span className="mono">
          <MonoValue value={resources?.active_agents ?? 0} decimals={0} />
          <span className="text-[color:var(--text-muted)]">
            /{resources?.max_agents ?? 0}
          </span>
        </span>
      </MiniStat>
    </div>
  );
}

function MiniStat({
  icon,
  label,
  accent,
  children,
}: {
  icon: ReactNode;
  label: string;
  accent: string;
  children: ReactNode;
}) {
  return (
    <div className="flex items-center gap-1.5" title={label}>
      <span style={{ color: accent }} aria-hidden="true">
        {icon}
      </span>
      <span className="eyebrow text-[0.5625rem] text-[color:var(--text-muted)]">
        {label}
      </span>
      <span className="mono text-xs font-semibold text-[color:var(--text-primary)]">
        {children}
      </span>
    </div>
  );
}
