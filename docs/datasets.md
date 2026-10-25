# Datasets

AgentScope datasets are project-scoped collections of golden agent cases. A dataset is a stable
identity; its contents live in immutable, sequential versions. Experiments reference a specific
`dataset_version_id`, so later edits cannot change the inputs to a historical run.

## Case format

Every case requires `input` and may contain `expected_output`, `expected_tools`, `context`, and
`metadata`. Input, output, and context accept any JSON value. Expected tools is a list of tool
names, and metadata is a JSON object.

Version hashes use canonical JSON over every normalized case plus version metadata. AgentScope
rejects an identical hash within the same dataset. Appending through the UI copies the latest
snapshot, adds the case, and creates a new version; it never modifies an existing row.

## Import formats

- JSON: an array of cases, or an object with an `items` array.
- JSONL: one case object per non-empty line.
- CSV: an `input` header is required. Optional headers are `expected_output`, `expected_tools`,
  `context`, and `metadata`. Structured cells contain JSON; input, output, and context may also be
  plain text.

The API reads at most `AGENTSCOPE_DATASET_MAX_IMPORT_BYTES` and accepts at most
`AGENTSCOPE_DATASET_MAX_ITEMS_PER_VERSION` cases. It decodes and validates every record before
starting version persistence. A malformed row returns a normalized error with the row/line and
field details, and no partial version is committed.

## Local workflow

1. Start the stack and open `/datasets`.
2. Choose an organization and project.
3. Create a dataset with its first manual case.
4. Open the dataset to append a case or import JSON, JSONL, or CSV.
5. Select older versions and verify their content hash and cases remain unchanged.

Dataset reads and writes use centralized `DATASET_READ` and `DATASET_MANAGE` permissions. Every
lookup includes the selected project, preventing access from another tenant even when a dataset
UUID is known.
