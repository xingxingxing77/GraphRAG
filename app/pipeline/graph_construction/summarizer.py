"""
G5 分层社区摘要（架构 P7-G5 · 单元 2.6）。

- 叶子社区：LLM 以「实体清单 + 关系清单」生成 ≈200 字摘要；
- 父社区：聚合子社区摘要再摘要，逐层向上；
- LLM 不可用时退化为抽取式摘要（实体清单拼接），不阻断管道。

Global Search 基础：摘要写入 Qdrant（source=global）与 Neo4j
(:Community)，由 2.6 存储步骤与阶段 3 检索器衔接。
"""

# --- 标准库 ---
import logging

# --- 本地模块 ---
from app.core.models import CommunityRecord
from app.llm.client import LLMClient

logger = logging.getLogger(__name__)

# 摘要长度目标（架构 G5：叶子社区 ≈200 字）
_LEAF_SUMMARY_PROMPT = """你是知识图谱摘要器。根据社区内的实体与关系清单，生成约 200 字的中文主题摘要，概括该社区覆盖的知识领域与核心内容。只输出摘要正文。

实体清单：
{members}

关系清单：
{relations}

摘要："""

_PARENT_SUMMARY_PROMPT = """你是知识图谱摘要器。以下是若干子社区的摘要，请聚合生成一段上层主题摘要（约 200 字），概括更宏观的知识领域。只输出摘要正文。

子社区摘要：
{child_summaries}

上层摘要："""

# 抽取式兜底摘要的最大实体数
_EXTRACTIVE_MAX_MEMBERS = 15


class CommunitySummarizer:
    """分层社区摘要器。

    Attributes:
        llm_client: LLM 客户端（None 时退化为抽取式摘要）。
    """

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        """初始化摘要器。

        Args:
            llm_client: LLM 客户端（可选）。
        """
        self.llm_client = llm_client

    async def summarize_leaf(
        self, members: list[str], relations: list[str]
    ) -> str:
        """生成叶子社区摘要。

        Args:
            members: 社区成员实体名列表。
            relations: 关系描述列表（如 "清蒸鲈鱼 -REQUIRES-> 鲈鱼"）。

        Returns:
            摘要文本。
        """
        if self.llm_client is None:
            return self._extractive_summary(members)
        prompt = _LEAF_SUMMARY_PROMPT.format(
            members="\n".join(f"- {m}" for m in members),
            relations="\n".join(f"- {r}" for r in relations) or "（无）",
        )
        return await self._generate(prompt, fallback_members=members)

    async def summarize_parent(self, child_summaries: list[str]) -> str:
        """聚合子社区摘要生成父社区摘要。

        Args:
            child_summaries: 子社区摘要列表。

        Returns:
            父社区摘要文本。
        """
        if self.llm_client is None or not child_summaries:
            return "；".join(child_summaries)[:400]
        prompt = _PARENT_SUMMARY_PROMPT.format(
            child_summaries="\n".join(
                f"- {s}" for s in child_summaries
            )
        )
        return await self._generate(prompt, fallback_members=[])

    async def summarize_hierarchy(
        self,
        records: list[CommunityRecord],
        relations: list[str] | None = None,
    ) -> list[CommunityRecord]:
        """按层级为全部社区生成摘要（叶子 → 父层）。

        Args:
            records: 社区记录列表（detect 输出）。
            relations: 全局关系描述列表（叶子摘要上下文）。

        Returns:
            summary 已填充的社区记录列表（新对象）。
        """
        rels = relations or []
        result: list[CommunityRecord] = []
        leaf_summaries: dict[str, str] = {}

        # 先叶子层（level 升序处理，父层聚合子层）
        for record in sorted(records, key=lambda r: r.level):
            if record.level == 0:
                summary = await self.summarize_leaf(record.members, rels)
            else:
                child_ids = [
                    r.community_id for r in records if r.parent_id == record.community_id
                ]
                child_texts = [leaf_summaries[cid] for cid in child_ids if cid in leaf_summaries]
                summary = await self.summarize_parent(child_texts)
            leaf_summaries[record.community_id] = summary
            result.append(record.model_copy(update={"summary": summary}))
        return result

    async def _generate(self, prompt: str, fallback_members: list[str]) -> str:
        """调用 LLM 生成摘要（失败降级抽取式）。

        Args:
            prompt: 提示词。
            fallback_members: 降级摘要用成员列表。

        Returns:
            摘要文本。
        """
        assert self.llm_client is not None
        try:
            completion = await self.llm_client.chat(
                [{"role": "user", "content": prompt}], temperature=0.3
            )
            text = completion.content.strip()
            if text:
                return text
        except Exception as exc:  # noqa: BLE001 - 摘要失败降级
            logger.warning("社区摘要 LLM 调用失败，降级抽取式: %s", exc)
        return self._extractive_summary(fallback_members)

    @staticmethod
    def _extractive_summary(members: list[str]) -> str:
        """抽取式兜底摘要（实体清单拼接）。

        Args:
            members: 成员实体名列表。

        Returns:
            拼接式摘要文本。
        """
        shown = members[:_EXTRACTIVE_MAX_MEMBERS]
        suffix = f"等 {len(members)} 个实体" if len(members) > len(shown) else ""
        return f"本社区涵盖：{'、'.join(shown)}{suffix}。"
