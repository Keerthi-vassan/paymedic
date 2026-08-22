"use client";

import { useEffect, useState } from "react";

import { generateBatch, getHealth, runPipeline } from "@/lib/api";
import { formatCurrency } from "@/lib/format";
import { ActionsTakenTable } from "@/components/ActionsTakenTable";
import { AuditTrailPanel } from "@/components/AuditTrailPanel";
import { FailedPaymentsFeed } from "@/components/FailedPaymentsFeed";
import { MetricsSummary } from "@/components/MetricsSummary";
import { RootCauseBreakdown } from "@/components/RootCauseBreakdown";
import { SafetyBoundsPanel } from "@/components/SafetyBoundsPanel";
import { TopBar } from "@/components/TopBar";

type HealthStatus = "checking" | "ok" | "error";

const SUMMARY_DISPLAY_MS = 4000;

export default function Home() {
  const [health, setHealth] = useState<HealthStatus>("checking");
  const [refreshKey, setRefreshKey] = useState(0);
  const [generating, setGenerating] = useState(false);
  const [running, setRunning] = useState(false);
  const [selectedTransaction, setSelectedTransaction] = useState<string | null>(null);
  const [lastRunSummary, setLastRunSummary] = useState<string | null>(null);

  useEffect(() => {
    getHealth()
      .then(() => setHealth("ok"))
      .catch(() => setHealth("error"));
  }, []);

  useEffect(() => {
    if (!lastRunSummary) return;
    const timer = setTimeout(() => setLastRunSummary(null), SUMMARY_DISPLAY_MS);
    return () => clearTimeout(timer);
  }, [lastRunSummary]);

  const handleGenerate = async () => {
    setGenerating(true);
    try {
      const res = await generateBatch(100, 42);
      setRefreshKey((k) => k + 1);
      setLastRunSummary(`✓ Generated ${res.count} transactions`);
    } finally {
      setGenerating(false);
    }
  };

  const handleRunPipeline = async () => {
    setRunning(true);
    try {
      const res = await runPipeline();
      setRefreshKey((k) => k + 1);
      setLastRunSummary(
        `✓ ${res.recovered} recovered · ${formatCurrency(res.total_recovered_amount)}`
      );
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="flex min-h-screen flex-col bg-background">
      <TopBar
        health={health}
        generating={generating}
        running={running}
        lastRunSummary={lastRunSummary}
        onGenerate={handleGenerate}
        onRunPipeline={handleRunPipeline}
      />

      <main className="mx-auto flex w-full max-w-7xl flex-1 flex-col gap-4 px-6 py-6">
        <MetricsSummary refreshKey={refreshKey} />

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          <div className="lg:col-span-2">
            <RootCauseBreakdown refreshKey={refreshKey} />
          </div>
          <SafetyBoundsPanel refreshKey={refreshKey} />
        </div>

        <ActionsTakenTable refreshKey={refreshKey} onSelectTransaction={setSelectedTransaction} />

        <FailedPaymentsFeed refreshKey={refreshKey} onSelectTransaction={setSelectedTransaction} />
      </main>

      <AuditTrailPanel transactionId={selectedTransaction} onClose={() => setSelectedTransaction(null)} />
    </div>
  );
}
