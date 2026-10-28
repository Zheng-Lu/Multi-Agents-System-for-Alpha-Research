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
  request: { mode: string; pattern: string; models: Assignments; budget: { max_cost_usd: number } };
  metrics: {
    model_calls: number;
    tool_calls: number;
    input_tokens: number;
    output_tokens: number;
    estimated_cost_usd: number | null;
    cost_complete: boolean;
    latency_ms: number;
    coordination_events: number;
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
  leakage_detected: boolean;
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
}
export interface Report {
  title: string;
  summary: string;
  verdict: string;
  disclaimer: string;
  ranked_candidates: string[];
  findings: Finding[];
  verifications: { verdict: string; feedback: string[]; attempt: number }[];
}
export interface Artifact {
  artifact_id: string;
  agent_id: string;
  kind: string;
  payload: Record<string, unknown>;
}
