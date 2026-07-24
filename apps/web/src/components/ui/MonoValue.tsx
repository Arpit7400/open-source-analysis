"use client";

import { useEffect, useRef } from "react";
import {
  animate,
  useMotionValue,
  useReducedMotion,
  type ValueAnimationTransition,
} from "framer-motion";
import { cn } from "@/lib/cn";

interface MonoValueProps {
  /** Target numeric value. */
  value: number;
  /** Decimal places to render (default 0). */
  decimals?: number;
  /** Prefix (e.g. "$") rendered inside the mono span. */
  prefix?: string;
  /** Suffix / unit (e.g. "%", "ms") rendered inside the mono span. */
  suffix?: string;
  /** Count-up duration in seconds. */
  duration?: number;
  /** Thousands grouping (default true). */
  group?: boolean;
  className?: string;
  "aria-label"?: string;
}

/**
 * A count-up animated number rendered in the mono face with tabular figures.
 * Uses a framer-motion MotionValue driven imperatively into text content so we
 * never re-render React on every frame. Under reduced motion (or SSR) it snaps
 * straight to the final value.
 */
export function MonoValue({
  value,
  decimals = 0,
  prefix = "",
  suffix = "",
  duration = 0.9,
  group = true,
  className,
  "aria-label": ariaLabel,
}: MonoValueProps) {
  const reduceMotion = useReducedMotion();
  const motionValue = useMotionValue(0);
  const ref = useRef<HTMLSpanElement>(null);
  const previous = useRef(0);

  const format = (n: number): string => {
    const fixed = Number.isFinite(n) ? n : 0;
    const body = group
      ? fixed.toLocaleString(undefined, {
          minimumFractionDigits: decimals,
          maximumFractionDigits: decimals,
        })
      : fixed.toFixed(decimals);
    return `${prefix}${body}${suffix}`;
  };

  useEffect(() => {
    const node = ref.current;
    if (!node) return;

    // Snap instantly when the user prefers reduced motion.
    if (reduceMotion) {
      motionValue.set(value);
      node.textContent = format(value);
      previous.current = value;
      return;
    }

    const unsubscribe = motionValue.on("change", (latest) => {
      node.textContent = format(latest);
    });

    const transition: ValueAnimationTransition = {
      duration,
      ease: [0.22, 1, 0.36, 1],
    };
    const controls = animate(motionValue, value, transition);
    previous.current = value;

    return () => {
      unsubscribe();
      controls.stop();
    };
    // format is derived purely from the props below; listing primitives avoids
    // re-running the animation for an unstable function identity.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value, reduceMotion, duration, decimals, prefix, suffix, group]);

  return (
    <span
      ref={ref}
      className={cn("mono tabular-nums", className)}
      aria-label={ariaLabel ?? format(value)}
      // Server-rendered fallback so there is no layout flash before hydration.
      suppressHydrationWarning
    >
      {format(value)}
    </span>
  );
}

export default MonoValue;
