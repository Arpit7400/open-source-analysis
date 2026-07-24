/**
 * CareerForge AI — client-side mission simulator (fallback).
 *
 * When the backend SSE stream cannot be reached, this simulator emits the
 * SAME event sequence (matching docs/API_CONTRACT.md) over time so the UI is
 * never dead. Content is deterministic and resembles a static+runtime
 * analysis of a small Python repository: it produces 5 findings and 3 fix
 * candidates including one REJECTED candidate (to demonstrate that
 * independent verification actually gates submissions).
 *
 * Usage:
 *   const stop = runMockMission(missionId, (name, payload) => { ... });
 *   // later: stop();  // cancels all pending timers
 */

import type {
  AgentNode,
  Candidate,
  Draft,
  Finding,
  GraphEdge,
  LogEvent,
  MissionStreamEventMap,
  MissionStreamEventName,
  ResourceEvent,
} from './types';

/** Callback invoked for each simulated SSE event. */
export type MockEmit = <K extends MissionStreamEventName>(
  event: K,
  payload: MissionStreamEventMap[K],
) => void;

/** Cancels an in-flight mock mission. */
export type MockCanceller = () => void;

const REPO = 'octo-labs/fastwidget';
const REPO_URL = `https://github.com/${REPO}`;

/** Deterministic timeline base timestamp (kept stable for reproducibility). */
const BASE_TS = Date.parse('2026-07-24T10:00:00Z');

function ts(offsetMs: number): string {
  return new Date(BASE_TS + offsetMs).toISOString();
}

/* ------------------------------------------------------------------ */
/* Agent roster                                                       */
/* ------------------------------------------------------------------ */

interface AgentSpec {
  id: string;
  label: string;
  group: AgentNode['group'];
  verifier_of: string | null;
}

const AGENT_SPECS: AgentSpec[] = [
  { id: 'control.mission', label: 'Mission Control', group: 'CONTROL', verifier_of: null },
  { id: 'intake.repo', label: 'Repo Intake Agent', group: 'INTAKE', verifier_of: null },
  { id: 'static.security', label: 'Security Smell Agent', group: 'STATIC', verifier_of: null },
  { id: 'static.typing', label: 'Typing & API Agent', group: 'STATIC', verifier_of: null },
  { id: 'static.docs', label: 'Docs Drift Agent', group: 'STATIC', verifier_of: null },
  { id: 'runtime.tests', label: 'Runtime Repro Agent', group: 'RUNTIME', verifier_of: null },
  { id: 'duplicate.search', label: 'Duplicate Search Agent', group: 'DUPLICATE', verifier_of: null },
  { id: 'aggregate.findings', label: 'Findings Aggregator', group: 'AGGREGATE', verifier_of: null },
  { id: 'fix.a', label: 'Fix Author A', group: 'FIX', verifier_of: null },
  { id: 'fix.b', label: 'Fix Author B', group: 'FIX', verifier_of: null },
  { id: 'fix.c', label: 'Fix Author C', group: 'FIX', verifier_of: null },
  { id: 'verify.regression', label: 'Regression Verifier', group: 'VERIFY', verifier_of: 'fix.a' },
  { id: 'verify.lint', label: 'Lint Verifier', group: 'VERIFY', verifier_of: 'fix.a' },
  { id: 'verify.scope', label: 'Scope Verifier', group: 'VERIFY', verifier_of: 'fix.b' },
];

const EDGE_SPECS: Array<Omit<GraphEdge, 'animated'>> = [
  { id: 'e-ctrl-intake', source: 'control.mission', target: 'intake.repo' },
  { id: 'e-intake-sec', source: 'intake.repo', target: 'static.security' },
  { id: 'e-intake-typ', source: 'intake.repo', target: 'static.typing' },
  { id: 'e-intake-docs', source: 'intake.repo', target: 'static.docs' },
  { id: 'e-intake-rt', source: 'intake.repo', target: 'runtime.tests' },
  { id: 'e-sec-dup', source: 'static.security', target: 'duplicate.search' },
  { id: 'e-sec-agg', source: 'static.security', target: 'aggregate.findings' },
  { id: 'e-typ-agg', source: 'static.typing', target: 'aggregate.findings' },
  { id: 'e-docs-agg', source: 'static.docs', target: 'aggregate.findings' },
  { id: 'e-rt-agg', source: 'runtime.tests', target: 'aggregate.findings' },
  { id: 'e-agg-fixa', source: 'aggregate.findings', target: 'fix.a' },
  { id: 'e-agg-fixb', source: 'aggregate.findings', target: 'fix.b' },
  { id: 'e-agg-fixc', source: 'aggregate.findings', target: 'fix.c' },
  { id: 'e-fixa-vreg', source: 'fix.a', target: 'verify.regression' },
  { id: 'e-fixa-vlint', source: 'fix.a', target: 'verify.lint' },
  { id: 'e-fixb-vscope', source: 'fix.b', target: 'verify.scope' },
];

function agent(
  spec: AgentSpec,
  state: AgentNode['state'],
  progress: number,
  resultCount: number,
  detail: string,
  startedAt: string | null,
): AgentNode {
  return {
    id: spec.id,
    label: spec.label,
    group: spec.group,
    state,
    progress,
    result_count: resultCount,
    started_at: startedAt,
    detail,
    verifier_of: spec.verifier_of,
  };
}

function specById(id: string): AgentSpec {
  const found = AGENT_SPECS.find((s) => s.id === id);
  if (!found) {
    throw new Error(`mockMission: unknown agent id "${id}"`);
  }
  return found;
}

/* ------------------------------------------------------------------ */
/* Findings (5, spanning categories/severities)                       */
/* ------------------------------------------------------------------ */

const FINDINGS: Finding[] = [
  {
    finding_id: 'f-0001',
    category: 'SECURITY_SMELL',
    severity: 'HIGH',
    confidence: 0.82,
    summary: 'Unpinned dependency `requests` with a known advisory range',
    evidence: [
      {
        repo: REPO,
        commit: 'abc1234',
        path: 'setup.py',
        start_line: 10,
        end_line: 14,
        snippet: 'install_requires=[\n    "requests",\n    "click>=8",\n]',
      },
    ],
    reproduction_required: true,
    reproduction_status: 'REPRODUCED',
    duplicate_search_terms: ['requests unpinned', 'CVE requests', 'dependency pin'],
    suggested_next_step: 'Pin `requests>=2.31,<3` and add a lockfile.',
    limitations: ['Static analysis only; no runtime exploit confirmation.'],
    agent_id: 'static.security',
  },
  {
    finding_id: 'f-0002',
    category: 'SECURITY_SMELL',
    severity: 'CRITICAL',
    confidence: 0.76,
    summary: 'subprocess call built from unsanitized user input (shell=True)',
    evidence: [
      {
        repo: REPO,
        commit: 'abc1234',
        path: 'fastwidget/runner.py',
        start_line: 42,
        end_line: 45,
        snippet: 'cmd = f"convert {user_path} out.png"\nsubprocess.run(cmd, shell=True)',
      },
    ],
    reproduction_required: true,
    reproduction_status: 'REPRODUCED',
    duplicate_search_terms: ['shell injection', 'subprocess shell=True', 'command injection'],
    suggested_next_step: 'Pass an argument list and drop shell=True; validate paths.',
    limitations: ['Reachability from external input inferred, not proven end-to-end.'],
    agent_id: 'static.security',
  },
  {
    finding_id: 'f-0003',
    category: 'TYPING',
    severity: 'MEDIUM',
    confidence: 0.68,
    summary: 'Public API function missing type hints; return type ambiguous',
    evidence: [
      {
        repo: REPO,
        commit: 'abc1234',
        path: 'fastwidget/api.py',
        start_line: 8,
        end_line: 11,
        snippet: 'def render(widget, opts=None):\n    return _draw(widget, opts)',
      },
    ],
    reproduction_required: false,
    reproduction_status: 'NOT_REQUIRED',
    duplicate_search_terms: ['missing type hints', 'mypy untyped def'],
    suggested_next_step: 'Add explicit parameter and return annotations; enable mypy strict.',
    limitations: ['Inferred types may not capture all runtime shapes.'],
    agent_id: 'static.typing',
  },
  {
    finding_id: 'f-0004',
    category: 'DOCS_DRIFT',
    severity: 'LOW',
    confidence: 0.71,
    summary: 'README documents a removed `--legacy` flag',
    evidence: [
      {
        repo: REPO,
        commit: 'abc1234',
        path: 'README.md',
        start_line: 55,
        end_line: 58,
        snippet: 'Run `fastwidget render --legacy` to use the old engine.',
      },
    ],
    reproduction_required: false,
    reproduction_status: 'NOT_REQUIRED',
    duplicate_search_terms: ['README stale flag', 'docs drift legacy'],
    suggested_next_step: 'Remove the `--legacy` usage block from the README.',
    limitations: ['Only the top-level README was scanned.'],
    agent_id: 'static.docs',
  },
  {
    finding_id: 'f-0005',
    category: 'TEST_QUALITY',
    severity: 'MEDIUM',
    confidence: 0.64,
    summary: 'Test asserts on log text instead of behavior; brittle to refactor',
    evidence: [
      {
        repo: REPO,
        commit: 'abc1234',
        path: 'tests/test_runner.py',
        start_line: 30,
        end_line: 34,
        snippet: 'assert "starting convert" in caplog.text',
      },
    ],
    reproduction_required: true,
    reproduction_status: 'NOT_REPRODUCED',
    duplicate_search_terms: ['brittle test log assertion', 'caplog behavior test'],
    suggested_next_step: 'Assert on returned exit status and output file instead of log text.',
    limitations: ['Reproduction pending a fixture rewrite; not yet confirmed flaky in CI.'],
    agent_id: 'runtime.tests',
  },
];

/* ------------------------------------------------------------------ */
/* Candidates (3; one REJECTED by verification)                       */
/* ------------------------------------------------------------------ */

const CANDIDATES: Candidate[] = [
  {
    candidate_id: 'c-0001',
    title: 'Pin vulnerable dependency `requests`',
    author_agent: 'fix.a',
    verdict: 'ACCEPTED',
    root_cause: 'Dependency range allowed a version with a known advisory.',
    risk_level: 'LOW',
    scope_files_changed: 1,
    unrelated_changes: false,
    diff: [
      {
        path: 'setup.py',
        old: '    "requests",',
        new: '    "requests>=2.31,<3",',
        hunk: '@@ -10,3 +10,3 @@ install_requires=[',
      },
    ],
    verification: [
      {
        check: 'regression_tests',
        status: 'PASS',
        detail: '142 passed, 0 failed',
        verifier_agent: 'verify.regression',
      },
      {
        check: 'lint',
        status: 'PASS',
        detail: 'ruff clean',
        verifier_agent: 'verify.lint',
      },
      {
        check: 'dependency_audit',
        status: 'PASS',
        detail: 'no advisories in resolved range',
        verifier_agent: 'verify.regression',
      },
    ],
    verification_summary: '3/3 checks passed by independent verifiers.',
  },
  {
    candidate_id: 'c-0002',
    title: 'Harden subprocess call (drop shell=True)',
    author_agent: 'fix.b',
    verdict: 'REJECTED',
    root_cause: 'Command string interpolated user input into a shell.',
    risk_level: 'HIGH',
    scope_files_changed: 3,
    unrelated_changes: true,
    diff: [
      {
        path: 'fastwidget/runner.py',
        old: 'cmd = f"convert {user_path} out.png"\nsubprocess.run(cmd, shell=True)',
        new: 'subprocess.run(["convert", user_path, "out.png"], check=True)',
        hunk: '@@ -42,4 +42,3 @@ def run_convert(user_path):',
      },
      {
        path: 'fastwidget/api.py',
        old: 'def render(widget, opts=None):',
        new: 'def render(widget, opts=None, *, experimental=False):',
        hunk: '@@ -8,2 +8,2 @@',
      },
      {
        path: 'fastwidget/__init__.py',
        old: '__version__ = "0.4.1"',
        new: '__version__ = "0.5.0-dev"',
        hunk: '@@ -1,1 +1,1 @@',
      },
    ],
    verification: [
      {
        check: 'regression_tests',
        status: 'FAIL',
        detail: '2 failed: test_render_opts, test_version_string',
        verifier_agent: 'verify.regression',
      },
      {
        check: 'scope_check',
        status: 'FAIL',
        detail: 'touched 2 files unrelated to the finding',
        verifier_agent: 'verify.scope',
      },
      {
        check: 'lint',
        status: 'PASS',
        detail: 'ruff clean',
        verifier_agent: 'verify.lint',
      },
    ],
    verification_summary:
      '1/3 checks passed — rejected for out-of-scope changes and regressions.',
  },
  {
    candidate_id: 'c-0003',
    title: 'Remove stale `--legacy` flag from README',
    author_agent: 'fix.c',
    verdict: 'ACCEPTED',
    root_cause: 'Documentation described a flag removed two releases ago.',
    risk_level: 'SAFE',
    scope_files_changed: 1,
    unrelated_changes: false,
    diff: [
      {
        path: 'README.md',
        old: 'Run `fastwidget render --legacy` to use the old engine.',
        new: 'Run `fastwidget render` to render a widget.',
        hunk: '@@ -55,3 +55,3 @@',
      },
    ],
    verification: [
      {
        check: 'docs_build',
        status: 'PASS',
        detail: 'mkdocs build clean',
        verifier_agent: 'verify.lint',
      },
      {
        check: 'link_check',
        status: 'SKIP',
        detail: 'no external links changed',
        verifier_agent: 'verify.lint',
      },
    ],
    verification_summary: '1/2 checks passed, 1 skipped — safe doc-only change.',
  },
];

const DRAFT: Draft = {
  kind: 'PR',
  title: 'fix(deps): pin requests and clean stale docs',
  body_markdown: [
    '## Summary',
    '',
    'This PR bundles the verified, in-scope fixes surfaced by the CareerForge',
    'analysis mission:',
    '',
    '- **Pin `requests>=2.31,<3`** to exclude a version with a known advisory (finding `f-0001`).',
    '- **Remove the stale `--legacy` flag** from the README (finding `f-0004`).',
    '',
    'The subprocess-hardening candidate (`c-0002`) was **rejected** by independent',
    'verifiers for out-of-scope edits and regression failures, so it is not included.',
    '',
    '## Verification',
    '',
    '- `regression_tests`: 142 passed',
    '- `lint`: ruff clean',
    '- `dependency_audit`: no advisories in resolved range',
    '',
    '> Generated locally. No changes were pushed to the target repository.',
  ].join('\n'),
  target_repo: REPO,
  submittable: false,
  reason_not_submittable: 'GitHub writes disabled',
};

/* ------------------------------------------------------------------ */
/* Timeline construction                                              */
/* ------------------------------------------------------------------ */

interface ScheduledEvent {
  at: number;
  emit: (send: MockEmit) => void;
}

function log(atMs: number, level: LogEvent['level'], agentId: string, message: string): ScheduledEvent {
  return {
    at: atMs,
    emit: (send) =>
      send('log', {
        ts: ts(atMs),
        level,
        agent_id: agentId,
        message,
      }),
  };
}

function agentUpdate(
  atMs: number,
  id: string,
  state: AgentNode['state'],
  progress: number,
  resultCount: number,
  detail: string,
): ScheduledEvent {
  return {
    at: atMs,
    emit: (send) =>
      send('agent.update', agent(specById(id), state, progress, resultCount, detail, ts(0))),
  };
}

function edgeUpdate(atMs: number, id: string, animated: boolean): ScheduledEvent {
  const base = EDGE_SPECS.find((e) => e.id === id);
  if (!base) {
    throw new Error(`mockMission: unknown edge id "${id}"`);
  }
  return {
    at: atMs,
    emit: (send) => send('edge.update', { ...base, animated }),
  };
}

function resource(atMs: number, payload: ResourceEvent): ScheduledEvent {
  return { at: atMs, emit: (send) => send('resource', payload) };
}

function buildTimeline(missionId: string): ScheduledEvent[] {
  const events: ScheduledEvent[] = [];

  // 0. Kickoff.
  events.push({
    at: 100,
    emit: (send) => send('mission.status', { mission_id: missionId, status: 'PLANNING' }),
  });
  events.push(log(120, 'INFO', 'control.mission', `Planning mission for ${REPO_URL}`));

  // Seed all agents as WAITING and edges idle.
  for (const spec of AGENT_SPECS) {
    events.push(agentUpdate(150, spec.id, 'WAITING', 0, 0, 'queued'));
  }
  for (const e of EDGE_SPECS) {
    events.push(edgeUpdate(160, e.id, false));
  }

  // 1. Control + intake.
  events.push({
    at: 600,
    emit: (send) => send('mission.status', { mission_id: missionId, status: 'RUNNING' }),
  });
  events.push(agentUpdate(620, 'control.mission', 'RUNNING', 0.2, 0, 'orchestrating agents'));
  events.push(edgeUpdate(640, 'e-ctrl-intake', true));
  events.push(agentUpdate(700, 'intake.repo', 'RUNNING', 0.3, 0, 'cloning + indexing repo'));
  events.push(log(720, 'INFO', 'intake.repo', 'Fetched 128 files, 6.2k LOC (Python)'));
  events.push(resource(760, { cpu_percent: 41.5, ram_used_mb: 9120, active_agents: 2 }));

  events.push(agentUpdate(1200, 'intake.repo', 'COMPLETED', 1, 1, 'index ready'));
  for (const id of ['e-intake-sec', 'e-intake-typ', 'e-intake-docs', 'e-intake-rt']) {
    events.push(edgeUpdate(1220, id, true));
  }

  // 2. Static + runtime agents fan out.
  events.push(agentUpdate(1300, 'static.security', 'RUNNING', 0.25, 0, 'scanning subprocess calls'));
  events.push(agentUpdate(1320, 'static.typing', 'RUNNING', 0.2, 0, 'checking public API annotations'));
  events.push(agentUpdate(1340, 'static.docs', 'RUNNING', 0.2, 0, 'diffing README vs CLI'));
  events.push(agentUpdate(1360, 'runtime.tests', 'RUNNING', 0.15, 0, 'building repro sandbox'));
  events.push(resource(1400, { cpu_percent: 68.2, ram_used_mb: 12640, active_agents: 4 }));
  events.push(log(1420, 'INFO', 'static.security', 'AST pass over 128 modules'));

  // 3. Findings stream in.
  events.push({ at: 1800, emit: (send) => send('finding.new', FINDINGS[0]!) });
  events.push(agentUpdate(1820, 'static.security', 'RUNNING', 0.55, 1, 'found unpinned dependency'));
  events.push(log(1840, 'WARN', 'static.security', 'Unpinned `requests` in setup.py'));

  events.push({ at: 2200, emit: (send) => send('finding.new', FINDINGS[1]!) });
  events.push(agentUpdate(2220, 'static.security', 'VERIFYING', 0.8, 2, 'reproducing shell injection'));
  events.push(edgeUpdate(2240, 'e-sec-dup', true));
  events.push(agentUpdate(2260, 'duplicate.search', 'RUNNING', 0.4, 0, 'searching prior reports'));
  events.push(log(2280, 'ERROR', 'static.security', 'shell=True with interpolated user input'));

  events.push({ at: 2600, emit: (send) => send('finding.new', FINDINGS[2]!) });
  events.push(agentUpdate(2620, 'static.typing', 'COMPLETED', 1, 1, '1 typing gap'));

  events.push({ at: 2900, emit: (send) => send('finding.new', FINDINGS[3]!) });
  events.push(agentUpdate(2920, 'static.docs', 'COMPLETED', 1, 1, '1 docs drift'));

  events.push({ at: 3200, emit: (send) => send('finding.new', FINDINGS[4]!) });
  events.push(agentUpdate(3220, 'runtime.tests', 'COMPLETED', 1, 1, 'repro sandbox done'));
  events.push(agentUpdate(3240, 'static.security', 'COMPLETED', 1, 2, '2 security findings'));
  events.push(agentUpdate(3260, 'duplicate.search', 'COMPLETED', 1, 0, 'no duplicates found'));
  events.push(resource(3300, { cpu_percent: 52.7, ram_used_mb: 11020, active_agents: 3 }));

  // 4. Aggregate.
  for (const id of ['e-sec-agg', 'e-typ-agg', 'e-docs-agg', 'e-rt-agg']) {
    events.push(edgeUpdate(3400, id, true));
  }
  events.push(agentUpdate(3450, 'aggregate.findings', 'RUNNING', 0.5, 0, 'deduping + ranking findings'));
  events.push(log(3470, 'INFO', 'aggregate.findings', 'Ranked 5 findings by severity × confidence'));
  events.push(agentUpdate(3900, 'aggregate.findings', 'COMPLETED', 1, 5, '5 findings aggregated'));

  // 5. Fix authors.
  for (const id of ['e-agg-fixa', 'e-agg-fixb', 'e-agg-fixc']) {
    events.push(edgeUpdate(4000, id, true));
  }
  events.push(agentUpdate(4050, 'fix.a', 'RUNNING', 0.3, 0, 'drafting dependency pin'));
  events.push(agentUpdate(4070, 'fix.b', 'RUNNING', 0.3, 0, 'drafting subprocess hardening'));
  events.push(agentUpdate(4090, 'fix.c', 'RUNNING', 0.3, 0, 'drafting README cleanup'));
  events.push({ at: 4200, emit: (send) => send('candidate.update', { ...CANDIDATES[0]!, verdict: 'PENDING' }) });
  events.push({ at: 4260, emit: (send) => send('candidate.update', { ...CANDIDATES[1]!, verdict: 'PENDING' }) });
  events.push({ at: 4320, emit: (send) => send('candidate.update', { ...CANDIDATES[2]!, verdict: 'PENDING' }) });
  events.push(resource(4400, { cpu_percent: 73.9, ram_used_mb: 13980, active_agents: 3 }));

  // 6. Verification (independent verifiers).
  for (const id of ['e-fixa-vreg', 'e-fixa-vlint', 'e-fixb-vscope']) {
    events.push(edgeUpdate(4600, id, true));
  }
  events.push(agentUpdate(4650, 'verify.regression', 'RUNNING', 0.4, 0, 'running regression suite'));
  events.push(agentUpdate(4670, 'verify.lint', 'RUNNING', 0.5, 0, 'running ruff'));
  events.push(agentUpdate(4690, 'verify.scope', 'RUNNING', 0.6, 0, 'checking change scope'));
  events.push(agentUpdate(4700, 'fix.a', 'VERIFYING', 0.9, 1, 'awaiting verifiers'));
  events.push(agentUpdate(4720, 'fix.b', 'VERIFYING', 0.9, 1, 'awaiting verifiers'));
  events.push(log(4740, 'INFO', 'verify.regression', '142 passed for c-0001'));
  events.push(log(4760, 'ERROR', 'verify.scope', 'c-0002 touched 2 unrelated files'));

  // Verdicts.
  events.push({ at: 5100, emit: (send) => send('candidate.update', CANDIDATES[0]!) });
  events.push(agentUpdate(5120, 'fix.a', 'COMPLETED', 1, 1, 'candidate accepted'));
  events.push(agentUpdate(5130, 'verify.regression', 'COMPLETED', 1, 1, 'pass'));
  events.push(agentUpdate(5140, 'verify.lint', 'COMPLETED', 1, 1, 'clean'));

  events.push({ at: 5300, emit: (send) => send('candidate.update', CANDIDATES[1]!) });
  events.push(agentUpdate(5320, 'fix.b', 'REJECTED', 1, 0, 'rejected by verifiers'));
  events.push(agentUpdate(5330, 'verify.scope', 'FAILED', 1, 0, 'scope violation'));
  events.push(log(5340, 'WARN', 'control.mission', 'Candidate c-0002 rejected — excluded from draft'));

  events.push({ at: 5500, emit: (send) => send('candidate.update', CANDIDATES[2]!) });
  events.push(agentUpdate(5520, 'fix.c', 'COMPLETED', 1, 1, 'candidate accepted'));
  events.push(resource(5600, { cpu_percent: 38.4, ram_used_mb: 9880, active_agents: 1 }));

  // 7. Approval gate.
  events.push({
    at: 5900,
    emit: (send) => send('mission.status', { mission_id: missionId, status: 'AWAITING_APPROVAL' }),
  });
  events.push({
    at: 5950,
    emit: (send) => send('approval.required', { mission_id: missionId, draft: DRAFT }),
  });
  events.push(agentUpdate(5970, 'control.mission', 'BLOCKED', 0.95, 2, 'awaiting human approval'));
  events.push(log(5990, 'INFO', 'control.mission', 'Draft prepared — human approval required'));

  // 8. Complete (draft stays local; approval is a separate user action).
  events.push({
    at: 6600,
    emit: (send) => send('mission.complete', { mission_id: missionId, status: 'COMPLETED' }),
  });
  events.push(agentUpdate(6620, 'control.mission', 'COMPLETED', 1, 2, 'mission complete'));
  events.push(log(6640, 'INFO', 'control.mission', 'Mission complete — 2 candidates accepted, 1 rejected'));

  events.sort((a, b) => a.at - b.at);
  return events;
}

/**
 * Run the mock mission, invoking `emit` for each event on its schedule.
 * Returns a canceller that clears all pending timers.
 */
export function runMockMission(missionId: string, emit: MockEmit): MockCanceller {
  const events = buildTimeline(missionId);
  const timers: ReturnType<typeof setTimeout>[] = [];

  for (const event of events) {
    const handle = setTimeout(() => {
      try {
        event.emit(emit);
      } catch {
        // Swallow: a rendering error in the consumer must not break the sim.
      }
    }, event.at);
    timers.push(handle);
  }

  return () => {
    for (const handle of timers) {
      clearTimeout(handle);
    }
    timers.length = 0;
  };
}

/** Total simulated duration in milliseconds (useful for tests/progress UI). */
export const MOCK_MISSION_DURATION_MS = 6700;
