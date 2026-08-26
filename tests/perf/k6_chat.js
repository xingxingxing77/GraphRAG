// tests/perf/k6_chat.js —— 三档对话压测（D4/D6 · 单元 9.2）
// 口径（07 §7）：fast P95 ≤6s / standard ≤18s / deep ≤35s；显存峰值 <22GB。
// 运行：k6 run tests/perf/k6_chat.js -e TIER=standard -e BASE=http://localhost:8001
// 报告归档：tests/perf/reports/（CI 产物，人工核对 P95 后入库）。
import http from "k6/http";
import { check, sleep } from "k6";

const BASE = __ENV.BASE || "http://localhost:8001";
const TIER = __ENV.TIER || "standard";

// 各档 VU/时长（9.2 压测矩阵，可按 GPU 资源调整）
const SCENARIOS = {
  fast: { vus: 10, duration: "60s" },
  standard: { vus: 6, duration: "120s" },
  deep: { vus: 3, duration: "180s" },
};

export const options = {
  scenarios: {
    chat: {
      executor: "constant-vus",
      vus: (SCENARIOS[TIER] || SCENARIOS.standard).vus,
      duration: (SCENARIOS[TIER] || SCENARIOS.standard).duration,
    },
  },
  thresholds: {
    // P95 目标（毫秒），按档位切换
    http_req_duration: [
      `p(95)<${TIER === "fast" ? 6000 : TIER === "deep" ? 35000 : 18000}`,
    ],
  },
};

const QUERIES = [
  "清蒸鲈鱼怎么做？",
  "鲈鱼和桂鱼哪个更适合清蒸？",
  "知识库覆盖了哪些菜系？",
];

export default function () {
  const query = QUERIES[__VU % QUERIES.length];
  const res = http.post(
    `${BASE}/threads/demo-${__VU}/runs`,
    JSON.stringify({
      assistant_id: "agent",
      input: { original_query: query, latency_tier: TIER },
      stream_mode: "values",
    }),
    { headers: { "Content-Type": "application/json" } }
  );
  check(res, {
    "status is 200/202": (r) => r.status === 200 || r.status === 202,
  });
  sleep(1);
}
