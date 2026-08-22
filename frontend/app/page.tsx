"use client";

import { useEffect, useState } from "react";

import { generateBatch, getHealth, runPipeline } from "@/lib/api";
import { ActionsTakenTable } from "@/components/ActionsTakenTable";
import { AuditTrailPanel } from "@/components/AuditTrailPanel";
import { FailedPaymentsFeed } from "@/components/FailedPaymentsFeed";
import { MetricsSummary } from "@/components/MetricsSummary";
import { RootCauseBreakdown } from "@/components/RootCauseBreakdown";
import { SafetyBoundsPanel } from "@/components/SafetyBoundsPanel";
import { TopBar } from "@/components/TopBar";

type HealthStatus = "checking" | "ok" | "error";

export default function Home() {
  const [health, setHealth] = useState<HealthStatus>("checking");
  const [refreshKey, setRefreshKey] = useState(0);
  const [generating, setGenerating] = useState(false);
  const [running, setRunning] = useState(false);
  const [selectedTransaction, setSelectedTransaction] = useState<string | null>(null);

  useEffect(() => {
    getHealth()
      .then(() => setHealth("ok"))
      .catch(() => setHealth("error"));
  }, []);

  const handleGenerate = async () => {
    setGenerating(true);
    try {
      await generateBatch(100, 42);
      setRefreshKey((k) => k + 1);
    } finally {
      setGenerating(false);
    }
  };

  const handleRunPipeline = async () => {
    setRunning(true);
    try {
      await runPipeline();
      setRefreshKey((k) => k + 1);
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
