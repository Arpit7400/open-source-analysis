import type { Metadata, Viewport } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import { Providers } from "./providers";
import "./globals.css";

/**
 * Fonts are exposed as CSS variables so `globals.css` (--font-sans / --font-mono)
 * and Tailwind's font families resolve to the loaded, self-hosted next/font files.
 * Inter stands in for "Geist Sans"; JetBrains Mono is the code/metric/ID face.
 */
const inter = Inter({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-sans",
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-mono",
});

export const metadata: Metadata = {
  title: "CareerForge AI — Engineering Command Center",
  description:
    "Local-first multi-agent career-intelligence platform. A dark technical operations console for repository intelligence, skill verification, and industry pulse.",
  applicationName: "CareerForge AI",
  authors: [{ name: "Arpit Sahu" }],
  creator: "Arpit Sahu",
  publisher: "Arpit Sahu",
  metadataBase: new URL("http://localhost:3000"),
  openGraph: {
    title: "CareerForge AI — Engineering Command Center",
    description:
      "Local-first multi-agent career-intelligence platform.",
    type: "website",
  },
  robots: { index: false, follow: false },
};

export const viewport: Viewport = {
  themeColor: "#05070d",
  colorScheme: "dark",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html
      lang="en"
      className={`dark ${inter.variable} ${jetbrainsMono.variable}`}
      suppressHydrationWarning
    >
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
