"""
Pydantic 请求/响应模型。

严格定义 API 接口的数据结构和校验规则。
"""

# --- 标准库 ---
from enum import Enum
from typing import Optional

# --- 第三方库 ---
from pydantic import BaseModel, Field


class QueryIntent(str, Enum):
    """查询意图类型枚举。"""

    FACT = "fact"
    MULTI_HOP = "multi_hop"
    COMPARISON = "comparison"
    CHITCHAT = "chitchat"


class ChatRequest(BaseModel):
    """聊天请求模型。

    Attributes:
        query: 用户查询文本。
        session_id: 会话 ID，用于对话上下文关联。
        user_id: 用户 ID，用于长期记忆。
        stream: 是否启用流式响应。
    """

    query: str = Field(..., min_length=1, max_length=2000, description="用户查询")
    session_id: Optional[str] = Field(default=None, description="会话 ID")
    user_id: Optional[str] = Field(default=None, description="用户 ID")
    stream: bool = Field(default=True, description="是否流式响应")


class CitationInfo(BaseModel):
    """引用来源信息。

    Attributes:
        source: 文档来源路径。
        title: 文档标题。
        chunk_id: 引用的文档块 ID。
        relevance_score: 相关性分数。
    """

    source: str
    title: str
    chunk_id: str
    relevance_score: float


class ChatResponse(BaseModel):
    """聊天响应模型。

    Attributes:
        answer: 生成的答案。
        citations: 引用来源列表。
        intent: 识别的查询意图。
        session_id: 会话 ID。
        token_usage: Token 使用统计。
    """

    answer: str
    citations: list[CitationInfo] = Field(default_factory=list)
    intent: Optional[QueryIntent] = None
    session_id: Optional[str] = None
    token_usage: Optional[dict[str, int]] = None


class HealthStatus(BaseModel):
    """健康检查响应模型。

    Attributes:
        status: 整体状态。
        neo4j: Neo4j 连接状态。
        qdrant: Qdrant 连接状态。
        redis: Redis 连接状态。
        ollama: Ollama 服务状态。
    """

    status: str = "ok"
    neo4j: bool = False
    qdrant: bool = False
    redis: bool = False
    ollama: bool = False


class AdminAction(BaseModel):
    """管理操作请求模型。

    Attributes:
        action: 操作类型（clear_cache / rebuild_index / etc）。
        parameters: 操作参数。
    """

    action: str
    parameters: Optional[dict] = None
