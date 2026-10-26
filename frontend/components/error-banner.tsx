"use client";

import { ApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";

export function errorText(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "Something went wrong.";
}

export function requestIdOf(error: unknown): string | undefined {
  return error instanceof ApiError && error.requestId ? error.requestId : undefined;
}

/** Inline error banner with request_id (required for support/debugging). */
export function ErrorBanner({
  error,
  onRetry,
  className = "",
}: {
  error: unknown;
  onRetry?: () => void;
  className?: string;
}) {
  const requestId = requestIdOf(error);
  return (
    <div
      role="alert"
      className={`rounded-lg border border-destructive/40 bg-destructive/10 p-4 ${className}`}
    >
      <p className="text-sm font-medium text-destructive">{errorText(error)}</p>
      {error instanceof ApiError && error.retryAfter ? (
        <p className="mt-1 text-xs text-muted-foreground">
          Retry after {error.retryAfter}.
        </p>
      ) : null}
      {requestId ? (
        <p className="mt-2 font-mono text-[11px] text-muted-foreground">
          request_id: {requestId}
        </p>
      ) : null}
      {onRetry ? (
        <Button variant="outline" size="sm" className="mt-3" onClick={onRetry}>
          Retry
        </Button>
      ) : null}
    </div>
  );
}
