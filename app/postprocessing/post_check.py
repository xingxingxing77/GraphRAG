"""
后处理分级编排（架构 L8 · M1 分级 · 单元 7.1）。

分级启用矩阵（准出）：
- fast/standard：跳过忠实度校验与幻觉检测（延迟优先）；
- deep：忠实度评分 → 低于阈值触发幻觉检测定位不受支撑声明；
- 校验 LLM 重试耗尽/不可用：degraded=True 放行（不阻塞交付，D5）。
"""

# --- 标准库 ---
import logging
from typing import Any

# --- 本地模块 ---
from app.core.models import RetrievalResult
from app.postprocessing.faithfulness_scorer import FaithfulnessScorer
from app.postprocessing.hallucination_detector import (
    HallucinationDetector,
    HallucinationReport,
)

logger = logging.getLogger(__name__)

# 送评证据条数上限（控 prompt 体积）
_MAX_EVIDENCE_FOR_CHECK = 5


class PostCheckResult:
    """后处理分级校验结果。

    Attributes:
        enabled: 本档是否启用校验（仅 deep）。
        score: 忠实度分数（未启用时 1.0）。
        report: 幻觉检测报告（未触发时 None）。
        degraded: 校验链路降级标记（重试耗尽/LLM 不可用）。
    """

    def __init__(
        self,
        enabled: bool,
        score: float = 1.0,
        report: HallucinationReport | None = None,
        degraded: bool = False,
    ) -> None:
        """初始化结果。

        Args:
            enabled: 是否启用校验。
            score: 忠实度分数。
            report: 幻觉检测报告。
            degraded: 降级标记。
        """
        self.enabled = enabled
        self.score = score
        self.report = report
        self.degraded = degraded


def build_evidence_text(evidence: list[RetrievalResult]) -> str:
    """组装送评证据文本（Top-N 编号列表）。

    Args:
        evidence: 检索证据列表。

    Returns:
        编号证据块文本。
    """
    lines = [
        f"[{i + 1}] {r.content[:200]}"
        for i, r in enumerate(evidence[:_MAX_EVIDENCE_FOR_CHECK])
    ]
    return "\n".join(lines)


async def run_post_check(
    answer: str,
    evidence: list[RetrievalResult],
    latency_tier: str,
    scorer: FaithfulnessScorer | None = None,
    detector: HallucinationDetector | None = None,
) -> PostCheckResult:
    """后处理分级校验入口（M1 分级）。

    Args:
        answer: 生成的答案文本。
        evidence: 检索证据列表。
        latency_tier: 执行档位（fast/standard/deep）。
        scorer: 忠实度评分器（缺省新建）。
        detector: 幻觉检测器（缺省新建）。

    Returns:
        PostCheckResult：fast/standard 跳过（enabled=False）；
        deep 执行评分 + 条件检测。
    """
    if latency_tier != "deep":
        return PostCheckResult(enabled=False)

    scorer = scorer or FaithfulnessScorer()
    detector = detector or HallucinationDetector()
    evidence_text = build_evidence_text(evidence)

    score = await scorer.score(answer, evidence_text)
    report: HallucinationReport | None = None
    if not scorer.is_faithful(score):
        # 低分触发幻觉检测：定位不受支撑声明（供重生成注入）
        report = await detector.detect(answer, evidence_text)
    return PostCheckResult(enabled=True, score=score, report=report)
