import { Badge } from "@/components/ui/badge";

/**
 * The backend never fabricates data, but responses can be flagged
 * `is_demo_data` / `demo` or come from the built-in "MOCK PROVIDER". Any such
 * payload must be visibly labelled.
 */
export function DemoBadge({
  isDemo,
  className = "",
}: {
  isDemo: boolean;
  className?: string;
}) {
  if (!isDemo) return null;
  return (
    <Badge variant="warning" className={className}>
      Simulated / demo data
    </Badge>
  );
}
