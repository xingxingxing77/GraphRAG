"""
核心数据契约（D1 契约唯一来源）。

跨层字段的唯一定义位置，落地依据《GraphRAG 系统架构文档》第三章与
`02_API接口契约.md` §5。修改契约 = 架构文档第三章 + 本文件 + 受影响层代码
三者同一个 PR（05 §3.1）。

禁止在层内私自扩展 dict 字段；新字段先进本文件再使用。
"""

# --- 标准库 ---
from datetime import datetime
from enum import Enum
from typing import Any, Generic, Literal, TypeVar

# --- 第三方库 ---
from pydantic import BaseModel, Field


# ============================================================
# 枚举定义
# ============================================================


class SourceKind(str, Enum):
    """检索来源枚举（架构 §3.3 RetrievalResult.source 六路）。"""

    DENSE = "dense"
    SPARSE = "sparse"
    GRAPH = "graph"
    GLOBAL = "global"
    FULLTEXT = "fulltext"
    WEB = "web"


class IntentType(str, Enum):
    """查询意图类型（第 2 层查询理解 M2 产出，fast 路径判定依据）。"""

    FACT = "fact"
    MULTI_HOP = "multi_hop"
    COMPARISON = "comparison"
    CHITCHAT = "chitchat"


class LatencyTier(str, Enum):
    """延迟档位（D4 三档策略）。"""

    FAST = "fast"
    STANDARD = "standard"
    DEEP = "deep"


# ============================================================
# metadata 键规范（架构 §3.2）
# ============================================================


class MetadataKeys:
    """Qdrant payload 与 Chunk.metadata 统一键名（禁止同义异名）。

    Attributes:
        DOC_ID: 父文档 ID（必填）。
        CHUNK_ID: 块 ID（必填）。
        SOURCE: 来源标识（必填）。
        DOC_TYPE: Collection 划分依据（必填）。
        CATEGORY: 业务分类。
        TITLE_PATH: 标题路径。
        CREATED_AT: 创建时间。
        UPDATED_AT: 更新时间。
        QUALITY_SCORE: 质量分。
        LANG: 语言标识。
    """

    DOC_ID = "doc_id"
    CHUNK_ID = "chunk_id"
    SOURCE = "source"
    DOC_TYPE = "doc_type"
    CATEGORY = "category"
    TITLE_PATH = "title_path"
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"
    QUALITY_SCORE = "quality_score"
    LANG = "lang"


# ============================================================
# 数据管道 Document 模型族（架构 §3.1）
# 五个中间表示按管道顺序流转，每一步只允许增补字段
# ============================================================


class StructureNode(BaseModel):
    """文档结构树节点（P2 解析层产出）。

    Attributes:
        level: 标题层级（1 起）。
        title: 标题文本。
        start_offset: 该节在全文中的起始字符偏移。
    """

    level: int
    title: str
    start_offset: int = 0


class PositionMeta(BaseModel):
    """块在父文档内的字符定位。

    Attributes:
        start_char: 起始字符偏移。
        end_char: 结束字符偏移（不含）。
    """

    start_char: int
    end_char: int


class EntityMention(BaseModel):
    """实体提及（P5 增强层产出）。

    Attributes:
        name: 实体原文。
        type: 实体类型（graph_schema.yaml 白名单约束）。
        span: 字符偏移区间 [start, end)。
        normalized_to: 归一化后的 canonical_name（未归一时为 None）。
    """

    name: str
    type: str
    span: list[int] = Field(default_factory=list, description="字符偏移 [start, end)")
    normalized_to: str | None = None


class RelationTriple(BaseModel):
    """关系三元组（P5 增强层产出，G4 幂等写入单元）。

    Attributes:
        head: 头实体 canonical_name。
        relation: 关系类型（graph_schema.yaml 白名单约束）。
        tail: 尾实体 canonical_name。
        evidence_chunk_id: 证据块 ID（写入 MENTIONS 边依据）。
    """

    head: str
    relation: str
    tail: str
    evidence_chunk_id: str | None = None


class CommunityRecord(BaseModel):
    """Leiden 社区记录（P7-G5，单元 2.6）。

    Attributes:
        community_id: 社区唯一标识。
        level: 层级（0 = 叶子社区，向上递增）。
        members: 成员实体 canonical_name 列表。
        parent_id: 父社区 ID（顶层为 None）。
        summary: 分层 LLM 摘要（写入后填充）。
    """

    community_id: str
    level: int = 0
    members: list[str] = Field(default_factory=list)
    parent_id: str | None = None
    summary: str = ""


class CommunitySummaryItem(BaseModel):
    """GET /admin/communities items（02 §3.11，单元 2.6）。

    Attributes:
        community_id: 社区 ID。
        level: 层级。
        summary: 社区摘要。
        size: 成员数。
    """

    community_id: str
    level: int = 0
    summary: str = ""
    size: int = 0


class QdrantPointItem(BaseModel):
    """Qdrant 点条目（02 §3.11 GET /admin/qdrant/points，单元 3.1）。

    Attributes:
        id: Point ID。
        chunk_id: 关联块 ID（payload 同源，三方映射）。
        score: 检索分数（scroll 查询时为 None）。
        payload: 点负载（04 §3.1 键规范）。
    """

    id: str
    chunk_id: str = ""
    score: float | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class QdrantPointsResponse(BaseModel):
    """GET /admin/qdrant/points 响应。

    Attributes:
        points: 按 doc_id 过滤的点列表。
    """

    points: list[QdrantPointItem] = Field(default_factory=list)


class IkAnalyzeRequest(BaseModel):
    """POST /admin/debug/analyze 请求（02 §3.11，单元 3.2）。

    Attributes:
        index: 目标索引（rag_entities | rag_chunks）。
        text: 待分词文本。
    """

    index: Literal["rag_entities", "rag_chunks"] = "rag_entities"
    text: str = Field(..., min_length=1)


class IkAnalyzeResponse(BaseModel):
    """POST /admin/debug/analyze 响应（IK 分词调试）。

    Attributes:
        tokens: 分词 token 列表。
    """

    tokens: list[str] = Field(default_factory=list)


class DebugRetrieveRequest(BaseModel):
    """POST /admin/debug/retrieve 请求（02 §3.11，单元 3.3-3.5）。

    Attributes:
        query: 查询文本。
        top_k: 每路返回数量（默认 10）。
        sources: 检索源过滤（六路枚举子集，缺省全选）。
    """

    query: str = Field(..., min_length=1)
    top_k: int = Field(default=10, ge=1, le=50)
    sources: list[SourceKind] | None = None


class DebugRetrieveResponse(BaseModel):
    """POST /admin/debug/retrieve 响应（02 §7 DebugRetrieveResponse）。

    Attributes:
        results: 按检索源分组的结果（source -> RetrievalResult 列表）。
        fused: 融合后 Top-N（result_id + content，3.5 接入）。
    """

    results: dict[str, list["RetrievalResult"]] = Field(default_factory=dict)
    fused: list[dict[str, str]] = Field(default_factory=list)


class DebugRerankDoc(BaseModel):
    """POST /admin/debug/rerank 候选文档条目（02 §3.11，单元 4.1）。

    Attributes:
        content: 文档内容。
    """

    content: str = Field(..., min_length=1)


class DebugRerankRequest(BaseModel):
    """POST /admin/debug/rerank 请求。

    Attributes:
        query: 查询文本。
        docs: 候选文档列表。
        top_k: 精排后保留数量。
    """

    query: str = Field(..., min_length=1)
    docs: list[DebugRerankDoc] = Field(..., min_length=1)
    top_k: int = Field(default=5, ge=1, le=50)


class DebugRerankRankedItem(BaseModel):
    """精排结果条目。

    Attributes:
        content: 文档内容。
        score: 精排分（降级时为粗排分）。
    """

    content: str
    score: float


class DebugRerankResponse(BaseModel):
    """POST /admin/debug/rerank 响应（精排对比）。

    Attributes:
        ranked: 精排后列表（按分降序）。
        degraded: 是否 no-rerank 降级。
        elapsed_ms: 精排耗时（毫秒）。
    """

    ranked: list[DebugRerankRankedItem] = Field(default_factory=list)
    degraded: bool = False
    elapsed_ms: int = 0


class ResolvedEntity(BaseModel):
    """实体对齐结果（P7-G2 实体规范化与对齐，单元 2.4）。

    Attributes:
        mention: 原始提及文本。
        canonical_name: 规范实体名（MERGE 键，G4）。
        type: 实体类型（开放区为 Other，J12）。
        zone: 白名单/开放区标记（J12）。
        status: 审核状态。
        similarity: 向量归并时的相似度（仅向量消歧路径有值）。
        needs_review: 灰区 [0.80, 0.92) 命中，入人工审核队列。
    """

    mention: str
    canonical_name: str
    type: str
    zone: Literal["core", "open"] = "open"
    status: Literal["approved", "pending"] = "pending"
    similarity: float | None = None
    needs_review: bool = False


class RawDocument(BaseModel):
    """P1 采集层输出：原始文档。

    Attributes:
        schema_version: 契约版本号。
        doc_id: UUID 全局唯一，贯穿全管道。
        source_path: 来源路径或 URL。
        raw_bytes: 原始字节。
        mime_type: MIME 类型。
        timestamp: 采集时间。
        content_hash: SHA-256，增量判断依据。
    """

    schema_version: Literal["1"] = "1"
    doc_id: str
    source_path: str
    raw_bytes: bytes
    mime_type: str
    timestamp: datetime
    content_hash: str


class ParsedDocument(BaseModel):
    """P2 解析层输出：解析后的文档。

    Attributes:
        doc_id: 父文档 ID。
        text: 提取的纯文本。
        structure_tree: 结构树 [{level, title, start_offset}]。
        format_meta: 页码/编码等格式信息。
    """

    doc_id: str
    schema_version: Literal["1"] = "1"
    text: str
    structure_tree: list[StructureNode] = Field(default_factory=list)
    format_meta: dict[str, Any] = Field(default_factory=dict)


class CleanedDocument(BaseModel):
    """P3 清洗层输出。清洗规则的输入输出均为本类型（架构 §3.1）。

    Attributes:
        doc_id: 父文档 ID。
        text: 清洗后的文本。
        structure_tree: 结构树（清洗过程保持）。
        quality_score: 质量分 [0,1]，质量门控产出。
        cleaned_meta: 应用的规则列表、门控结果。
    """

    doc_id: str
    schema_version: Literal["1"] = "1"
    text: str
    structure_tree: list[StructureNode] = Field(default_factory=list)
    quality_score: float = Field(default=1.0, ge=0.0, le=1.0)
    cleaned_meta: dict[str, Any] = Field(default_factory=dict)


class Chunk(BaseModel):
    """P4 分块层输出：文档块。

    Attributes:
        chunk_id: 块 ID，格式 f"{doc_id}-{seq}"。
        doc_id: 父文档 ID。
        seq: 文档内顺序号。
        content: 块内容。
        title_path: 标题路径，如 ["清蒸鲈鱼", "操作步骤", "蒸制"]。
        position: 父文档内字符定位。
        metadata: 键名遵循 MetadataKeys 规范（架构 §3.2）。
    """

    chunk_id: str
    doc_id: str
    seq: int
    content: str
    title_path: list[str] = Field(default_factory=list)
    position: PositionMeta
    metadata: dict[str, Any] = Field(default_factory=dict)


class EnrichedChunk(BaseModel):
    """P5 增强层输出，P6/P7 索引层的输入。

    Attributes:
        chunk: 分块本体。
        keywords: 提取的关键词。
        entities: 实体提及列表。
        summary: 摘要（高价值文档才有）。
        relations: 关系三元组列表。
    """

    chunk: Chunk
    keywords: list[str] = Field(default_factory=list)
    entities: list[EntityMention] = Field(default_factory=list)
    summary: str | None = None
    relations: list[RelationTriple] = Field(default_factory=list)


# ============================================================
# 检索侧与 Agent 编排核心模型（架构 §3.3）
# ============================================================


class RetrievalResult(BaseModel):
    """所有检索器（dense/sparse/graph/global/fulltext/web）的统一输出。

    Attributes:
        result_id: 全局唯一结果标识，融合层去重键，格式 f"{name}:{stable_hash}"。
        chunk_id: 关联块 ID（图谱/Web 结果可为 None）。
        content: 文本片段或子图序列化文本。
        score: 原始分数（归一化前，口径见各检索器 docstring）。
        source: 检索来源（六路枚举）。
        doc_id: 关联父文档，支持上下文扩展。
        metadata: 附加元数据（键名遵循 MetadataKeys）。
    """

    result_id: str
    chunk_id: str | None = None
    content: str
    score: float
    source: SourceKind
    doc_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class Citation(BaseModel):
    """引用标注（02 §5）。

    Attributes:
        marker: 答案中的 [n] 编号。
        result_ids: 支撑该结论的证据 ID。
        quote: 原文摘录（可选）。
    """

    marker: int
    result_ids: list[str] = Field(default_factory=list)
    quote: str | None = None


class TokenUsage(BaseModel):
    """Token 用量（Ollama 口径: prompt_eval_count / eval_count 自动映射）。

    Attributes:
        model: 模型条目名。
        prompt_tokens: 提示 token 数。
        completion_tokens: 生成 token 数。
        latency_ms: 调用耗时（毫秒）。
    """

    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: int = 0


class PlanStep(BaseModel):
    """Planner 产出的单步计划。

    约定（架构 §3.3）：
    - depends_on 是 A1 并行扇出的依据：拓扑分组后同组步骤经 Send API 并行
    - tool="direct_answer" 即 J9 chitchat「直答」单步，ToolRouter 零执行
    - status 由 ToolRouter 维护，支撑断点恢复与 tracing 展示

    Attributes:
        step_id: 步骤 ID，格式 "step-{seq}"。
        tool: 检索器名（六路枚举值）或 "direct_answer"。
        query: 该步执行的检索查询。
        depends_on: 前置 step_id；空数组即可并行扇出。
        status: 步骤状态。
    """

    step_id: str
    tool: str
    query: str
    depends_on: list[str] = Field(default_factory=list)
    status: Literal["pending", "running", "done", "skipped"] = "pending"


class ReflectFeedback(BaseModel):
    """Reflector 结构化输出（C8 契约），回环时 Planner 增量补计划的依据。

    Attributes:
        sufficient: 证据充分性判定，驱动回环路由。
        missing_aspects: 缺失的信息维度。
        followup_queries: 下一轮补检查询。
    """

    sufficient: bool
    missing_aspects: list[str] = Field(default_factory=list)
    followup_queries: list[str] = Field(default_factory=list)


class EmbeddingResult(BaseModel):
    """BGE-M3 双通道向量化结果（架构 §6.2）。

    Attributes:
        dense: 密集向量列表，shape: (n, 1024)。
        sparse: 稀疏向量列表，每项为 {token_id: weight}。
    """

    dense: list[list[float]] = Field(default_factory=list)
    sparse: list[dict[int, float]] = Field(default_factory=list)


# ============================================================
# 业务面 REST API 契约模型（架构 §3.6 + 02 §3/§5）
# ============================================================


class ErrorBody(BaseModel):
    """统一错误体（02 §2.3）：{code, message, detail?}。

    Attributes:
        code: 错误码（02 §6 总表命名空间）。
        message: 面向用户的错误消息。
        detail: 调试细节（可选）。
    """

    code: str
    message: str
    detail: str | None = None


T = TypeVar("T")


class Paged(BaseModel, Generic[T]):
    """游标分页响应（02 §2.5）：?cursor=&limit=，响应携 next_cursor。

    Attributes:
        items: 当前页条目。
        next_cursor: 下一页游标（None 表示末页）。
    """

    items: list[T] = Field(default_factory=list)
    next_cursor: str | None = None


class ChatRequest(BaseModel):
    """聊天请求（架构 §3.6 通用约定）。

    Attributes:
        query: 用户查询文本。
        session_id: 会话 ID。
        user_id: 用户 ID。
        stream: 是否流式响应。
        latency_tier: 延迟档位，缺省 auto 由意图路由定档（D4）。
        model: J2 请求级覆盖 generator 角色默认条目（None = 默认）。
    """

    query: str = Field(..., min_length=1, max_length=2000)
    session_id: str | None = None
    user_id: str | None = None
    stream: bool = True
    latency_tier: Literal["auto", "fast", "standard", "deep"] = "auto"
    model: str | None = None


class ChatResponse(BaseModel):
    """聊天响应（架构 §3.6：含 degraded 与 latency_tier）。

    Attributes:
        answer: 生成的答案。
        citations: 引用标注列表。
        degraded: 是否降级运行（与 X-Degraded 头一致）。
        latency_tier: 实际执行档位。
        session_id: 会话 ID。
        model: 实际使用的模型条目名。
        token_usage: 全程 Token 用量。
    """

    answer: str
    citations: list[Citation] = Field(default_factory=list)
    degraded: bool = False
    latency_tier: LatencyTier | None = None
    session_id: str | None = None
    model: str | None = None
    token_usage: list[TokenUsage] = Field(default_factory=list)


class ChatRunInput(BaseModel):
    """Agent 面 run 入参（02 §5，与 AgentState 对齐）。

    Attributes:
        original_query: 用户原始查询。
        session_id: 会话 ID。
        user_id: 用户 ID。
    """

    original_query: str = Field(..., min_length=1, max_length=2000)
    session_id: str | None = None
    user_id: str | None = None


class PrecheckRequest(BaseModel):
    """POST /chat/precheck 请求（02 §3.8，J22 语义缓存短路）。

    Attributes:
        query: 查询文本。
        session_id: 会话 ID。
    """

    query: str = Field(..., min_length=1, max_length=2000)
    session_id: str | None = None


class SuggestedRun(BaseModel):
    """precheck 未命中时的建议 run 参数。

    Attributes:
        latency_tier: 意图分类轻量启发式给出的建议档位（前端可覆盖）。
    """

    latency_tier: LatencyTier = LatencyTier.STANDARD


class PrecheckResponse(BaseModel):
    """POST /chat/precheck 响应（02 §3.8 命中/未命中两态）。

    Attributes:
        hit: 是否命中缓存（score >= 0.95，H2）。
        answer: 命中时的缓存答案。
        citations: 命中时的引用列表。
        cache_score: 命中时的相似度分数。
        matched_query: 命中时匹配的原始缓存查询。
        suggested_run: 未命中时的建议 run 参数。
    """

    hit: bool
    answer: str | None = None
    citations: list[Citation] = Field(default_factory=list)
    cache_score: float | None = None
    matched_query: str | None = None
    suggested_run: SuggestedRun | None = None


class SessionSummary(BaseModel):
    """会话摘要（02 §3.2）。

    Attributes:
        session_id: 会话 ID。
        title: 首条用户消息截断（≤30 字符）。
        message_count: 消息数。
        created_at: 创建时间（ISO 8601 UTC）。
        updated_at: 更新时间。
    """

    session_id: str
    title: str
    message_count: int = 0
    created_at: datetime
    updated_at: datetime


class SessionMessage(BaseModel):
    """会话历史消息（02 §3.3，聚合 thread checkpoint 与工作记忆）。

    Attributes:
        message_id: 消息 ID。
        role: 消息角色。
        content: 消息内容。
        created_at: 创建时间。
        citations: 引用列表（assistant 消息）。
        degraded: 该回答是否降级产出。
        latency_tier: 该回答的执行档位。
        model: 该回答使用的模型条目名。
    """

    message_id: str
    role: Literal["user", "assistant"]
    content: str
    created_at: datetime
    citations: list[Citation] = Field(default_factory=list)
    degraded: bool = False
    latency_tier: LatencyTier | None = None
    model: str | None = None


class FeedbackRequest(BaseModel):
    """POST /feedback 请求（02 §3.5，在线评估闭环数据源）。

    Attributes:
        session_id: 会话 ID。
        message_id: 消息 ID。
        rating: 点赞/点踩。
        reason: 点踩原因（仅 down 必填）。
        comment: 补充说明。
    """

    session_id: str
    message_id: str
    rating: Literal["up", "down"]
    reason: Literal["wrong", "incomplete", "unsafe", "other"] | None = None
    comment: str | None = None


class GraphNode(BaseModel):
    """图谱子图节点（02 §3.6，NVL 直连格式）。

    Attributes:
        id: 节点 ID。
        label: 显示名（canonical_name）。
        type: 实体类型。
        zone: 白名单/开放区（J12）。
    """

    id: str
    label: str
    type: str
    zone: Literal["core", "open"] = "open"


class GraphRelationship(BaseModel):
    """图谱子图关系边（02 §3.6）。

    Attributes:
        source: 头节点 ID。
        target: 尾节点 ID。
        type: 关系类型。
    """

    source: str
    target: str
    type: str


class SubgraphResponse(BaseModel):
    """GET /graph/subgraph 响应（@neo4j-nvl/react 直接可用格式）。

    Attributes:
        nodes: 节点列表。
        relationships: 关系边列表。
    """

    nodes: list[GraphNode] = Field(default_factory=list)
    relationships: list[GraphRelationship] = Field(default_factory=list)


class ModelOption(BaseModel):
    """可选模型条目（02 §3.7）。

    Attributes:
        id: 注册表条目名（请求参数可引用）。
        label: 展示名。
        provider: 提供方（云端/本地）。
    """

    id: str
    label: str
    provider: Literal["cloud", "local"]


class PublicConfig(BaseModel):
    """GET /config/public 响应（J2「请求参数指定模型」的前端前提）。

    Attributes:
        models: 可选模型条目清单。
        latency_tiers: 延迟档位枚举。
        compression_strategies: 压缩策略枚举（J11）。
        profile: 运行 Profile（cloud-primary / local）。
    """

    models: list[ModelOption] = Field(default_factory=list)
    latency_tiers: list[str] = Field(default_factory=lambda: ["fast", "standard", "deep"])
    compression_strategies: list[str] = Field(
        default_factory=lambda: ["llm_extract", "extractive", "none"]
    )
    profile: str = "cloud-primary"


class AuthTokenRequest(BaseModel):
    """POST /auth/token 请求（02 §3.1，二选一凭证）。

    Attributes:
        grant_type: 兑换方式。
        api_key: API Key（grant_type=api_key）。
        username: 用户名（grant_type=password）。
        password: 密码（grant_type=password）。
    """

    grant_type: Literal["api_key", "password"]
    api_key: str | None = None
    username: str | None = None
    password: str | None = None


class UserInfo(BaseModel):
    """用户信息（随 token 响应下发）。

    Attributes:
        id: 用户 ID。
        name: 用户名。
        role: 角色（admin 可访问 /admin/*）。
    """

    id: str
    name: str
    role: Literal["user", "admin"] = "user"


class TokenResponse(BaseModel):
    """POST /auth/token 响应（02 §3.1）。

    Attributes:
        access_token: JWT。
        token_type: 固定 bearer。
        expires_in: 有效期（秒）。
        user: 用户信息。
    """

    access_token: str
    token_type: str = "bearer"
    expires_in: int = 86400
    user: UserInfo


class HealthComponent(BaseModel):
    """单组件健康状态（02 §3.9）。

    Attributes:
        status: 组件状态。
        latency_ms: 探测耗时（毫秒）。
        detail: 异常详情。
    """

    status: Literal["up", "degraded", "down"]
    latency_ms: int | None = None
    detail: str | None = None


class HealthStatus(BaseModel):
    """健康聚合响应（02 §3.9，/health 与 /ready 共用）。

    Attributes:
        status: 聚合状态（ready 为就绪）。
        components: 七组件探测结果（postgres/qdrant/neo4j/elasticsearch/
            redis/langgraph-server/ollama）。
    """

    status: str = "ok"
    components: dict[str, HealthComponent] = Field(default_factory=dict)


class FeedbackResponse(BaseModel):
    """POST /feedback 响应（02 §3.5）。

    Attributes:
        ok: 是否受理成功。
    """

    ok: bool = True


# ============================================================
# 管理接口组契约模型（02 §3.10，仅 role=admin）
# ============================================================


class CacheClearRequest(BaseModel):
    """POST /admin/cache/clear 请求。

    Attributes:
        scope: 清理范围（l1 语义缓存 / l2 检索缓存 / all）。
        doc_id: 可选，按 doc_id 反查清除受影响缓存（失效联动）。
    """

    scope: Literal["l1", "l2", "all"] = "all"
    doc_id: str | None = None


class CacheClearResponse(BaseModel):
    """POST /admin/cache/clear 响应。

    Attributes:
        purged: 清除的缓存条目数。
    """

    purged: int = 0


class IndexRebuildRequest(BaseModel):
    """POST /admin/index/rebuild 请求。

    Attributes:
        scope: 重建范围。
        full: 是否全量重建。
    """

    scope: Literal["vector", "graph", "fulltext", "all"] = "all"
    full: bool = True


class TaskAccepted(BaseModel):
    """异步任务受理响应（202）。

    Attributes:
        task_id: 任务 ID，进度查 GET /admin/tasks/{task_id}。
    """

    task_id: str


class TaskStatus(BaseModel):
    """GET /admin/tasks/{task_id} 响应。

    Attributes:
        state: 任务状态。
        progress: 进度 [0,1]。
    """

    state: Literal["running", "done", "failed"]
    progress: float = Field(default=0.0, ge=0.0, le=1.0)


class HotReloadResponse(BaseModel):
    """PUT /admin/config/hot-reload 响应（J18 受限热更）。

    Attributes:
        reloaded: 重载成功的配置文件名。
        errors: 重载错误列表。
    """

    reloaded: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class ReviewQueueItem(BaseModel):
    """开放区人工审核队列条目（J12，按出现频次排序）。

    Attributes:
        entity_id: 实体 ID。
        name: 实体名。
        freq: 出现频次。
        first_seen: 首次发现时间。
    """

    entity_id: str
    name: str
    freq: int = 0
    first_seen: datetime | None = None


class ReviewDecisionRequest(BaseModel):
    """POST /admin/review/decision 请求。

    Attributes:
        entity_id: 待审核实体 ID。
        action: approve 升级白名单并重放关联三元组；reject 拒绝。
    """

    entity_id: str
    action: Literal["approve", "reject"]


# ============================================================
# 管道调试接口组契约模型（02 §3.11，随关联单元落地；
# 02 §7 类型镜像同步登记）
# ============================================================


class IngestionRunRequest(BaseModel):
    """POST /admin/ingestion/run 请求（02 §3.11，单元 1.1）。

    Attributes:
        mode: 全量或增量扫描（架构 P1 文件发现策略）。
        source: 可选数据源标识（缺省用 pipeline_config 全部 sources）。
    """

    mode: Literal["full", "incremental"] = "incremental"
    source: str | None = None


class ScanRecord(BaseModel):
    """扫描结果记录（02 §3.11 GET /admin/ingestion/scans items，04 §2.3 水位联动）。

    Attributes:
        scan_id: 扫描任务 ID。
        mode: 扫描模式。
        discovered: 发现的候选文件数。
        changed: 新增/变更文件数（增量判定依据 content_hash）。
        deduped: 内容哈希去重拦截数。
        finished_at: 完成时间（ISO 8601 UTC）。
    """

    scan_id: str
    mode: Literal["full", "incremental"]
    discovered: int = 0
    changed: int = 0
    deduped: int = 0
    finished_at: datetime | None = None


class ParsingPreviewResponse(BaseModel):
    """POST /admin/parsing/preview 响应（02 §3.11，单元 1.2）。

    Attributes:
        text: 解析出的纯文本。
        structure_tree: 标题层级树。
        format_meta: 格式元信息（format/encoding/page_count 等）。
    """

    text: str
    structure_tree: list[StructureNode] = Field(default_factory=list)
    format_meta: dict[str, Any] = Field(default_factory=dict)


class CleaningPreviewRequest(BaseModel):
    """POST /admin/cleaning/preview 请求（02 §3.11，单元 1.3）。

    Attributes:
        doc_id: 已采集文档 ID。
        rules_override: 可选规则子集（按名称过滤，缺省全部启用规则）。
    """

    doc_id: str
    rules_override: list[str] | None = None


class CleaningPreviewResponse(BaseModel):
    """POST /admin/cleaning/preview 响应（02 §3.11：before/after/removed_spans/quality_score）。

    Attributes:
        before: 清洗前文本（解析态）。
        after: 清洗后文本。
        removed_spans: 被删除的行片段（diff 高亮用）。
        quality_score: 质量门控评分 [0,1]。
    """

    before: str
    after: str
    removed_spans: list[str] = Field(default_factory=list)
    quality_score: float = 0.0


class ChunkingPreviewRequest(BaseModel):
    """POST /admin/chunking/preview 请求（02 §3.11，单元 2.1）。

    Attributes:
        doc_id: 已采集文档 ID。
    """

    doc_id: str


class ChunkingPreviewResponse(BaseModel):
    """POST /admin/chunking/preview 响应（02 §3.11：chunks 含边界/title_path/position）。

    Attributes:
        chunks: 分块列表（chunk 边界高亮与 title_path 展示用）。
    """

    chunks: list["Chunk"] = Field(default_factory=list)


class EmbedProbeRequest(BaseModel):
    """POST /admin/debug/embed 请求（02 §3.11，单元 2.3）。

    Attributes:
        text: 探针文本。
    """

    text: str = Field(..., min_length=1)


class EmbedProbeResponse(BaseModel):
    """POST /admin/debug/embed 响应（向量探针：dense 维数 / sparse 键数 / 耗时）。

    Attributes:
        dense_dims: 密集向量维度（BGE-M3 = 1024）。
        sparse_keys: 稀疏向量非零键数（FlagEmbedding 未接入时为 0）。
        latency_ms: 双通道向量化耗时（毫秒）。
    """

    dense_dims: int = 0
    sparse_keys: int = 0
    latency_ms: int = 0


# 前向引用模型重建（RetrievalResult 定义于后，需延迟解析）
DebugRetrieveResponse.model_rebuild()
