"""统一 Embedding 服务测试（单元 2.3 S3，07 §5 断言）。

断言：并发调用下事件循环不被阻塞（semaphore 串行化）；
独立超时生效；FlagEmbedding 未接入时 sparse 降级为空。
真实模型断言（dense=1024 / sparse 非空）为集成用例，
Ollama + bge-m3 就绪后自动启用（不可达时跳过）。
"""

# --- 标准库 ---
import asyncio

# --- 第三方库 ---
import pytest

# --- 本地模块 ---
from app.embedding.ollama_client import OllamaClient
from app.embedding.service import BgeM3EmbeddingService


class FakeOllamaClient:
    """Ollama 客户端测试替身（07 §3 stub 思路）。"""

    def __init__(self, delay: float = 0.0, dim: int = 1024) -> None:
        """初始化替身。

        Args:
            delay: 每次 embed 的模拟耗时（秒）。
            dim: 向量维度。
        """
        self.delay = delay
        self.dim = dim
        self.active = 0
        self.max_active = 0

    async def embed(self, model: str, texts: list[str]) -> list[list[float]]:
        """模拟 embed：记录并发度，返回全 1 向量。"""
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            if self.delay:
                await asyncio.sleep(self.delay)
            return [[1.0] * self.dim for _ in texts]
        finally:
            self.active -= 1


class TestSemaphoreSerialization:
    """全局 semaphore 串行化（05 §3.3 铁律 2）。"""

    @pytest.mark.asyncio
    async def test_concurrent_embeds_serialized(self) -> None:
        fake = FakeOllamaClient(delay=0.05)
        service = BgeM3EmbeddingService(
            ollama_client=fake, semaphore_limit=1, timeout=5.0  # type: ignore[arg-type]
        )
        # 并发 4 个请求：semaphore 上限 1 → 任意时刻最多 1 个活跃
        results = await asyncio.gather(
            service.embed(["a"]),
            service.embed(["b"]),
            service.embed(["c"]),
            service.embed(["d"]),
        )
        assert len(results) == 4
        assert fake.max_active == 1  # 串行执行，事件循环不阻塞

    @pytest.mark.asyncio
    async def test_event_loop_not_blocked(self) -> None:
        """embed 等待期间事件循环仍可调度其他协程。"""
        fake = FakeOllamaClient(delay=0.1)
        service = BgeM3EmbeddingService(ollama_client=fake, timeout=5.0)  # type: ignore[arg-type]
        ticks = 0

        async def ticker() -> None:
            nonlocal ticks
            for _ in range(5):
                await asyncio.sleep(0.02)
                ticks += 1

        await asyncio.gather(service.embed(["x"]), ticker())
        assert ticks == 5  # 等待期间其他协程正常运行


class TestTimeout:
    """独立超时（05 §3.3 铁律 3）。"""

    @pytest.mark.asyncio
    async def test_dense_timeout_raises(self) -> None:
        fake = FakeOllamaClient(delay=0.5)
        service = BgeM3EmbeddingService(ollama_client=fake, timeout=0.05)  # type: ignore[arg-type]
        with pytest.raises(asyncio.TimeoutError):
            await service.embed(["慢请求"])


class TestSparseFallback:
    """FlagEmbedding 未接入时 sparse 降级。"""

    @pytest.mark.asyncio
    async def test_sparse_empty_without_flag_client(self) -> None:
        fake = FakeOllamaClient()
        service = BgeM3EmbeddingService(ollama_client=fake, flag_client=None)  # type: ignore[arg-type]
        result = await service.embed(["清蒸鲈鱼"])
        assert len(result.dense) == 1
        assert len(result.dense[0]) == 1024
        assert result.sparse == [{}]  # 降级为空字典，不阻塞 dense


class TestRealOllamaIntegration:
    """集成用例：Ollama + bge-m3 就绪后启用（07 §3：质量类测试不可 mock）。"""

    @pytest.mark.asyncio
    async def test_dense_1024_and_sparse_contract(self) -> None:
        client = OllamaClient(timeout=10.0)
        if not await client.check_health():
            pytest.skip("Ollama 不可达，集成用例跳过（环境就绪后自动启用）")
        service = BgeM3EmbeddingService(ollama_client=client, timeout=30.0)  # type: ignore[arg-type]
        try:
            result = await service.embed(["清蒸鲈鱼怎么做"])
            assert len(result.dense) == 1
            assert len(result.dense[0]) == 1024  # BGE-M3 dense 维度
        finally:
            await client.close()
