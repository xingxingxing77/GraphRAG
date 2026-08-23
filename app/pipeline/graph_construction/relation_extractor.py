"""
G3 关系抽取（架构 P7-G3 · J13 · 单元 2.5）。

执行模型：本地轻量模型（models.yaml extractor 角色条目，J13 定案）；
方法：LLM few-shot 结构化抽取——输入 chunk 文本 + schema 白名单 +
开放区规则，输出三元组 JSON；规则/词典仅做兜底。

Prompt 要点（架构 G3）：给出白名单合法关系枚举与开放区标记规则；
要求标注 evidence（原文依据）；单 chunk 单次调用。
"""

# --- 标准库 ---
import json
import logging
import re

# --- 本地模块 ---
from app.core.models import RelationTriple
from app.llm.client import LLMClient
from app.pipeline.graph_construction.schema import GraphSchema

logger = logging.getLogger(__name__)

# JSON 数组兜底提取（LLM 输出可能带解释性前后缀）
_JSON_ARRAY_PATTERN: re.Pattern[str] = re.compile(r"\[.*\]", re.DOTALL)


def _build_prompt(chunk_text: str, schema: GraphSchema) -> str:
    """构建 few-shot 抽取提示词。

    Args:
        chunk_text: 待抽取的 chunk 文本。
        schema: 图 Schema（白名单关系枚举来源）。

    Returns:
        提示词字符串。
    """
    edges_desc = "\n".join(
        f"- ({e.from_type})-[:{e.type}]->({e.to_type})" for e in schema.edge_types
    )
    return f"""你是知识图谱关系抽取器。从给定文本中抽取实体间关系三元组。

合法白名单关系（仅限以下类型与方向）：
{edges_desc}

规则：
1. 只输出 JSON 数组，元素为 {{"head": 头实体, "relation": 关系类型, "tail": 尾实体, "evidence": 原文依据}}；
2. 关系类型必须在白名单内；无法匹配白名单的关系一律 relation="REL"；
3. 无关系时输出空数组 []；
4. head/tail 使用文本中的实体原文。

示例：
文本：清蒸鲈鱼需要鲈鱼一条，葱姜适量。
输出：[{{"head": "清蒸鲈鱼", "relation": "REQUIRES", "tail": "鲈鱼", "evidence": "需要鲈鱼一条"}}]

文本：
{chunk_text}

输出："""


class RelationExtractor:
    """LLM few-shot 关系抽取器（G3）。

    Attributes:
        schema: 图 Schema（白名单关系枚举）。
        llm_client: extractor 角色 LLM 客户端。
    """

    def __init__(self, schema: GraphSchema, llm_client: LLMClient) -> None:
        """初始化抽取器。

        Args:
            schema: 图 Schema。
            llm_client: extractor 角色 LLM 客户端（registry.for_role("extractor")）。
        """
        self.schema = schema
        self.llm_client = llm_client

    async def extract(self, chunk_text: str, chunk_id: str) -> list[RelationTriple]:
        """对单个 chunk 执行关系抽取。

        Args:
            chunk_text: chunk 文本。
            chunk_id: 块 ID（写入三元组 evidence_chunk_id）。

        Returns:
            RelationTriple 列表（抽取失败返回空列表，不阻断管道）。
        """
        prompt = _build_prompt(chunk_text, self.schema)
        try:
            completion = await self.llm_client.chat(
                [{"role": "user", "content": prompt}],
                temperature=0.0,
                response_format={"type": "json_object"},
            )
        except Exception as exc:  # noqa: BLE001 - 抽取失败降级为空
            logger.warning("关系抽取 LLM 调用失败（chunk=%s）: %s", chunk_id, exc)
            return []
        return self._parse_triples(completion.content, chunk_id)

    def _parse_triples(self, content: str, chunk_id: str) -> list[RelationTriple]:
        """解析 LLM 输出为三元组列表（容错）。

        Args:
            content: LLM 输出文本。
            chunk_id: 块 ID。

        Returns:
            合法的 RelationTriple 列表。
        """
        match = _JSON_ARRAY_PATTERN.search(content)
        if not match:
            return []
        try:
            items = json.loads(match.group(0))
        except json.JSONDecodeError:
            logger.warning("关系抽取输出 JSON 解析失败")
            return []
        if not isinstance(items, list):
            return []
        triples: list[RelationTriple] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            head = str(item.get("head") or "").strip()
            tail = str(item.get("tail") or "").strip()
            relation = str(item.get("relation") or "").strip()
            if not head or not tail or not relation:
                continue
            triples.append(
                RelationTriple(
                    head=head, relation=relation, tail=tail, evidence_chunk_id=chunk_id
                )
            )
        return triples
