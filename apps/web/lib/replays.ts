export type ReplayStatus =
  "PENDING" | "RUNNING" | "EVALUATING" | "COMPLETED" | "FAILED";

export type TraceReplay = {
  id: string;
  project_id: string;
  environment_id: string;
  original_trace_id: string;
  replay_trace_id: string | null;
  status: ReplayStatus;
  agent: {
    endpoint: string;
    timeout_seconds: number;
    headers_from_env: Record<string, string>;
  };
  overrides: Record<string, unknown>;
  effective_configuration: Record<string, unknown>;
  error_type: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
};

export type ReplaySnapshot = {
  trace_id: string;
  output: unknown;
  evaluation_score: string | null;
  latency_ms: number | null;
  total_cost: string;
  total_tokens: number;
  tool_sequence: string[];
  span_structure: {
    ordinal: number;
    parent_ordinal: number | null;
    type: string;
    name: string;
    status: string;
  }[];
};

export type ReplayComparison = {
  replay_id: string;
  original: ReplaySnapshot;
  replay: ReplaySnapshot;
  differences: {
    output_changed: boolean;
    evaluation_score_delta: number | null;
    latency_ms_delta: number | null;
    total_cost_delta: number;
    total_tokens_delta: number;
    tool_sequence_changed: boolean;
    span_structure_changed: boolean;
  };
};
