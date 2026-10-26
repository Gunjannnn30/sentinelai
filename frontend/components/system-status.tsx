"use client";

// Polls the root /ready endpoint (mounted in backend/app/main.py, not under
// /api/v1) and renders a small health chip.
import { useEffect, useState } from "react";
import { API_BASE } from "@/lib/api";

interface ReadyOut {
  status: string;
  database: string;
  checks: Record<string, string>;
}

type State = "checking" | "ready" | "degraded" | "down";

export function SystemStatus() {
  const [state, setState] = useState<State>("checking");
  const [detail, setDetail] = useState<string>("");

  useEffect(() => {
    let cancelled = false;
    const check = async () => {
      try {
        const res = await fetch(`${API_BASE}/ready`, { credentials: "include" });
        const body = (await res.json()) as ReadyOut;
        if (cancelled) return;
        if (res.ok && body.status === "ready") {
          setState("ready");
          setDetail(`database: ${body.database}`);
        } else {
          setState("degraded");
          setDetail(`status: ${body.status ?? "unknown"}`);
        }
      } catch {
        if (!cancelled) {
          setState("down");
          setDetail("API unreachable");
        }
      }
    };
    void check();
    const timer = window.setInterval(check, 30_000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  const styles: Record<State, string> = {
    checking: "bg-muted text-muted-foreground",
    ready: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300",
    degraded: "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300",
    down: "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300",
  };

  const labels: Record<State, string> = {
    checking: "Checking…",
    ready: "Operational",
    degraded: "Degraded",
    down: "Offline",
  };

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ${styles[state]}`}
      title={detail}
    >
      <span
        aria-hidden="true"
        className={`h-1.5 w-1.5 rounded-full ${
          state === "ready"
            ? "bg-emerald-500"
            : state === "degraded"
              ? "bg-amber-500"
              : state === "down"
                ? "bg-red-500"
                : "bg-muted-foreground"
        }`}
      />
      {labels[state]}
    </span>
  );
}
