/**
 * CareerForge AI — typed API client.
 *
 * One function per endpoint in docs/API_CONTRACT.md (v1). All calls go through
 * `request()` which handles JSON parsing and normalizes errors into the
 * contract error shape (`{ error: { code, message, detail } }`).
 */

import type {
  AnalyzeRepoResponse,
  ApiErrorBody,
  ApprovalRequest,
  ApprovalResponse,
  Health,
  Mission,
  Profile,
  PulseResponse,
  Resources,
  ResumeIngestResponse,
  SkillEvidenceResponse,
  SkillsResponse,
} from './types';

/** Base URL of the FastAPI backend. Configured via NEXT_PUBLIC_API_BASE. */
export const API_BASE: string =
  process.env.NEXT_PUBLIC_API_BASE ?? 'http://localhost:8000';

const API_PREFIX = '/api/v1';

/**
 * Error thrown by the API client. Carries the contract error body plus the
 * HTTP status so callers can branch on either.
 */
export class ApiError extends Error {
  public readonly status: number;
  public readonly code: string;
  public readonly detail: unknown;

  constructor(status: number, body: ApiErrorBody) {
    super(body.error.message);
    this.name = 'ApiError';
    this.status = status;
    this.code = body.error.code;
    this.detail = body.error.detail;
  }
}

function joinUrl(path: string): string {
  const trimmedBase = API_BASE.replace(/\/+$/, '');
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  return `${trimmedBase}${API_PREFIX}${normalizedPath}`;
}

function isApiErrorBody(value: unknown): value is ApiErrorBody {
  if (typeof value !== 'object' || value === null) return false;
  const maybe = value as { error?: unknown };
  if (typeof maybe.error !== 'object' || maybe.error === null) return false;
  const err = maybe.error as { code?: unknown; message?: unknown };
  return typeof err.code === 'string' && typeof err.message === 'string';
}

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH';
  body?: BodyInit | null;
  headers?: Record<string, string>;
  signal?: AbortSignal;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const url = joinUrl(path);
  const { method = 'GET', body = null, headers = {}, signal } = options;

  let response: Response;
  try {
    response = await fetch(url, {
      method,
      body,
      headers: {
        Accept: 'application/json',
        ...headers,
      },
      signal,
      cache: 'no-store',
    });
  } catch (cause) {
    // Network-level failure (backend unreachable, CORS, aborted, etc.).
    throw new ApiError(0, {
      error: {
        code: 'NETWORK_ERROR',
        message:
          cause instanceof Error ? cause.message : 'Failed to reach the API.',
        detail: { url },
      },
    });
  }

  const text = await response.text();
  let parsed: unknown = null;
  if (text.length > 0) {
    try {
      parsed = JSON.parse(text) as unknown;
    } catch {
      parsed = null;
    }
  }

  if (!response.ok) {
    if (isApiErrorBody(parsed)) {
      throw new ApiError(response.status, parsed);
    }
    throw new ApiError(response.status, {
      error: {
        code: `HTTP_${response.status}`,
        message: response.statusText || 'Request failed.',
        detail: { url, body: parsed ?? text },
      },
    });
  }

  return parsed as T;
}

function jsonBody(value: unknown): RequestOptions {
  return {
    method: 'POST',
    body: JSON.stringify(value),
    headers: { 'Content-Type': 'application/json' },
  };
}

/* ------------------------------------------------------------------ */
/* System                                                             */
/* ------------------------------------------------------------------ */

export function getHealth(signal?: AbortSignal): Promise<Health> {
  return request<Health>('/system/health', { signal });
}

export function getResources(signal?: AbortSignal): Promise<Resources> {
  return request<Resources>('/system/resources', { signal });
}

/* ------------------------------------------------------------------ */
/* Profile Brain                                                      */
/* ------------------------------------------------------------------ */

export function getProfile(signal?: AbortSignal): Promise<Profile> {
  return request<Profile>('/profile', { signal });
}

export function getSkills(signal?: AbortSignal): Promise<SkillsResponse> {
  return request<SkillsResponse>('/skills', { signal });
}

export function getSkillEvidence(
  skillId: string,
  signal?: AbortSignal,
): Promise<SkillEvidenceResponse> {
  return request<SkillEvidenceResponse>(
    `/skills/${encodeURIComponent(skillId)}/evidence`,
    { signal },
  );
}

/**
 * Ingest a resume. Accepts either raw text (sent as `{ text }`) or a
 * multipart FormData payload (e.g. an uploaded file). Never auto-verifies —
 * returns claims only.
 */
export function ingestResume(
  input: string | FormData,
  signal?: AbortSignal,
): Promise<ResumeIngestResponse> {
  if (typeof input === 'string') {
    return request<ResumeIngestResponse>('/profile/ingest-resume', {
      ...jsonBody({ text: input }),
      signal,
    });
  }
  // FormData: let the browser set the multipart boundary header.
  return request<ResumeIngestResponse>('/profile/ingest-resume', {
    method: 'POST',
    body: input,
    signal,
  });
}

/* ------------------------------------------------------------------ */
/* Repositories & Analysis                                            */
/* ------------------------------------------------------------------ */

export function analyzeRepo(
  repoUrl: string,
  signal?: AbortSignal,
): Promise<AnalyzeRepoResponse> {
  return request<AnalyzeRepoResponse>('/repositories/analyze', {
    ...jsonBody({ repo_url: repoUrl }),
    signal,
  });
}

export function getMission(
  missionId: string,
  signal?: AbortSignal,
): Promise<Mission> {
  return request<Mission>(
    `/missions/${encodeURIComponent(missionId)}`,
    { signal },
  );
}

export function approve(
  missionId: string,
  payload: ApprovalRequest,
  signal?: AbortSignal,
): Promise<ApprovalResponse> {
  return request<ApprovalResponse>(
    `/approvals/${encodeURIComponent(missionId)}`,
    { ...jsonBody(payload), signal },
  );
}

/* ------------------------------------------------------------------ */
/* Industry Pulse                                                     */
/* ------------------------------------------------------------------ */

export function getPulse(signal?: AbortSignal): Promise<PulseResponse> {
  return request<PulseResponse>('/pulse', { signal });
}

/** URL of the SSE mission stream for a given mission id. */
export function missionStreamUrl(missionId: string): string {
  const trimmedBase = API_BASE.replace(/\/+$/, '');
  return `${trimmedBase}${API_PREFIX}/events/stream?mission_id=${encodeURIComponent(
    missionId,
  )}`;
}
