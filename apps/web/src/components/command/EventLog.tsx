"use client";

/**
 * EventLog — the streaming mono log on the right of the Command Center.
 *
 *  - Reads capped log entries from the mission store (already ring-buffered at
 *    LOG_CAP by the store).
 *  - Renders each line mono, colored by level (INFO/WARN/ERROR).
 *  - Auto-scrolls to the newest line, but PAUSES auto-scroll while the pointer
 *    is over the log (so the user can read) or when they scroll up manually.
 *  - Announces new lines politely via ARIA (role="log", aria-live="polite").
 *  - Caps the rendered DOM to the most recent N lines for perf.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { Pause, ArrowDownToLine } from "lucide-react";
import type { LogLevel, StoredLog } from "@/lib/types";
import { useMissionStore } from "@/lib/store";
import { cn } from "@/lib/cn";

/** Maximum number of lines actually mounted in the DOM (perf cap). */
const RENDER_CAP = 160;

const LEVEL_COLOR: Record<LogLevel, string> = {
  INFO: "var(--accent-cyan)",
  WARN: "var(--accent-amber)",
  ERROR: "var(--accent-rose)",
};

const LEVEL_LABEL: Record<LogLevel, string> = {
  INFO: "INFO",
  WARN: "WARN",
  ERROR: "ERRR",
};

function timeOf(iso: string): string {
  const parsed = Date.parse(iso);
  if (Number.isNaN(parsed)) return "--:--:--";
  const date = new Date(parsed);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${pad(date.getUTCHours())}:${pad(date.getUTCMinutes())}:${pad(
    date.getUTCSeconds(),
  )}`;
}

export function EventLog() {
  const logs = useMissionStore((s) => s.logs);
  const scrollRef = useRef<HTMLDivElement>(null);
  const [paused, setPaused] = useState(false);
  const [atBottom, setAtBottom] = useState(true);

  // Only mount the most recent RENDER_CAP lines.
  const visible: StoredLog[] = useMemo(() => {
    if (logs.length <= RENDER_CAP) return logs;
    return logs.slice(logs.length - RENDER_CAP);
  }, [logs]);

  const lastSeq = visible.length > 0 ? visible[visible.length - 1]!.seq : 0;

  // Auto-scroll to bottom on new lines unless paused or the user scrolled up.
  useEffect(() => {
    const node = scrollRef.current;
    if (!node) return;
    if (paused || !atBottom) return;
    node.scrollTop = node.scrollHeight;
  }, [lastSeq, paused, atBottom]);

  const handleScroll = () => {
    const node = scrollRef.current;
    if (!node) return;
    const distance = node.scrollHeight - node.scrollTop - node.clientHeight;
    setAtBottom(distance < 24);
  };

  const jumpToLatest = () => {
    const node = scrollRef.current;
    if (!node) return;
    node.scrollTop = node.scrollHeight;
    setAtBottom(true);
  };

  const showResume = paused || !atBottom;

  return (
    <div className="relative flex h-full min-h-0 flex-col">
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        onMouseEnter={() => setPaused(true)}
        onMouseLeave={() => setPaused(false)}
        role="log"
        aria-live="polite"
        aria-relevant="additions"
        aria-label="Mission event log"
        className="mono min-h-0 flex-1 overflow-y-auto px-3 py-2 text-[0.6875rem] leading-relaxed"
        tabIndex={0}
      >
        {visible.length === 0 ? (
          <p className="px-1 py-4 text-center text-[color:var(--text-muted)]">
            Awaiting mission telemetry…
          </p>
        ) : (
          <ul className="flex flex-col gap-0.5">
            {visible.map((entry) => {
              const color = LEVEL_COLOR[entry.level] ?? "var(--text-secondary)";
              return (
                <li
                  key={entry.seq}
                  className="group flex items-start gap-2 rounded px-1 py-0.5 hover:bg-[color:var(--bg-elevated)]/40"
                >
                  <span className="shrink-0 text-[color:var(--text-muted)]">
                    {timeOf(entry.ts)}
                  </span>
                  <span
                    className="shrink-0 font-semibold"
                    style={{ color }}
                    aria-label={`${entry.level} level`}
                  >
                    {LEVEL_LABEL[entry.level] ?? entry.level}
                  </span>
                  <span className="shrink-0 max-w-[9rem] truncate text-[color:var(--text-secondary)]">
                    {entry.agent_id}
                  </span>
                  <span className="min-w-0 flex-1 text-[color:var(--text-primary)]">
                    {entry.message}
                  </span>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      {/* Pause / resume affordance. */}
      {showResume ? (
        <button
          type="button"
          onClick={jumpToLatest}
          className={cn(
            "absolute bottom-2 right-3 z-10 inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[0.625rem] font-semibold shadow-lg transition-colors",
          )}
          style={{
            color: "var(--accent-cyan)",
            background: "color-mix(in srgb, var(--bg-elevated) 92%, transparent)",
            border: "1px solid color-mix(in srgb, var(--accent-cyan) 40%, transparent)",
          }}
          aria-label="Resume auto-scroll and jump to latest"
        >
          {paused ? (
            <Pause className="h-3 w-3" aria-hidden="true" />
          ) : (
            <ArrowDownToLine className="h-3 w-3" aria-hidden="true" />
          )}
          {paused ? "Paused" : "Latest"}
        </button>
      ) : null}
    </div>
  );
}

export default EventLog;
