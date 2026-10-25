export type QualityMetric =
  | "pass_rate"
  | "average_correctness"
  | "hallucination_rate"
  | "tool_accuracy"
  | "average_latency_ms"
  | "p50_latency_ms"
  | "p95_latency_ms"
  | "p99_latency_ms"
  | "average_cost"
  | "total_cost"
  | "token_usage";

export type QualityGateRule = {
  metric: QualityMetric;
  constraint: "max_regression" | "max_increase";
  threshold: number;
  comparison: "absolute" | "relative";
  severity: "FAIL" | "WARN";
};

export type QualityGate = {
  id: string;
  project_id: string;
  name: string;
  description: string | null;
  rules: QualityGateRule[];
  created_at: string;
  updated_at: string;
};

export type MetricComparison = {
  metric: QualityMetric;
  baseline: number;
  candidate: number;
  absolute_delta: number;
  percentage_delta: number | null;
  direction: "UP" | "DOWN" | "UNCHANGED";
  classification: "IMPROVEMENT" | "REGRESSION" | "UNCHANGED";
};

export type GateFinding = {
  metric: QualityMetric;
  message: string;
  observed: number;
  threshold: number;
  comparison: "absolute" | "relative";
};

export type QualityGateResult = {
  id: string;
  quality_gate_id: string;
  baseline_experiment_id: string;
  candidate_experiment_id: string;
  status: "PASSED" | "PASSED_WITH_WARNINGS" | "FAILED";
  comparisons: MetricComparison[];
  violations: GateFinding[];
  warnings: GateFinding[];
  evaluated_at: string;
};

export const QUALITY_METRICS: { value: QualityMetric; label: string }[] = [
  { value: "pass_rate", label: "Pass rate" },
  { value: "average_correctness", label: "Average correctness" },
  { value: "hallucination_rate", label: "Hallucination rate" },
  { value: "tool_accuracy", label: "Tool accuracy" },
  { value: "average_latency_ms", label: "Average latency" },
  { value: "p50_latency_ms", label: "P50 latency" },
  { value: "p95_latency_ms", label: "P95 latency" },
  { value: "p99_latency_ms", label: "P99 latency" },
  { value: "average_cost", label: "Average cost" },
  { value: "total_cost", label: "Total cost" },
  { value: "token_usage", label: "Token usage" },
];
