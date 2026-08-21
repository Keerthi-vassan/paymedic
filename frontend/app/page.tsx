"use client";

import { useEffect, useState } from "react";

type HealthStatus = "checking" | "ok" | "error";

export default function Home() {
  const [status, setStatus] = useState<HealthStatus>("checking");

  useEffect(() => {
    const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

    fetch(`${apiBaseUrl}/health`)
      .then((res) => {
        if (!res.ok) throw new Error(`status ${res.status}`);
        return res.json();
      })
      .then(() => setStatus("ok"))
      .catch(() => setStatus("error"));
  }, []);

  const statusText: Record<HealthStatus, string> = {
    checking: "Checking backend connection...",
    ok: "Backend connected",
    error: "Backend unreachable",
  };

  const statusColor: Record<HealthStatus, string> = {
    checking: "bg-zinc-400",
    ok: "bg-green-500",
    error: "bg-red-500",
  };

  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-zinc-50 font-sans dark:bg-black">
      <h1 className="text-2xl font-semibold text-black dark:text-zinc-50">
        Paymedic
      </h1>
      <div className="flex items-center gap-2">
        <span className={`h-2.5 w-2.5 rounded-full ${statusColor[status]}`} />
        <span className="text-sm text-zinc-600 dark:text-zinc-400">
          {statusText[status]}
        </span>
      </div>
    </div>
  );
}
