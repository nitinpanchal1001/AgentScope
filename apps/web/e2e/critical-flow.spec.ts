import { expect, test, type APIRequestContext } from "@playwright/test";

const apiUrl = (
  process.env.PLAYWRIGHT_API_URL ?? "http://localhost:8000"
).replace(/\/$/, "");

type DatasetResponse = { latest_version: { id: string } };
type EvaluatorResponse = { versions: { id: string }[] };
type EnvironmentResponse = { id: string; slug: string };
type ExperimentResponse = {
  id: string;
  status: string;
  error_message?: string | null;
};
type GateResponse = { id: string };

async function api<T>(
  request: APIRequestContext,
  token: string,
  method: "get" | "post",
  path: string,
  data?: unknown,
): Promise<T> {
  const response = await request[method](`${apiUrl}${path}`, {
    headers: { Authorization: `Bearer ${token}` },
    data,
  });
  expect(
    response.ok(),
    `${method.toUpperCase()} ${path}: ${await response.text()}`,
  ).toBeTruthy();
  return response.json() as Promise<T>;
}

async function waitForExperiment(
  request: APIRequestContext,
  token: string,
  projectId: string,
  experimentId: string,
): Promise<ExperimentResponse> {
  for (let attempt = 0; attempt < 60; attempt += 1) {
    const experiment = await api<ExperimentResponse>(
      request,
      token,
      "get",
      `/api/v1/projects/${projectId}/experiments/${experimentId}`,
    );
    if (experiment.status === "COMPLETED") return experiment;
    if (["FAILED", "CANCELLED"].includes(experiment.status)) {
      throw new Error(
        `Experiment stopped with ${experiment.status}: ${experiment.error_message}`,
      );
    }
    await new Promise((resolve) => setTimeout(resolve, 1_000));
  }
  throw new Error(
    `Experiment ${experimentId} did not complete within 60 seconds`,
  );
}

test("register to quality gate critical path", async ({ page, request }) => {
  const suffix = `${Date.now()}-${Math.floor(Math.random() * 10_000)}`;
  const email = `e2e-${suffix}@example.com`;
  const password = "correct-horse-42";

  await page.goto("/register");
  await page.getByLabel("Name").fill("E2E Operator");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  const registrationResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/v1/auth/register") &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Create account" }).click();
  const registration = await (await registrationResponse).json();
  const token = registration.access_token as string;
  await expect(page).toHaveURL(/\/dashboard$/);

  const organizationResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/v1/organizations") &&
      response.request().method() === "POST",
  );
  await page.getByPlaceholder("Acme AI").fill(`E2E Org ${suffix}`);
  await page.getByRole("button", { name: "Create organization" }).click();
  const organization = await (await organizationResponse).json();
  await expect(
    page.getByRole("heading", { name: `E2E Org ${suffix}`, exact: true }),
  ).toBeVisible();

  const projectResponse = page.waitForResponse(
    (response) =>
      response.url().includes("/projects") &&
      response.request().method() === "POST",
  );
  await page.getByPlaceholder("Support agent").fill(`E2E Agent ${suffix}`);
  await page.getByRole("button", { name: "Create project" }).click();
  const project = await (await projectResponse).json();
  const projectId = project.id as string;
  await expect(
    page.getByText(`E2E Agent ${suffix}`, { exact: true }),
  ).toBeVisible();

  const keyResponsePromise = page.waitForResponse(
    (response) =>
      response.url().includes("/api-keys") &&
      response.request().method() === "POST",
  );
  await page.getByPlaceholder("Local SDK").fill("E2E SDK");
  await page.getByRole("button", { name: "Issue key" }).click();
  const keyResponse = await (await keyResponsePromise).json();
  await expect(page.getByText("Copy now — shown once")).toBeVisible();

  const now = new Date();
  const traceId = `e2e-trace-${suffix}`;
  const ingest = await request.post(`${apiUrl}/v1/ingest/batch`, {
    headers: { Authorization: `Bearer ${keyResponse.key}` },
    data: {
      sdk: { name: "playwright", version: "1" },
      events: [
        {
          event_id: crypto.randomUUID(),
          timestamp: now.toISOString(),
          type: "TRACE_START",
          trace_id: traceId,
          payload: { name: "e2e-agent-trace", input: { message: "hello" } },
        },
        {
          event_id: crypto.randomUUID(),
          timestamp: new Date(now.getTime() + 5).toISOString(),
          type: "TRACE_END",
          trace_id: traceId,
          payload: { status: "SUCCESS", output: { message: "hello" } },
        },
      ],
    },
  });
  expect(ingest.status()).toBe(202);

  const dataset = await api<DatasetResponse>(
    request,
    token,
    "post",
    `/api/v1/projects/${projectId}/datasets`,
    {
      name: `E2E Golden ${suffix}`,
      items: [
        {
          input: { intent: "cancel_order", order_id: "A100" },
          expected_output: {
            message: "Order A100 cannot be cancelled after shipping.",
            order_id: "A100",
            status: "shipped",
          },
          expected_tools: ["cancel_order"],
        },
      ],
    },
  );
  const evaluator = await api<EvaluatorResponse>(
    request,
    token,
    "post",
    `/api/v1/projects/${projectId}/evaluators`,
    {
      name: `E2E Exact ${suffix}`,
      version: { type: "EXACT_MATCH", configuration: {}, threshold: "1" },
    },
  );
  const environments = await api<EnvironmentResponse[]>(
    request,
    token,
    "get",
    `/api/v1/projects/${projectId}/environments`,
  );
  const environmentId = environments.find(
    (item) => item.slug === "development",
  )!.id;
  const datasetVersionId = dataset.latest_version.id;
  const evaluatorVersionId = evaluator.versions[0].id;

  const createExperiment = async (name: string, promptVersion: string) =>
    api<ExperimentResponse>(
      request,
      token,
      "post",
      `/api/v1/projects/${projectId}/experiments`,
      {
        name,
        dataset_version_id: datasetVersionId,
        environment_id: environmentId,
        agent: {
          endpoint: "http://demo-agent:8090/invoke",
          prompt_version: promptVersion,
        },
        evaluator_version_ids: [evaluatorVersionId],
        max_concurrency: 1,
      },
    );

  const baseline = await createExperiment(
    `E2E Baseline ${suffix}`,
    "support-v2",
  );
  const candidate = await createExperiment(
    `E2E Candidate ${suffix}`,
    "support-v1",
  );
  await api(
    request,
    token,
    "post",
    `/api/v1/projects/${projectId}/experiments/${baseline.id}/start`,
  );
  await api(
    request,
    token,
    "post",
    `/api/v1/projects/${projectId}/experiments/${candidate.id}/start`,
  );
  await waitForExperiment(request, token, projectId, baseline.id);
  await waitForExperiment(request, token, projectId, candidate.id);

  await api(
    request,
    token,
    "post",
    `/api/v1/projects/${projectId}/experiments/${baseline.id}/baseline`,
  );
  const comparison = await api<Array<Record<string, unknown>>>(
    request,
    token,
    "get",
    `/api/v1/projects/${projectId}/experiments/${candidate.id}/comparison`,
  );
  expect(comparison.some((item) => item.metric === "pass_rate")).toBeTruthy();

  const gate = await api<GateResponse>(
    request,
    token,
    "post",
    `/api/v1/projects/${projectId}/quality-gates`,
    {
      name: `E2E Release Gate ${suffix}`,
      rules: [
        {
          metric: "pass_rate",
          constraint: "max_regression",
          threshold: 0,
          comparison: "absolute",
          severity: "FAIL",
        },
      ],
    },
  );
  const gateResult = await api<Record<string, unknown>>(
    request,
    token,
    "post",
    `/api/v1/projects/${projectId}/quality-gates/${gate.id}/evaluate`,
    { candidate_experiment_id: candidate.id },
  );
  expect(gateResult.status).toBe("FAILED");

  await page.goto("/traces");
  await expect(page.getByRole("link", { name: "AgentScope" })).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Traces", exact: true }),
  ).toHaveAttribute("aria-current", "page");
  await expect(
    page.getByText("e2e-agent-trace", { exact: true }),
  ).toBeVisible();
  await page.goto("/experiments");
  await expect(page.getByRole("link", { name: "AgentScope" })).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Experiments", exact: true }),
  ).toHaveAttribute("aria-current", "page");
  await expect(
    page.getByText(`E2E Baseline ${suffix}`, { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText(`E2E Candidate ${suffix}`, { exact: true }),
  ).toBeVisible();
  await page.goto("/quality-gates");
  await expect(
    page.getByText(`E2E Release Gate ${suffix}`, { exact: true }),
  ).toBeVisible();

  expect(organization.id).toBeTruthy();
});
