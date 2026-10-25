import http from "k6/http";
import { check } from "k6";
import { Counter, Rate, Trend } from "k6/metrics";

const apiUrl = (__ENV.AGENTSCOPE_API_URL || "http://localhost:8000").replace(/\/$/, "");
const apiKey = __ENV.AGENTSCOPE_API_KEY;
const batchSize = Number(__ENV.BATCH_SIZE || 50);
const virtualUsers = Number(__ENV.VUS || 100);
const iterationsPerUser = Number(__ENV.ITERATIONS_PER_VU || 1);

if (!apiKey) {
  throw new Error("AGENTSCOPE_API_KEY is required");
}
if (!Number.isInteger(batchSize) || batchSize < 2 || batchSize % 2 !== 0) {
  throw new Error("BATCH_SIZE must be an even integer of at least 2");
}

const rejectedBatches = new Counter("ingestion_rejected_batches");
const requestFailures = new Rate("ingestion_request_failures");
const ingestionLatency = new Trend("ingestion_latency_ms", true);

export const options = {
  scenarios: {
    concurrent_batches: {
      executor: "per-vu-iterations",
      vus: virtualUsers,
      iterations: iterationsPerUser,
      maxDuration: __ENV.MAX_DURATION || "2m",
    },
  },
  thresholds: {
    ingestion_request_failures: [__ENV.ERROR_RATE_THRESHOLD || "rate<0.01"],
    ingestion_latency_ms: [__ENV.P95_THRESHOLD || "p(95)<10000"],
  },
};

function uuid() {
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (value) => {
    const random = Math.floor(Math.random() * 16);
    const nibble = value === "x" ? random : (random & 0x3) | 0x8;
    return nibble.toString(16);
  });
}

export default function () {
  const events = [];
  const timestamp = new Date().toISOString();
  for (let index = 0; index < batchSize / 2; index += 1) {
    const traceId = `load-vu${__VU}-iter${__ITER}-${uuid()}`;
    events.push({
      event_id: uuid(),
      timestamp,
      type: "TRACE_START",
      trace_id: traceId,
      payload: {
        name: "load-test-agent",
        input: { request: index },
        agent_version: "load-profile-v1",
        tags: ["load-test"],
      },
    });
    events.push({
      event_id: uuid(),
      timestamp,
      type: "TRACE_END",
      trace_id: traceId,
      payload: {
        status: "SUCCESS",
        output: { accepted: true },
      },
    });
  }

  const response = http.post(
    `${apiUrl}/v1/ingest/batch`,
    JSON.stringify({ sdk: { name: "k6", version: "1" }, events }),
    {
      headers: {
        Authorization: `Bearer ${apiKey}`,
        "Content-Type": "application/json",
      },
      tags: { endpoint: "ingest_batch" },
    },
  );
  const accepted = check(response, {
    "batch accepted": (value) => value.status === 202,
    "all events accounted for": (value) => {
      if (value.status !== 202) return false;
      const body = value.json();
      return body.accepted + body.duplicates === batchSize;
    },
  });
  requestFailures.add(!accepted);
  ingestionLatency.add(response.timings.duration);
  if (!accepted) rejectedBatches.add(1);
}
