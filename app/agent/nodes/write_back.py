"""
写侧尾节点（单元 8.3，05 §5.4 幂等三件事，10.4 时序对齐）。

答案定稿后幂等执行三项写入（任一失败互不阻塞、不抛错）：
1. wm：LPUSH+LTRIM 工作记忆一轮问答；
2. episodic：rag_episodic 情景片段入库；
3. rag_cache：仅当「首轮问答且未降级」时写入 L1 语义缓存
   （H2：含个性化上下文的答案不入缓存——多轮会话注入了
   工作记忆/情景，视为个性化；degraded 答案按 D5 不落缓存）。
"""

# --- 标准库 ---
import logging

# --- 本地模块 ---
from app.agent.state import AgentState
from app.memory.semantic_cache import L1Entry

import app.api.deps as deps

logger = logging.getLogger(__name__)


def _matched_doc_ids(state: AgentState) -> list[str]:
    """从累积证据提取去重 doc_id（rag_cache 反查失效联动依据）。

    M5：doc_id 优先读顶层字段（fulltext 路的 doc_id 不在 metadata），
    metadata 作回退；兼容 RetrievalResult 对象与 checkpoint 反序列化
    后的 dict 两种形态。
    """
    doc_ids: list[str] = []
    for evidence in state.get("retrieved_evidence", []):
        metadata = getattr(evidence, "metadata", None)
        if metadata is None and isinstance(evidence, dict):
            metadata = evidence.get("metadata")
        doc_id = getattr(evidence, "doc_id", None)
        if doc_id is None and isinstance(evidence, dict):
            doc_id = evidence.get("doc_id")
        if not doc_id:
            doc_id = (metadata or {}).get("doc_id")
        if doc_id and str(doc_id) not in doc_ids:
            doc_ids.append(str(doc_id))
    return doc_ids


async def write_back_node(state: AgentState) -> dict[str, object]:
    """执行写侧三件事（幂等：重复执行结果一致）。

    Args:
        state: 终态 Agent 状态（answer/citations/original_query 等）。

    Returns:
        空增量 dict（写入副作用在存储层）。
    """
    answer = str(state.get("answer", ""))
    if not answer or state.get("degraded", False):
        return {}  # 空答案/降级作答不落任何记忆与缓存（D5/H2）

    try:
        stack = await deps.get_memory_stack()
    except Exception as exc:  # noqa: BLE001 - 存储不可达不影响应答交付
        logger.warning("write_back 初始化失败，跳过写侧三件事: %s", exc)
        return {}

    session_id = str(state.get("session_id", "anon-session"))
    user_id = str(state.get("user_id", "anon-user"))
    question = str(state.get("original_query", state.get("query", "")))

    history_len = 0
    try:
        history_len = len(await stack.working_memory.get_history(session_id))
        # 1) 工作记忆
        await stack.working_memory.add_exchange(session_id, question, answer)
        # 2) 情景记忆（turn_seq 取写入前长度 +1，重放幂等由 point ID 保证）
        await stack.episodic.add(
            session_id, user_id, history_len + 1, question, answer
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("wm/episodic 写入失败: %s", exc)

    # 3) L1 缓存：多轮会话（已注入个性化上下文）跳过（H2）
    if history_len == 0:
        try:
            usage = state.get("token_usage") or []
            await stack.semantic_cache.set_l1(
                L1Entry(
                    question=question,
                    answer=answer,
                    citations=list(state.get("citations", [])),
                    matched_doc_ids=_matched_doc_ids(state),
                    latency_tier=str(state.get("latency_tier", "standard")),
                    model=str(usage[-1].model) if usage else "",
                )
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("rag_cache 写入失败: %s", exc)
    return {}
