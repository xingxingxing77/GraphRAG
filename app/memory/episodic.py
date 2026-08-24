"""
情景记忆（单元 8.2，J17，04 §3.2 `rag_episodic`）。

历史会话按「情景片段」（一轮 QA）向量化存储，跨会话可检索：
- Point ID 由逻辑 ID `{session_id}-{turn_seq}` 确定性派生（uuid5，
  幂等覆盖写，同 04 §3.1 业务集合实践；Qdrant 仅接受 UUID/整数 ID）；
- payload：session_id · user_id · timestamp · question · answer · summary；
- 删除会话级联清理（07 A-05）；180 天应用层过期（D8，11 路线图）。
"""

# --- 标准库 ---
import time
import uuid

# --- 第三方库 ---
from pydantic import BaseModel
from qdrant_client.models import FieldCondition, Filter, MatchValue, PointStruct

# --- 本地模块 ---
from app.db.qdrant_client import QdrantDBClient
from app.embedding.base import EmbeddingService

# 集合名与 ID 派生命名空间（04 §3.2）
RAG_EPISODIC_COLLECTION = "rag_episodic"
_POINT_ID_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "graphrag://rag-episodic-point")

# 情景记忆保留天数（D8 默认 180 天定时清理）
EPISODIC_RETENTION_DAYS = 180


class EpisodicHit(BaseModel):
    """情景检索命中项。

    Attributes:
        score: 相似度分数。
        session_id: 来源会话。
        question: 历史问题。
        answer: 历史答案。
        summary: 话题段摘要（可空）。
        timestamp: 入库 unix 时间。
    """

    score: float
    session_id: str
    question: str
    answer: str
    summary: str = ""
    timestamp: int = 0


class EpisodicMemory:
    """情景记忆管理器（rag_episodic 向量化存储与相关性检索）。"""

    def __init__(
        self,
        qdrant: QdrantDBClient,
        embedder: EmbeddingService,
        retention_days: int = EPISODIC_RETENTION_DAYS,
    ) -> None:
        """初始化情景记忆。

        Args:
            qdrant: Qdrant 客户端。
            embedder: Embedding 服务（dense 通道）。
            retention_days: 保留天数（D8 默认 180，可经 reliability.yaml 覆盖）。
        """
        self.qdrant = qdrant
        self.embedder = embedder
        self.retention_days = retention_days

    @staticmethod
    def _point_id(session_id: str, turn_seq: int) -> str:
        """由逻辑 ID 派生确定性 Point ID（幂等）。"""
        return str(uuid.uuid5(_POINT_ID_NAMESPACE, f"{session_id}-{turn_seq}"))

    @staticmethod
    def _compose_text(question: str, answer: str) -> str:
        """拼取向量化文本（问答成对语义更完整）。"""
        return f"Q: {question}\nA: {answer}"

    async def add(
        self,
        session_id: str,
        user_id: str,
        turn_seq: int,
        question: str,
        answer: str,
        summary: str = "",
        timestamp: int | None = None,
    ) -> None:
        """入库一轮 QA 情景片段（图内尾节点调用，幂等覆盖写）。

        Args:
            session_id: 会话 ID。
            user_id: 用户 ID。
            turn_seq: 会话内轮次序号（逻辑 ID 组成部分）。
            question: 用户问题。
            answer: 助手答案终稿。
            summary: 可选话题段摘要。
            timestamp: 入库 unix 秒（默认取系统时间）。
        """
        await self.qdrant.ensure_collection(RAG_EPISODIC_COLLECTION)
        result = await self.embedder.embed(
            [self._compose_text(question, answer)]
        )
        vector = result.dense[0]
        await self.qdrant.upsert_points(
            RAG_EPISODIC_COLLECTION,
            [
                PointStruct(
                    id=self._point_id(session_id, turn_seq),
                    vector={"dense": vector},
                    payload={
                        "session_id": session_id,
                        "user_id": user_id,
                        "turn_seq": turn_seq,
                        "timestamp": timestamp if timestamp is not None else int(time.time()),
                        "question": question,
                        "answer": answer,
                        "summary": summary,
                    },
                )
            ],
        )

    async def search(
        self,
        user_id: str,
        query: str,
        top_m: int = 3,
        exclude_session: str | None = None,
    ) -> list[EpisodicHit]:
        """按用户检索相关情景（跨会话注入；可排除当前会话）。

        Args:
            user_id: 用户 ID（隔离边界，payload index 前提见 11 路线图）。
            query: 当前查询文本。
            top_m: 返回条数上限。
            exclude_session: 需排除的当前会话 ID（避免自我重复注入）。

        Returns:
            相关性降序的命中列表；存储异常时返回空列表（不阻塞主链路）。
        """
        try:
            result = await self.embedder.embed([query])
            vector = result.dense[0]
            flt = Filter(
                must=[FieldCondition(key="user_id", match=MatchValue(value=user_id))],
                must_not=(
                    [
                        FieldCondition(
                            key="session_id", match=MatchValue(value=exclude_session)
                        )
                    ]
                    if exclude_session
                    else []
                ),
            )
            hits = await self.qdrant.search(
                RAG_EPISODIC_COLLECTION,
                vector,
                top_k=top_m,
                filter_condition=flt,
            )
        except Exception:  # noqa: BLE001 - 记忆检索失败不阻塞主链路
            return []
        return [
            EpisodicHit(
                score=h["score"],
                session_id=str(h["payload"].get("session_id", "")),
                question=str(h["payload"].get("question", "")),
                answer=str(h["payload"].get("answer", "")),
                summary=str(h["payload"].get("summary", "")),
                timestamp=int(h["payload"].get("timestamp", 0)),
            )
            for h in hits
        ]

    async def delete_by_session(self, session_id: str) -> None:
        """删除会话的全部情景点（DELETE /sessions 级联，07 A-05）。"""
        try:
            await self.qdrant.delete_by_payload_match(
                RAG_EPISODIC_COLLECTION, "session_id", session_id
            )
        except Exception:  # noqa: BLE001 - 级联失败不阻塞会话删除主流程
            return

    async def purge_expired(self, now: int | None = None) -> int:
        """清理超过保留期的情景点（D8：默认 180 天定时任务）。

        Args:
            now: 当前 unix 秒（默认取系统时间）。

        Returns:
            删除的点数。
        """
        current = now if now is not None else int(time.time())
        try:
            return await self.qdrant.delete_created_before(
                RAG_EPISODIC_COLLECTION,
                "timestamp",
                current - self.retention_days * 86400,
            )
        except Exception:  # noqa: BLE001 - 定时任务失败不抛出
            return 0
