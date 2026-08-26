import { describe, expect, it, vi } from "vitest";

// agentClient 在模块顶层构造 SDK Client（依赖 import.meta.env），node 测试态 mock 掉
vi.mock("@/lib/agentClient", () => ({
  bindJwt: vi.fn(),
  ensureThread: vi.fn(),
  streamRun: vi.fn(),
  client: {},
}));

import { mapErrorText } from "./useChatStream";

describe("mapErrorText（06 §9 错误码 → 文案）", () => {
  it("输入校验类", () => {
    expect(mapErrorText("CHAT_400_EMPTY_QUERY")).toBe("输入有误，请检查后重试");
    expect(mapErrorText("CHAT_400_INVALID_TIER")).toBe("输入有误，请检查后重试");
  });

  it("限流/超时/会话失效", () => {
    expect(mapErrorText("CHAT_429_RATE_LIMITED")).toBe("请求太频繁，请稍后再试");
    expect(mapErrorText("CHAT_504_TIER_TIMEOUT")).toBe("回答超时，可重试或切换深度模式");
    expect(mapErrorText("CHAT_404_THREAD_NOT_FOUND")).toBe("会话已失效，请新建会话");
  });

  it("认证过期", () => {
    expect(mapErrorText("AUTH_401_TOKEN_EXPIRED")).toBe("登录已过期，请重新登录");
    expect(mapErrorText("AUTH_401_TOKEN_INVALID")).toBe("登录已过期，请重新登录");
  });

  it("服务端故障与未知兜底", () => {
    expect(mapErrorText("SYS_500_INTERNAL")).toBe("服务开小差了，请稍后重试");
    expect(mapErrorText("SYS_503_DEPENDENCY_DOWN")).toBe("服务开小差了，请稍后重试");
    expect(mapErrorText("SOME_UNKNOWN")).toBe("请求失败，请稍后重试");
  });
});
