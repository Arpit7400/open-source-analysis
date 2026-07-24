"use client";

import { useMemo, useState } from "react";
import dynamic from "next/dynamic";
import type { DiffEditorProps } from "@monaco-editor/react";
import { FileDiff, Loader2 } from "lucide-react";
import type { Candidate, DiffLine } from "@/lib/types";
import { cn } from "@/lib/cn";

/**
 * Monaco's DiffEditor is browser-only (it touches `window`/web workers), so it
 * is loaded dynamically with SSR disabled. If the chunk fails to load we render
 * a styled unified-diff fallback instead — the UI is never dead.
 */
const DiffEditor = dynamic<DiffEditorProps>(
  () => import("@monaco-editor/react").then((mod) => mod.DiffEditor),
  {
    ssr: false,
    loading: () => <DiffLoading />,
  },
);

/* ------------------------------------------------------------------ */
/* Diff text construction                                             */
/* ------------------------------------------------------------------ */

/**
 * Join a candidate's DiffLine[] into two plain-text documents (original vs
 * modified) that Monaco can diff. Each entry is prefixed with a file/hunk
 * header so multi-file candidates read coherently on both sides.
 */
function buildSides(diff: DiffLine[]): { original: string; modified: string } {
  const originalParts: string[] = [];
  const modifiedParts: string[] = [];

  for (const line of diff) {
    const header = `// ${line.path}${line.hunk ? `  ${line.hunk}` : ""}`;
    originalParts.push(header);
    originalParts.push(line.old);
    originalParts.push("");

    modifiedParts.push(header);
    modifiedParts.push(line.new);
    modifiedParts.push("");
  }

  return {
    original: originalParts.join("\n").trimEnd(),
    modified: modifiedParts.join("\n").trimEnd(),
  };
}

/**
 * Guess a Monaco language id from the first changed file's extension so
 * syntax highlighting is reasonable without a heavy detection pass.
 */
function guessLanguage(diff: DiffLine[]): string {
  const first = diff[0];
  const path = first?.path ?? "";
  const dot = path.lastIndexOf(".");
  const ext = dot >= 0 ? path.slice(dot + 1).toLowerCase() : "";
  switch (ext) {
    case "ts":
    case "tsx":
      return "typescript";
    case "js":
    case "jsx":
      return "javascript";
    case "py":
      return "python";
    case "md":
      return "markdown";
    case "json":
      return "json";
    case "yml":
    case "yaml":
      return "yaml";
    case "toml":
      return "ini";
    case "sh":
      return "shell";
    default:
      return "plaintext";
  }
}

/* ------------------------------------------------------------------ */
/* Component                                                          */
/* ------------------------------------------------------------------ */

export interface DiffViewerProps {
  candidate: Candidate | null;
  className?: string;
}

/**
 * Read-only, dark side-by-side diff for the selected candidate. Falls back to
 * a styled unified diff if Monaco cannot load in this environment.
 */
export function DiffViewer({ candidate, className }: DiffViewerProps) {
  const [monacoFailed, setMonacoFailed] = useState(false);

  const sides = useMemo(
    () => buildSides(candidate?.diff ?? []),
    [candidate],
  );
  const language = useMemo(
    () => guessLanguage(candidate?.diff ?? []),
    [candidate],
  );

  if (!candidate) {
    return (
      <div
        className={cn(
          "flex flex-1 flex-col items-center justify-center gap-2 rounded-[var(--radius-sm)] p-8 text-center hairline",
          className,
        )}
        style={{ background: "var(--bg-void)" }}
      >
        <FileDiff
          className="h-6 w-6 text-[color:var(--text-muted)]"
          aria-hidden="true"
        />
        <p className="text-sm text-[color:var(--text-secondary)]">
          Select a candidate to view its diff.
        </p>
      </div>
    );
  }

  const showFallback = monacoFailed || candidate.diff.length === 0;

  return (
    <div
      className={cn(
        "flex min-h-0 flex-col overflow-hidden rounded-[var(--radius-sm)] hairline",
        className,
      )}
      style={{ background: "var(--bg-void)" }}
    >
      <div className="flex items-center justify-between gap-2 px-3 py-2 hairline-b">
        <span className="eyebrow flex items-center gap-1.5 text-[0.5625rem]">
          <FileDiff className="h-3 w-3" aria-hidden="true" />
          Candidate diff
        </span>
        <span className="mono text-[0.625rem] text-[color:var(--text-muted)]">
          {candidate.diff.length}{" "}
          {candidate.diff.length === 1 ? "hunk" : "hunks"} · read-only
        </span>
      </div>

      <div className="relative min-h-[16rem] flex-1">
        {showFallback ? (
          <UnifiedDiffFallback diff={candidate.diff} />
        ) : (
          <DiffEditor
            original={sides.original}
            modified={sides.modified}
            language={language}
            theme="vs-dark"
            keepCurrentOriginalModel={false}
            keepCurrentModifiedModel={false}
            options={{
              readOnly: true,
              renderSideBySide: true,
              automaticLayout: true,
              minimap: { enabled: false },
              scrollBeyondLastLine: false,
              fontFamily:
                'var(--font-mono), "JetBrains Mono", ui-monospace, monospace',
              fontSize: 12,
              lineNumbers: "on",
              renderOverviewRuler: false,
              scrollbar: { alwaysConsumeMouseWheel: false },
              contextmenu: false,
              domReadOnly: true,
            }}
            onMount={(_editor, monaco) => {
              try {
                monaco.editor.setTheme("vs-dark");
              } catch {
                setMonacoFailed(true);
              }
            }}
          />
        )}
      </div>
    </div>
  );
}

/** Spinner shown while the Monaco chunk streams in. */
function DiffLoading() {
  return (
    <div className="flex h-full min-h-[16rem] w-full items-center justify-center gap-2 text-[color:var(--text-muted)]">
      <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
      <span className="mono text-xs">loading diff editor…</span>
    </div>
  );
}

/**
 * Styled unified-diff fallback: `-` old lines in rose, `+` new lines in
 * emerald, with per-file hunk headers. Pure CSS, no editor dependency.
 */
function UnifiedDiffFallback({ diff }: { diff: DiffLine[] }) {
  if (diff.length === 0) {
    return (
      <div className="flex h-full items-center justify-center p-6 text-center">
        <p className="text-sm text-[color:var(--text-muted)]">
          This candidate proposes no file changes.
        </p>
      </div>
    );
  }

  return (
    <div
      className="h-full overflow-auto p-3"
      aria-label="Unified diff (fallback renderer)"
    >
      {diff.map((line, i) => (
        <div
          key={`hunk-${i}`}
          className="mb-3 overflow-hidden rounded-md hairline"
        >
          <div className="mono flex flex-wrap items-center gap-x-2 px-2.5 py-1.5 text-[0.625rem] text-[color:var(--text-secondary)] hairline-b">
            <span className="text-[color:var(--text-primary)]">
              {line.path}
            </span>
            {line.hunk ? (
              <span className="text-[color:var(--accent-cyan)]">
                {line.hunk}
              </span>
            ) : null}
          </div>
          <div className="mono text-[0.6875rem] leading-relaxed">
            {line.old
              .split("\n")
              .map((text, j) => (
                <pre
                  key={`old-${i}-${j}`}
                  className="overflow-x-auto px-2.5 py-0.5"
                  style={{
                    color: "var(--accent-rose)",
                    background:
                      "color-mix(in srgb, var(--accent-rose) 8%, transparent)",
                  }}
                >
                  <code>- {text}</code>
                </pre>
              ))}
            {line.new
              .split("\n")
              .map((text, j) => (
                <pre
                  key={`new-${i}-${j}`}
                  className="overflow-x-auto px-2.5 py-0.5"
                  style={{
                    color: "var(--accent-emerald)",
                    background:
                      "color-mix(in srgb, var(--accent-emerald) 8%, transparent)",
                  }}
                >
                  <code>+ {text}</code>
                </pre>
              ))}
          </div>
        </div>
      ))}
    </div>
  );
}

export default DiffViewer;
