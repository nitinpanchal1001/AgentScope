export type ExperimentStatus =
  "PENDING" | "RUNNING" | "COMPLETED" | "FAILED" | "CANCELLED";

export type Experiment = {
  id: string;
  organization_id: string;
  project_id: string;
  environment_id: string;
  dataset_version_id: string;
  dataset_name: string;
  dataset_version: number;
  name: string;
  description: string | null;
  status: ExperimentStatus;
  agent: {
    type: "http";
    endpoint: string;
    timeout_seconds: number;
    headers_from_env: Record<string, string>;
    provider: string | null;
    model: string | null;
    prompt_version: string | null;
    temperature: number | null;
    parameters: Record<string, unknown>;
  };
  evaluator_version_ids: string[];
  max_concurrency: number;
  total_cases: number;
  completed_cases: number;
  passed_cases: number;
  failed_cases: number;
  metrics: Record<string, number | string>;
  cancel_requested: boolean;
  error_message: string | null;
  created_at: string;
  updated_at: string;
  started_at: string | null;
  completed_at: string | null;
};

export type ExperimentRun = {
  id: string;
  experiment_id: string;
  dataset_item_id: string;
  trace_id: string | null;
  ordinal: number;
  status: string;
  input: unknown;
  expected_output: unknown;
  expected_tools: string[];
  output: unknown;
  latency_ms: number | null;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  total_cost: string;
  evaluation_score: string | null;
  passed: boolean | null;
  error_type: string | null;
  error_message: string | null;
};

export type ExperimentRunPage = {
  items: ExperimentRun[];
  page: number;
  page_size: number;
  total_items: number;
  total_pages: number;
  has_next: boolean;
  has_previous: boolean;
};
