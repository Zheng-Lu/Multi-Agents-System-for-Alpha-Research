export interface ModelConfig {
  provider: string;
  model: string;
  max_output_tokens?: number;
}
export interface Assignments {
  default: ModelConfig;
  roles: Record<string, ModelConfig>;
}
export interface ModelEntry {
  provider: string;
  model: string;
  smoke_tested: boolean;
  notes: string;
  capabilities: { tool_calling: boolean; structured_output: boolean };
  pricing: null | { input_per_million: number; output_per_million: number; effective_date: string };
}
export interface Pattern {
  id: string;
  name: string;
  available: boolean;
  mechanism: string;
}
export interface Run {
  run_id: string;
  status: string;
  error: string | null;
  request: {
    mode: string;
    pattern: string;
    models: Assignments;
    budget: Budget;
    experiment?: { case_id: string; parallel_tools: boolean; simulated_latency_ms: number } | null;
  };
  metrics: {
    model_calls: number;
    tool_calls: number;
    input_tokens: number;
    output_tokens: number;
    estimated_cost_usd: number | null;
    cost_complete: boolean;
    latency_ms: number;
    coordination_events: number;
    peak_input_tokens?: number | null;
    peak_input_tokens_by_agent?: Record<string, number | null>;
    usage_complete?: boolean;
  };
}
export interface Trace {
  seq: number;
  event_id: string;
  event_type: string;
  agent_id: string | null;
  timestamp: string;
  parent_event_id: string | null;
  output_ref: string | null;
  provider_id: string | null;
  model_id: string | null;
  status: string;
  metadata: Record<string, unknown>;
}
export interface Result {
  config: { factor: string };
  net_return: number;
  test_ic: number;
  gross_return: number;
  max_drawdown: number;
  leakage_detected: boolean | null;
  methodology: string;
  limitations: string[];
}
export interface Finding {
  finding_id: string;
  agent_id: string;
  hypothesis: { factor: string; rationale: string };
  result: Result;
  evidence: { artifact_id: string }[];
  status: string;
  candidate_id?: string | null;
  version?: number;
  supersedes_finding_id?: string | null;
}
export interface Report {
  title: string;
  summary: string;
  verdict: string;
  disclaimer: string;
  ranked_candidates: string[];
  findings: Finding[];
  verifications: { verdict: string; feedback: string[]; attempt: number }[];
  reviews?: { candidate_id: string; version: number; verdict: string; observations: string[] }[];
  agent_proposal?: { finding_ids: string[]; rationale: string } | null;
  publication?: Publication[];
  published_recommendations?: string[];
  blocked_recommendations?: string[];
}
export interface Publication {
  finding_id: string;
  state: string;
  version: number;
}
export interface Budget {
  max_cost_usd: number;
  max_calls_per_run: number;
  max_tokens_per_run: number;
  max_calls_per_agent: number;
  max_tokens_per_agent: number;
  max_steps: number;
  max_runtime_seconds: number;
  max_retries: number;
}
export interface CasePreset {
  case_id: string;
  name: string;
  prompt: string;
  candidates: string[];
  description: string;
}
export interface ComparisonRow {
  run: Run;
  label: string;
  evidence_coverage: number;
  review_caught_issue: boolean | null;
  repair_completed: boolean | null;
  top_proposed_validity: string;
  published_count: number | null;
  blocked_count: number | null;
}
export interface Comparison {
  comparison_id: string;
  case_id: string;
  created_at: string;
  status: string;
  request: { budget: Budget; simulated_latency_ms: number };
  case: CasePreset;
  run_ids: string[];
  rows: ComparisonRow[];
  takeaways: string[];
}
export interface Artifact {
  artifact_id: string;
  agent_id: string;
  kind: string;
  payload: Record<string, unknown>;
}
