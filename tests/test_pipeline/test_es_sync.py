"""ES 索引与同步测试（单元 3.2 S3，07 §5 断言）。

断言：死信重试演练（失败入队 → 重放成功）；别名原子切换演练
（零停机重建路径）；_id 映射与 Neo4j/Qdrant 一致（chunk_id 裸值）。
"""

# --- 第三方库 ---
import pytest

# --- 本地模块 ---
from app.db.es_client import _IK_SETTINGS, CHUNKS_ALIAS, ESClient
from app.pipeline.indexing.fulltext_indexer import ESSyncer

_TEST_PREFIX = "__test_3_2__"


class FakeRedisDeadLetter:
    """Redis 死信队列测试替身（内存 List）。"""

    def __init__(self) -> None:
        """初始化空队列。"""
        self.queue: list[str] = []

    async def dead_letter_push(self, message: str) -> None:
        """左端推入。"""
        self.queue.insert(0, message)

    async def dead_letter_pop(self) -> str | None:
        """右端弹出。"""
        return self.queue.pop() if self.queue else None

    async def dead_letter_len(self) -> int:
        """队列长度。"""
        return len(self.queue)


class FakeES:
    """ES 测试替身：可控失败次数。"""

    def __init__(self, fail_times: int = 0) -> None:
        """初始化替身。

        Args:
            fail_times: bulk_index 前 N 次调用抛出异常。
        """
        self.fail_times = fail_times
        self.calls = 0
        self.indexed: list[tuple[str, dict]] = []

    async def ensure_indices(self) -> None:
        """无操作。"""

    async def bulk_index(self, alias: str, docs: list[tuple[str, dict]]) -> int:
        """模拟批量写入（前 fail_times 次失败）。"""
        self.calls += 1
        if self.calls <= self.fail_times:
            raise RuntimeError("ES down")
        self.indexed.extend(docs)
        return len(docs)


class TestDeadLetterDrill:
    """死信重试演练（07 §5）。"""

    @pytest.mark.asyncio
    async def test_failure_goes_to_dead_letter_then_replay(self) -> None:
        redis = FakeRedisDeadLetter()
        failing_es = FakeES(fail_times=1)
        syncer = ESSyncer(failing_es, redis)  # type: ignore[arg-type]

        chunks = [{"chunk_id": f"{_TEST_PREFIX}c-0", "content": "内容"}]
        n = await syncer.sync_chunks(chunks)
        assert n == 0  # 首次失败
        assert await redis.dead_letter_len() == 1  # 入死信

        # ES 恢复后重放成功（FakeES 第二次调用不再失败）
        replayed = await syncer.replay_dead_letter()
        assert replayed == 1
        assert await redis.dead_letter_len() == 0
        assert failing_es.indexed[0][0] == f"{_TEST_PREFIX}c-0"

    @pytest.mark.asyncio
    async def test_sync_success_no_dead_letter(self) -> None:
        redis = FakeRedisDeadLetter()
        syncer = ESSyncer(FakeES(fail_times=0), redis)  # type: ignore[arg-type]
        n = await syncer.sync_entities(
            [{"entity_id": f"{_TEST_PREFIX}e-0", "name": "实体"}]
        )
        assert n == 1
        assert await redis.dead_letter_len() == 0

    @pytest.mark.asyncio
    async def test_id_mapping_bare_value(self) -> None:
        """_id 裸值 = chunk_id（与 Neo4j/Qdrant 三方一致，11 D9）。"""
        redis = FakeRedisDeadLetter()
        es = FakeES()
        syncer = ESSyncer(es, redis)  # type: ignore[arg-type]
        await syncer.sync_chunks([{"chunk_id": "doc-a-3", "content": "x"}])
        doc_id, _ = es.indexed[0]
        assert doc_id == "doc-a-3"  # 裸值，无前缀


class TestESAliasSwap:
    """别名原子切换演练（集成，ES 不可达/IK 未就绪时跳过）。"""

    @pytest.mark.asyncio
    async def test_alias_atomic_swap_drill(self) -> None:
        es = ESClient(host="http://localhost:9200")
        if not await es.check_health():
            pytest.skip("ES 不可达，集成用例跳过")
        try:
            await es.ensure_indices()
            if not await es.ik_available():
                pytest.skip("IK 插件未就绪，集成用例跳过")
        except Exception:  # noqa: BLE001
            pytest.skip("ES 索引创建失败（插件未就绪），集成用例跳过")

        client = await es._ensure_client()
        try:
            # v1 灌数
            await es.index_doc(
                CHUNKS_ALIAS,
                f"{_TEST_PREFIX}c-0",
                {"chunk_id": f"{_TEST_PREFIX}c-0", "doc_id": f"{_TEST_PREFIX}doc",
                 "content": "清蒸鲈鱼测试内容", "title_path": ["测试"],
                 "created_at": "2026-08-24T00:00:00Z"},
            )
            await client.indices.refresh(index=CHUNKS_ALIAS)
            assert await es.count(CHUNKS_ALIAS) >= 1

            # 建 v2 并复制数据
            old_index = await es.alias_target(CHUNKS_ALIAS)
            assert old_index is not None
            new_index = old_index.replace("_v1", "_v2") if old_index.endswith("_v1") else f"{CHUNKS_ALIAS}_v2"
            mapping = await client.indices.get_mapping(index=old_index)
            # 用标准 settings 重建（内部 settings 如 index.uuid 不可复制）
            await client.indices.create(
                index=new_index,
                settings=_IK_SETTINGS,
                mappings=mapping[old_index]["mappings"],
            )
            docs = await client.search(index=old_index, size=100)
            batch = [
                (h["_id"], h["_source"]) for h in docs["hits"]["hits"]
            ]
            await es.bulk_index(new_index, batch)
            await client.indices.refresh(index=new_index)

            # 校验 count 一致后原子切换
            assert await es.count(new_index) == await es.count(old_index)
            removed = await es.alias_atomic_swap(CHUNKS_ALIAS, new_index)
            assert removed == old_index
            assert await es.alias_target(CHUNKS_ALIAS) == new_index
            assert await es.count(CHUNKS_ALIAS) >= 1
        finally:
            # 清理：删除测试数据与可能的 v2 索引，恢复 v1 别名
            current = await es.alias_target(CHUNKS_ALIAS)
            await es.delete_by_id(CHUNKS_ALIAS, f"{_TEST_PREFIX}c-0")
            try:
                if current is not None and current != f"{CHUNKS_ALIAS}_v1":
                    # 切回 v1
                    if await client.indices.exists(index=f"{CHUNKS_ALIAS}_v1"):
                        await es.alias_atomic_swap(CHUNKS_ALIAS, f"{CHUNKS_ALIAS}_v1")
                    else:
                        await client.indices.delete(index=current, ignore_unavailable=True)
            except Exception:  # noqa: BLE001 - 清理尽力而为
                pass
            await es.close()
