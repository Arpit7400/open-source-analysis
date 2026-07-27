"use client";

/**
 * ResourceGauges — radial CPU / RAM / active-agent readouts for the left rail
 * of the Command Center. Primary source is the live mission store's
 * `resources` (fed by SSE `resource` events); if the store has no resources
 * yet it falls back to polling `api.getResources()` so the gauges are never
 * blank. Renders each metric as a ProgressRing with a MonoValue center, plus a
 * low-resource advisory note when the host looks constrained.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { Cpu, MemoryStick, Bot, TriangleAlert } from "lucide-react";
import type { Resources } from "@/lib/types";
import * as api from "@/lib/api";
import { useMissionStore } from "@/lib/store";
import { ProgressRing } from "@/components/ui/ProgressRing";
import { MonoValue } from "@/components/ui/MonoValue";
import { Eyebrow } from "@/components/ui/Eyebrow";

const POLL_INTERVAL_MS = 4000;

/** Pick a ramp color for a 0..1 utilization: cyan → amber → rose. */
function utilizationColor(fraction: number): string {
  if (fraction >= 0.85) return "var(--accent-rose)";
  if (fraction >= 0.65) return "var(--accent-amber)";
  return "var(--accent-cyan)";
}

interface GaugeProps {
  label: string;
  icon: React.ReactNode;
  fraction: number;
  color: string;
  center: React.ReactNode;
  footnote: React.ReactNode;
}

function Gauge({ label, icon, fraction, color, center, footnote }: GaugeProps) {
  return (
    <div className="flex min-w-0 flex-col items-center gap-1.5">
      {/* The ring is fluid: it fills its grid cell (min 52px, ideal ~64px, max
          72px) so three gauges always fit a narrow left rail without clipping,
          and scale up gracefully in a wider column. */}
      <div className="w-full max-w-[72px]">
        <ProgressRing
          progress={fraction}
          size={72}
          responsive
          stroke={6}
          color={color}
          glow
          aria-label={`${label} gauge`}
        >
          <span className="flex flex-col items-center leading-none">
            <span aria-hidden="true" style={{ color }}>
              {icon}
            </span>
            <span
              className="mono mt-0.5 text-[0.8125rem] font-semibold"
              style={{ color: "var(--text-primary)" }}
            >
              {center}
            </span>
          </span>
        </ProgressRing>
      </div>
      <div className="flex min-w-0 max-w-full flex-col items-center gap-0.5">
        <Eyebrow className="text-[0.5625rem] text-[color:var(--text-muted)]">
          {label}
        </Eyebrow>
        <span className="mono max-w-full truncate whitespace-nowrap text-[0.625rem] text-[color:var(--text-secondary)]">
          {footnote}
        </span>
      </div>
    </div>
  );
}

export function ResourceGauges() {
  const storeResources = useMissionStore((s) => s.resources);
  const [polled, setPolled] = useState<Resources | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  // Poll the REST endpoint only while the store has not yet produced live data.
  const haveLive = storeResources !== null;

  useEffect(() => {
    if (haveLive) return;
    let active = true;

    const tick = async () => {
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      try {
        const data = await api.getResources(controller.signal);
        if (active) setPolled(data);
      } catch {
        // Leave the last known value; the UI degrades to zeros gracefully.
      }
    };

    void tick();
    const handle = setInterval(() => {
      void tick();
    }, POLL_INTERVAL_MS);

    return () => {
      active = false;
      clearInterval(handle);
      abortRef.current?.abort();
    };
  }, [haveLive]);

  const resources: Resources = storeResources ??
    polled ?? {
      cpu_percent: 0,
      ram_used_mb: 0,
      ram_total_mb: 0,
      active_agents: 0,
      max_agents: 0,
    };

  const cpuFraction = Math.max(0, Math.min(1, resources.cpu_percent / 100));
  const ramFraction =
    resources.ram_total_mb > 0
      ? Math.max(0, Math.min(1, resources.ram_used_mb / resources.ram_total_mb))
      : 0;
  const agentFraction =
    resources.max_agents > 0
      ? Math.max(0, Math.min(1, resources.active_agents / resources.max_agents))
      : 0;
  const ramGb = resources.ram_total_mb / 1024;

  // Low-resource advisory: few agent slots or a tiny RAM footprint suggests a
  // constrained host (CPU_LOW profile). Purely informational.
  const lowResource = useMemo(() => {
    const smallRam = resources.ram_total_mb > 0 && resources.ram_total_mb < 12_288;
    const fewSlots = resources.max_agents > 0 && resources.max_agents <= 2;
    return smallRam || fewSlots;
  }, [resources.ram_total_mb, resources.max_agents]);

  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-3 items-start gap-x-1.5 gap-y-2">
        <Gauge
          label="CPU"
          icon={<Cpu className="h-3.5 w-3.5" aria-hidden="true" />}
          fraction={cpuFraction}
          color={utilizationColor(cpuFraction)}
          center={
            <MonoValue
              value={resources.cpu_percent}
              decimals={0}
              suffix="%"
              aria-label={`CPU ${Math.round(resources.cpu_percent)} percent`}
            />
          }
          footnote={
            <>
              load
            </>
          }
        />
        <Gauge
          label="RAM"
          icon={<MemoryStick className="h-3.5 w-3.5" aria-hidden="true" />}
          fraction={ramFraction}
          color={utilizationColor(ramFraction)}
          center={
            <MonoValue
              value={ramFraction * 100}
              decimals={0}
              suffix="%"
              aria-label={`RAM ${Math.round(ramFraction * 100)} percent`}
            />
          }
          footnote={
            <>
              <MonoValue
                value={resources.ram_used_mb / 1024}
                decimals={1}
                suffix="G"
              />
              {" / "}
              <MonoValue value={ramGb} decimals={0} suffix="G" />
            </>
          }
        />
        <Gauge
          label="Agents"
          icon={<Bot className="h-3.5 w-3.5" aria-hidden="true" />}
          fraction={agentFraction}
          color={utilizationColor(agentFraction)}
          center={
            <span className="flex items-baseline">
              <MonoValue
                value={resources.active_agents}
                decimals={0}
                aria-label={`${resources.active_agents} active agents`}
              />
            </span>
          }
          footnote={
            <>
              active/
              <MonoValue value={resources.max_agents} decimals={0} />
            </>
          }
        />
      </div>

      {lowResource ? (
        <p
          className="flex items-start gap-2 rounded-lg px-2.5 py-2 text-[0.6875rem] leading-relaxed"
          style={{
            color: "var(--accent-amber)",
            background: "color-mix(in srgb, var(--accent-amber) 10%, transparent)",
            border: "1px solid color-mix(in srgb, var(--accent-amber) 30%, transparent)",
          }}
          role="note"
        >
          <TriangleAlert
            className="mt-0.5 h-3.5 w-3.5 shrink-0"
            aria-hidden="true"
          />
          <span>
            Low-resource host detected — agent concurrency is capped to keep the
            mission responsive on constrained hardware.
          </span>
        </p>
      ) : null}
    </div>
  );
}

export default ResourceGauges;
