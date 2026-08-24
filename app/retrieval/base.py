"""
检索器统一接口协议（架构 §3.5 + 05 §3.2）。

新增检索器的标准接入方式：继承 BaseRetriever，name 为 SourceKind
枚举成员；接入清单见 05 §3.2（SourceKind 加成员 → fusion 权重表加
默认值 → 如需暴露同步 02）。
"""

# --- 标准库 ---
from typing import Any, Protocol, runtime_checkable

# --- 本地模块 ---
from app.core.models import RetrievalResult, SourceKind


@runtime_checkable
class BaseRetriever(Protocol):
    """检索器结构协议（六路检索统一输出 RetrievalResult）。

    实现约束（AGENT.md Playbook A / 05 §3.2）：
    - result_id 全局唯一，格式 f"{name}:{stable_hash}"，融合层去重键
    - chunk_id 无对应块时显式 None
    - score 为归一化前原始分，口径写入实现类 docstring
    - 外部调用必须带独立超时（reliability.yaml），失败返回空列表
      + 计数器，不抛错（D5）

    Attributes:
        name: 检索来源（SourceKind 枚举成员）。
        error_count: 失败计数器（可观测 rag_retrieval_errors_total 数据源）。
    """

    name: SourceKind
    error_count: int

    async def retrieve(
        self,
        query: str,
        top_k: int,
        filters: dict[str, Any] | None = None,
    ) -> list[RetrievalResult]:
        """执行检索。

        Args:
            query: 查询文本。
            top_k: 返回数量。
            filters: 元数据过滤条件（可选）。

        Returns:
            检索结果列表，按原始分降序。
        """
        ...
