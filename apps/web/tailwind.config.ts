import type { Config } from 'tailwindcss';

const config: Config = {
  darkMode: 'class',
  content: [
    './src/app/**/*.{ts,tsx,js,jsx,mdx}',
    './src/components/**/*.{ts,tsx,js,jsx,mdx}',
    './src/**/*.{ts,tsx,js,jsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        // Background ramp
        void: '#05070d',
        base: '#0a0e17',
        panel: '#0e1420',
        elevated: '#131b2b',
        glass: 'rgba(18,26,42,0.55)',
        // Accent ramps
        accent: {
          cyan: '#22d3ee',
          'cyan-dim': '#0e7490',
          violet: '#a78bfa',
          amber: '#fbbf24',
          emerald: '#34d399',
          rose: '#fb7185',
          blue: '#60a5fa',
        },
        // Text ramp
        text: {
          primary: '#e6edf7',
          secondary: '#93a4bd',
          muted: '#556274',
        },
        // Borders
        border: {
          hair: 'rgba(120,160,220,0.12)',
          glow: 'rgba(80,200,255,0.35)',
        },
      },
      fontFamily: {
        sans: [
          'var(--font-sans)',
          'Geist Sans',
          'ui-sans-serif',
          'system-ui',
          '-apple-system',
          'Segoe UI',
          'Roboto',
          'Helvetica Neue',
          'Arial',
          'sans-serif',
        ],
        mono: [
          'var(--font-mono)',
          'Geist Mono',
          'JetBrains Mono',
          'ui-monospace',
          'SFMono-Regular',
          'Menlo',
          'Consolas',
          'Liberation Mono',
          'monospace',
        ],
      },
      keyframes: {
        flow: {
          '0%': { strokeDashoffset: '24' },
          '100%': { strokeDashoffset: '0' },
        },
        pulse: {
          '0%, 100%': { opacity: '1', transform: 'scale(1)' },
          '50%': { opacity: '0.55', transform: 'scale(1.04)' },
        },
        shimmer: {
          '0%': { transform: 'translateX(-120%)' },
          '100%': { transform: 'translateX(120%)' },
        },
        breathe: {
          '0%, 100%': {
            boxShadow: '0 0 0 0 rgba(34,211,238,0.45)',
            opacity: '0.9',
          },
          '50%': {
            boxShadow: '0 0 24px 6px rgba(34,211,238,0.28)',
            opacity: '1',
          },
        },
        'count-up': {
          '0%': { opacity: '0', transform: 'translateY(6px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
      },
      animation: {
        flow: 'flow 0.9s linear infinite',
        pulse: 'pulse 2s ease-in-out infinite',
        shimmer: 'shimmer 2.4s ease-in-out infinite',
        breathe: 'breathe 3.2s ease-in-out infinite',
        'count-up': 'count-up 0.4s ease-out both',
      },
      backdropBlur: {
        xs: '2px',
      },
    },
  },
  plugins: [],
};

export default config;
