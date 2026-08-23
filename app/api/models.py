"""
API 请求/响应模型再导出。

全部契约模型的唯一定义位置为 `app.core.models`（D1 契约唯一来源，
架构文档 §3.6 + 02 §5）。本模块仅保持历史 import 路径兼容，
禁止在此新增模型定义。
"""

# --- 本地模块 ---
from app.core.models import (  # noqa: F401
    AuthTokenRequest,
    ChatRequest,
    ChatResponse,
    ChatRunInput,
    Citation,
    ErrorBody,
    FeedbackRequest,
    GraphNode,
    GraphRelationship,
    HealthComponent,
    HealthStatus,
    IntentType,
    LatencyTier,
    ModelOption,
    Paged,
    PrecheckRequest,
    PrecheckResponse,
    PublicConfig,
    SessionMessage,
    SessionSummary,
    SourceKind,
    SubgraphResponse,
    SuggestedRun,
    TokenResponse,
    UserInfo,
)

# 历史别名：query/router.py 等旧代码按 QueryIntent 引用意图枚举
QueryIntent = IntentType

# 历史别名：引用标注统一为契约模型 Citation（架构 §3.3）
CitationInfo = Citation
