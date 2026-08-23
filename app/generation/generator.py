"""
流式答案生成器。

基于检索证据使用 LLM 流式生成答案，支持 SSE 推送。
"""

# --- 标准库 ---
from typing import AsyncGenerator

# --- 第三方库 ---
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import SystemMessage, HumanMessage

# --- 本地模块 ---
from app.core.models import RetrievalResult


class StreamGenerator:
    """流式答案生成器。

    基于检索证据和系统 Prompt，使用 LLM 流式生成答案。
    """

    def __init__(self, llm: BaseChatModel) -> None:
        """初始化生成器。

        Args:
            llm: 用于生成的 LLM 实例。
        """
        self.llm = llm

    async def generate_stream(
        self,
        query: str,
        evidence: list[RetrievalResult],
    ) -> AsyncGenerator[str, None]:
        """流式生成答案。

        Args:
            query: 用户查询。
            evidence: 检索证据列表。

        Yields:
            逐 Token 生成的文本片段。
        """
        # TODO: 构建包含证据的 Prompt
        # TODO: 调用 llm.astream() 流式生成
        # TODO: yield 每个 token
        raise NotImplementedError

    async def generate(
        self,
        query: str,
        evidence: list[RetrievalResult],
    ) -> str:
        """同步生成完整答案。

        Args:
            query: 用户查询。
            evidence: 检索证据列表。

        Returns:
            生成的完整答案文本。
        """
        # TODO: 构建 Prompt 并调用 LLM
        raise NotImplementedError
