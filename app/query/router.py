"""
查询意图路由器。

对用户查询进行意图分类，决定后续的检索策略组合。
"""

# --- 标准库 ---
from enum import Enum

# --- 本地模块 ---
from app.api.models import QueryIntent


class QueryRouter:
    """查询意图路由器。

    将用户查询分类为不同的意图类型，以选择最优的检索策略。

    意图类型:
        - FACT: 简单事实型 -> 向量优先
        - MULTI_HOP: 多跳推理型 -> 图谱优先
        - COMPARISON: 对比型 -> 向量 + 图谱
        - CHITCHAT: 闲聊型 -> 跳过检索
    """

    async def classify(self, query: str) -> QueryIntent:
        """分类查询意图。

        Args:
            query: 用户查询文本。

        Returns:
            QueryIntent: 识别的意图类型。
        """
        # TODO: 使用轻量 LLM（Qwen2.5-7B）或规则引擎进行意图分类
        raise NotImplementedError

    def get_retrieval_strategy(self, intent: QueryIntent) -> dict[str, float]:
        """根据意图类型返回检索权重配置。

        Args:
            intent: 查询意图类型。

        Returns:
            各检索器权重字典，如 {"dense": 0.4, "sparse": 0.2, "graph": 0.3, "web": 0.1}。
        """
        # TODO: 根据意图类型返回不同的权重配置
        raise NotImplementedError
