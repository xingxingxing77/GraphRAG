"""
质量门控（架构 P3 · 单元 1.3）。

对清洗后的文档执行最小长度、语言检测、SimHash 近似去重、
敏感信息脱敏四项检查，输出 quality_score 与门控结果
（写入 cleaned_meta，07 §8 断言）。近似去重自实现 SimHash，
不引入 datasketch（保持标准库 + 既有依赖）。
"""

# --- 标准库 ---
import hashlib
import re
from dataclasses import dataclass, field
from typing import Any

# --- 本地模块 ---
from app.core.models import CleanedDocument

# 敏感信息正则（02 §3.11 / 07 §9 脱敏口径：手机号 / 身份证 / 邮箱）
_PII_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("phone", re.compile(r"1[3-9]\d{9}")),
    ("id_card", re.compile(r"\d{17}[\dXx]")),
    ("email", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
]

_MASK = "***"


def mask_pii(text: str) -> tuple[str, int]:
    """对文本中的敏感信息脱敏为 ``***``。

    Args:
        text: 原始文本。

    Returns:
        (脱敏后文本, 命中次数)。
    """
    hits = 0
    for _, pat in _PII_PATTERNS:
        text, n = pat.subn(_MASK, text)
        hits += n
    return text, hits


def _simhash(text: str, hash_bits: int = 64) -> int:
    """计算文本的 SimHash 指纹（字符 3-gram 特征）。

    Args:
        text: 输入文本。
        hash_bits: 指纹位宽。

    Returns:
        SimHash 整数指纹。
    """
    tokens = [text[i : i + 3] for i in range(max(0, len(text) - 2))] or [text]
    vec = [0] * hash_bits
    for tok in tokens:
        digest = int(hashlib.md5(tok.encode("utf-8")).hexdigest(), 16)
        for i in range(hash_bits):
            if digest & (1 << i):
                vec[i] += 1
            else:
                vec[i] -= 1
    fingerprint = 0
    for i in range(hash_bits):
        if vec[i] > 0:
            fingerprint |= 1 << i
    return fingerprint


def _hamming(a: int, b: int) -> int:
    """两整数指纹的汉明距离。"""
    return bin(a ^ b).count("1")


@dataclass
class QualityReport:
    """质量检查报告。

    Attributes:
        is_valid: 文档是否通过质量检查。
        reasons: 不通过原因列表（空表示通过）。
        quality_score: 综合质量评分 [0.0, 1.0]。
    """

    is_valid: bool
    reasons: list[str] = field(default_factory=list)
    quality_score: float = 1.0


class QualityGate:
    """质量门控检查器（priority 99，始终最后执行）。

    Attributes:
        min_length: 文档最小允许字符数。
        expected_languages: 允许的语言代码集合。
        dedup_threshold: 近似重复相似度阈值。
        enable_pii_check: 是否启用敏感信息检测。
    """

    def __init__(
        self,
        min_length: int = 20,
        expected_languages: set[str] | None = None,
        dedup_threshold: float = 0.9,
        enable_pii_check: bool = True,
        hash_bits: int = 64,
    ) -> None:
        """初始化 QualityGate。

        Args:
            min_length: 最小字符数阈值（cleaning_rules.yaml 默认 20）。
            expected_languages: 允许语言集合，默认 {"zh"}（YAML language 字段）。
            dedup_threshold: SimHash 相似度阈值，默认 0.9。
            enable_pii_check: 是否启用 PII 检测。
            hash_bits: SimHash 位宽。
        """
        self.min_length = min_length
        self.expected_languages = expected_languages or {"zh"}
        self.dedup_threshold = dedup_threshold
        self.enable_pii_check = enable_pii_check
        self.hash_bits = hash_bits
        self._seen_fingerprints: list[int] = []

    def check(self, doc: CleanedDocument) -> QualityReport:
        """执行全部质量检查并返回报告。

        Args:
            doc: 清洗后的文档对象。

        Returns:
            QualityReport（is_valid / reasons / quality_score）。
        """
        reasons: list[str] = []
        score = 1.0

        ok_len, reason = self._check_min_length(doc.text)
        if not ok_len:
            reasons.append(reason)
            score -= 0.5

        ok_lang, reason = self._check_language(doc.text)
        if not ok_lang:
            reasons.append(reason)
            score -= 0.2

        ok_dup, reason = self._check_near_duplicate(doc.text)
        if not ok_dup:
            reasons.append(reason)
            score -= 0.3

        if self.enable_pii_check:
            ok_pii, reason = self._check_pii(doc.text)
            if not ok_pii:
                reasons.append(reason)
                score -= 0.1

        return QualityReport(
            is_valid=not reasons,
            reasons=reasons,
            quality_score=max(0.0, round(score, 4)),
        )

    def register(self, text: str) -> None:
        """登记文本指纹到去重库（供跨文档近似去重）。

        Args:
            text: 已接受文档的文本。
        """
        self._seen_fingerprints.append(_simhash(text, self.hash_bits))

    def _check_min_length(self, text: str) -> tuple[bool, str]:
        if len(text.strip()) < self.min_length:
            return False, f"文本长度不足 {self.min_length} 字符"
        return True, ""

    def _check_language(self, text: str) -> tuple[bool, str]:
        sample = text[:2000]
        if not sample.strip():
            return True, ""
        try:
            from langdetect import detect

            lang = detect(sample)
        except Exception:  # noqa: BLE001 - 检测失败不阻断
            return True, ""
        # langdetect 中文返回 zh-cn/zh-tw，统一归一为 zh 前缀比对
        normalized = {l.split("-")[0] for l in self.expected_languages}
        if lang.split("-")[0] not in normalized:
            return False, f"检测到语言 {lang}，不在允许范围 {sorted(self.expected_languages)}"
        return True, ""

    def _check_near_duplicate(self, text: str) -> tuple[bool, str]:
        fp = _simhash(text, self.hash_bits)
        for seen in self._seen_fingerprints:
            similarity = 1.0 - _hamming(fp, seen) / self.hash_bits
            if similarity >= self.dedup_threshold:
                return False, f"与已有文档近似重复（相似度 {similarity:.2f}）"
        return True, ""

    def _check_pii(self, text: str) -> tuple[bool, str]:
        hits = 0
        for label, pat in _PII_PATTERNS:
            if pat.search(text):
                hits += 1
        if hits:
            return False, f"检测到 {hits} 类敏感信息（已建议脱敏）"
        return True, ""

    def to_meta(self, report: QualityReport) -> dict[str, Any]:
        """将门控结果序列化为 cleaned_meta 片段。

        Args:
            report: 质量报告。

        Returns:
            供写入 CleanedDocument.cleaned_meta 的字典。
        """
        return {
            "quality_gate": {
                "is_valid": report.is_valid,
                "reasons": report.reasons,
            }
        }
