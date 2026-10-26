"use client";

// Tiny mutation helper: tracks pending state and the last error so callers can
// render the error envelope (including request_id) without boilerplate.
import { useCallback, useState } from "react";
import { apiFetch } from "@/lib/api";

export function useMutation<TInput, TOutput>(
  path: string | ((input: TInput) => string),
  method: "POST" | "PUT" | "PATCH" | "DELETE" = "POST",
) {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const mutate = useCallback(
    async (input: TInput): Promise<TOutput | null> => {
      setPending(true);
      setError(null);
      try {
        const url = typeof path === "function" ? path(input) : path;
        const result = await apiFetch<TOutput>(url, {
          method,
          body: input === undefined ? undefined : input,
        });
        return result;
      } catch (err) {
        setError(err);
        return null;
      } finally {
        setPending(false);
      }
    },
    [path, method],
  );

  return { mutate, pending, error, reset: () => setError(null) };
}
