// Formatting helpers. Money comes from the backend as strings; when pricing is
// unavailable the API sends null — we render "Unavailable", never a guess.

export const UNAVAILABLE = "Unavailable";

export function money(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return UNAVAILABLE;
  const n = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(n)) return UNAVAILABLE;
  return `$${n.toLocaleString("en-US", {
    minimumFractionDigits: n < 1 && n > 0 ? 6 : 2,
    maximumFractionDigits: n < 1 && n > 0 ? 6 : 2,
  })}`;
}

/** Compact money for chart axes: $1.2k / $3.4M. */
export function moneyCompact(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return UNAVAILABLE;
  const n = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(n)) return UNAVAILABLE;
  if (Math.abs(n) >= 1_000_000) return `$${(n / 1_000_000).toFixed(1)}M`;
  if (Math.abs(n) >= 1_000) return `$${(n / 1_000).toFixed(1)}k`;
  return money(n);
}

export function ms(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return UNAVAILABLE;
  if (value >= 1000) return `${(value / 1000).toFixed(2)}s`;
  return `${Math.round(value)}ms`;
}

export function pct(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return UNAVAILABLE;
  return `${(value * 100).toFixed(digits)}%`;
}

export function num(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return UNAVAILABLE;
  return value.toLocaleString("en-US");
}

export function dateTime(value: string | null | undefined): string {
  if (!value) return UNAVAILABLE;
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString("en-US", {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function timeAgo(value: string | null | undefined): string {
  if (!value) return UNAVAILABLE;
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  const diff = Date.now() - d.getTime();
  const mins = Math.round(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  if (days < 30) return `${days}d ago`;
  return dateTime(value);
}

export function truncate(value: string | null | undefined, max = 80): string {
  if (!value) return "";
  return value.length > max ? `${value.slice(0, max)}…` : value;
}
