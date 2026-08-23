"""
清洗管道编排器（架构 P3 规则链模式 · 05 §5.6 · 单元 1.3）。

cleaning_rules.yaml 加载（pydantic 校验）→ priority 排序执行 →
敏感信息脱敏 → 质量门控（quality_score 与结果入 cleaned_meta）。
清洗规则的输入输出均为 CleanedDocument（架构 §3.1）；入口负责
ParsedDocument → CleanedDocument 转换。
"""

# --- 标准库 ---
import logging
from typing import Any

# --- 本地模块 ---
from app.core.models import CleanedDocument, ParsedDocument
from app.pipeline.cleaning.quality_gate import QualityGate, mask_pii
from app.pipeline.cleaning.rules.base_rule import CleaningRule
from app.pipeline.cleaning.rules.fix_encoding import FixEncodingRule
from app.pipeline.cleaning.rules.normalize_punctuation import NormalizePunctuationRule
from app.pipeline.cleaning.rules.normalize_whitespace import NormalizeWhitespaceRule
from app.pipeline.cleaning.rules.remove_boilerplate import RemoveBoilerplateRule
from app.pipeline.cleaning.rules.remove_image_refs import RemoveImageRefsRule
from app.pipeline.config import CleaningPipelineConfig, load_cleaning_config

logger = logging.getLogger(__name__)

# 规则注册表：name → 规则类（YAML 登记的规则必须在此注册）
RULE_REGISTRY: dict[str, type[CleaningRule]] = {
    "RemoveImageRefs": RemoveImageRefsRule,
    "RemoveBoilerplate": RemoveBoilerplateRule,
    "NormalizeWhitespace": NormalizeWhitespaceRule,
    "FixEncoding": FixEncodingRule,
    "NormalizePunctuation": NormalizePunctuationRule,
}


class CleaningPipeline:
    """清洗管道编排器。

    Attributes:
        gate: 质量门控检查器。
    """

    def __init__(self, gate: QualityGate | None = None) -> None:
        """初始化清洗管道。

        Args:
            gate: 质量门控实例（缺省自动创建）。
        """
        self._rules: list[CleaningRule] = []
        self._params: dict[str, dict[str, Any]] = {}
        self.gate = gate or QualityGate()

    def add_rule(self, rule: CleaningRule, params: dict[str, Any] | None = None) -> None:
        """注册一条清洗规则（按 priority 排序）。

        Args:
            rule: CleaningRule 实例。
            params: YAML 透传参数（process 的 config 入参）。

        Raises:
            TypeError: rule 非 CleaningRule 子类实例。
        """
        if not isinstance(rule, CleaningRule):
            raise TypeError(f"规则必须继承 CleaningRule: {type(rule)!r}")
        self._rules.append(rule)
        self._params[rule.name] = params or {}
        self._rules.sort(key=lambda r: r.priority)

    async def run(
        self,
        doc: ParsedDocument,
        config: dict[str, Any] | None = None,
    ) -> CleanedDocument:
        """执行清洗管道：转换 → 规则链 → 脱敏 → 质量门控。

        Args:
            doc: 待清洗的解析后文档。
            config: 附加运行时配置（与 YAML 参数合并，YAML 优先键同名时覆盖）。

        Returns:
            CleanedDocument（quality_score 与门控结果入 cleaned_meta）。
        """
        current = CleanedDocument(
            doc_id=doc.doc_id,
            text=doc.text,
            structure_tree=doc.structure_tree,
        )
        applied: list[str] = []
        for rule in self._rules:
            if not rule.enabled:
                continue
            merged = {**(config or {}), **self._params.get(rule.name, {})}
            try:
                current = await rule.process(current, merged)
                applied.append(rule.name)
            except Exception:
                logger.exception("清洗规则 %s 执行失败，跳过", rule.name)
                raise

        # 敏感信息脱敏（架构 P3 内容安全过滤）
        text, pii_hits = mask_pii(current.text)
        if pii_hits:
            current = current.model_copy(update={"text": text})

        report = self.gate.check(current)
        if report.is_valid:
            self.gate.register(current.text)
        meta = {
            "applied_rules": applied,
            "pii_masked": pii_hits,
            **self.gate.to_meta(report),
        }
        return current.model_copy(
            update={"quality_score": report.quality_score, "cleaned_meta": meta}
        )

    @property
    def rule_names(self) -> list[str]:
        """已注册规则名称（按执行顺序）。"""
        return [rule.name for rule in self._rules]


def build_cleaning_pipeline(
    config: CleaningPipelineConfig | None = None,
) -> CleaningPipeline:
    """按 cleaning_rules.yaml 构建清洗管道（fail-fast 校验）。

    Args:
        config: 清洗配置（缺省从默认 YAML 加载）。

    Returns:
        CleaningPipeline: 已装配规则链与门控的管道。

    Raises:
        SystemExit: YAML 缺失/校验失败；登记规则未注册。
    """
    cfg = config or load_cleaning_config()
    gate_cfg = cfg.quality_gate
    gate = QualityGate(
        min_length=gate_cfg.min_length,
        expected_languages={gate_cfg.language},
        dedup_threshold=gate_cfg.dedup_threshold,
        enable_pii_check=gate_cfg.enabled,
    )
    pipeline = CleaningPipeline(gate=gate)
    for rc in sorted(cfg.rules, key=lambda r: r.priority):
        cls = RULE_REGISTRY.get(rc.name)
        if cls is None:
            raise SystemExit(f"[fail-fast] cleaning_rules.yaml 登记了未注册规则: {rc.name}")
        rule = cls()
        rule.enabled = rc.enabled
        rule.priority = rc.priority
        pipeline.add_rule(rule, rc.rule_params())
    return pipeline
