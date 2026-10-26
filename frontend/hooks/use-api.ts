"use client";

// Minimal GET hook: loading / error / data / refetch. No state library.
import { useCallback, useEffect, useRef, useState } from "react";
import { apiFetch } from "@/lib/api";

interface UseApiResult<T> {
  data: T | null;
  error: unknown;
  loading: boolean;
  refetch: () => void;
}

export function useApi<T>(path: string | null): UseApiResult<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(Boolean(path));
  const [tick, setTick] = useState(0);
  const signalRef = useRef<AbortController | null>(null);

  useEffect(() => {
    if (!path) {
      setLoading(false);
      return;
    }
    signalRef.current?.abort();
    const controller = new AbortController();
    signalRef.current = controller;
    setLoading(true);
    setError(null);
    apiFetch<T>(path, { signal: controller.signal })
      .then((result) => {
        if (!controller.signal.aborted) {
          setData(result);
          setLoading(false);
        }
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        setError(err);
        setLoading(false);
      });
    return () => controller.abort();
  }, [path, tick]);

  const refetch = useCallback(() => setTick((t) => t + 1), []);
  return { data, error, loading, refetch };
}
