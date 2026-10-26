// Types mirroring the backend schemas in backend/app/schemas/common.py.
// Only fields that exist server-side are declared here — never invent one.

// ---------- error envelope (backend/app/core/errors.py) ----------
export interface ApiFieldError {
  field: string;
  message: string;
  type?: string;
}
export interface Api422Details {
  errors: ApiFieldError[];
}
export interface ApiErrorBody {
  error?: {
    code?: string;
    message?: string;
    details?: unknown;
    request_id?: string;
  };
}

export type Role = "owner" | "admin" | "developer" | "viewer";

export interface UserOut {
  id: string;
  email: string;
  full_name: string;
}

export interface OrgOut {
  id: string;
  name: string;
  slug: string;
  retention_days: number;
  rate_limit_per_minute: number;
  budget_monthly_usd: string | null;
}

/** POST /auth/register|login, GET /auth/me, POST /auth/switch-org */
export interface MeOut {
  user: UserOut;
  org: OrgOut;
  role: Role;
  csrf_token: string;
  available_providers: Record<string, boolean>;
}

export interface ModelOut {
  id: string;
  model_key: string;
  display_name: string;
  provider: string;
  provider_kind: string;
  capabilities: string[];
  context_window: number | null;
  input_cost_per_1m: number | null;
  output_cost_per_1m: number | null;
  pricing_source: string | null;
  enabled: boolean;
  is_demo_data: boolean;
}

export type ChatRole = "system" | "user" | "assistant";

export interface ChatMessage {
  role: ChatRole;
  content: string;
}

export interface SecurityFinding {
  category: string;
  severity: string;
  rule_name: string;
  action_taken: string;
  detail: string;
  masked_types: string[];
}

export interface UsageOut {
  prompt_tokens: number | null;
  completion_tokens: number | null;
  total_tokens: number | null;
  estimated_cost_usd: number | null;
  cost_pricing_source: string | null;
  pricing_available: boolean;
}

/** POST /chat/completions request body (backend/app/schemas/common.py). */
export interface ChatCompletionIn {
  messages: ChatMessage[];
  model?: string | null;
  project_id?: string | null;
  max_tokens?: number | null;
  temperature?: number | null;
  dry_run?: boolean;
}

/** The gateway always answers HTTP 200 with this body. */
export interface ChatCompletionOut {
  request_id: string;
  status: "success" | "blocked" | "error";
  policy_outcome: "allow" | "warn" | "block";
  model: string | null;
  provider: string | null;
  content: string | null;
  latency_ms: number | null;
  usage: UsageOut;
  findings: SecurityFinding[];
  route_explanation: string | null;
  error: {
    category?: string;
    retryable?: boolean;
    policy_outcome?: string;
    blocked_reason?: string | null;
    message?: string;
    [key: string]: unknown;
  } | null;
  demo: boolean;
}

export interface RequestOut {
  id: string;
  org_id: string;
  project_id: string | null;
  status: string;
  policy_outcome: string;
  provider_kind: string | null;
  model_key: string | null;
  route_explanation: string | null;
  latency_ms: number | null;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  total_tokens: number | null;
  estimated_cost_usd: number | null;
  cost_pricing_source: string | null;
  error_category: string | null;
  error_message: string | null;
  blocked_reason: string | null;
  prompt_chars: number;
  response_chars: number;
  has_content: boolean;
  actor_email: string | null;
  created_at: string;
  is_demo_data: boolean;
}

export interface SecurityEventOut {
  id: string;
  request_id: string | null;
  category: string;
  severity: string;
  action_taken: string;
  rule_name: string;
  detail: string;
  masked_types: string[];
  created_at: string;
}

export interface RequestDetailOut extends RequestOut {
  security_events: SecurityEventOut[];
}

export interface RequestPage {
  items: RequestOut[];
  total: number;
  page: number;
  page_size: number;
}

export type PolicyField =
  | "prompt_injection_category"
  | "pii_type"
  | "prompt_contains"
  | "model"
  | "provider"
  | "message_role"
  | "project_id"
  | "actor_role"
  | "prompt_length_over"
  | "response_contains";

export type PolicyOp = "equals" | "contains" | "in" | "gte" | "matches";

export interface PolicyCondition {
  field: PolicyField;
  op: PolicyOp;
  value: string | number | null;
}

export interface PolicyIn {
  name: string;
  description: string;
  enabled: boolean;
  severity: "low" | "medium" | "high" | "critical";
  action: "allow" | "warn" | "mask" | "block";
  scope: "organization" | "project" | "role";
  scope_role: Role | null;
  project_id: string | null;
  conditions: PolicyCondition[];
}

export interface PolicyOut extends PolicyIn {
  id: string;
  org_id: string;
  conditions: PolicyCondition[];
  version: number;
  created_at: string;
  updated_at: string;
}

export interface PolicyPreviewOut {
  decision: {
    matched: boolean;
    action: string;
    severity: string;
    matched_conditions: Record<string, unknown>[];
    explanation: string;
  };
  injection: Record<string, unknown>;
  pii: Record<string, unknown>;
}

export interface OverviewOut {
  total_requests: number;
  successful_requests: number;
  blocked_requests: number;
  error_requests: number;
  avg_latency_ms: number | null;
  estimated_spend_usd: number | null;
  spend_pricing_available: boolean;
  policy_pass_rate: number | null;
  unique_models: number;
  demo_data_included: boolean;
  series: Array<{
    date: string;
    total: number;
    success: number;
    blocked: number;
    error: number;
  }>;
}

export interface CostBreakdownRow {
  key: string;
  requests: number;
  tokens: number;
  cost_usd: number | null;
  pricing_available: boolean;
}

export interface AnalyticsOut {
  by_provider: CostBreakdownRow[];
  by_model: CostBreakdownRow[];
  daily: Array<{
    date: string;
    cost_usd: number | null;
    pricing_available: boolean;
    tokens: number;
    requests: number;
  }>;
  budget_monthly_usd: string | null;
  month_to_date_usd: number | null;
  pricing_source_note: string;
}

export interface SecurityAnalyticsOut {
  blocked_requests: number;
  injection_detections: number;
  pii_masking_events: number;
  policy_violations: number;
  by_severity: Record<string, number>;
  top_rules: Array<{ rule: string; count: number; severity: string }>;
  series: Array<{
    date: string;
    prompt_injection: number;
    pii_detected: number;
    policy_violation: number;
  }>;
}

export interface ModelAnalyticsRow {
  model_key: string;
  provider_kind: string;
  requests: number;
  errors: number;
  error_rate: number;
  avg_latency_ms: number | null;
  p95_latency_ms: number | null;
  total_tokens: number;
  est_cost_usd: number | null;
  pricing_available: boolean;
}

export interface ModelAnalyticsOut {
  rows: ModelAnalyticsRow[];
  demo_data_included: boolean;
}

export interface EvalCaseOut {
  id: string;
  prompt: string;
  expected: string;
  reference: string;
  tags: string[];
}

export interface EvalDatasetOut {
  id: string;
  name: string;
  description: string;
  is_synthetic: boolean;
  created_at: string;
  case_count: number;
}

export interface EvalResultOut {
  id: string;
  case_id: string;
  model_key: string;
  status: string;
  output: string | null;
  error_category: string | null;
  latency_ms: number | null;
  total_tokens: number | null;
  estimated_cost_usd: number | null;
  metrics: Record<
    string,
    { score: number | null; value?: unknown; method?: string; note?: string }
  >;
}

export interface EvalRunSummaryModel {
  cases: number;
  avg_score: number | null;
  completion_rate: number | null;
  errors: number;
  avg_latency_ms: number | null;
  total_cost_usd: number | null;
  cost_available: boolean;
}

export interface EvalRunOut {
  id: string;
  dataset_id: string;
  name: string;
  model_keys: string[];
  status: string;
  baseline_run_id: string | null;
  started_at: string | null;
  finished_at: string | null;
  summary: {
    models?: Record<string, EvalRunSummaryModel>;
    judge_enabled?: boolean;
    scoring_note?: string;
    regression?: {
      available: boolean;
      note?: string;
      models?: Record<
        string,
        {
          delta: number | null;
          baseline?: number;
          current?: number;
          regressed?: boolean;
          note?: string;
        }
      >;
    };
    [key: string]: unknown;
  };
  created_at: string;
}

export interface EvalRunDetailOut extends EvalRunOut {
  results: EvalResultOut[];
}

export interface ProviderOut {
  id: string;
  kind: string;
  name: string;
  base_url: string;
  secret_ref: string;
  enabled: boolean;
  configured: boolean;
  model_count: number;
}

export interface ProviderIn {
  kind: "openai" | "anthropic" | "gemini" | "ollama" | "mock";
  name: string;
  base_url: string;
  secret_ref: string;
  enabled: boolean;
  api_key?: string | null;
}

/** GET /admin/models — plain dict rows, richer than the public ModelOut. */
export interface AdminModelRow {
  id: string;
  provider_id: string;
  provider: string;
  model_key: string;
  display_name: string;
  capabilities: string[];
  context_window: number | null;
  max_output_tokens: number | null;
  input_cost_per_1m: number | null;
  output_cost_per_1m: number | null;
  pricing_source: string | null;
  priority: number;
  latency_class: string;
  enabled: boolean;
  is_demo_data: boolean;
}

export interface MemberOut {
  user_id: string;
  email: string;
  full_name: string;
  role: Role;
  teams: string[];
}

export interface TeamOut {
  id: string;
  name: string;
  member_count: number;
}

export interface ProjectOut {
  id: string;
  org_id: string;
  name: string;
  slug: string;
  description: string;
  is_default: boolean;
}

export interface OrgSettings {
  name: string;
  slug: string;
  retention_days: number;
  rate_limit_per_minute: number;
  budget_monthly_usd: string | null;
}

export interface AuditLogOut {
  id: string;
  seq: number;
  event_type: string;
  actor_email: string | null;
  resource_type: string;
  resource_id: string | null;
  request_id: string | null;
  outcome: string;
  detail: Record<string, unknown>;
  prev_hash: string;
  hash: string;
  created_at: string;
}

export interface AuditPage {
  total: number;
  limit: number;
  offset: number;
  items: AuditLogOut[];
}

export interface AuditVerifyOut {
  ok: boolean;
  checked: number;
  first_bad_seq: number | null;
  message: string;
}

export interface ReadyOut {
  status: string;
  database: string;
  checks: Record<string, unknown>;
}
