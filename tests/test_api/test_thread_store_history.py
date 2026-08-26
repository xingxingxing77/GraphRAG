"""thread_store 会话历史聚合与 feedback 快照反查测试（BUG-A/B 回归）。

断言（GAP-A1/A2 缺陷修复）：
- get_history 倒序返回（最新 checkpoint 在前）→ 输出消息按时间升序；
- 同一 run 的中间 checkpoint 重复携带 original_query → 用户消息去重，
  q_/a_ 成对发射；
- run 中断（无 answer）→ 挂起提问保留；
- feedback._resolve_snapshot 未命中 message_id 时回退到「最新」assistant
  并配对正确的 query（修复前倒序列表取到最旧回答）。
"""

# --- 标准库 ---
from datetime import datetime, timezone
from typing import Any

# --- 第三方库 ---
import pytest

# --- 本地模块 ---
from app.api import thread_store
from app.api.endpoints.feedback import _resolve_snapshot
from app.core.models import SessionMessage


class _FakeThreads:
    """langgraph threads API 替身：get 归属校验 + get_history 倒序。"""

    def __init__(self, history: list[dict[str, Any]], owner: str = "u1") -> None:
        self._history = history  # 调用方按「最新在前」构造
        self._owner = owner

    async def get(self, thread_id: str) -> dict[str, Any]:
        return {"thread_id": thread_id, "metadata": {"user_id": self._owner}}

    async def get_history(self, thread_id: str, limit: int) -> list[dict[str, Any]]:
        return self._history[:limit]


class _FakeClient:
    def __init__(self, threads: _FakeThreads) -> None:
        self.threads = threads


def _ckpt(cid: str, values: dict[str, Any], ts: str) -> dict[str, Any]:
    return {
        "values": values,
        "checkpoint": {"checkpoint_id": cid},
        "created_at": ts,
    }


def _dt(day: int) -> datetime:
    """构造带时区的 datetime（避免测试里裸写 None）。"""
    return datetime(2026, 8, 27, 0, day, 0, tzinfo=timezone.utc)


def _patch_history(monkeypatch: pytest.MonkeyPatch, history: list[dict[str, Any]]) -> None:
    monkeypatch.setattr(
        thread_store, "_client", lambda user_id: _FakeClient(_FakeThreads(history))
    )


class TestGetMessagesOrdering:
    """BUG-A：时序升序 + q_ 去重。"""

    async def test_reverse_history_emits_chronological(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # langgraph 返回最新在前：run2 最终态 → run1 最终态 → run1 中间态
        history = [
            _ckpt("c4", {"original_query": "Q2", "answer": "A2"}, "2026-08-27T00:04:00Z"),
            _ckpt("c2", {"original_query": "Q1", "answer": "A1"}, "2026-08-27T00:02:00Z"),
            _ckpt("c1", {"original_query": "Q1"}, "2026-08-27T00:01:00Z"),
        ]
        _patch_history(monkeypatch, history)

        messages, _ = await thread_store.get_messages("u1", "t1", None, 100)

        assert [(m.role, m.content) for m in messages] == [
            ("user", "Q1"),
            ("assistant", "A1"),
            ("user", "Q2"),
            ("assistant", "A2"),
        ]

    async def test_query_dedup_within_run(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 单 run 三个 super-step：中间 checkpoint 均带 original_query，
        # answer 仅最终 checkpoint 出现 → 一对 q_/a_。
        history = [
            _ckpt("c3", {"original_query": "Q1", "answer": "A1"}, "2026-08-27T00:03:00Z"),
            _ckpt("c2", {"original_query": "Q1", "retrieval_rounds": 1}, "2026-08-27T00:02:00Z"),
            _ckpt("c1", {"original_query": "Q1"}, "2026-08-27T00:01:00Z"),
        ]
        _patch_history(monkeypatch, history)

        messages, _ = await thread_store.get_messages("u1", "t1", None, 100)

        roles = [m.role for m in messages]
        assert roles == ["user", "assistant"]
        assert messages[0].message_id == "q_c1"

    async def test_interrupted_run_keeps_pending_query(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # run1 已完成，run2 中断（无 answer）→ 保留挂起提问。
        history = [
            _ckpt("c3", {"original_query": "Q2"}, "2026-08-27T00:03:00Z"),
            _ckpt("c2", {"original_query": "Q1", "answer": "A1"}, "2026-08-27T00:02:00Z"),
        ]
        _patch_history(monkeypatch, history)

        messages, _ = await thread_store.get_messages("u1", "t1", None, 100)

        assert [(m.role, m.content) for m in messages] == [
            ("user", "Q1"),
            ("assistant", "A1"),
            ("user", "Q2"),
        ]

    async def test_repeated_identical_query_across_runs(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 两轮同文本提问（重试场景）：每轮独立成对，不互相吞并。
        history = [
            _ckpt("c4", {"original_query": "Q1", "answer": "A2"}, "2026-08-27T00:04:00Z"),
            _ckpt("c3", {"original_query": "Q1"}, "2026-08-27T00:03:00Z"),
            _ckpt("c2", {"original_query": "Q1", "answer": "A1"}, "2026-08-27T00:02:00Z"),
            _ckpt("c1", {"original_query": "Q1"}, "2026-08-27T00:01:00Z"),
        ]
        _patch_history(monkeypatch, history)

        messages, _ = await thread_store.get_messages("u1", "t1", None, 100)

        assert [(m.role, m.content) for m in messages] == [
            ("user", "Q1"),
            ("assistant", "A1"),
            ("user", "Q1"),
            ("assistant", "A2"),
        ]

    async def test_foreign_thread_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        history = [_ckpt("c1", {"original_query": "Q1", "answer": "A1"}, "2026-08-27T00:01:00Z")]
        monkeypatch.setattr(
            thread_store,
            "_client",
            lambda user_id: _FakeClient(_FakeThreads(history, owner="someone-else")),
        )

        assert await thread_store.get_messages("u1", "t1", None, 100) is None


class TestResolveSnapshotFallback:
    """BUG-B：未命中 message_id 回退最新 assistant + 正确配对 query。"""

    @staticmethod
    def _messages() -> list[SessionMessage]:
        return [
            SessionMessage(message_id="q_1", role="user", content="Q1", created_at=_dt(1)),
            SessionMessage(message_id="a_1", role="assistant", content="A1", created_at=_dt(1)),
            SessionMessage(message_id="q_2", role="user", content="Q2", created_at=_dt(1)),
            SessionMessage(message_id="a_2", role="assistant", content="A2", created_at=_dt(1)),
        ]

    async def test_fallback_hits_latest_assistant(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def fake_get(user_id, session_id, cursor, limit):
            return self._messages(), None

        monkeypatch.setattr(thread_store, "get_messages", fake_get)

        query, answer = await _resolve_snapshot("u1", "t1", "live-local-id")

        # 修复前：倒序列表 assists[-1] 取到 A1（最旧）；修复后取最新 A2。
        assert answer == "A2"
        assert query == "Q2"

    async def test_exact_hit_pairs_correct_query(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def fake_get(user_id, session_id, cursor, limit):
            return self._messages(), None

        monkeypatch.setattr(thread_store, "get_messages", fake_get)

        query, answer = await _resolve_snapshot("u1", "t1", "a_1")

        assert answer == "A1"
        assert query == "Q1"

    async def test_no_assistant_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def fake_get(user_id, session_id, cursor, limit):
            return [], None

        monkeypatch.setattr(thread_store, "get_messages", fake_get)

        query, answer = await _resolve_snapshot("u1", "t1", "whatever")

        assert query is None and answer is None
