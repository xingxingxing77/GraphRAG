"""Qdrant 集合口径单一来源（审查 C3）。

业务集合（rag_{doc_type}）与记忆层集合（rag_cache/rag_episodic）共用
rag_ 前缀。任何「遍历 rag_* 集合做检索/清空/删除」的代码必须经本模块
判定排除记忆层：其 payload 只有 question/answer 等记忆字段，无
content/chunk_id/doc_id，混入检索会产出空内容高分配的伪证据
（历史问题与当前查询的 cosine 常 >0.9）。

历史口径分散在 pipeline_service（唯一正确排除）、tool_router 与
debug 端点（漏排除），本模块收敛后各处统一引用。
"""

# --- 记忆层集合（检索与业务遍历一律排除） ---
MEMORY_COLLECTIONS: tuple[str, ...] = ("rag_cache", "rag_episodic")

# 业务/记忆集合共用的前缀
COLLECTION_PREFIX = "rag_"


def is_memory_collection(name: str) -> bool:
    """判定是否记忆层集合。

    Args:
        name: 集合名。

    Returns:
        True 表示 rag_cache/rag_episodic 等记忆层集合。
    """
    return name in MEMORY_COLLECTIONS


def is_business_collection(name: str) -> bool:
    """判定是否业务向量集合（rag_{doc_type}，可安全检索/清空/删除）。

    Args:
        name: 集合名。

    Returns:
        True 表示业务集合（已排除记忆层）。
    """
    return name.startswith(COLLECTION_PREFIX) and not is_memory_collection(name)
