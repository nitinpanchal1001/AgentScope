export type AlertMetric =
  | "ERROR_RATE"
  | "HALLUCINATION_RATE"
  | "P95_LATENCY_MS"
  | "AVERAGE_COST"
  | "EVALUATION_SCORE"
  | "TOOL_FAILURE_RATE";

export type AlertRule = {
  id: string;
  project_id: string;
  name: string;
  environment_id: string | null;
  metric: AlertMetric;
  operator:
    | "GREATER_THAN"
    | "GREATER_THAN_OR_EQUAL"
    | "LESS_THAN"
    | "LESS_THAN_OR_EQUAL";
  threshold: string;
  window_minutes: number;
  severity: "INFO" | "WARNING" | "CRITICAL";
  enabled: boolean;
  channel: "WEBHOOK" | "EMAIL";
  channel_target: string;
  cooldown_minutes: number;
};

export type AlertEvent = {
  id: string;
  rule_name: string;
  metric: AlertMetric;
  observed_value: string;
  threshold: string;
  severity: "INFO" | "WARNING" | "CRITICAL";
  channel: "WEBHOOK" | "EMAIL";
  status: "PENDING" | "DELIVERED" | "FAILED";
  triggered_at: string;
  delivery_attempts: number;
  last_error: string | null;
};
