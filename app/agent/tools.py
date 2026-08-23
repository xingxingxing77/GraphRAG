"""
Agent 工具集定义。

使用 @tool 装饰器定义 LangGraph Agent 可调用的工具。
"""

# --- 第三方库 ---
from langchain_core.tools import tool

# --- 本地模块 ---
from app.retrieval.dense_retriever import RetrievalResult


@tool
def search_vector_store(query: str, top_k: int = 10) -> list[dict]:
    """在向量数据库中执行语义检索。

    Args:
        query: 搜索查询。
        top_k: 返回数量。

    Returns:
        检索结果列表。
    """
    # TODO: 调用 DenseRetriever 和 SparseRetriever
    raise NotImplementedError


@tool
def search_knowledge_graph(entity_names: list[str], depth: int = 2) -> list[dict]:
    """在知识图谱中执行图遍历检索。

    Args:
        entity_names: 实体名称列表。
        depth: 关系扩展深度。

    Returns:
        图检索结果列表。
    """
    # TODO: 调用 GraphRetriever
    raise NotImplementedError


@tool
def search_web(query: str, top_k: int = 5) -> list[dict]:
    """在 Web 上搜索外部知识。

    Args:
        query: 搜索查询。
        top_k: 返回数量。

    Returns:
        Web 搜索结果列表。
    """
    # TODO: 调用 WebRetriever
    raise NotImplementedError


@tool
def get_user_memory(user_id: str) -> dict:
    """获取用户长期记忆。

    Args:
        user_id: 用户 ID。

    Returns:
        用户记忆字典（preferences, past_summaries）。
    """
    # TODO: 从 Redis 读取用户记忆
    raise NotImplementedError


@tool
def update_user_memory(user_id: str, key: str, value: str) -> str:
    """更新用户长期记忆。

    Args:
        user_id: 用户 ID。
        key: 记忆键。
        value: 记忆值。

    Returns:
        操作结果消息。
    """
    # TODO: 写入 Redis 用户记忆
    raise NotImplementedError
