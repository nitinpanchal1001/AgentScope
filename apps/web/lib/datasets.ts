export type DatasetVersion = {
  id: string;
  dataset_id: string;
  version: number;
  content_hash: string;
  item_count: number;
  metadata: Record<string, unknown>;
  created_at: string;
};

export type Dataset = {
  id: string;
  organization_id: string;
  project_id: string;
  name: string;
  description: string | null;
  created_at: string;
  updated_at: string;
  latest_version: DatasetVersion;
  versions: DatasetVersion[];
};

export type DatasetItem = {
  id: string;
  dataset_version_id: string;
  ordinal: number;
  input: unknown;
  expected_output: unknown;
  expected_tools: string[];
  context: unknown;
  metadata: Record<string, unknown>;
};

export type DatasetVersionPage = {
  dataset_id: string;
  dataset_name: string;
  version: DatasetVersion;
  items: DatasetItem[];
  pagination: {
    page: number;
    page_size: number;
    total_items: number;
    total_pages: number;
    has_next: boolean;
    has_previous: boolean;
  };
};

export function parseFlexibleValue(value: string): unknown {
  const trimmed = value.trim();
  if (!trimmed) return null;
  try {
    return JSON.parse(trimmed) as unknown;
  } catch {
    return trimmed;
  }
}

export function parseTools(value: string): string[] {
  return value
    .split(",")
    .map((tool) => tool.trim())
    .filter(Boolean);
}
