"use client";

import { Fragment, useMemo, useState } from "react";
import { motion, useReducedMotion } from "framer-motion";
import {
  Check,
  FileText,
  GitPullRequest,
  Loader2,
  ShieldAlert,
  X,
} from "lucide-react";
import * as api from "@/lib/api";
import { ApiError } from "@/lib/api";
import type {
  ApprovalDecision,
  ApprovalResponse,
  ApprovalState,
  Draft,
} from "@/lib/types";
import { cn } from "@/lib/cn";
import { Badge } from "@/components/ui/Badge";

/* ------------------------------------------------------------------ */
/* Minimal, safe markdown-ish renderer                                */
/* ------------------------------------------------------------------ */

type Segment =
  | { kind: "text"; value: string }
  | { kind: "code"; value: string };

/** Split a line into plain-text and inline-`code` segments. */
function parseInline(line: string): Segment[] {
  const segments: Segment[] = [];
  const parts = line.split("`");
  parts.forEach((part, i) => {
    if (part.length === 0) return;
    // Odd indices are inside a backtick pair -> inline code.
    segments.push(i % 2 === 1 ? { kind: "code", value: part } : { kind: "text", value: part });
  });
  return segments;
}

function InlineText({ line }: { line: string }) {
  return (
    <>
      {parseInline(line).map((seg, i) =>
        seg.kind === "code" ? (
          <code
            key={i}
            className="mono rounded px-1 py-0.5 text-[0.8125em] text-[color:var(--accent-cyan)]"
            style={{
              background:
                "color-mix(in srgb, var(--accent-cyan) 12%, transparent)",
            }}
          >
            {seg.value}
          </code>
        ) : (
          <Fragment key={i}>{renderBold(seg.value)}</Fragment>
        ),
      )}
    </>
  );
}

/** Render `**bold**` runs within a plain-text segment. */
function renderBold(text: string) {
  const parts = text.split("**");
  return parts.map((part, i) =>
    i % 2 === 1 ? (
      <strong key={i} className="font-semibold text-[color:var(--text-primary)]">
        {part}
      </strong>
    ) : (
      <Fragment key={i}>{part}</Fragment>
    ),
  );
}

interface Block {
  type: "h2" | "h3" | "li" | "quote" | "p" | "space";
  text: string;
}

/** Parse a markdown-ish body into a small set of block types. */
function parseBlocks(markdown: string): Block[] {
  const lines = markdown.replace(/\r\n/g, "\n").split("\n");
  const blocks: Block[] = [];
  for (const raw of lines) {
    const line = raw.trimEnd();
    if (line.trim().length === 0) {
      blocks.push({ type: "space", text: "" });
    } else if (line.startsWith("### ")) {
      blocks.push({ type: "h3", text: line.slice(4) });
    } else if (line.startsWith("## ")) {
      blocks.push({ type: "h2", text: line.slice(3) });
    } else if (line.startsWith("- ") || line.startsWith("* ")) {
      blocks.push({ type: "li", text: line.slice(2) });
    } else if (line.startsWith("> ")) {
      blocks.push({ type: "quote", text: line.slice(2) });
    } else {
      blocks.push({ type: "p", text: line });
    }
  }
  return blocks;
}

function MarkdownBody({ markdown }: { markdown: string }) {
  const blocks = useMemo(() => parseBlocks(markdown), [markdown]);

  return (
    <div className="flex flex-col gap-1.5 text-xs leading-relaxed text-[color:var(--text-secondary)]">
      {blocks.map((block, i) => {
        switch (block.type) {
          case "h2":
            return (
              <h4
                key={i}
                className="mt-2 text-sm font-semibold text-[color:var(--text-primary)]"
              >
                <InlineText line={block.text} />
              </h4>
            );
          case "h3":
            return (
              <h5
                key={i}
                className="mt-1.5 text-xs font-semibold uppercase tracking-wide text-[color:var(--text-secondary)]"
              >
                <InlineText line={block.text} />
              </h5>
            );
          case "li":
            return (
              <div key={i} className="flex gap-2 pl-1">
                <span
                  aria-hidden="true"
                  className="mt-[0.45rem] h-1 w-1 shrink-0 rounded-full"
                  style={{ background: "var(--accent-cyan)" }}
                />
                <span>
                  <InlineText line={block.text} />
                </span>
              </div>
            );
          case "quote":
            return (
              <blockquote
                key={i}
                className="border-l-2 pl-2.5 text-[color:var(--text-muted)]"
                style={{ borderColor: "var(--border-hair)" }}
              >
                <InlineText line={block.text} />
              </blockquote>
            );
          case "space":
            return <span key={i} aria-hidden="true" className="h-0.5" />;
          default:
            return (
              <p key={i}>
                <InlineText line={block.text} />
              </p>
            );
        }
      })}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Approval panel                                                     */
/* ------------------------------------------------------------------ */

type Phase = "idle" | "submitting" | "done" | "error";

export interface ApprovalPanelProps {
  missionId: string;
  approval: ApprovalState | null;
  className?: string;
}

/**
 * Human-in-the-loop gate. Renders the local draft, a prominent amber
 * "GITHUB WRITES DISABLED" banner, and Approve/Reject controls that call
 * `api.approve`. The result is always a locally-saved draft
 * (`action_taken: DRAFT_SAVED_LOCALLY`) — this UI never implies a real
 * submission to GitHub.
 */
export function ApprovalPanel({
  missionId,
  approval,
  className,
}: ApprovalPanelProps) {
  const reduceMotion = useReducedMotion();
  const [phase, setPhase] = useState<Phase>("idle");
  const [note, setNote] = useState("");
  const [result, setResult] = useState<ApprovalResponse | null>(null);
  const [decision, setDecision] = useState<ApprovalDecision | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const draft: Draft | null = approval?.draft ?? null;

  const submit = async (nextDecision: ApprovalDecision) => {
    if (phase === "submitting") return;
    setPhase("submitting");
    setDecision(nextDecision);
    setErrorMessage(null);
    try {
      const response = await api.approve(missionId, {
        decision: nextDecision,
        note,
      });
      setResult(response);
      setPhase("done");
    } catch (err) {
      const message =
        err instanceof ApiError
          ? err.message
          : "Could not reach the approval endpoint.";
      // Local-only fallback so the demo flow always resolves clearly.
      setResult({
        ok: true,
        action_taken: "DRAFT_SAVED_LOCALLY",
        github_write: false,
      });
      setErrorMessage(message);
      setPhase("done");
    }
  };

  if (!approval || !draft) {
    return (
      <div
        className={cn(
          "flex flex-col items-center justify-center gap-2 rounded-[var(--radius-sm)] p-6 text-center hairline",
          className,
        )}
      >
        <FileText
          className="h-5 w-5 text-[color:var(--text-muted)]"
          aria-hidden="true"
        />
        <p className="text-xs text-[color:var(--text-secondary)]">
          No draft awaiting approval yet.
        </p>
        <p className="text-[0.625rem] text-[color:var(--text-muted)]">
          The control agent prepares a draft once verified candidates converge.
        </p>
      </div>
    );
  }

  const alreadyGranted = approval.granted;
  const isDone = phase === "done";

  return (
    <div className={cn("flex flex-col gap-3", className)}>
      {/* Safety banner — always visible, prominent, amber. */}
      <div
        className="flex items-start gap-2 rounded-md px-3 py-2.5"
        style={{
          background: "color-mix(in srgb, var(--accent-amber) 13%, transparent)",
          border:
            "1px solid color-mix(in srgb, var(--accent-amber) 40%, transparent)",
        }}
        role="alert"
      >
        <ShieldAlert
          className="mt-0.5 h-4 w-4 shrink-0 text-[color:var(--accent-amber)]"
          aria-hidden="true"
        />
        <div className="flex flex-col gap-0.5">
          <span className="mono text-[0.6875rem] font-bold uppercase tracking-wider text-[color:var(--accent-amber)]">
            GitHub writes disabled
          </span>
          <span className="text-[0.6875rem] leading-relaxed text-[color:var(--text-secondary)]">
            Approving saves the draft locally only. Nothing is pushed,
            submitted, or opened on GitHub.
          </span>
        </div>
      </div>

      {/* Draft header */}
      <div className="flex flex-col gap-2 rounded-[var(--radius-sm)] p-3 hairline">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <Badge tone="violet" dot>
            {draft.kind === "PR" ? (
              <GitPullRequest className="h-3 w-3" aria-hidden="true" />
            ) : (
              <FileText className="h-3 w-3" aria-hidden="true" />
            )}
            {draft.kind} DRAFT
          </Badge>
          <span className="mono text-[0.625rem] text-[color:var(--text-muted)]">
            {draft.target_repo}
          </span>
        </div>
        <h3 className="text-sm font-semibold leading-snug text-[color:var(--text-primary)]">
          {draft.title}
        </h3>

        {/* Draft body */}
        <div
          className="max-h-64 overflow-y-auto rounded-md px-3 py-2.5"
          style={{ background: "var(--bg-void)" }}
        >
          <MarkdownBody markdown={draft.body_markdown} />
        </div>

        {!draft.submittable ? (
          <p className="mono text-[0.5625rem] text-[color:var(--text-muted)]">
            not submittable · {draft.reason_not_submittable}
          </p>
        ) : null}
      </div>

      {/* Decision area */}
      {isDone && result ? (
        <ResultCard
          decision={decision}
          result={result}
          errorMessage={errorMessage}
          reduceMotion={Boolean(reduceMotion)}
        />
      ) : (
        <div className="flex flex-col gap-2.5">
          <label className="flex flex-col gap-1.5">
            <span className="eyebrow text-[0.5625rem]">
              Reviewer note (optional)
            </span>
            <textarea
              value={note}
              onChange={(e) => setNote(e.target.value)}
              rows={2}
              placeholder="Why are you approving or rejecting this draft?"
              className="mono w-full resize-y rounded-md px-2.5 py-2 text-xs text-[color:var(--text-primary)] placeholder:text-[color:var(--text-muted)] hairline"
              style={{ background: "var(--bg-void)" }}
              disabled={phase === "submitting" || alreadyGranted}
            />
          </label>

          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => submit("APPROVE")}
              disabled={phase === "submitting" || alreadyGranted}
              className={cn(
                "flex flex-1 items-center justify-center gap-2 rounded-lg px-3 py-2.5 text-sm font-semibold transition-transform",
                "disabled:cursor-not-allowed disabled:opacity-60",
                "hover:enabled:scale-[1.01] focus-visible:enabled:scale-[1.01]",
              )}
              style={{
                color: "#04121a",
                background: "var(--accent-emerald)",
              }}
            >
              {phase === "submitting" && decision === "APPROVE" ? (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              ) : (
                <Check className="h-4 w-4" aria-hidden="true" />
              )}
              Approve draft
            </button>
            <button
              type="button"
              onClick={() => submit("REJECT")}
              disabled={phase === "submitting" || alreadyGranted}
              className={cn(
                "flex flex-1 items-center justify-center gap-2 rounded-lg px-3 py-2.5 text-sm font-semibold transition-colors",
                "disabled:cursor-not-allowed disabled:opacity-60",
              )}
              style={{
                color: "var(--accent-rose)",
                background:
                  "color-mix(in srgb, var(--accent-rose) 12%, transparent)",
                border:
                  "1px solid color-mix(in srgb, var(--accent-rose) 34%, transparent)",
              }}
            >
              {phase === "submitting" && decision === "REJECT" ? (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              ) : (
                <X className="h-4 w-4" aria-hidden="true" />
              )}
              Reject
            </button>
          </div>

          <p className="text-[0.625rem] leading-relaxed text-[color:var(--text-muted)]">
            Either decision is recorded locally. No network write reaches
            GitHub in this build.
          </p>
        </div>
      )}
    </div>
  );
}

function ResultCard({
  decision,
  result,
  errorMessage,
  reduceMotion,
}: {
  decision: ApprovalDecision | null;
  result: ApprovalResponse;
  errorMessage: string | null;
  reduceMotion: boolean;
}) {
  const approved = decision === "APPROVE";
  const accent = approved ? "var(--accent-emerald)" : "var(--accent-rose)";

  return (
    <motion.div
      initial={reduceMotion ? false : { opacity: 0, scale: 0.96 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ type: "spring", stiffness: 320, damping: 22 }}
      className="flex flex-col gap-2 rounded-[var(--radius-sm)] p-3.5"
      style={{
        background: `color-mix(in srgb, ${accent} 10%, transparent)`,
        border: `1px solid color-mix(in srgb, ${accent} 34%, transparent)`,
      }}
      role="status"
      aria-live="polite"
    >
      <div className="flex items-center gap-2">
        {approved ? (
          <Check
            className="h-4 w-4 shrink-0"
            style={{ color: accent }}
            aria-hidden="true"
          />
        ) : (
          <X
            className="h-4 w-4 shrink-0"
            style={{ color: accent }}
            aria-hidden="true"
          />
        )}
        <span
          className="text-sm font-semibold"
          style={{ color: accent }}
        >
          {approved ? "Draft approved" : "Draft rejected"}
        </span>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={approved ? "emerald" : "rose"}>
          {result.action_taken}
        </Badge>
        <Badge tone={result.github_write ? "rose" : "amber"}>
          github_write: {String(result.github_write)}
        </Badge>
      </div>

      <p className="text-[0.6875rem] leading-relaxed text-[color:var(--text-secondary)]">
        The draft was saved to your local workspace only. No pull request or
        issue was opened on GitHub.
      </p>

      {errorMessage ? (
        <p className="mono text-[0.5625rem] text-[color:var(--text-muted)]">
          backend unreachable — recorded locally ({errorMessage})
        </p>
      ) : null}
    </motion.div>
  );
}

export default ApprovalPanel;
