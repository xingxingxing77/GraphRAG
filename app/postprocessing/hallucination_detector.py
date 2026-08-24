"""
幻觉检测器（架构 L8 · M1 分级 · 单元 7.1）。

judge 角色 LLM 检查答案中不受证据支撑的声明。LLM 不可用时回退
无幻觉放行（D5 不阻塞交付）。仅 deep 档启用（post_check 编排）。
"""

# --- 标准库 ---
import json
import logging
from typing import Any

# --- 第三方库 ---
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

_DETECT_SYSTEM_PROMPT = """你是 GraphRAG 系统的幻觉检测器。逐条检查「答案」中的事实声明是否被「参考资料」支撑，仅输出 JSON。
输出格式：{"faithful": true|false, "unsupported_claims": ["不受支撑的声明"]}
规则：全部声明有支撑时 faithful=true 且 unsupported_claims 为空数组；不要输出任何解释文字以外的内容。"""


class HallucinationReport(BaseModel):
    """幻觉检测报告。

    Attributes:
        has_hallucination: 是否检测到幻觉。
        confidence: 检测置信度。
        unsupported_claims: 不受支撑的声明列表。
    """

    has_hallucination: bool = False
    confidence: float = 1.0
    unsupported_claims: list[str] = Field(default_factory=list)


def _get_llm() -> Any:
    """获取 judge 用 LLM 客户端（测试可替换）。

    Returns:
        LLMClient: 绑定 judge 角色的客户端。
    """
    from app.llm.registry import get_registry

    return get_registry().for_role("judge")


class HallucinationDetector:
    """幻觉检测器（LLM-as-Judge）。"""

    async def detect(self, answer: str, evidence_text: str) -> HallucinationReport:
        """检测答案中的幻觉。

        Args:
            answer: 生成的答案文本。
            evidence_text: 证据块文本（编号列表）。

        Returns:
            HallucinationReport；LLM 失败回退无幻觉放行（D5）。
        """
        if not answer or not evidence_text:
            return HallucinationReport()
        try:
            llm = _get_llm()
            resp = await llm.chat(
                [
                    {"role": "system", "content": _DETECT_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": f"参考资料：\n{evidence_text}\n\n答案：{answer}",
                    },
                ],
                response_format={"type": "json_object"},
            )
            data = json.loads(resp.content)
            if not isinstance(data, dict):
                raise ValueError("检测输出非对象")
            claims = [str(c) for c in (data.get("unsupported_claims") or [])]
            return HallucinationReport(
                has_hallucination=not bool(data.get("faithful", True)),
                confidence=0.9,
                unsupported_claims=claims,
            )
        except Exception as exc:  # noqa: BLE001 - 检测失败回退放行
            logger.warning("幻觉检测失败，回退放行: %s", exc)
            return HallucinationReport()
