"""
语义增强器（架构 P5 语义增强 · ROI 分级 · 单元 2.2）。

按 ROI 分级使用（架构 P5 表）：
- keyword_extract：轻量（频率统计，零外部依赖），所有文档默认使用；
- summary_generate / hypothetical_questions：重度（LLM），仅高价值文档，
  由 HighValueFilter（J15）判定资格；LLM 实现随模型接入单元落地。

J15 ROI 判定：类别白名单打底（冷启动可用）+ 访问计数叠加
（运行期自适应），两套机制**并集**生效。
"""

# --- 标准库 ---
import re
from typing import Any, Protocol

# --- 本地模块 ---
from app.core.models import Chunk, EnrichedChunk

# 中文连续片段（用于 n-gram 切分） / ASCII 单词
_CJK_RUN_PATTERN: re.Pattern[str] = re.compile(r"[\u4e00-\u9fff]+")
_ASCII_WORD_PATTERN: re.Pattern[str] = re.compile(r"[A-Za-z][A-Za-z0-9_-]{1,}")

# 中文 n-gram 长度窗口（无分词依赖下的轻量策略）
_CJK_NGRAM_SIZES: tuple[int, ...] = (2, 3, 4)

# 高频停用词（轻量过滤，避免无意义关键词）
_STOPWORDS: frozenset[str] = frozenset(
    {
        "我们", "你们", "他们", "可以", "如果", "然后", "或者", "因为",
        "所以", "这个", "那个", "一个", "就是", "不是", "还是", "以及",
        "进行", "使用", "加入", "适量", "少许", "左右", "即可", "备用",
        "the", "and", "for", "with", "this", "that",
    }
)


class LLMServiceLike(Protocol):
    """LLM 服务协议接口（重度增强方法依赖，随模型接入单元注入）。"""

    async def generate(self, prompt: str, **kwargs: Any) -> str:
        """调用 LLM 生成文本。"""
        ...


class KeywordExtractor:
    """轻量关键词提取器（频率统计，所有文档默认使用）。

    Attributes:
        top_k: 返回关键词数量上限。
        min_token_len: 最短 token 长度（字符）。
    """

    def __init__(self, top_k: int = 8, min_token_len: int = 2) -> None:
        """初始化提取器。

        Args:
            top_k: 关键词数量上限。
            min_token_len: 最短 token 长度。
        """
        self.top_k = top_k
        self.min_token_len = min_token_len

    def extract(self, text: str) -> list[str]:
        """提取关键词（频次降序，去停用词）。

        中文无分词依赖：对 CJK 连续片段取 2-4 字 n-gram 统计频次；
        ASCII 单词直接作为候选。

        Args:
            text: chunk 文本内容。

        Returns:
            关键词字符串列表（≤ top_k）。
        """
        freq: dict[str, int] = {}
        # 中文 n-gram 候选
        for run_match in _CJK_RUN_PATTERN.finditer(text):
            run = run_match.group(0)
            if len(run) <= max(_CJK_NGRAM_SIZES):
                candidates = [run] if len(run) >= self.min_token_len else []
            else:
                candidates = [
                    run[i : i + n]
                    for n in _CJK_NGRAM_SIZES
                    for i in range(len(run) - n + 1)
                ]
            for token in candidates:
                if token in _STOPWORDS:
                    continue
                freq[token] = freq.get(token, 0) + 1
        # ASCII 单词候选
        for m in _ASCII_WORD_PATTERN.finditer(text):
            token = m.group(0)
            if len(token) < self.min_token_len or token.lower() in _STOPWORDS:
                continue
            freq[token] = freq.get(token, 0) + 1
        ranked = sorted(freq.items(), key=lambda kv: (-kv[1], kv[0]))
        return [token for token, _ in ranked[: self.top_k]]


class HighValueFilter:
    """高价值文档判定器（J15：白名单打底 + 访问计数叠加，并集生效）。

    Attributes:
        categories: 类别白名单（冷启动打底）。
        min_access_count: 访问计数阈值（运行期叠加）。
    """

    def __init__(
        self,
        categories: list[str] | None = None,
        min_access_count: int = 10,
    ) -> None:
        """初始化判定器。

        Args:
            categories: 类别白名单（缺省空 = 白名单不命中）。
            min_access_count: 访问计数阈值。
        """
        self.categories = set(categories or [])
        self.min_access_count = min_access_count

    def is_high_value(self, category: str, access_count: int = 0) -> bool:
        """判定文档是否值得 LLM 重度增强。

        两套机制并集：类别在白名单 **或** 访问计数达阈值。

        Args:
            category: 文档业务分类。
            access_count: 累计检索命中次数。

        Returns:
            True 表示进入高价值增强队列。
        """
        in_whitelist = category in self.categories
        over_threshold = access_count >= self.min_access_count
        return in_whitelist or over_threshold


class SemanticEnricher:
    """语义增强器（关键词提取已落地；摘要/HyDE 随 LLM 接入落地）。

    Attributes:
        keyword_extractor: 轻量关键词提取器。
        high_value_filter: J15 高价值判定器。
        llm_service: LLM 服务实例（可选，重度方法需要）。
    """

    SUPPORTED_METHODS: set[str] = {
        "keyword_extract",
        "summary_generate",
        "hypothetical_questions",
    }

    def __init__(
        self,
        llm_service: LLMServiceLike | None = None,
        keyword_extractor: KeywordExtractor | None = None,
        high_value_filter: HighValueFilter | None = None,
    ) -> None:
        """初始化 SemanticEnricher。

        Args:
            llm_service: LLM 服务（重度方法需要；缺省则重度方法不可用）。
            keyword_extractor: 关键词提取器（缺省自动创建）。
            high_value_filter: 高价值判定器（缺省自动创建）。
        """
        self.llm_service = llm_service
        self.keyword_extractor = keyword_extractor or KeywordExtractor()
        self.high_value_filter = high_value_filter or HighValueFilter()

    async def enrich(
        self,
        chunk: EnrichedChunk,
        category: str = "",
        access_count: int = 0,
    ) -> EnrichedChunk:
        """对 EnrichedChunk 执行语义增强。

        关键词提取对所有文档生效；摘要/HyDE 仅对高价值文档
        且 LLM 可用时执行（当前为骨架，随模型接入单元落地）。

        Args:
            chunk: 待增强的 EnrichedChunk。
            category: 文档分类（J15 白名单判定输入）。
            access_count: 访问计数（J15 叠加判定输入）。

        Returns:
            语义增强后的 EnrichedChunk（keywords 已填充）。
        """
        keywords = self.keyword_extractor.extract(chunk.chunk.content)
        updates: dict[str, Any] = {"keywords": keywords}

        if self.high_value_filter.is_high_value(category, access_count):
            # TODO(模型接入单元): summary_generate —— LLM 生成摘要写入 updates["summary"]
            # TODO(模型接入单元): hypothetical_questions —— HyDE 假设性问题
            pass

        return chunk.model_copy(update=updates)
