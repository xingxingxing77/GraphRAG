"""
记忆注入调度器（单元 8.1/8.2，05 §5.4 双闸去重 + 03 §8 load_memory 事件）。

职责：在查询改写之前组装记忆上下文——
- 工作记忆：最近 N 轮原文（全文注入）；
- 情景记忆：跨会话 top-m 相关片段；
- 双闸去重（05 §5.4）：闸 1 = 工作记忆原文 hash 集合精确剔除；
  闸 2 = 情景候选与工作记忆语义相似度 > 0.92 剔除（避免重复注入）。

输出 context_text 格式两段式：`[历史n轮]` + `[相关记忆top-m]`；
计数字段与 03 §8 `load_memory` 更新事件对齐
（injected_working_turns / episodic_hits / dedup_removed）。
"""

# --- 标准库 ---
import hashlib
import math

# --- 第三方库 ---
from pydantic import BaseModel

# --- 本地模块 ---
from app.embedding.base import EmbeddingService
from app.memory.working_memory import WorkingMemory
from app.memory.episodic import EpisodicHit, EpisodicMemory

# 闸 2 阈值：情景与工作记忆相似度高于该值视为重复（05 §5.4）
DEDUP_SIMILARITY_THRESHOLD = 0.92


class MemoryContext(BaseModel):
    """注入决策结果（字段对齐 03 §8 load_memory 事件载荷）。

    Attributes:
        injected_working_turns: 实际注入的工作记忆轮数。
        episodic_hits: 注入的情景条数（去重后）。
        dedup_removed: 双闸剔除的情景条数。
        context_text: 两段式注入文本；无任何记忆时为空串。
    """

    injected_working_turns: int = 0
    episodic_hits: int = 0
    dedup_removed: int = 0
    context_text: str = ""


def _cosine(a: list[float], b: list[float]) -> float:
    """余弦相似度（零向量安全返回 0）。"""
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def _text_hash(text: str) -> str:
    """规范化原文 hash（闸 1 精确去重键）。"""
    return hashlib.sha256(" ".join(text.split()).lower().encode("utf-8")).hexdigest()


class MemoryScheduler:
    """记忆注入调度器（load_memory 前置节点的领域逻辑载体）。"""

    def __init__(
        self,
        working_memory: WorkingMemory,
        episodic: EpisodicMemory,
        embedder: EmbeddingService,
        *,
        working_turns: int = 6,
        episodic_top_m: int = 3,
        dedup_similarity_threshold: float = DEDUP_SIMILARITY_THRESHOLD,
    ) -> None:
        """初始化调度器。

        Args:
            working_memory: 工作记忆。
            episodic: 情景记忆。
            embedder: Embedding 服务（闸 2 相似度计算用）。
            working_turns: 注入的最近轮数上限。
            episodic_top_m: 注入的情景条数上限。
            dedup_similarity_threshold: 闸 2 相似度阈（可经 reliability.yaml 覆盖）。
        """
        self.working_memory = working_memory
        self.episodic = episodic
        self.embedder = embedder
        self.working_turns = working_turns
        self.episodic_top_m = episodic_top_m
        self.dedup_similarity_threshold = dedup_similarity_threshold

    async def build_context(
        self,
        user_id: str,
        session_id: str,
        current_query: str,
    ) -> MemoryContext:
        """组装注入上下文（置于改写前调用）。

        Args:
            user_id: 用户 ID（情景隔离边界）。
            session_id: 当前会话 ID（工作记忆来源；情景检索排除本会话）。
            current_query: 当前用户查询。

        Returns:
            MemoryContext: 计数与拼接后的注入文本。
        """
        history = await self.working_memory.get_history(session_id)
        recent = history[-self.working_turns :]

        # --- 闸 1：工作记忆原文 hash 集合 ---
        wm_texts = [f"Q: {h['q']}\nA: {h['a']}" for h in recent]
        wm_hashes = {_text_hash(t) for t in wm_texts}

        candidates = await self.episodic.search(
            user_id,
            current_query,
            top_m=self.episodic_top_m + len(wm_hashes),
            exclude_session=session_id,
        )

        # --- 闸 2：情景 × 工作记忆 语义相似度 > 0.92 剔除 ---
        kept: list[EpisodicHit] = []
        removed = 0
        if candidates and wm_texts:
            wm_vectors = (await self.embedder.embed(wm_texts)).dense
            cand_vectors = (
                await self.embedder.embed([c.question + "\n" + c.answer for c in candidates])
            ).dense
            for hit, cvec in zip(candidates, cand_vectors, strict=True):
                max_sim = max(
                    (_cosine(cvec, wvec) for wvec in wm_vectors), default=0.0
                )
                if _text_hash(f"Q: {hit.question}\nA: {hit.answer}") in wm_hashes or max_sim > self.dedup_similarity_threshold:
                    removed += 1
                else:
                    kept.append(hit)
        elif candidates:
            # 无工作记忆时仅应用闸 1
            kept = [
                h
                for h in candidates
                if _text_hash(f"Q: {h.question}\nA: {h.answer}") not in wm_hashes
            ]

        kept = kept[: self.episodic_top_m]

        # --- 两段式拼接（05 §5.4 格式）---
        parts: list[str] = []
        if recent:
            turns = "\n".join(f"Q: {h['q']}\nA: {h['a']}" for h in recent)
            parts.append(f"[历史{len(recent)}轮]\n{turns}")
        if kept:
            memories = "\n".join(
                f"- Q: {h.question} A: {h.answer}" for h in kept
            )
            parts.append(f"[相关记忆{len(kept)}条]\n{memories}")

        return MemoryContext(
            injected_working_turns=len(recent),
            episodic_hits=len(kept),
            dedup_removed=removed,
            context_text="\n\n".join(parts),
        )
