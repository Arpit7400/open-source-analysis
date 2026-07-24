"use client";

/**
 * AgentGraph — the live React Flow agent graph at the heart of the Command
 * Center. Reads agents + edges from the mission store, renders each agent via
 * the custom AgentNode renderer, and animates edges whose `animated` flag is
 * set. Nodes without explicit coordinates are auto-placed with a simple
 * layered layout keyed on the agent group (left-to-right pipeline order).
 *
 * Clicking a node sets `selectedAgentId` in the store (opens the AgentDrawer).
 */

import { useCallback, useMemo } from "react";
import {
  ReactFlow,
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  type Edge,
  type Node,
  type NodeMouseHandler,
  type NodeTypes,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useReducedMotion } from "framer-motion";
import type { AgentGroup, AgentNode as AgentNodeData, GraphEdge } from "@/lib/types";
import {
  selectAgentList,
  selectEdgeList,
  useMissionStore,
} from "@/lib/store";
import { AgentNode, type AgentFlowData } from "./AgentNode";

/** Column order used by the auto-layout (mirrors the mission phase pipeline). */
const GROUP_ORDER: AgentGroup[] = [
  "CONTROL",
  "INTAKE",
  "STATIC",
  "RUNTIME",
  "DUPLICATE",
  "AGGREGATE",
  "FIX",
  "VERIFY",
];

const COLUMN_WIDTH = 300;
const ROW_HEIGHT = 108;
const X_ORIGIN = 40;
const Y_ORIGIN = 40;

const STATE_EDGE_COLOR: Record<string, string> = {
  RUNNING: "var(--accent-cyan)",
  VERIFYING: "var(--accent-violet)",
  COMPLETED: "var(--accent-emerald)",
  FAILED: "var(--accent-rose)",
  REJECTED: "var(--text-muted)",
  BLOCKED: "var(--accent-amber)",
  WAITING: "var(--border-hair)",
};

/**
 * Layered layout: group agents into columns by `GROUP_ORDER`, then stack the
 * members of each column vertically and center them around the tallest column.
 * Pure, deterministic, and stable across re-renders (input order preserved).
 */
function layout(agents: AgentNodeData[]): Map<string, { x: number; y: number }> {
  const byGroup = new Map<AgentGroup, AgentNodeData[]>();
  for (const group of GROUP_ORDER) {
    byGroup.set(group, []);
  }
  for (const agent of agents) {
    const bucket = byGroup.get(agent.group);
    if (bucket) {
      bucket.push(agent);
    } else {
      byGroup.set(agent.group, [agent]);
    }
  }

  const columns = Array.from(byGroup.entries()).filter(
    ([, members]) => members.length > 0,
  );
  const maxRows = columns.reduce(
    (max, [, members]) => Math.max(max, members.length),
    1,
  );
  const centerY = Y_ORIGIN + ((maxRows - 1) * ROW_HEIGHT) / 2;

  const positions = new Map<string, { x: number; y: number }>();
  columns.forEach(([, members], columnIndex) => {
    const x = X_ORIGIN + columnIndex * COLUMN_WIDTH;
    const columnHeight = (members.length - 1) * ROW_HEIGHT;
    const startY = centerY - columnHeight / 2;
    members.forEach((agent, rowIndex) => {
      positions.set(agent.id, { x, y: startY + rowIndex * ROW_HEIGHT });
    });
  });
  return positions;
}

const nodeTypes: NodeTypes = { agent: AgentNode };

const PRO_OPTIONS = { hideAttribution: true } as const;

export function AgentGraph() {
  const reduceMotion = useReducedMotion();
  const agents = useMissionStore(selectAgentList);
  const edges = useMissionStore(selectEdgeList);
  const selectedAgentId = useMissionStore((s) => s.selectedAgentId);
  const selectAgentId = useMissionStore((s) => s.selectAgentId);

  const positions = useMemo(() => layout(agents), [agents]);

  const nodes: Node<AgentFlowData>[] = useMemo(
    () =>
      agents.map((agent) => {
        const pos = positions.get(agent.id) ?? { x: X_ORIGIN, y: Y_ORIGIN };
        return {
          id: agent.id,
          type: "agent",
          position: pos,
          data: { ...agent, selected: agent.id === selectedAgentId },
          draggable: true,
          selectable: true,
        };
      }),
    [agents, positions, selectedAgentId],
  );

  const flowEdges: Edge[] = useMemo(() => {
    const agentById = new Map<string, AgentNodeData>(
      agents.map((a) => [a.id, a]),
    );
    return edges.map((edge: GraphEdge) => {
      const source = agentById.get(edge.source);
      const stroke =
        source != null
          ? STATE_EDGE_COLOR[source.state] ?? "var(--border-hair)"
          : "var(--border-hair)";
      const animated = edge.animated && !reduceMotion;
      return {
        id: edge.id,
        source: edge.source,
        target: edge.target,
        animated,
        style: {
          stroke,
          strokeWidth: edge.animated ? 1.8 : 1,
          opacity: edge.animated ? 0.9 : 0.4,
        },
      } satisfies Edge;
    });
  }, [edges, agents, reduceMotion]);

  const onNodeClick = useCallback<NodeMouseHandler>(
    (_event, node) => {
      selectAgentId(node.id);
    },
    [selectAgentId],
  );

  const onPaneClick = useCallback(() => {
    selectAgentId(null);
  }, [selectAgentId]);

  return (
    <div className="h-full w-full" aria-label="Live agent graph" role="group">
      <ReactFlow
        nodes={nodes}
        edges={flowEdges}
        nodeTypes={nodeTypes}
        onNodeClick={onNodeClick}
        onPaneClick={onPaneClick}
        fitView
        fitViewOptions={{ padding: 0.2, maxZoom: 1.1 }}
        minZoom={0.25}
        maxZoom={1.6}
        proOptions={PRO_OPTIONS}
        nodesConnectable={false}
        elementsSelectable
        panOnScroll
        selectionOnDrag={false}
        defaultEdgeOptions={{ type: "default" }}
        className="cf-agent-flow"
        style={{ background: "transparent" }}
      >
        <Background
          variant={BackgroundVariant.Dots}
          gap={26}
          size={1}
          color="rgba(120,160,220,0.14)"
        />
        <MiniMap
          pannable
          zoomable
          ariaLabel="Agent graph minimap"
          maskColor="rgba(5,7,13,0.72)"
          style={{
            background: "color-mix(in srgb, var(--bg-panel) 88%, transparent)",
            border: "1px solid var(--border-hair)",
            borderRadius: 8,
          }}
          nodeColor={(node) => {
            const state = (node.data as AgentFlowData | undefined)?.state;
            return state ? STATE_EDGE_COLOR[state] ?? "var(--text-muted)" : "var(--text-muted)";
          }}
          nodeStrokeWidth={2}
        />
        <Controls
          showInteractive={false}
          style={{
            background: "color-mix(in srgb, var(--bg-panel) 88%, transparent)",
            border: "1px solid var(--border-hair)",
            borderRadius: 8,
          }}
        />
      </ReactFlow>
    </div>
  );
}

export default AgentGraph;
