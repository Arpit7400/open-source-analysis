"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { cn } from "@/lib/cn";

/** Coloring maps to the accent ramp: ok=emerald, boot/info=cyan, warn=amber. */
type BootLevel = "boot" | "ok" | "info" | "warn";

interface BootLine {
  level: BootLevel;
  text: string;
}

interface BootSequenceProps {
  /** Fired once the sequence finishes (typed out or skipped). */
  onDone: () => void;
  /** sessionStorage key; the sequence only runs once per browser session. */
  storageKey?: string;
}

const LINES: readonly BootLine[] = [
  { level: "boot", text: "initializing model gateway…" },
  { level: "ok", text: "model gateway online · ollama (mock) attached" },
  { level: "boot", text: "connecting vector store…" },
  { level: "ok", text: "qdrant online · 3 collections indexed" },
  { level: "boot", text: "attaching workflow engine…" },
  { level: "ok", text: "temporal worker attached · task-queue: missions" },
  { level: "info", text: "loading profile brain · 12 verified skills" },
  { level: "boot", text: "spinning up agent pool…" },
  { level: "ok", text: "agent pool ready · max_agents=4" },
  { level: "warn", text: "github writes DISABLED (safe mode)" },
  { level: "ok", text: "mission controller ready" },
] as const;

const LEVEL_COLOR: Record<BootLevel, string> = {
  boot: "var(--accent-cyan)",
  ok: "var(--accent-emerald)",
  info: "var(--accent-blue)",
  warn: "var(--accent-amber)",
};

const LEVEL_TAG: Record<BootLevel, string> = {
  boot: "boot",
  ok: " ok ",
  info: "info",
  warn: "warn",
};

/** Per-character typing cadence and inter-line pause, in ms. */
const CHAR_MS = 12;
const LINE_PAUSE_MS = 130;

/**
 * A fake-but-real terminal boot log. On a full-motion first visit it types the
 * lines out with a blinking cursor; under reduced motion it renders every line
 * instantly. It runs at most once per session (sessionStorage guard) and is
 * skippable. `onDone` fires on completion or skip.
 */
export function BootSequence({
  onDone,
  storageKey = "cf.boot.seen",
}: BootSequenceProps) {
  const reduceMotion = useReducedMotion();

  // Which lines are fully revealed, and how much of the in-progress line.
  const [visibleLines, setVisibleLines] = useState(0);
  const [typedChars, setTypedChars] = useState(0);
  const [finished, setFinished] = useState(false);

  const doneRef = useRef(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);

  const clearTimers = useCallback(() => {
    for (const t of timers.current) clearTimeout(t);
    timers.current = [];
  }, []);

  const finish = useCallback(() => {
    if (doneRef.current) return;
    doneRef.current = true;
    clearTimers();
    setVisibleLines(LINES.length);
    setFinished(true);
    try {
      window.sessionStorage.setItem(storageKey, "1");
    } catch {
      /* sessionStorage may be unavailable (privacy mode) — ignore. */
    }
    // Brief beat so the completed log is legible before we hand off.
    const t = setTimeout(() => onDone(), reduceMotion ? 0 : 420);
    timers.current.push(t);
  }, [clearTimers, onDone, reduceMotion, storageKey]);

  // Reduced motion: reveal everything immediately, then done.
  useEffect(() => {
    if (!reduceMotion) return;
    setVisibleLines(LINES.length);
    setTypedChars(0);
    finish();
    return () => clearTimers();
  }, [reduceMotion, finish, clearTimers]);

  // Full-motion typewriter driver.
  useEffect(() => {
    if (reduceMotion || doneRef.current) return;

    const current = LINES[visibleLines];
    if (!current) {
      // All lines are typed.
      finish();
      return;
    }

    if (typedChars < current.text.length) {
      const t = setTimeout(() => setTypedChars((c) => c + 1), CHAR_MS);
      timers.current.push(t);
      return () => clearTimeout(t);
    }

    // Line complete → pause, then advance to the next line.
    const t = setTimeout(() => {
      setVisibleLines((v) => v + 1);
      setTypedChars(0);
    }, LINE_PAUSE_MS);
    timers.current.push(t);
    return () => clearTimeout(t);
  }, [reduceMotion, visibleLines, typedChars, finish]);

  // Keep the newest line in view.
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [visibleLines, typedChars]);

  // Clean up on unmount.
  useEffect(() => () => clearTimers(), [clearTimers]);

  // Skip via keyboard (Enter/Esc/Space) as well as the button.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Enter" || e.key === "Escape" || e.key === " ") {
        e.preventDefault();
        finish();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [finish]);

  const completedLines = useMemo(
    () => LINES.slice(0, Math.min(visibleLines, LINES.length)),
    [visibleLines],
  );
  const activeLine =
    !reduceMotion && visibleLines < LINES.length ? LINES[visibleLines] : null;

  return (
    <AnimatePresence>
      {!finished || reduceMotion ? (
        <motion.div
          key="bootseq"
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
          style={{ background: "var(--bg-void)" }}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0, transition: { duration: 0.35 } }}
          role="status"
          aria-live="polite"
          aria-label="System boot sequence"
        >
          <motion.div
            initial={reduceMotion ? false : { opacity: 0, y: 14, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            transition={{ type: "spring", stiffness: 220, damping: 26 }}
            className="glass glow-cyan w-full max-w-2xl overflow-hidden"
          >
            {/* Terminal title bar */}
            <div className="flex items-center gap-2 px-4 py-2.5 hairline-b">
              <span className="flex items-center gap-1.5" aria-hidden="true">
                <span className="h-2.5 w-2.5 rounded-full bg-[color:var(--accent-rose)]" />
                <span className="h-2.5 w-2.5 rounded-full bg-[color:var(--accent-amber)]" />
                <span className="h-2.5 w-2.5 rounded-full bg-[color:var(--accent-emerald)]" />
              </span>
              <span className="mono ml-2 text-xs text-[color:var(--text-secondary)]">
                careerforge://boot
              </span>
              <button
                type="button"
                onClick={finish}
                className="mono ml-auto rounded-md px-2.5 py-1 text-xs font-semibold text-[color:var(--text-secondary)] transition-colors hover:bg-white/5 hover:text-[color:var(--text-primary)]"
              >
                Skip →
              </button>
            </div>

            {/* Log body */}
            <div
              ref={scrollRef}
              className="mono max-h-[52vh] min-h-[16rem] overflow-y-auto px-4 py-3 text-[0.8125rem] leading-relaxed"
            >
              {completedLines.map((line, i) => (
                <LogRow key={i} line={line} full />
              ))}

              {activeLine ? (
                <LogRow
                  line={activeLine}
                  text={activeLine.text.slice(0, typedChars)}
                  cursor
                />
              ) : null}

              {(visibleLines >= LINES.length || reduceMotion) && (
                <div className="mt-2 flex items-center gap-2 text-[color:var(--accent-emerald)]">
                  <span aria-hidden="true">›</span>
                  <span>boot complete — entering command center</span>
                  <span className="cf-cursor" aria-hidden="true">
                    ▊
                  </span>
                </div>
              )}
            </div>
          </motion.div>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}

function LogRow({
  line,
  text,
  full = false,
  cursor = false,
}: {
  line: BootLine;
  text?: string;
  full?: boolean;
  cursor?: boolean;
}) {
  const color = LEVEL_COLOR[line.level];
  const body = full ? line.text : (text ?? "");
  return (
    <div className="flex items-start gap-2 py-0.5">
      <span
        className="shrink-0 select-none tracking-tight"
        style={{ color }}
        aria-hidden="true"
      >
        [{LEVEL_TAG[line.level]}]
      </span>
      <span className="text-[color:var(--text-primary)]">
        {body}
        {cursor ? (
          <span className="cf-cursor" style={{ color }} aria-hidden="true">
            ▊
          </span>
        ) : null}
      </span>
    </div>
  );
}

export default BootSequence;
