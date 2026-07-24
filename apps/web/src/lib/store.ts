/**
 * CareerForge AI — live mission Zustand store.
 *
 * Holds the streaming state of the active mission: status, plan, agents,
 * edges, findings, candidates, a capped log ring, resource telemetry, and the
 * human-in-the-loop approval gate. SSE events (or the client mock) dispatch
 * into these actions; the Command Center renders from this store.
 */

import { create } from 'zustand';
import type {
  AgentNode,
  ApprovalState,
  Candidate,
  Finding,
  GraphEdge,
  LogEvent,
  Mission,
  MissionPlan,
  MissionStatus,
  Resources,
  StoredLog,
} from './types';

/** Maximum number of log lines retained in memory. */
export const LOG_CAP = 300;

export interface MissionStoreState {
  /** Current mission id being streamed, or null when idle. */
  missionId: string | null;
  repoUrl: string | null;
  status: MissionStatus | null;
  createdAt: string | null;
  plan: MissionPlan | null;

  agents: Record<string, AgentNode>;
  edges: Record<string, GraphEdge>;
  findings: Finding[];
  candidates: Record<string, Candidate>;
  logs: StoredLog[];

  resources: Resources | null;
  approval: ApprovalState | null;

  /** UI selection state (detail drawers). */
  selectedAgentId: string | null;
  selectedCandidateId: string | null;

  /** Monotonic counter used to key log entries. */
  logSeq: number;

  /* Actions */
  reset: () => void;
  setMission: (snapshot: Mission) => void;
  upsertAgent: (agent: AgentNode) => void;
  upsertEdge: (edge: GraphEdge) => void;
  addFinding: (finding: Finding) => void;
  upsertCandidate: (candidate: Candidate) => void;
  appendLog: (entry: LogEvent) => void;
  setResources: (resources: Partial<Resources>) => void;
  setStatus: (status: MissionStatus) => void;
  setApproval: (approval: ApprovalState | null) => void;
  setMissionId: (missionId: string | null) => void;
  selectAgentId: (agentId: string | null) => void;
  selectCandidateId: (candidateId: string | null) => void;
}

const initialState = {
  missionId: null as string | null,
  repoUrl: null as string | null,
  status: null as MissionStatus | null,
  createdAt: null as string | null,
  plan: null as MissionPlan | null,
  agents: {} as Record<string, AgentNode>,
  edges: {} as Record<string, GraphEdge>,
  findings: [] as Finding[],
  candidates: {} as Record<string, Candidate>,
  logs: [] as StoredLog[],
  resources: null as Resources | null,
  approval: null as ApprovalState | null,
  selectedAgentId: null as string | null,
  selectedCandidateId: null as string | null,
  logSeq: 0,
};

function toRecord<T extends { id: string }>(items: T[]): Record<string, T> {
  const out: Record<string, T> = {};
  for (const item of items) {
    out[item.id] = item;
  }
  return out;
}

export const useMissionStore = create<MissionStoreState>((set) => ({
  ...initialState,

  reset: () => set({ ...initialState, agents: {}, edges: {}, findings: [], candidates: {}, logs: [] }),

  setMission: (snapshot) =>
    set((state) => {
      const candidateRecord: Record<string, Candidate> = {};
      for (const candidate of snapshot.candidates) {
        candidateRecord[candidate.candidate_id] = candidate;
      }
      return {
        missionId: snapshot.mission_id,
        repoUrl: snapshot.repo_url,
        status: snapshot.status,
        createdAt: snapshot.created_at,
        plan: snapshot.plan,
        agents: toRecord(snapshot.agents),
        edges: toRecord(snapshot.edges),
        findings: [...snapshot.findings],
        candidates: candidateRecord,
        approval: snapshot.approval,
        // Preserve accumulated logs/resources across a snapshot refresh.
        logs: state.logs,
        resources: state.resources,
      };
    }),

  upsertAgent: (agent) =>
    set((state) => ({
      agents: { ...state.agents, [agent.id]: agent },
    })),

  upsertEdge: (edge) =>
    set((state) => ({
      edges: { ...state.edges, [edge.id]: edge },
    })),

  addFinding: (finding) =>
    set((state) => {
      const existingIndex = state.findings.findIndex(
        (f) => f.finding_id === finding.finding_id,
      );
      if (existingIndex >= 0) {
        const next = state.findings.slice();
        next[existingIndex] = finding;
        return { findings: next };
      }
      return { findings: [...state.findings, finding] };
    }),

  upsertCandidate: (candidate) =>
    set((state) => ({
      candidates: {
        ...state.candidates,
        [candidate.candidate_id]: candidate,
      },
    })),

  appendLog: (entry) =>
    set((state) => {
      const seq = state.logSeq + 1;
      const stored: StoredLog = { ...entry, seq };
      const next = [...state.logs, stored];
      if (next.length > LOG_CAP) {
        next.splice(0, next.length - LOG_CAP);
      }
      return { logs: next, logSeq: seq };
    }),

  setResources: (resources) =>
    set((state) => {
      const base: Resources = state.resources ?? {
        cpu_percent: 0,
        ram_used_mb: 0,
        ram_total_mb: 0,
        active_agents: 0,
        max_agents: 0,
      };
      return { resources: { ...base, ...resources } };
    }),

  setStatus: (status) => set({ status }),

  setApproval: (approval) => set({ approval }),

  setMissionId: (missionId) => set({ missionId }),

  selectAgentId: (agentId) => set({ selectedAgentId: agentId }),

  selectCandidateId: (candidateId) =>
    set({ selectedCandidateId: candidateId }),
}));

/* ------------------------------------------------------------------ */
/* Selectors (stable helpers for components)                          */
/* ------------------------------------------------------------------ */

export const selectAgentList = (state: MissionStoreState): AgentNode[] =>
  Object.values(state.agents);

export const selectEdgeList = (state: MissionStoreState): GraphEdge[] =>
  Object.values(state.edges);

export const selectCandidateList = (state: MissionStoreState): Candidate[] =>
  Object.values(state.candidates);
