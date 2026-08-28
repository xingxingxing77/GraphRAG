"""清洗规则集合。"""
from app.pipeline.cleaning.rules.base_rule import CleaningRule
from app.pipeline.cleaning.rules.fix_encoding import FixEncodingRule
from app.pipeline.cleaning.rules.normalize_punctuation import NormalizePunctuationRule
from app.pipeline.cleaning.rules.normalize_whitespace import NormalizeWhitespaceRule
from app.pipeline.cleaning.rules.remove_boilerplate import RemoveBoilerplateRule
from app.pipeline.cleaning.rules.remove_image_refs import RemoveImageRefsRule

__all__ = [
    "CleaningRule",
    "FixEncodingRule",
    "NormalizePunctuationRule",
    "NormalizeWhitespaceRule",
    "RemoveBoilerplateRule",
    "RemoveImageRefsRule",
]
