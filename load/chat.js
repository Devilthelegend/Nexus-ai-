// k6 load test for the NexusAI critical path.
//
// Exercises register -> login -> workspace -> conversation once per virtual
// user, then loops on the chat hot path. Run against a live stack:
//
//   k6 run -e BASE_URL=http://localhost:8000 load/chat.js
//
// Thresholds encode the SLO: p95 chat latency < 1500ms and < 1% errors.

import http from "k6/http";
import { check, sleep } from "k6";
import { Trend } from "k6/metrics";

const BASE_URL = __ENV.BASE_URL || "http://localhost:8000";
const API = `${BASE_URL}/api/v1`;
const PASSWORD = "s3cret-password";

const chatLatency = new Trend("chat_latency", true);

export const options = {
  stages: [
    { duration: "30s", target: 20 },
    { duration: "1m", target: 50 },
    { duration: "30s", target: 0 },
  ],
  thresholds: {
    http_req_failed: ["rate<0.01"],
    chat_latency: ["p(95)<1500"],
  },
};

const JSON_HEADERS = { "Content-Type": "application/json" };

function post(path, body, headers) {
  return http.post(`${API}${path}`, JSON.stringify(body), {
    headers: { ...JSON_HEADERS, ...(headers || {}) },
  });
}

export function setup() {
  return {};
}

export default function () {
  const email = `load-${__VU}-${Date.now()}@example.com`;

  post("/auth/register", { email, password: PASSWORD });
  const login = post("/auth/login", { email, password: PASSWORD });
  check(login, { "login 200": (r) => r.status === 200 });
  const token = login.json("access_token");
  const auth = { Authorization: `Bearer ${token}` };

  const ws = post("/workspaces", { name: "load-test" }, auth);
  const workspaceId = ws.json("id");

  const conv = post(
    `/workspaces/${workspaceId}/conversations`,
    { title: "load-test" },
    auth,
  );
  const conversationId = conv.json("id");

  for (let i = 0; i < 5; i++) {
    const res = post(
      `/workspaces/${workspaceId}/conversations/${conversationId}/messages`,
      { message: "What does the knowledge base say about this?" },
      auth,
    );
    chatLatency.add(res.timings.duration);
    check(res, { "chat 200": (r) => r.status === 200 });
    sleep(1);
  }
}
