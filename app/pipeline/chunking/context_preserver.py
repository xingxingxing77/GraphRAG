"""
上下文保留策略。

为切分后的文档块注入上下文信息，包括：
- 标题路径前缀注入
- 父子文档引用关系
"""

# --- 标准库 ---
from typing import Any

# --- 本地模块 ---
from app.pipeline.base import Chunk


class ContextPreserver:
    """上下文保留策略。

    切分后的文档块可能丢失原始上下文（如所属标题、父文档信息），
    本类提供方法将这些上下文注入到 chunk 中，提升检索和生成质量。

    主要功能：
    - ``inject_title_path``：将标题路径作为前缀注入 chunk 内容。
    - ``add_parent_ref``：为 chunk 添加父文档引用。
    """

    def __init__(
        self,
        title_prefix_template: str = "[{title_path}]\n",
    ) -> None:
        """初始化 ContextPreserver。

        Args:
            title_prefix_template: 标题路径前缀模板，
                ``{title_path}`` 占位符会被实际路径替换。
        """
        self.title_prefix_template = title_prefix_template

    def inject_title_path(
        self,
        chunks: list[Chunk],
    ) -> list[Chunk]:
        """为每个 chunk 的内容前缀注入标题路径。

        例如，chunk 的 title_path 为 ``"清蒸鲈鱼 > 操作步骤"``，
        则其 content 前缀变为 ``"[清蒸鲈鱼 > 操作步骤]\\n..."``。

        Args:
            chunks: 待处理的 chunk 列表。

        Returns:
            标题路径已注入的 chunk 列表。
        """
        # TODO: 1. 遍历 chunks
        # TODO: 2. 若 chunk.title_path 非空，拼接前缀到 content
        # TODO: 3. 返回更新后的 chunk 列表
        raise NotImplementedError

    def add_parent_ref(
        self,
        chunks: list[Chunk],
        parent_id: str,
    ) -> list[Chunk]:
        """为每个 chunk 添加父文档引用。

        在 chunk 的 parent_ref 字段中记录父文档 ID，
        便于检索时回溯原始文档上下文。

        Args:
            chunks: 待处理的 chunk 列表。
            parent_id: 父文档的唯一标识（如文档哈希或路径）。

        Returns:
            父引用已注入的 chunk 列表。
        """
        # TODO: 1. 遍历 chunks
        # TODO: 2. 设置 chunk.parent_ref = parent_id
        # TODO: 3. 在 metadata 中记录 parent_id
        # TODO: 4. 返回更新后的 chunk 列表
        raise NotImplementedError
