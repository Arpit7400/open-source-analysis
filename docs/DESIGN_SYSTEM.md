# CareerForge AI — Design System & Motion Language

> **Goal:** anyone who opens this thinks *"this is a serious, complex, heavy engineering system."*
> Dark technical command-center aesthetic. Restrained glass. Data-driven motion. Selective 3D.
> NOT a decorative marketing landing page — an engineering operations console.

## Brand + Tokens (Tailwind / CSS variables)

Dark-first. Define in `globals.css` as CSS variables and mirror in `tailwind.config`.

```
--bg-void:        #05070d   /* deepest background */
--bg-base:        #0a0e17   /* app background */
--bg-panel:       #0e1420   /* card/panel base */
--bg-elevated:    #131b2b   /* elevated surface */
--glass:          rgba(18,26,42,0.55)  /* glass surfaces, backdrop-blur */
--border-hair:    rgba(120,160,220,0.12)
--border-glow:    rgba(80,200,255,0.35)

--text-primary:   #e6edf7
--text-secondary: #93a4bd
--text-muted:     #556274

/* Accent ramps — cyan (primary/data), violet (agents), amber (blocked), emerald (success), rose (fail) */
--accent-cyan:    #22d3ee
--accent-cyan-dim:#0e7490
--accent-violet:  #a78bfa
--accent-amber:   #fbbf24
--accent-emerald: #34d399
--accent-rose:    #fb7185
--accent-blue:    #60a5fa

/* Agent-state colors — MUST match AgentState enum */
WAITING   -> text-muted, dim
RUNNING   -> accent-cyan  (animated)
COMPLETED -> accent-emerald
VERIFYING -> accent-violet (dual-ring)
BLOCKED   -> accent-amber
FAILED    -> accent-rose
REJECTED  -> desaturated / strikethrough feel
```

Typography: **Geist Sans** (UI) + **Geist Mono** / **JetBrains Mono** (code, logs, metrics, IDs). Numbers and IDs are ALWAYS mono. Tight tracking on headings. Uppercase micro-labels with letter-spacing for section eyebrows.

Surfaces: subtle 1px hairline borders, faint inner glow on active elements, `backdrop-blur` glass over a very dark base. A fixed **starfield / grid vignette** background (very low opacity, GPU-cheap, respects reduced-motion) sells the "space command center" feel.

## Motion language (framer-motion / `motion`)

- **Everything enters** with a staggered fade+rise (`opacity 0→1`, `y 12→0`, spring). Panels stagger children by ~40ms.
- **Data-driven motion**: edges in the agent graph have flowing animated dashes when `animated:true`. Numbers count up (`animate-count`). Progress rings sweep.
- **State transitions**: agent node color/scale springs on state change; a soft pulse on RUNNING; a checkmark draw-on for COMPLETED; a shake+red flash for FAILED.
- **Ambient**: slow parallax on the background grid; scanning shimmer line across the Command Center header; subtle "breathing" glow on the active mission node.
- **Reduced motion**: `prefers-reduced-motion` disables ambient/loops, keeps essential state feedback (instant, no spring).
- **Perf**: 60fps target. Never animate layout width/height on many nodes — use transform/opacity. FPS meter in a corner dev widget.

## Signature components (build these — they make it look heavy)

1. **BootSequence** — a fake-but-real terminal boot log that types out on first load ("initializing model gateway… qdrant online… temporal worker attached…") then reveals the app. Instant "this is a big system" impression. Skippable, reduced-motion aware.
2. **Command Center** — the hero. Left: live mission list + resource gauges (animated radial CPU/RAM/VRAM). Center: **React Flow live agent graph** with animated edges and state-colored nodes. Right: streaming **event log** (mono, colored levels, auto-scroll, virtualized). Top: mission status bar with phase pipeline (Intake → Static → Runtime → Aggregate → Fix → Verify → Approval) that lights up as it progresses.
3. **Agent Graph (React Flow)** — custom node renderers per group, animated flow edges, minimap, state-colored glow, progress ring on each node, click → detail drawer.
4. **Repo X-Ray / Findings** — severity-coded finding cards with evidence (file\:line, code snippet via a mono block), reproduction badge, expandable limitations.
5. **Candidate Diff (Monaco)** — side-by-side diff, verification matrix (checks × verdicts), risk panel, "independent verifier" badges. Include at least one **REJECTED** candidate to show verification works.
6. **Verification Matrix** — grid of checks vs status with animated pass/fail stamps.
7. **Approval Panel** — human-in-the-loop gate; shows draft (Monaco/markdown), big "GitHub writes DISABLED" safety banner, Approve/Reject.
8. **Skill Constellation (R3F)** — 3D skill nodes, size=evidence, glow intensity=confidence, pulse=recency, edges=relationships. Lazy-loaded, with an **accessible table fallback** and non-WebGL fallback.
9. **Industry Pulse** — momentum timeline (ECharts), relevance overlays, gap cards.

## Accessibility (required, not optional)

- Respect `prefers-reduced-motion` everywhere.
- Lazy-load all Three.js; provide table/list fallback + non-WebGL detection.
- Keyboard nav, visible focus rings, semantic headings, ARIA on live regions (log, status).
- High-contrast mode toggle. User-selectable **Performance Mode** (disables 3D + ambient).
- SSE live regions announced politely; never trap focus.

## Frontend stack (fixed)

Next.js 14 (App Router) · TypeScript · Tailwind · shadcn/ui · framer-motion (`motion`) · @xyflow/react (React Flow) · @react-three/fiber + drei · @monaco-editor/react · echarts-for-react · TanStack Query · Zustand · lucide-react icons.

Data layer: a typed API client (`lib/api.ts`) matching `API_CONTRACT.md`, an SSE hook (`useMissionStream`), and a Zustand store for live mission state. In demo mode the client hits the real backend's scripted simulation (preferred) OR a bundled client-side mock (fallback) so the UI is never dead.
