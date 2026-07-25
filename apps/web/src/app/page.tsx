"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { motion, useReducedMotion, type Variants } from "framer-motion";
import {
  ArrowRight,
  Radar,
  FlaskConical,
  Network,
  Activity,
} from "lucide-react";
import { BootSequence } from "@/components/BootSequence";
import { Eyebrow } from "@/components/ui/Eyebrow";

const BOOT_KEY = "cf.boot.seen";

interface NavCard {
  href: string;
  title: string;
  eyebrow: string;
  description: string;
  icon: typeof Radar;
  accent: string;
}

const NAV_CARDS: readonly NavCard[] = [
  {
    href: "/command",
    title: "Command Center",
    eyebrow: "Mission control",
    description:
      "Launch a repository mission and watch the multi-agent graph reason, verify, and converge in real time.",
    icon: Network,
    accent: "var(--accent-cyan)",
  },
  {
    href: "/lab",
    title: "Contribution Lab",
    eyebrow: "Fix & verify",
    description:
      "Inspect candidate fixes, side-by-side diffs, and independent verification matrices before any human-gated draft.",
    icon: FlaskConical,
    accent: "var(--accent-violet)",
  },
  {
    href: "/skills",
    title: "Skill Constellation",
    eyebrow: "Profile brain",
    description:
      "A verifiable map of your skills — sized by evidence, lit by confidence, sourced to commits, tests, and PRs.",
    icon: Radar,
    accent: "var(--accent-emerald)",
  },
  {
    href: "/pulse",
    title: "Industry Pulse",
    eyebrow: "Signal radar",
    description:
      "Momentum-ranked technology signals scored for personal relevance, skill gaps, and concrete next actions.",
    icon: Activity,
    accent: "var(--accent-blue)",
  },
] as const;

export default function LandingPage() {
  const reduceMotion = useReducedMotion();
  // Start with boot NOT shown to avoid an SSR/client mismatch; decide on mount.
  const [booting, setBooting] = useState(false);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let seen = false;
    try {
      seen = window.sessionStorage.getItem(BOOT_KEY) === "1";
    } catch {
      seen = false;
    }
    if (seen) {
      setReady(true);
    } else {
      setBooting(true);
    }
  }, []);

  const handleBootDone = () => {
    setBooting(false);
    setReady(true);
  };

  const container: Variants = {
    hidden: {},
    show: {
      transition: { staggerChildren: reduceMotion ? 0 : 0.08, delayChildren: 0.05 },
    },
  };

  const item: Variants = {
    hidden: { opacity: 0, y: reduceMotion ? 0 : 16 },
    show: {
      opacity: 1,
      y: 0,
      transition: { type: "spring", stiffness: 220, damping: 26, mass: 0.7 },
    },
  };

  return (
    <>
      {booting ? (
        <BootSequence onDone={handleBootDone} storageKey={BOOT_KEY} />
      ) : null}

      <main className="relative mx-auto flex min-h-screen w-full max-w-6xl flex-col items-center justify-center px-6 py-16">
        <motion.div
          variants={container}
          initial="hidden"
          animate={ready ? "show" : "hidden"}
          className="flex w-full flex-col items-center"
        >
          {/* Eyebrow */}
          <motion.div variants={item}>
            <Eyebrow className="text-[color:var(--accent-cyan)]">
              Local-first · Multi-agent · Human-gated
            </Eyebrow>
          </motion.div>

          {/* Hero title */}
          <motion.h1
            variants={item}
            className="mt-5 text-center text-5xl font-semibold tracking-tight sm:text-6xl md:text-7xl"
          >
            <span className="bg-gradient-to-b from-[color:var(--text-primary)] to-[color:var(--text-secondary)] bg-clip-text text-transparent">
              CareerForge
            </span>{" "}
            <span
              className="bg-gradient-to-r from-[color:var(--accent-cyan)] to-[color:var(--accent-violet)] bg-clip-text text-transparent"
              style={{ WebkitTextFillColor: "transparent" }}
            >
              AI
            </span>
          </motion.h1>

          {/* Subhead */}
          <motion.p
            variants={item}
            className="mt-5 max-w-2xl text-center text-base leading-relaxed text-[color:var(--text-secondary)] sm:text-lg"
          >
            An engineering command center that runs a fleet of reasoning agents
            over real repositories — analyzing, reproducing, fixing, and
            independently verifying — then turns the evidence into a verifiable
            map of what you can actually do.
          </motion.p>

          {/* Primary CTA */}
          <motion.div variants={item} className="mt-8">
            <Link
              href="/command"
              className="group inline-flex items-center gap-2 rounded-full bg-[color:var(--accent-cyan)] px-6 py-3 text-sm font-semibold text-[#04121a] transition-transform hover:scale-[1.02] focus-visible:scale-[1.02]"
            >
              Enter Command Center
              <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
            </Link>
          </motion.div>

          {/* Nav cards */}
          <div className="mt-14 grid w-full grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {NAV_CARDS.map((card) => {
              const Icon = card.icon;
              return (
                <motion.div key={card.href} variants={item}>
                  <Link
                    href={card.href}
                    className="glass group relative flex h-full flex-col gap-3 p-5 transition-colors hover:border-[color:var(--border-glow)] focus-visible:border-[color:var(--border-glow)]"
                  >
                    <span
                      className="inline-flex h-10 w-10 items-center justify-center rounded-lg hairline"
                      style={{
                        color: card.accent,
                        background: `color-mix(in srgb, ${card.accent} 12%, transparent)`,
                        borderColor: `color-mix(in srgb, ${card.accent} 30%, transparent)`,
                      }}
                    >
                      <Icon className="h-5 w-5" aria-hidden="true" />
                    </span>
                    <Eyebrow style={{ color: card.accent }}>
                      {card.eyebrow}
                    </Eyebrow>
                    <h2 className="text-base font-semibold text-[color:var(--text-primary)]">
                      {card.title}
                    </h2>
                    <p className="text-sm leading-relaxed text-[color:var(--text-secondary)]">
                      {card.description}
                    </p>
                    <span className="mono mt-auto inline-flex items-center gap-1 pt-2 text-xs text-[color:var(--text-muted)] transition-colors group-hover:text-[color:var(--text-secondary)]">
                      {card.href}
                      <ArrowRight className="h-3 w-3 transition-transform group-hover:translate-x-0.5" />
                    </span>
                  </Link>
                </motion.div>
              );
            })}
          </div>
        </motion.div>

        {/* ---- Ownership / copyright ------------------------------------ */}
        <footer className="mt-10 text-center text-xs text-[color:var(--text-muted)]">
          © 2026 CareerForge AI — All rights reserved by Arpit Sahu.
        </footer>
      </main>
    </>
  );
}
