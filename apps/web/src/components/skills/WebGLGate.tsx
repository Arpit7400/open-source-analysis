"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

/**
 * Result of the client-side capability probe used by {@link WebGLGate}.
 * `undefined` fields mean "not yet measured" (SSR / first paint).
 */
export interface WebGLCapability {
  /** True once the probe has run on the client. */
  ready: boolean;
  /** Whether a WebGL context could be acquired. */
  hasWebGL: boolean;
  /** Whether the OS requests reduced motion. */
  prefersReducedMotion: boolean;
  /** User-controlled performance mode (persisted to localStorage). */
  performanceMode: boolean;
}

const PERF_MODE_KEY = "cf.performanceMode";
/** Fired on the window so every gate on the page reacts to a toggle at once. */
const PERF_MODE_EVENT = "cf:performance-mode";

/**
 * Attempt to acquire a WebGL rendering context on a throwaway canvas. Wrapped
 * in try/catch because some browsers throw (rather than returning null) when
 * WebGL is blocked by policy or a driver blocklist.
 */
function detectWebGL(): boolean {
  if (typeof document === "undefined") return false;
  try {
    const canvas = document.createElement("canvas");
    const gl =
      canvas.getContext("webgl2") ??
      canvas.getContext("webgl") ??
      canvas.getContext("experimental-webgl");
    return Boolean(gl);
  } catch {
    return false;
  }
}

function readPerformanceMode(): boolean {
  if (typeof window === "undefined") return false;
  try {
    return window.localStorage.getItem(PERF_MODE_KEY) === "1";
  } catch {
    return false;
  }
}

/**
 * Read the current capability set and subscribe to the two things that can
 * change at runtime: the reduced-motion media query and the performance-mode
 * toggle (via a custom window event + the storage event for cross-tab sync).
 */
export function useWebGLCapability(): WebGLCapability {
  const [state, setState] = useState<WebGLCapability>({
    ready: false,
    hasWebGL: false,
    prefersReducedMotion: false,
    performanceMode: false,
  });

  useEffect(() => {
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");

    const sync = () => {
      setState({
        ready: true,
        hasWebGL: detectWebGL(),
        prefersReducedMotion: media.matches,
        performanceMode: readPerformanceMode(),
      });
    };

    sync();

    const onStorage = (event: StorageEvent) => {
      if (event.key === null || event.key === PERF_MODE_KEY) sync();
    };

    media.addEventListener("change", sync);
    window.addEventListener("storage", onStorage);
    window.addEventListener(PERF_MODE_EVENT, sync);

    return () => {
      media.removeEventListener("change", sync);
      window.removeEventListener("storage", onStorage);
      window.removeEventListener(PERF_MODE_EVENT, sync);
    };
  }, []);

  return state;
}

/** Imperatively set performance mode and notify every listening gate. */
export function setPerformanceMode(enabled: boolean): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(PERF_MODE_KEY, enabled ? "1" : "0");
  } catch {
    /* storage may be unavailable (private mode); ignore. */
  }
  window.dispatchEvent(new Event(PERF_MODE_EVENT));
}

interface WebGLGateProps {
  /** The 3D content — rendered only when the environment can support it. */
  children: ReactNode;
  /** The non-WebGL / reduced-motion / performance-mode fallback. */
  fallback: ReactNode;
  /**
   * Called whenever the resolved mode changes, so a parent can e.g. sync a UI
   * toggle. Receives `true` when 3D is active.
   */
  onModeChange?: (threeDActive: boolean) => void;
  /**
   * Render-prop banner shown above the fallback, receiving the reason 3D is
   * unavailable and a callback to force-enable it (only meaningful when the
   * reason is performance-mode / reduced-motion, not a hard WebGL failure).
   */
  renderFallbackNotice?: (info: {
    reason: FallbackReason;
    canOverride: boolean;
    enableThreeD: () => void;
  }) => ReactNode;
}

export type FallbackReason =
  | "none"
  | "no-webgl"
  | "reduced-motion"
  | "performance-mode"
  | "probing";

/**
 * Gate that decides, on the client only, whether to render WebGL 3D content or
 * an accessible fallback. It renders the fallback:
 *  - before the capability probe resolves (avoids SSR/hydration WebGL access),
 *  - when no WebGL context is available (hard requirement),
 *  - when the user prefers reduced motion, or
 *  - when Performance Mode is enabled.
 */
export function WebGLGate({
  children,
  fallback,
  onModeChange,
  renderFallbackNotice,
}: WebGLGateProps) {
  const cap = useWebGLCapability();

  const reason = useMemo<FallbackReason>(() => {
    if (!cap.ready) return "probing";
    if (!cap.hasWebGL) return "no-webgl";
    if (cap.performanceMode) return "performance-mode";
    if (cap.prefersReducedMotion) return "reduced-motion";
    return "none";
  }, [cap]);

  const threeDActive = reason === "none";

  useEffect(() => {
    onModeChange?.(threeDActive);
  }, [threeDActive, onModeChange]);

  const enableThreeD = useCallback(() => {
    // Force performance mode off; reduced-motion cannot be overridden here
    // (it is an OS preference), so the gate still respects a hard WebGL failure.
    setPerformanceMode(false);
  }, []);

  if (threeDActive) {
    return <>{children}</>;
  }

  const canOverride = reason === "performance-mode";

  return (
    <>
      {renderFallbackNotice
        ? renderFallbackNotice({ reason, canOverride, enableThreeD })
        : null}
      {fallback}
    </>
  );
}

export default WebGLGate;
