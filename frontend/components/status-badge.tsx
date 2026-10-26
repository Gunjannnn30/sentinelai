import { Badge } from "@/components/ui/badge";

const statusVariant: Record<string, "success" | "warning" | "destructive" | "secondary"> = {
  success: "success",
  succeeded: "success",
  completed: "success",
  ok: "success",
  passed: "success",
  allow: "success",
  blocked: "destructive",
  block: "destructive",
  failed: "destructive",
  error: "destructive",
  running: "secondary",
  pending: "secondary",
  warn: "warning",
  warning: "warning",
};

export function StatusBadge({ value, className = "" }: { value: string; className?: string }) {
  const variant = statusVariant[value] ?? "secondary";
  return (
    <Badge variant={variant} className={className}>
      {value}
    </Badge>
  );
}
