'use client';

/**
 * useMissionStream — subscribe a mission to the backend SSE stream and mirror
 * every event into the Zustand mission store.
 *
 * Behavior:
 *  - Opens an EventSource to `${API_BASE}/api/v1/events/stream?mission_id=...`.
 *  - Registers a listener per contract event name (mission.status,
 *    agent.update, edge.update, finding.new, candidate.update, log, resource,
 *    approval.required, mission.complete).
 *  - Reconnects with exponential backoff on transient errors.
 *  - After repeated connection failures, falls back to the client-side
 *    `mockMission` simulator so the UI is never dead.
 *  - Cleans up the EventSource / timers / mock on unmount or mission change.
 */

import { useEffect, useRef, useState } from 'react';
import { missionStreamUrl } from './api';
import { runMockMission, type MockCanceller } from './mockMission';
import { useMissionStore } from './store';
import type {
  MissionStreamEventMap,
  MissionStreamEventName,
} from './types';

export type StreamMode = 'idle' | 'connecting' | 'live' | 'mock' | 'closed';

export interface UseMissionStreamResult {
  mode: StreamMode;
  attempts: number;
}

/** Number of failed reconnects before falling back to the mock simulator. */
const MAX_ATTEMPTS = 3;
const BASE_BACKOFF_MS = 800;
const MAX_BACKOFF_MS = 8000;

const EVENT_NAMES: MissionStreamEventName[] = [
  'mission.status',
  'agent.update',
  'edge.update',
  'finding.new',
  'candidate.update',
  'log',
  'resource',
  'approval.required',
  'mission.complete',
];

function parsePayload<K extends MissionStreamEventName>(
  raw: string,
): MissionStreamEventMap[K] | null {
  try {
    return JSON.parse(raw) as MissionStreamEventMap[K];
  } catch {
    return null;
  }
}

/**
 * Subscribe to a mission's event stream. Pass `null` to remain idle.
 */
export function useMissionStream(
  missionId: string | null,
): UseMissionStreamResult {
  const [mode, setMode] = useState<StreamMode>('idle');
  const [attempts, setAttempts] = useState(0);

  // Grab stable action references from the store (they never change identity).
  const store = useMissionStore;

  const sourceRef = useRef<EventSource | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mockCancelRef = useRef<MockCanceller | null>(null);
  const attemptRef = useRef(0);
  const disposedRef = useRef(false);

  useEffect(() => {
    disposedRef.current = false;
    attemptRef.current = 0;
    setAttempts(0);

    if (!missionId) {
      setMode('idle');
      return () => {
        /* nothing to clean up */
      };
    }

    const {
      setStatus,
      upsertAgent,
      upsertEdge,
      addFinding,
      upsertCandidate,
      appendLog,
      setResources,
      setApproval,
    } = store.getState();

    /** Dispatch a decoded event into the store. */
    const dispatch = <K extends MissionStreamEventName>(
      name: K,
      payload: MissionStreamEventMap[K],
    ): void => {
      switch (name) {
        case 'mission.status':
          setStatus((payload as MissionStreamEventMap['mission.status']).status);
          break;
        case 'agent.update':
          upsertAgent(payload as MissionStreamEventMap['agent.update']);
          break;
        case 'edge.update':
          upsertEdge(payload as MissionStreamEventMap['edge.update']);
          break;
        case 'finding.new':
          addFinding(payload as MissionStreamEventMap['finding.new']);
          break;
        case 'candidate.update':
          upsertCandidate(payload as MissionStreamEventMap['candidate.update']);
          break;
        case 'log':
          appendLog(payload as MissionStreamEventMap['log']);
          break;
        case 'resource':
          setResources(payload as MissionStreamEventMap['resource']);
          break;
        case 'approval.required': {
          const evt = payload as MissionStreamEventMap['approval.required'];
          setApproval({ required: true, granted: false, draft: evt.draft });
          setStatus('AWAITING_APPROVAL');
          break;
        }
        case 'mission.complete':
          setStatus(
            (payload as MissionStreamEventMap['mission.complete']).status,
          );
          break;
        default:
          break;
      }
    };

    const clearReconnectTimer = (): void => {
      if (reconnectTimerRef.current !== null) {
        clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
    };

    const closeSource = (): void => {
      if (sourceRef.current) {
        sourceRef.current.close();
        sourceRef.current = null;
      }
    };

    const startMock = (): void => {
      if (disposedRef.current) return;
      closeSource();
      clearReconnectTimer();
      setMode('mock');
      mockCancelRef.current = runMockMission(missionId, (name, payload) => {
        dispatch(name, payload);
      });
    };

    const scheduleReconnect = (): void => {
      if (disposedRef.current) return;
      attemptRef.current += 1;
      setAttempts(attemptRef.current);

      if (attemptRef.current > MAX_ATTEMPTS) {
        startMock();
        return;
      }

      const backoff = Math.min(
        MAX_BACKOFF_MS,
        BASE_BACKOFF_MS * 2 ** (attemptRef.current - 1),
      );
      clearReconnectTimer();
      reconnectTimerRef.current = setTimeout(connect, backoff);
    };

    function connect(): void {
      if (disposedRef.current || !missionId) return;

      // EventSource is browser-only; on the server, defer to the mock.
      if (typeof window === 'undefined' || typeof EventSource === 'undefined') {
        startMock();
        return;
      }

      closeSource();
      setMode('connecting');

      let source: EventSource;
      try {
        source = new EventSource(missionStreamUrl(missionId));
      } catch {
        scheduleReconnect();
        return;
      }
      sourceRef.current = source;

      source.onopen = () => {
        if (disposedRef.current) return;
        attemptRef.current = 0;
        setAttempts(0);
        setMode('live');
      };

      for (const name of EVENT_NAMES) {
        source.addEventListener(name, (event: MessageEvent<string>) => {
          if (disposedRef.current) return;
          const payload = parsePayload(event.data);
          if (payload === null) return;
          dispatch(name, payload as MissionStreamEventMap[typeof name]);
        });
      }

      source.onerror = () => {
        if (disposedRef.current) return;
        // Browsers auto-retry EventSource; we take control to apply our own
        // backoff and to enable the mock fallback after repeated failures.
        closeSource();
        scheduleReconnect();
      };
    }

    connect();

    return () => {
      disposedRef.current = true;
      clearReconnectTimer();
      closeSource();
      if (mockCancelRef.current) {
        mockCancelRef.current();
        mockCancelRef.current = null;
      }
      setMode('closed');
    };
    // `store` is a stable module singleton; only re-run when the mission changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [missionId]);

  return { mode, attempts };
}
