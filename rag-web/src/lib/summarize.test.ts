import { describe, expect, it } from "vitest";

import { extractFinalState, isAgentNode, summarizeNodeUpdate } from "./summarize";

describe("summarizeNodeUpdate（03 §3.5 节点摘要）", () => {
  it("固定文案节点", () => {
    expect(summarizeNodeUpdate("load_memory", {})).toBe("注入会话记忆");
    expect(summarizeNodeUpdate("generator", {})).toBe("生成答案");
    expect(summarizeNodeUpdate("write_back", {})).toBe("写入记忆与缓存");
  });

  it("query_understanding 带意图与档位", () => {
    expect(
      summarizeNodeUpdate("query_understanding", { intent: "factoid", latency_tier: "standard" }),
    ).toBe("理解查询（意图 factoid，档位 standard）");
  });

  it("query_understanding 无档位", () => {
    expect(summarizeNodeUpdate("query_understanding", { intent: "chitchat" })).toBe(
      "理解查询（意图 chitchat）",
    );
  });

  it("planner 计划步数 / 增量补计划", () => {
    expect(summarizeNodeUpdate("planner", { plan: [1, 2, 3] })).toBe("制定检索计划（3 步）");
    expect(summarizeNodeUpdate("planner", { plan: [] })).toBe("补充检索计划");
  });

  it("tool_router 检索轮次", () => {
    expect(summarizeNodeUpdate("tool_router", { retrieval_rounds: 2 })).toBe("执行检索（第 2 轮）");
    expect(summarizeNodeUpdate("tool_router", {})).toBe("执行检索");
  });

  it("reflector 短路/补充", () => {
    expect(summarizeNodeUpdate("reflector", { needs_more_retrieval: true })).toBe(
      "反思：证据不足，补充检索",
    );
    expect(summarizeNodeUpdate("reflector", { needs_more_retrieval: false })).toBe("反思：证据充分");
  });

  it("self_correction 忠实度评分", () => {
    expect(summarizeNodeUpdate("self_correction", { faithfulness_score: 0.92 })).toBe(
      "忠实度校验（92%）",
    );
  });

  it("未知节点回退为节点名", () => {
    expect(summarizeNodeUpdate("unknown", {})).toBe("unknown");
  });
});

describe("extractFinalState（values 终态提取）", () => {
  it("提取 answer/citations/档位并过滤非法降级枚举", () => {
    const f = extractFinalState({
      answer: "hello",
      citations: [{ marker: 1, quote: "q" }],
      degraded_reasons: ["no-graph", "bogus-reason"],
      latency_tier: "deep",
    });
    expect(f.answer).toBe("hello");
    expect(f.citations).toHaveLength(1);
    expect(f.degradedReasons).toEqual(["no-graph"]);
    expect(f.latencyTier).toBe("deep");
  });

  it("空 values 返回安全缺省", () => {
    const f = extractFinalState({});
    expect(f.answer).toBe("");
    expect(f.citations).toEqual([]);
    expect(f.degradedReasons).toEqual([]);
    expect(f.latencyTier).toBeNull();
  });
});

describe("isAgentNode（AgentNodeName 校验）", () => {
  it("识别全部节点名", () => {
    const nodes = [
      "load_memory",
      "query_understanding",
      "planner",
      "tool_router",
      "reflector",
      "generator",
      "self_correction",
      "write_back",
    ];
    for (const n of nodes) expect(isAgentNode(n)).toBe(true);
  });

  it("拒绝非节点名", () => {
    expect(isAgentNode("foobar")).toBe(false);
    expect(isAgentNode("")).toBe(false);
  });
});
