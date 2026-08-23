"""LLM 注册表测试（单元 0.4 S3，07 §3 stub 思路）。

断言：models.yaml 结构校验、api_key_ref 缺失 fail-fast（D7）、
fallback 链触发次序与全链失败 LLMUnavailable（05 §4）。
"""

# --- 标准库 ---
from typing import Any

# --- 第三方库 ---
import pytest
from pydantic import ValidationError

# --- 本地模块 ---
from app.llm.client import ChatCompletion, LLMClient, ModelEntry
from app.llm.registry import LLMUnavailable, ModelRegistry, ModelsConfig


def _make_registry() -> ModelRegistry:
    """构造双条目测试注册表（m1 主 / m2 备）。"""
    config = ModelsConfig(
        models={
            "m1": ModelEntry(base_url="http://a/v1", api_key_ref="TEST_KEY_M1", model="m1"),
            "m2": ModelEntry(base_url="http://b/v1", api_key_ref="TEST_KEY_M2", model="m2"),
        },
        roles={"generator": "m1"},
        fallback_chain=["m1", "m2"],
    )
    return ModelRegistry(config)


class TestModelsConfigValidation:
    """models.yaml 结构校验（05 §6 fail-fast）。"""

    def test_roles_must_reference_registered_entry(self) -> None:
        with pytest.raises(ValidationError):
            ModelsConfig(
                models={"m1": ModelEntry(base_url="u", api_key_ref="K", model="m")},
                roles={"generator": "ghost"},
            )

    def test_fallback_chain_must_reference_registered_entry(self) -> None:
        with pytest.raises(ValidationError):
            ModelsConfig(
                models={"m1": ModelEntry(base_url="u", api_key_ref="K", model="m")},
                fallback_chain=["ghost"],
            )


class TestResolveApiKey:
    """api_key_ref → os.environ 解析（D7/J16 密钥纪律）。"""

    def test_missing_env_fails_fast(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("TEST_KEY_M1", raising=False)
        registry = _make_registry()
        entry = registry.config.models["m1"]
        with pytest.raises(SystemExit):
            registry.resolve_api_key(entry)

    def test_present_env_returns_value(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TEST_KEY_M2", "sk-test")
        registry = _make_registry()
        entry = registry.config.models["m2"]
        assert registry.resolve_api_key(entry) == "sk-test"

    def test_for_role_unknown_role_raises(self) -> None:
        registry = _make_registry()
        with pytest.raises(KeyError):
            registry.entry_for_role("judge")


class TestFallbackChain:
    """fallback 链触发次序（05 §4）。"""

    @pytest.mark.asyncio
    async def test_first_entry_failure_falls_back_in_order(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("TEST_KEY_M1", "k1")
        monkeypatch.setenv("TEST_KEY_M2", "k2")
        registry = _make_registry()
        calls: list[str] = []

        async def fake_chat(self: LLMClient, messages: Any, **kwargs: Any) -> ChatCompletion:
            calls.append(self.entry.model)
            if self.entry.model == "m1":
                raise RuntimeError("primary down")
            return ChatCompletion(content="ok", model=self.entry.model)

        monkeypatch.setattr(LLMClient, "chat", fake_chat)
        result = await registry.chat_with_fallback([{"role": "user", "content": "hi"}])
        assert calls == ["m1", "m2"]
        assert result.content == "ok"
        assert result.model == "m2"

    @pytest.mark.asyncio
    async def test_all_entries_fail_raises_unavailable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("TEST_KEY_M1", "k1")
        monkeypatch.setenv("TEST_KEY_M2", "k2")
        registry = _make_registry()

        async def fake_chat(self: LLMClient, messages: Any, **kwargs: Any) -> ChatCompletion:
            raise RuntimeError("all down")

        monkeypatch.setattr(LLMClient, "chat", fake_chat)
        with pytest.raises(LLMUnavailable):
            await registry.chat_with_fallback([{"role": "user", "content": "hi"}])

    @pytest.mark.asyncio
    async def test_missing_api_key_is_config_error_not_degradation(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """api_key_ref 缺失为配置错误：fail-fast（SystemExit），不吞为降级。"""
        monkeypatch.delenv("TEST_KEY_M1", raising=False)
        monkeypatch.setenv("TEST_KEY_M2", "k2")
        registry = _make_registry()
        with pytest.raises(SystemExit):
            await registry.chat_with_fallback([{"role": "user", "content": "hi"}])
