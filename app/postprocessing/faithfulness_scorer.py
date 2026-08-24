"""
忠实度评分器（架构 L8 · M1 分级 · 单元 7.1）。

judge 角色 LLM 对答案-证据对打分（0-1）。经 registry 角色调用；
LLM 不可用时回退放行（score=1.0，D5 不阻塞交付）。分级启用：
仅 deep 档执行（standard/fast 跳过，见 run_post_check）。
"""

# --- 标准库 ---
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

_SCORE_SYSTEM_PROMPT = """你是 GraphRAG 系统的忠实度评审员。评估「答案」对「参考资料」的忠实程度，仅输出 JSON。
输出格式：{"score": 0.0-1.0}
评分标准：1.0 全部事实有资料支撑；0.5-0.9 主体有支撑、少量细节无出处；<0.5 明显编造或矛盾。
不要输出任何解释文字以外的内容。"""


def _get_llm() -> Any:
    """获取 judge 用 LLM 客户端（测试可替换）。

    Returns:
        LLMClient: 绑定 judge 角色的客户端。
    """
    from app.llm.registry import get_registry

    return get_registry().for_role("judge")


class FaithfulnessScorer:
    """忠实度评分器（LLM-as-Judge）。

    Attributes:
        threshold: 忠实度阈值（低于此值判定不忠实）。
    """

    def __init__(self, threshold: float = 0.7) -> None:
        """初始化忠实度评分器。

        Args:
            threshold: 忠实度阈值。
        """
        self.threshold = threshold

    async def score(self, answer: str, evidence_text: str) -> float:
        """计算答案的忠实度分数。

        Args:
            answer: 生成的答案文本。
            evidence_text: 证据块文本（编号列表）。

        Returns:
            忠实度分数 [0.0, 1.0]；LLM 失败回退 1.0（D5 放行）。
        """
        if not answer or not evidence_text:
            return 1.0
        try:
            llm = _get_llm()
            resp = await llm.chat(
                [
                    {"role": "system", "content": _SCORE_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": f"参考资料：\n{evidence_text}\n\n答案：{answer}",
                    },
                ],
                response_format={"type": "json_object"},
            )
            data = json.loads(resp.content)
            raw = data.get("score") if isinstance(data, dict) else None
            if raw is None:
                raise ValueError("score 字段缺失")
            return max(0.0, min(1.0, float(raw)))
        except Exception as exc:  # noqa: BLE001 - 评分失败回退放行
            logger.warning("忠实度评分失败，回退放行: %s", exc)
            return 1.0

    def is_faithful(self, score: float) -> bool:
        """判断忠实度分数是否通过阈值。

        Args:
            score: 忠实度分数。

        Returns:
            True 表示忠实度达标。
        """
        return score >= self.threshold
