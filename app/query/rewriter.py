"""
HyDE 深度改写器（架构 L2 v3.1 · 单元 6.1 配套）。

仅 deep 档可选增强：生成假设性答案文本，用其向量检索语义相近的
真实文档。经 registry 角色调用（query_understanding），不持独立
LLM 客户端（v3.1 模块职责收敛）。失败回退原始查询（D5）。
"""

# --- 标准库 ---
import logging
from typing import Any

logger = logging.getLogger(__name__)

_HYDE_SYSTEM_PROMPT = """你是 GraphRAG 系统的 HyDE 改写器。针对用户查询写出一段假设性的答案文本（150 字以内），
用于以该文本的向量检索语义相近的真实文档。直接输出假设答案本身，不要解释。"""


def _get_llm() -> Any:
    """获取 HyDE 用 LLM 客户端（registry 角色，测试可替换）。

    Returns:
        LLMClient: 绑定 query_understanding 角色的客户端。
    """
    from app.llm.registry import get_registry

    return get_registry().for_role("query_understanding")


async def hyde_rewrite(query: str) -> str:
    """HyDE 假设性答案改写（deep 档可选增强）。

    Args:
        query: 用户查询（可为改写后主查询）。

    Returns:
        假设性答案文本；LLM 失败回退原始查询（D5）。
    """
    try:
        llm = _get_llm()
        resp = await llm.chat(
            [
                {"role": "system", "content": _HYDE_SYSTEM_PROMPT},
                {"role": "user", "content": query},
            ]
        )
        content = resp.content.strip()
        return content or query
    except Exception as exc:  # noqa: BLE001 - HyDE 失败回退原查询
        logger.warning("HyDE 改写失败，回退原始查询: %s", exc)
        return query
