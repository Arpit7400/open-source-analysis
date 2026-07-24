"use client";

import { useMemo, useRef, useState } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { Html, OrbitControls, Stars } from "@react-three/drei";
import { useReducedMotion } from "framer-motion";
import * as THREE from "three";
import type { Skill } from "@/lib/types";
import {
  verificationColor,
  verificationLabel,
} from "./VerificationBadge";

/* ------------------------------------------------------------------ */
/* Layout                                                             */
/* ------------------------------------------------------------------ */

interface PlacedSkill {
  skill: Skill;
  position: THREE.Vector3;
  /** Sphere radius derived from evidence strength. */
  radius: number;
  /** Base (verification-tinted) color. */
  color: THREE.Color;
  /** Emissive intensity derived from confidence. */
  emissive: number;
  /** Pulse speed derived from recency (recent → livelier). */
  pulseSpeed: number;
}

/**
 * Deterministically place skills on a Fibonacci sphere so the layout is stable
 * across renders (no jitter) and evenly distributed regardless of count. The
 * radius of the shell scales gently with the number of skills so dense graphs
 * do not overlap.
 */
function useLayout(skills: Skill[]): {
  placed: PlacedSkill[];
  byId: Map<string, PlacedSkill>;
  shellRadius: number;
} {
  return useMemo(() => {
    const count = Math.max(skills.length, 1);
    const shellRadius = 4.5 + Math.min(count, 40) * 0.12;
    const golden = Math.PI * (3 - Math.sqrt(5)); // golden angle

    const placed: PlacedSkill[] = skills.map((skill, i) => {
      // Evenly spaced points on a sphere (Fibonacci lattice).
      const y = count === 1 ? 0 : 1 - (i / (count - 1)) * 2;
      const r = Math.sqrt(Math.max(0, 1 - y * y));
      const theta = golden * i;
      const position = new THREE.Vector3(
        Math.cos(theta) * r * shellRadius,
        y * shellRadius,
        Math.sin(theta) * r * shellRadius,
      );

      const clamp01 = (n: number) =>
        Math.max(0, Math.min(1, Number.isFinite(n) ? n : 0));

      // size ∝ evidence_strength
      const radius = 0.28 + clamp01(skill.evidence_strength) * 0.62;
      // emissive intensity ∝ confidence
      const emissive = 0.3 + clamp01(skill.confidence) * 1.9;
      // pulse speed ∝ recency
      const pulseSpeed = 0.6 + clamp01(skill.recency) * 2.2;
      // verification_level tints the base color
      const color = new THREE.Color(
        verificationColor(skill.verification_level),
      );

      return { skill, position, radius, color, emissive, pulseSpeed };
    });

    const byId = new Map(placed.map((p) => [p.skill.id, p]));
    return { placed, byId, shellRadius };
  }, [skills]);
}

/* ------------------------------------------------------------------ */
/* Nodes                                                              */
/* ------------------------------------------------------------------ */

interface SkillNodeProps {
  node: PlacedSkill;
  animate: boolean;
  hovered: boolean;
  onHover: (id: string | null) => void;
}

function SkillNode({ node, animate, hovered, onHover }: SkillNodeProps) {
  const meshRef = useRef<THREE.Mesh>(null);
  const materialRef = useRef<THREE.MeshStandardMaterial>(null);
  const { skill, position, radius, color, emissive, pulseSpeed } = node;

  useFrame((state) => {
    const mesh = meshRef.current;
    const material = materialRef.current;
    if (!mesh || !material) return;

    if (animate) {
      // Gentle breathing pulse; recent skills breathe faster/brighter.
      const t = state.clock.elapsedTime;
      const pulse = 0.5 + 0.5 * Math.sin(t * pulseSpeed);
      const scale = 1 + pulse * 0.12;
      mesh.scale.setScalar(hovered ? scale * 1.25 : scale);
      material.emissiveIntensity = emissive * (0.7 + pulse * 0.6);
    } else {
      mesh.scale.setScalar(hovered ? 1.2 : 1);
      material.emissiveIntensity = emissive;
    }
  });

  return (
    <group position={position}>
      <mesh
        ref={meshRef}
        onPointerOver={(e) => {
          e.stopPropagation();
          onHover(skill.id);
        }}
        onPointerOut={(e) => {
          e.stopPropagation();
          onHover(null);
        }}
      >
        <sphereGeometry args={[radius, 32, 32]} />
        <meshStandardMaterial
          ref={materialRef}
          color={color}
          emissive={color}
          emissiveIntensity={emissive}
          roughness={0.35}
          metalness={0.1}
          toneMapped={false}
        />
      </mesh>

      {hovered ? (
        <Html
          center
          distanceFactor={12}
          position={[0, radius + 0.7, 0]}
          zIndexRange={[20, 0]}
          style={{ pointerEvents: "none" }}
        >
          <NodeLabel skill={skill} />
        </Html>
      ) : null}
    </group>
  );
}

function NodeLabel({ skill }: { skill: Skill }) {
  const accent = verificationColor(skill.verification_level);
  return (
    <div
      className="mono select-none whitespace-nowrap rounded-md px-2.5 py-1.5 text-[11px] leading-tight"
      style={{
        background: "rgba(10, 14, 23, 0.92)",
        border: `1px solid color-mix(in srgb, ${accent} 45%, transparent)`,
        color: "var(--text-primary)",
        boxShadow: `0 0 18px -6px ${accent}`,
        backdropFilter: "blur(6px)",
      }}
    >
      <div className="font-semibold" style={{ color: accent }}>
        {skill.name}
      </div>
      <div className="mt-0.5 text-[10px] text-[color:var(--text-secondary)]">
        {verificationLabel(skill.verification_level)} ·{" "}
        {Math.round(skill.confidence * 100)}% conf
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Relationship lines                                                 */
/* ------------------------------------------------------------------ */

/**
 * Draw a single line-segments object connecting every related skill pair. Using
 * one BufferGeometry for all edges keeps draw calls low even with many skills.
 */
function RelationshipLines({ layout }: { layout: ReturnType<typeof useLayout> }) {
  const geometry = useMemo(() => {
    const points: number[] = [];
    const seen = new Set<string>();

    for (const node of layout.placed) {
      for (const relatedId of node.skill.related_skill_ids) {
        const target = layout.byId.get(relatedId);
        if (!target) continue;
        // Dedupe undirected pairs.
        const key =
          node.skill.id < relatedId
            ? `${node.skill.id}|${relatedId}`
            : `${relatedId}|${node.skill.id}`;
        if (seen.has(key)) continue;
        seen.add(key);

        points.push(
          node.position.x,
          node.position.y,
          node.position.z,
          target.position.x,
          target.position.y,
          target.position.z,
        );
      }
    }

    const geo = new THREE.BufferGeometry();
    geo.setAttribute(
      "position",
      new THREE.Float32BufferAttribute(points, 3),
    );
    return geo;
  }, [layout]);

  const positionAttr = geometry.getAttribute("position");
  if (!positionAttr || positionAttr.count === 0) return null;

  return (
    <lineSegments geometry={geometry}>
      <lineBasicMaterial
        color={new THREE.Color("#3b82c4")}
        transparent
        opacity={0.22}
        toneMapped={false}
      />
    </lineSegments>
  );
}

/* ------------------------------------------------------------------ */
/* Scene                                                              */
/* ------------------------------------------------------------------ */

function Scene({
  skills,
  animate,
}: {
  skills: Skill[];
  animate: boolean;
}) {
  const layout = useLayout(skills);
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const groupRef = useRef<THREE.Group>(null);

  // Slow ambient auto-rotation of the whole cloud (disabled: reduced-motion).
  useFrame((_, delta) => {
    if (!animate) return;
    const group = groupRef.current;
    if (group && hoveredId === null) {
      group.rotation.y += delta * 0.05;
    }
  });

  return (
    <>
      <color attach="background" args={["#05070d"]} />
      <fog attach="fog" args={["#05070d", 12, 30]} />

      <ambientLight intensity={0.4} />
      <pointLight position={[10, 10, 10]} intensity={0.6} />
      <pointLight position={[-10, -6, -8]} intensity={0.3} color="#a78bfa" />

      <Stars
        radius={60}
        depth={40}
        count={1800}
        factor={3}
        saturation={0}
        fade
        speed={animate ? 0.4 : 0}
      />

      <group ref={groupRef}>
        <RelationshipLines layout={layout} />
        {layout.placed.map((node) => (
          <SkillNode
            key={node.skill.id}
            node={node}
            animate={animate}
            hovered={hoveredId === node.skill.id}
            onHover={setHoveredId}
          />
        ))}
      </group>

      <OrbitControls
        enablePan={false}
        enableDamping
        dampingFactor={0.08}
        rotateSpeed={0.6}
        zoomSpeed={0.7}
        minDistance={6}
        maxDistance={26}
        autoRotate={false}
      />
    </>
  );
}

/* ------------------------------------------------------------------ */
/* Public component                                                   */
/* ------------------------------------------------------------------ */

interface ConstellationProps {
  skills: Skill[];
  /** Fixed height of the canvas container. */
  height?: number | string;
}

/**
 * The Skill Constellation — a 3D force-free star map of the user's skills.
 * Each skill is an emissive sphere: size scales with evidence strength,
 * emissive intensity with confidence, and a gentle breathing pulse with
 * recency. Lines connect related skills; the base color is tinted by
 * verification level. Orbit to explore; hover a node for a label.
 *
 * This component is always mounted behind a WebGL gate and loaded via
 * `next/dynamic` (ssr:false), so it never runs during SSR.
 */
export function Constellation({ skills, height = 560 }: ConstellationProps) {
  const reduceMotion = useReducedMotion();
  const animate = !reduceMotion;
  const cameraDistance = 4.5 + Math.min(skills.length, 40) * 0.12 + 6;

  return (
    <div
      style={{ height }}
      className="relative w-full overflow-hidden rounded-lg"
      role="img"
      aria-label={`Interactive 3D constellation of ${skills.length} skills. Orbit to explore, or switch to the accessible table view.`}
    >
      <Canvas
        dpr={[1, 1.75]}
        frameloop={animate ? "always" : "demand"}
        camera={{ position: [0, 0, cameraDistance], fov: 50, near: 0.1, far: 100 }}
        gl={{ antialias: true, alpha: false, powerPreference: "high-performance" }}
      >
        <Scene skills={skills} animate={animate} />
      </Canvas>
    </div>
  );
}

export default Constellation;
