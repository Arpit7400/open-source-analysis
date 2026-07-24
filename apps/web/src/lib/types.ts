/**
 * CareerForge AI — shared TypeScript types.
 *
 * These MIRROR docs/API_CONTRACT.md (v1) EXACTLY. Enum spellings and field
 * names are load-bearing — the frontend/backend boundary depends on them.
 * Do not "improve" names here; change the contract first.
 */

/* ------------------------------------------------------------------ */
/* Enums (UPPER_SNAKE string-literal unions)                          */
/* ------------------------------------------------------------------ */

export type VerificationLevel =
  | 'SELF_DECLARED'
  | 'AI_INFERRED'
  | 'TOOL_VERIFIED'
  | 'HUMAN_REVIEWED'
  | 'EXTERNALLY_VALIDATED';

export type AgentState =
  | 'WAITING'
  | 'RUNNING'
  | 'COMPLETED'
  | 'VERIFYING'
  | 'BLOCKED'
  | 'FAILED'
  | 'REJECTED';

export type Severity = 'INFO' | 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';

export type FindingCategory =
  | 'ARCHITECTURE'
  | 'CODE_QUALITY'
  | 'DOCS_DRIFT'
  | 'DEPENDENCY'
  | 'TEST_QUALITY'
  | 'TYPING'
  | 'API_CONSISTENCY'
  | 'SECURITY_SMELL'
  | 'DEPRECATION'
  | 'RUNTIME';

export type ReproductionStatus =
  | 'NOT_REQUIRED'
  | 'PENDING'
  | 'REPRODUCED'
  | 'NOT_REPRODUCED';

export type MissionStatus =
  | 'QUEUED'
  | 'PLANNING'
  | 'RUNNING'
  | 'AWAITING_APPROVAL'
  | 'COMPLETED'
  | 'FAILED'
  | 'CANCELLED';

export type CandidateVerdict =
  | 'ACCEPTED'
  | 'REJECTED'
  | 'NO_SUBMISSION'
  | 'PENDING';

export type RiskLevel = 'SAFE' | 'LOW' | 'MEDIUM' | 'HIGH' | 'BLOCKED';

/* Supporting literal unions used inside the interfaces below. */

export type ServiceState = 'up' | 'down' | 'mock';

export type HardwareProfile =
  | 'CPU_LOW'
  | 'VRAM_8_12'
  | 'VRAM_16_24'
  | 'WORKSTATION';

export type AgentGroup =
  | 'STATIC'
  | 'RUNTIME'
  | 'INTAKE'
  | 'DUPLICATE'
  | 'FIX'
  | 'VERIFY'
  | 'CONTROL'
  | 'AGGREGATE';

export type EvidenceType = 'COMMIT' | 'TEST' | 'DOC' | 'PR' | 'PROJECT';

export type VerificationStatus = 'PASS' | 'FAIL' | 'SKIP';

export type DraftKind = 'ISSUE' | 'PR';

export type LogLevel = 'INFO' | 'WARN' | 'ERROR';

export type ApprovalDecision = 'APPROVE' | 'REJECT';

export type PulseSource = 'arXiv' | 'GitHub' | 'Blog' | 'Advisory';

/* ------------------------------------------------------------------ */
/* System                                                             */
/* ------------------------------------------------------------------ */

export interface HealthServices {
  api: string;
  database: ServiceState;
  qdrant: ServiceState;
  redis: ServiceState;
  ollama: ServiceState;
  temporal: ServiceState;
}

export interface HealthFlags {
  github_writes: boolean;
  repository_execution: boolean;
}

export interface Health {
  status: string;
  version: string;
  services: HealthServices;
  hardware_profile: HardwareProfile;
  flags: HealthFlags;
}

export interface Resources {
  cpu_percent: number;
  ram_used_mb: number;
  ram_total_mb: number;
  active_agents: number;
  max_agents: number;
}

/* ------------------------------------------------------------------ */
/* Profile Brain                                                      */
/* ------------------------------------------------------------------ */

export interface Profile {
  user_id: string;
  name: string;
  headline: string;
  goals: string[];
  verified_skill_count: number;
  merged_prs: number;
  evidence_count: number;
}

export interface Skill {
  id: string;
  name: string;
  category: string;
  confidence: number;
  evidence_strength: number;
  recency: number;
  complexity: number;
  independence: number;
  verification_level: VerificationLevel;
  evidence_ids: string[];
  last_updated: string;
  last_change_reason: string;
  related_skill_ids: string[];
}

export interface SkillsResponse {
  skills: Skill[];
}

export interface Evidence {
  id: string;
  type: EvidenceType;
  summary: string;
  source_url: string;
  verification_level: VerificationLevel;
  created_at: string;
}

export interface SkillEvidenceResponse {
  skill_id: string;
  evidence: Evidence[];
}

export interface ResumeClaim {
  skill: string;
  evidence_level: VerificationLevel;
  raw_span: string;
}

export interface ResumeIngestResponse {
  claims: ResumeClaim[];
}

/* ------------------------------------------------------------------ */
/* Repositories & Analysis (flagship flow)                            */
/* ------------------------------------------------------------------ */

export interface AnalyzeRepoRequest {
  repo_url: string;
}

export interface AnalyzeRepoResponse {
  mission_id: string;
  status: MissionStatus;
}

export interface MissionPlan {
  goal: string;
  assumptions: string[];
  success_criteria: string[];
}

export interface AgentNode {
  id: string;
  label: string;
  group: AgentGroup;
  state: AgentState;
  progress: number;
  result_count: number;
  started_at: string | null;
  detail: string;
  verifier_of: string | null;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  animated: boolean;
}

export interface EvidenceRef {
  repo: string;
  commit: string;
  path: string;
  start_line: number;
  end_line: number;
  snippet: string;
}

export interface Finding {
  finding_id: string;
  category: FindingCategory;
  severity: Severity;
  confidence: number;
  summary: string;
  evidence: EvidenceRef[];
  reproduction_required: boolean;
  reproduction_status: ReproductionStatus;
  duplicate_search_terms: string[];
  suggested_next_step: string;
  limitations: string[];
  agent_id: string;
}

export interface DiffLine {
  path: string;
  old: string;
  new: string;
  hunk: string;
}

export interface VerificationCheck {
  check: string;
  status: VerificationStatus;
  detail: string;
  verifier_agent: string;
}

export interface Candidate {
  candidate_id: string;
  title: string;
  author_agent: string;
  verdict: CandidateVerdict;
  root_cause: string;
  risk_level: RiskLevel;
  scope_files_changed: number;
  unrelated_changes: boolean;
  diff: DiffLine[];
  verification: VerificationCheck[];
  verification_summary: string;
}

export interface Draft {
  kind: DraftKind;
  title: string;
  body_markdown: string;
  target_repo: string;
  submittable: boolean;
  reason_not_submittable: string;
}

export interface ApprovalState {
  required: boolean;
  granted: boolean;
  draft: Draft;
}

export interface Mission {
  mission_id: string;
  repo_url: string;
  status: MissionStatus;
  created_at: string;
  plan: MissionPlan;
  agents: AgentNode[];
  edges: GraphEdge[];
  findings: Finding[];
  candidates: Candidate[];
  approval: ApprovalState | null;
}

export interface ApprovalRequest {
  decision: ApprovalDecision;
  note: string;
}

export interface ApprovalResponse {
  ok: boolean;
  action_taken: string;
  github_write: boolean;
}

/* ------------------------------------------------------------------ */
/* Industry Pulse                                                     */
/* ------------------------------------------------------------------ */

export interface PulseItem {
  id: string;
  title: string;
  source: PulseSource;
  technology: string;
  published_at: string;
  momentum: number;
  personal_relevance: number;
  actionability: number;
  why_it_matters: string;
  skill_gap: string;
  suggested_action: string;
  canonical_url: string;
}

export interface PulseResponse {
  items: PulseItem[];
}

/* ------------------------------------------------------------------ */
/* Error shape                                                        */
/* ------------------------------------------------------------------ */

export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    detail: unknown;
  };
}

/* ------------------------------------------------------------------ */
/* SSE event payloads (keyed by event name)                           */
/* ------------------------------------------------------------------ */

export interface MissionStatusEvent {
  mission_id: string;
  status: MissionStatus;
}

export type AgentUpdateEvent = AgentNode;

export type EdgeUpdateEvent = GraphEdge;

export type FindingNewEvent = Finding;

export type CandidateUpdateEvent = Candidate;

export interface LogEvent {
  ts: string;
  level: LogLevel;
  agent_id: string;
  message: string;
}

export interface ResourceEvent {
  cpu_percent: number;
  ram_used_mb: number;
  active_agents: number;
}

export interface ApprovalRequiredEvent {
  mission_id: string;
  draft: Draft;
}

export interface MissionCompleteEvent {
  mission_id: string;
  status: MissionStatus;
}

/**
 * Map of SSE event name -> decoded JSON payload type.
 * Mirrors the "SSE Event Stream" section of API_CONTRACT.md.
 */
export interface MissionStreamEventMap {
  'mission.status': MissionStatusEvent;
  'agent.update': AgentUpdateEvent;
  'edge.update': EdgeUpdateEvent;
  'finding.new': FindingNewEvent;
  'candidate.update': CandidateUpdateEvent;
  log: LogEvent;
  resource: ResourceEvent;
  'approval.required': ApprovalRequiredEvent;
  'mission.complete': MissionCompleteEvent;
}

export type MissionStreamEventName = keyof MissionStreamEventMap;

/** A log entry as stored in the client store (id assigned locally). */
export interface StoredLog extends LogEvent {
  seq: number;
}
