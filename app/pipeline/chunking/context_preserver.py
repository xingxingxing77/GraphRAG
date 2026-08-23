"""
上下文保留策略（架构 P4 上下文保留 · 单元 2.1）。

为切分后的文档块注入上下文信息：
- 标题路径前缀注入（prefix_injection）：块内容头部拼接 title_path；
- 父子文档引用（parent_ref）：metadata 记录父文档 ID，检索时可回溯。

注意：position 定位始终指向原文档区间；前缀注入仅扩充 content，
不修改 position（检索命中后可按偏移回原文定位）。
"""

# --- 本地模块 ---
from app.core.models import Chunk


class ContextPreserver:
    """上下文保留策略。

    Attributes:
        title_prefix_template: 标题路径前缀模板，
            ``{title_path}`` 占位符会被 " > " 连接的路径替换。
    """

    def __init__(self, title_prefix_template: str = "[{title_path}]\n") -> None:
        """初始化 ContextPreserver。

        Args:
            title_prefix_template: 前缀模板（含 {title_path} 占位符）。
        """
        self.title_prefix_template = title_prefix_template

    def inject_title_path(self, chunks: list[Chunk]) -> list[Chunk]:
        """为每个 chunk 的内容前缀注入标题路径。

        例：title_path=["清蒸鲈鱼","操作步骤"] 的块，content 前缀变为
        ``[清蒸鲈鱼 > 操作步骤]\\n``。空 title_path 的块不注入。

        Args:
            chunks: 待处理的 chunk 列表。

        Returns:
            标题路径已注入的 chunk 列表（新对象，不改动入参）。
        """
        result: list[Chunk] = []
        for chunk in chunks:
            if not chunk.title_path:
                result.append(chunk)
                continue
            prefix = self.title_prefix_template.format(
                title_path=" > ".join(chunk.title_path)
            )
            result.append(chunk.model_copy(update={"content": prefix + chunk.content}))
        return result

    def add_parent_ref(self, chunks: list[Chunk], parent_id: str) -> list[Chunk]:
        """为每个 chunk 的 metadata 添加父文档引用。

        Args:
            chunks: 待处理的 chunk 列表。
            parent_id: 父文档唯一标识（doc_id）。

        Returns:
            metadata 含 parent_ref 的 chunk 列表（新对象）。
        """
        result: list[Chunk] = []
        for chunk in chunks:
            metadata = {**chunk.metadata, "parent_ref": parent_id}
            result.append(chunk.model_copy(update={"metadata": metadata}))
        return result
