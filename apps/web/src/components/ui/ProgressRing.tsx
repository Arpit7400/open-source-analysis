"use client";

import { type ReactNode } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { cn } from "@/lib/cn";

interface ProgressRingProps {
  /** Progress in the range 0..1 (values are clamped). */
  progress: number;
  /** Outer diameter in px — used as the SVG viewBox coordinate space. */
  size?: number;
  /**
   * When true, the ring scales to fill its parent's width (SVG uses the `size`
   * viewBox for geometry but renders at 100% × auto). Lets a row of gauges
   * auto-fit any column width instead of clipping at a fixed pixel size.
   */
  responsive?: boolean;
  /** Stroke width in px. */
  stroke?: number;
  /** Ring color — CSS color or custom-property string. */
  color?: string;
  /** Track (unfilled) color. */
  trackColor?: string;
  /** Show a second, offset ring (used for the VERIFYING dual-ring state). */
  dual?: boolean;
  /** Secondary ring color when `dual`. */
  dualColor?: string;
  /** Optional centered content (a number, glyph, icon). */
  children?: ReactNode;
  /** Soft outer glow tinted to `color`. */
  glow?: boolean;
  className?: string;
  "aria-label"?: string;
}

/**
 * SVG circular progress ring with an animated stroke-dashoffset sweep.
 * The arc starts at 12 o'clock (rotated -90deg). Animation is spring-driven
 * and disabled under reduced motion (the ring jumps to its final value).
 */
export function ProgressRing({
  progress,
  size = 44,
  responsive = false,
  stroke = 4,
  color = "var(--accent-cyan)",
  trackColor = "var(--border-hair)",
  dual = false,
  dualColor = "var(--accent-violet)",
  children,
  glow = false,
  className,
  "aria-label": ariaLabel,
}: ProgressRingProps) {
  const reduceMotion = useReducedMotion();
  const clamped = Math.max(0, Math.min(1, Number.isFinite(progress) ? progress : 0));

  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const targetOffset = circumference * (1 - clamped);
  const center = size / 2;
  const pct = Math.round(clamped * 100);

  const ringTransition = reduceMotion
    ? { duration: 0 }
    : { type: "spring" as const, stiffness: 120, damping: 22, mass: 0.6 };

  return (
    <div
      className={cn("relative inline-flex items-center justify-center", className)}
      style={
        responsive
          ? { width: "100%", aspectRatio: "1 / 1", maxWidth: size }
          : { width: size, height: size }
      }
      role="progressbar"
      aria-valuenow={pct}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={ariaLabel ?? `${pct}%`}
    >
      <svg
        width={responsive ? "100%" : size}
        height={responsive ? "100%" : size}
        viewBox={`0 0 ${size} ${size}`}
        style={{
          transform: "rotate(-90deg)",
          filter: glow
            ? `drop-shadow(0 0 6px color-mix(in srgb, ${color} 55%, transparent))`
            : undefined,
        }}
        aria-hidden="true"
      >
        {/* Track */}
        <circle
          cx={center}
          cy={center}
          r={radius}
          fill="none"
          stroke={trackColor}
          strokeWidth={stroke}
        />

        {/* Optional inner dual ring (drawn first, slightly inset). */}
        {dual ? (
          <motion.circle
            cx={center}
            cy={center}
            r={Math.max(radius - stroke - 1.5, 1)}
            fill="none"
            stroke={dualColor}
            strokeWidth={Math.max(stroke - 1, 1)}
            strokeLinecap="round"
            strokeDasharray={2 * Math.PI * Math.max(radius - stroke - 1.5, 1)}
            initial={false}
            animate={{
              strokeDashoffset:
                2 *
                Math.PI *
                Math.max(radius - stroke - 1.5, 1) *
                (1 - Math.min(clamped + 0.12, 1)),
            }}
            transition={ringTransition}
            opacity={0.8}
          />
        ) : null}

        {/* Primary progress arc */}
        <motion.circle
          cx={center}
          cy={center}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={circumference}
          initial={false}
          animate={{ strokeDashoffset: targetOffset }}
          transition={ringTransition}
        />
      </svg>

      {children != null ? (
        <span className="absolute inset-0 flex items-center justify-center">
          {children}
        </span>
      ) : null}
    </div>
  );
}

export default ProgressRing;
