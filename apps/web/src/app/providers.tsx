"use client";

import { useState, type ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MotionConfig } from "framer-motion";

/**
 * App-wide providers.
 *
 * - A single TanStack QueryClient, created once per browser session via
 *   useState so it survives re-renders but is never shared across requests
 *   during SSR (each render tree gets its own instance).
 * - MotionConfig with reducedMotion="user" so framer-motion honors the OS
 *   `prefers-reduced-motion` setting globally, matching the design system's
 *   accessibility contract.
 */
export function Providers({ children }: { children: ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 5_000,
            refetchOnWindowFocus: false,
            retry: 1,
          },
        },
      }),
  );

  return (
    <QueryClientProvider client={queryClient}>
      <MotionConfig reducedMotion="user">{children}</MotionConfig>
    </QueryClientProvider>
  );
}
