import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Paymedic",
  description: "Bounded AI agent for failed-payment recovery",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        {/*
          THESIS: A precise, trustworthy operations console for bounded AI-driven
          payment recovery -- not a flashy agent demo.
          OWN-WORLD: Restrained neutrals + Razorpay Blade palette (Prussian Blue
          chrome, Dodger Blue accent); functional status colors (slate/green/
          amber/crimson) independent of brand; Geist Sans/Mono throughout.
          STORY: An operator sees real recovery metrics, understands the system
          is rule-gated and self-correcting, and can trace any transaction's
          full decision trail.
          FIRST VIEWPORT: Chrome top bar (name + connection + actions) -> KPI
          tile row -> root-cause breakdown + safety bounds side-by-side ->
          actions table -> failed payments feed, in that reading order.
          FORM: Operate mode, restrained color strategy, built directly from
          operate.md guidance (no concept-tournament -- this mode's own
          guidance explicitly favors familiarity/consistency over reinvention).
          FINISH: unreviewed and undocumented is unfinished; this build ends
          with the finish review, the verdict, DESIGN.md, and every shipping
          raster carrying its provenance.
        */}
        {children}
      </body>
    </html>
  );
}
