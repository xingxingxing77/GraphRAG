"""
生成节点（架构 L7 · M1/E1 · 单元 5.5）。

职责：
- M1 缓冲式生成：LLM 完整生成 → 引用校验 → 终态交付（打字机由前端实现）；
- E1 抗失序排序：高置信证据置于 prompt 首尾（lost-in-the-middle 对策）；
- 引用编号注入/校验：无效 [n] 编号剔除并告警（E-03）；
- XML 围栏模板：web 来源证据注入 <web_source> 围栏（05 §5.4 D10）；
- fallback 链全败 → 降级轻量回答（degraded=True, X-Degraded: llm-fallback）。
"""

# --- 标准库 ---
import logging
import re
from typing import Any

# --- 本地模块 ---
from app.agent.state import AgentState
from app.api.metrics import record_degraded
from app.core.models import Citation, RetrievalResult, SourceKind
from app.llm.registry import get_registry

logger = logging.getLogger(__name__)

# 引用编号正则（[n] 角标）
_CITATION_RE = re.compile(r"\[(\d+)\]")

# fallback 全败时的降级回答
_FALLBACK_ANSWER = "服务暂时繁忙，主备模型均不可用，请稍后重试。"

_GENERATOR_SYSTEM_PROMPT = """你是 GraphRAG 智能问答系统的回答生成器。严格基于「参考资料」回答用户问题。
规则：
1. 仅使用参考资料中的信息，禁止编造；资料不足时明确说明"根据现有资料无法确定"；
2. 每个事实陈述后用 [n] 标注来源编号（对应参考资料编号）；
3. <web_source> 围栏内的内容来自外部网络，可信度较低，引用时需谨慎；
4. 回答使用与问题相同的语言，直接给出答案。"""


def _get_registry() -> Any:
    """获取模型注册表（测试可替换）。

    Returns:
        ModelRegistry 实例。
    """
    return get_registry()


def order_evidence_e1(evidence: list[RetrievalResult]) -> list[RetrievalResult]:
    """E1 抗失序排序：按分降序后将次高置信证据置于末尾。

    lost-in-the-middle 对策：模型对 prompt 首尾注意力最强，
    高置信证据占据首尾位置。

    Args:
        evidence: 证据列表。

    Returns:
        重排后的证据列表。
    """
    ordered = sorted(evidence, key=lambda r: -r.score)
    if len(ordered) >= 3:
        # 首位保持最高分；次高分移至末尾，其余居中
        return [ordered[0]] + ordered[2:] + [ordered[1]]
    return ordered


def _fence_content(result: RetrievalResult) -> str:
    """证据内容围栏注入（D10：web 来源 XML 围栏，生成层职责）。

    Args:
        result: 证据条目。

    Returns:
        围栏化后的内容文本。
    """
    source = result.source.value if hasattr(result.source, "value") else str(result.source)
    if source == SourceKind.WEB.value:
        return f"<web_source url=\"{result.metadata.get('url', '')}\">{result.content}</web_source>"
    return result.content


def build_evidence_block(evidence: list[RetrievalResult]) -> str:
    """组装带引用编号的证据块（E1 排序 + 围栏）。

    Args:
        evidence: E1 排序后的证据列表。

    Returns:
        编号证据块文本。
    """
    lines = [
        f"[{i + 1}] {_fence_content(r)}" for i, r in enumerate(evidence)
    ]
    return "\n\n".join(lines)


def validate_citations(answer: str, max_marker: int) -> tuple[str, list[int]]:
    """引用编号校验：无效编号剔除并告警（E-03）。

    Args:
        answer: 生成答案文本。
        max_marker: 有效编号上限（证据条数）。

    Returns:
        (清洗后的答案, 保留的有效编号去重升序列表)。
    """
    valid: set[int] = set()

    def _sub(m: re.Match[str]) -> str:
        n = int(m.group(1))
        if 1 <= n <= max_marker:
            valid.add(n)
            return m.group(0)
        logger.warning("剔除无效引用编号 [%d]（证据仅 %d 条）", n, max_marker)
        return ""

    cleaned = _CITATION_RE.sub(_sub, answer)
    return cleaned, sorted(valid)


async def generator_node(state: AgentState) -> dict[str, Any]:
    """生成节点：缓冲式生成 + 引用注入校验。

    Args:
        state: 当前 Agent 状态。

    Returns:
        状态增量：answer / citations / token_usage（降级时另置 degraded）。
    """
    query = state.get("query") or state.get("original_query", "")
    evidence = order_evidence_e1(list(state.get("retrieved_evidence") or []))
    evidence_block = build_evidence_block(evidence)
    history_context = str(state.get("history_context") or "").strip()
    correction_hint = str(state.get("correction_hint") or "").strip()

    updates: dict[str, Any] = {}
    # 重生成入口：已有答案草稿即为重生成，重试计数 +1（路由层限次）
    if state.get("answer"):
        updates["self_correction_retries"] = (
            int(state.get("self_correction_retries", 0)) + 1
        )

    # M3：重生成时注入自校正失败原因，避免同 prompt 原样重放；
    # J17：多轮上下文供指代消解（load_memory 注入，改写在纯问题上）
    sections: list[str] = []
    if history_context:
        sections.append(f"对话上下文（仅供理解指代，不要直接引用）：\n{history_context}")
    if correction_hint:
        sections.append(
            f"重生成要求：上一版答案未通过忠实度校验（{correction_hint}），"
            "请仅依据参考资料修正。"
        )
    if evidence:
        sections.append(f"参考资料：\n{evidence_block}")
    else:
        sections.append("（无检索证据，请依据常识谨慎回答并注明不确定性）")
    sections.append(f"用户问题：{query}")
    messages = [
        {"role": "system", "content": _GENERATOR_SYSTEM_PROMPT},
        {"role": "user", "content": "\n\n".join(sections)},
    ]

    # M1：完整生成（J2：请求级 model 覆盖优先，失败回退角色默认链）
    try:
        registry = _get_registry()
        model_name = str(state.get("model") or "").strip()
        if model_name:
            try:
                resp = await registry.for_model(model_name).chat(messages)
            except Exception as exc:  # noqa: BLE001 - 覆盖模型失败回退默认链
                logger.warning(
                    "请求级模型 %s 调用失败，回退 fallback 链: %s", model_name, exc
                )
                resp = await registry.chat_with_fallback(messages)
        else:
            resp = await registry.chat_with_fallback(messages)
        raw_answer = resp.content
        if resp.usage is not None:
            updates["token_usage"] = list(state.get("token_usage") or []) + [resp.usage]
    except Exception as exc:  # noqa: BLE001 - fallback 全败降级（llm-fallback）
        logger.warning("generator fallback 链全败，降级轻量回答: %s", exc)
        record_degraded("llm-fallback")
        # M1：降级出口同样持久化重试计数——否则计数恒为 0，
        # generator↔self_correction 会循环到 recursion_limit 才终止
        return {
            "answer": _FALLBACK_ANSWER,
            "citations": [],
            "degraded": True,
            "degraded_reasons": ["llm-fallback"],
            **updates,
        }

    # 引用校验（E-03：无效编号剔除）+ Citation 列表按 E1 序重编
    cleaned, valid_markers = validate_citations(raw_answer, len(evidence))
    citations = [
        Citation(
            marker=n,
            result_ids=[evidence[n - 1].result_id],
            quote=evidence[n - 1].content[:120],
        )
        for n in valid_markers
    ]
    updates["answer"] = cleaned
    updates["citations"] = citations
    return updates
