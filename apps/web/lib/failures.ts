export type FailureRecord = {
  id: string;
  project_id: string;
  trace_id: string;
  failure_type: string;
  title: string;
  document: string;
  evidence: Record<string, unknown>;
  agent_version: string | null;
  detected_at: string;
};

export type SimilarFailure = { failure: FailureRecord; similarity: number };

export type FailureCluster = {
  id: string;
  project_id: string;
  title: string;
  description: string;
  probable_cause: string | null;
  suggested_action: string | null;
  summary_source: string;
  size: number;
  failure_percentage: string;
  first_seen: string;
  last_seen: string;
  representative_failure_ids: string[];
  failure_ids: string[];
};
