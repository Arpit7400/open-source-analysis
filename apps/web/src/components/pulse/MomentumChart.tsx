"use client";

import { useMemo } from "react";
import ReactECharts from "echarts-for-react";
import type { EChartsOption } from "echarts";
import type { PulseItem, PulseSource } from "@/lib/types";

/** Accent per source, matching the design-system ramps. */
const SOURCE_COLOR: Record<PulseSource, string> = {
  arXiv: "#a78bfa", // violet
  GitHub: "#22d3ee", // cyan
  Blog: "#60a5fa", // blue
  Advisory: "#fb7185", // rose
};

const TEXT_SECONDARY = "#93a4bd";
const TEXT_MUTED = "#556274";
const HAIRLINE = "rgba(120,160,220,0.12)";

interface MomentumChartProps {
  items: PulseItem[];
  height?: number | string;
}

function clamp01(n: number): number {
  return Math.max(0, Math.min(1, Number.isFinite(n) ? n : 0));
}

/**
 * Dark-themed ECharts scatter of the Industry Pulse.
 *  - x axis: publication time
 *  - y axis: momentum (0..1)
 *  - symbol size: personal relevance (bigger = more relevant to you)
 *  - color: source
 *  - tooltip: title + technology + the three scores
 *
 * One series per source so the legend doubles as a source filter reference and
 * colors stay stable. Responsive via echarts-for-react's autoResize.
 */
export function MomentumChart({ items, height = 360 }: MomentumChartProps) {
  const option = useMemo<EChartsOption>(() => {
    const bySource = new Map<PulseSource, PulseItem[]>();
    for (const item of items) {
      const bucket = bySource.get(item.source) ?? [];
      bucket.push(item);
      bySource.set(item.source, bucket);
    }

    const series = Array.from(bySource.entries()).map(([source, group]) => ({
      name: source,
      type: "scatter" as const,
      symbolSize: (data: (number | string)[]) => {
        // data = [timestamp, momentum, relevance, actionability]
        const relevance = clamp01(Number(data[2]));
        return 12 + relevance * 34;
      },
      itemStyle: {
        color: SOURCE_COLOR[source],
        borderColor: SOURCE_COLOR[source],
        borderWidth: 1,
        opacity: 0.82,
        shadowBlur: 12,
        shadowColor: SOURCE_COLOR[source],
      },
      emphasis: {
        focus: "series" as const,
        itemStyle: { opacity: 1, shadowBlur: 20 },
      },
      data: group.map((item) => ({
        name: item.title,
        value: [
          new Date(item.published_at).getTime(),
          clamp01(item.momentum),
          clamp01(item.personal_relevance),
          clamp01(item.actionability),
          item.technology,
        ],
      })),
    }));

    return {
      backgroundColor: "transparent",
      textStyle: {
        fontFamily:
          '"JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, monospace',
        color: TEXT_SECONDARY,
      },
      grid: { left: 56, right: 24, top: 42, bottom: 48, containLabel: false },
      legend: {
        top: 8,
        right: 8,
        textStyle: { color: TEXT_SECONDARY, fontSize: 11 },
        inactiveColor: TEXT_MUTED,
        icon: "circle",
        itemWidth: 9,
        itemHeight: 9,
      },
      tooltip: {
        trigger: "item",
        backgroundColor: "rgba(14,20,32,0.96)",
        borderColor: HAIRLINE,
        borderWidth: 1,
        padding: 10,
        textStyle: { color: "#e6edf7", fontSize: 12 },
        extraCssText: "backdrop-filter: blur(8px); border-radius: 8px;",
        formatter: (params: unknown): string => {
          const p = params as {
            data: { name: string; value: (number | string)[] };
            color: string;
            seriesName: string;
          };
          const value = p.data.value;
          const ts = new Date(Number(value[0]));
          const momentum = Math.round(Number(value[1]) * 100);
          const relevance = Math.round(Number(value[2]) * 100);
          const actionability = Math.round(Number(value[3]) * 100);
          const tech = String(value[4] ?? "");
          const dateStr = ts.toLocaleDateString(undefined, {
            year: "numeric",
            month: "short",
            day: "numeric",
          });
          const safe = (s: string) =>
            s.replace(/[&<>"]/g, (c) =>
              c === "&"
                ? "&amp;"
                : c === "<"
                  ? "&lt;"
                  : c === ">"
                    ? "&gt;"
                    : "&quot;",
            );
          return [
            `<div style="max-width:260px;">`,
            `<div style="font-weight:600;margin-bottom:4px;color:${p.color};white-space:normal;">${safe(p.data.name)}</div>`,
            `<div style="color:${TEXT_SECONDARY};font-size:11px;margin-bottom:6px;">${safe(p.seriesName)} · ${safe(tech)} · ${dateStr}</div>`,
            `<div style="font-size:11px;">momentum <b>${momentum}%</b> · relevance <b>${relevance}%</b> · actionability <b>${actionability}%</b></div>`,
            `</div>`,
          ].join("");
        },
      },
      xAxis: {
        type: "time",
        name: "published",
        nameLocation: "middle",
        nameGap: 30,
        nameTextStyle: { color: TEXT_MUTED, fontSize: 10 },
        axisLine: { lineStyle: { color: HAIRLINE } },
        axisLabel: {
          color: TEXT_MUTED,
          fontSize: 10,
          hideOverlap: true,
        },
        splitLine: {
          show: true,
          lineStyle: { color: HAIRLINE, type: "dashed" },
        },
      },
      yAxis: {
        type: "value",
        name: "momentum",
        min: 0,
        max: 1,
        nameTextStyle: { color: TEXT_MUTED, fontSize: 10, align: "left" },
        axisLine: { lineStyle: { color: HAIRLINE } },
        axisLabel: {
          color: TEXT_MUTED,
          fontSize: 10,
          formatter: (val: number) => `${Math.round(val * 100)}%`,
        },
        splitLine: { lineStyle: { color: HAIRLINE, type: "dashed" } },
      },
      animationDuration: 600,
      animationEasing: "cubicOut",
      series,
    };
  }, [items]);

  if (items.length === 0) {
    return (
      <div
        className="flex items-center justify-center rounded-lg text-sm text-[color:var(--text-secondary)] hairline"
        style={{ height }}
      >
        No signals match the current filters.
      </div>
    );
  }

  return (
    <div style={{ height }} className="w-full">
      <ReactECharts
        option={option}
        notMerge
        lazyUpdate
        style={{ height: "100%", width: "100%" }}
        opts={{ renderer: "canvas" }}
      />
    </div>
  );
}

export default MomentumChart;
