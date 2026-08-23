"""
NER 实体抽取器。

使用命名实体识别（NER）技术从文本中提取实体，
返回实体名称和类型的列表，供图谱索引使用。
"""

# --- 标准库 ---
from typing import Any

# --- 第三方库 ---
# TODO: 选择并引入 NER 库（如 spaCy、transformers pipeline、GLiNER 等）

# --- 本地模块 ---
# 无本地依赖


class NEREntityExtractor:
    """NER 实体抽取器。

    从文本中识别命名实体（人名、地名、组织、食材等），
    返回结构化的实体列表，供下游关系增强器和图谱索引使用。

    Attributes:
        model_name: NER 模型名称/路径。
        entity_types: 要提取的实体类型白名单，None 表示全部。
        confidence_threshold: 实体识别置信度阈值。
    """

    def __init__(
        self,
        model_name: str = "zh_core_web_sm",
        entity_types: set[str] | None = None,
        confidence_threshold: float = 0.7,
    ) -> None:
        """初始化 NEREntityExtractor。

        Args:
            model_name: NER 模型标识符（spaCy 模型名或 HuggingFace 模型路径）。
            entity_types: 要提取的实体类型白名单（如 {"PERSON", "ORG", "FOOD"}），
                None 表示提取所有类型。
            confidence_threshold: 置信度阈值，低于此值的实体被过滤。
        """
        self.model_name = model_name
        self.entity_types = entity_types
        self.confidence_threshold = confidence_threshold
        self._model: Any = None  # TODO: 延迟加载 NER 模型

    async def extract(self, text: str) -> list[dict[str, str]]:
        """从文本中提取命名实体。

        Args:
            text: 待提取实体的文本。

        Returns:
            实体列表，每项为字典，包含：
            - ``name``: 实体名称。
            - ``type``: 实体类型（如 "PERSON"、"ORG"、"FOOD"）。
            - ``span``: 实体在文本中的位置范围（可选）。

        Example::

            [
                {"name": "清蒸鲈鱼", "type": "DISH"},
                {"name": "鲈鱼", "type": "INGREDIENT"},
            ]
        """
        # TODO: 1. 延迟加载 NER 模型（首次调用时）
        # TODO: 2. 对 text 执行 NER 推理
        # TODO: 3. 按 confidence_threshold 过滤
        # TODO: 4. 按 entity_types 白名单过滤
        # TODO: 5. 去重并格式化返回
        raise NotImplementedError

    def _load_model(self) -> None:
        """加载 NER 模型。

        根据 self.model_name 加载对应的 NER 模型实例，
        存储在 self._model 中。
        """
        # TODO: 根据 model_name 加载模型（spaCy / HuggingFace）
        raise NotImplementedError
