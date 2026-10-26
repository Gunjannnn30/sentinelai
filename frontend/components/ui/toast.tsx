"use client";

// Minimal toast system: no dependency, respects reduced motion via CSS.
import * as React from "react";

export interface ToastMessage {
  id: number;
  title: string;
  description?: string;
  variant?: "default" | "destructive";
  /** Backend request id, shown in the footer so users can quote it in support. */
  requestId?: string;
}

interface ToastContextValue {
  toast: (input: Omit<ToastMessage, "id">) => void;
}

const ToastContext = React.createContext<ToastContextValue | null>(null);
let nextId = 1;

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [messages, setMessages] = React.useState<ToastMessage[]>([]);

  const dismiss = React.useCallback((id: number) => {
    setMessages((prev) => prev.filter((m) => m.id !== id));
  }, []);

  const toast = React.useCallback(
    (input: Omit<ToastMessage, "id">) => {
      const id = nextId++;
      setMessages((prev) => [...prev, { ...input, id }]);
      window.setTimeout(() => dismiss(id), 7000);
    },
    [dismiss],
  );

  const value = React.useMemo(() => ({ toast }), [toast]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        className="pointer-events-none fixed bottom-4 right-4 z-[100] flex w-full max-w-sm flex-col gap-2"
        aria-live="polite"
        aria-atomic="false"
      >
        {messages.map((m) => (
          <div
            key={m.id}
            role="status"
            className={`pointer-events-auto rounded-lg border p-4 shadow-lg ${
              m.variant === "destructive"
                ? "border-destructive/40 bg-destructive text-destructive-foreground"
                : "bg-background"
            }`}
          >
            <div className="text-sm font-semibold">{m.title}</div>
            {m.description ? (
              <div className="mt-1 text-sm opacity-90">{m.description}</div>
            ) : null}
            {m.requestId ? (
              <div className="mt-2 font-mono text-[11px] opacity-70">
                request_id: {m.requestId}
              </div>
            ) : null}
            <button
              type="button"
              onClick={() => dismiss(m.id)}
              className="mt-2 text-xs underline opacity-70 hover:opacity-100"
            >
              Dismiss
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const ctx = React.useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used inside <ToastProvider>");
  return ctx;
}
