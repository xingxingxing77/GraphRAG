"""
实体提取器。

从查询中提取关键实体名称，供 Neo4j 图检索使用。
"""

# --- 标准库 ---
from dataclasses import dataclass, field

# --- 第三方库 ---
from langchain_core.language_models import BaseChatModel


@dataclass
class ExtractedEntity:
    """提取的实体信息。

    Attributes:
        name: 实体名称。
        entity_type: 实体类型（如人物、食材、菜名等）。
        confidence: 提取置信度。
    """

    name: str
    entity_type: str = ""
    confidence: float = 1.0


class EntityExtractor:
    """实体提取器。

    从用户查询中提取关键实体名，用于 Neo4j 图检索的实体匹配。
    支持 LLM 辅助提取和规则提取两种方式。
    """

    def __init__(self, llm: BaseChatModel | None = None) -> None:
        """初始化实体提取器。

        Args:
            llm: 可选的 LLM 实例。为 None 时使用规则提取。
        """
        self.llm = llm

    async def extract(self, query: str) -> list[ExtractedEntity]:
        """从查询中提取实体列表。

        Args:
            query: 用户查询文本。

        Returns:
            提取的实体列表。
        """
        # TODO: 如果 llm 可用，使用 LLM + Prompt 提取实体
        # TODO: 否则使用正则/词典等规则方式提取
        raise NotImplementedError

    async def extract_with_llm(self, query: str) -> list[ExtractedEntity]:
        """使用 LLM 提取实体。

        Args:
            query: 用户查询文本。

        Returns:
            提取的实体列表。
        """
        # TODO: 构建 NER Prompt，要求 LLM 返回结构化实体列表
        raise NotImplementedError
