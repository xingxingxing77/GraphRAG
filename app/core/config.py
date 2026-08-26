"""
应用配置管理。

使用 pydantic-settings 管理所有配置项，支持环境变量和 .env 文件加载。
"""

# --- 标准库 ---
from functools import lru_cache
from typing import Optional

# --- 第三方库 ---
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    """应用基础配置。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        # 无关环境变量（LangChain 生态/工具链注入）不阻断启动；
        # 必需项缺失的 fail-fast 由各模块自行校验（05 §6/D7）
        extra="ignore",
    )

    # 应用信息
    app_name: str = Field(default="GraphRAG", description="应用名称")
    app_version: str = Field(default="0.1.0", description="应用版本")
    debug: bool = Field(default=False, description="调试模式")
    debug_enabled: bool = Field(
        default=True,
        description="admin 调试端点开关（/admin/debug/* 等；生产置 False 返回 SYS_403_DEBUG_DISABLED，02 §3.11）",
    )

    # CORS：显式白名单（禁用 "*" + credentials 组合，架构第 1 层注；
    # 开发期含 Vite dev 源，生产经环境变量收紧）
    cors_origins: list[str] = Field(
        default=["http://localhost:5173"], description="允许的跨域来源"
    )

    # --- 限流（单元 9.2，D6）：默认关闭，生产经环境变量开启 ---
    rate_limit_enabled: bool = Field(
        default=False, description="是否启用全局限流中间件"
    )
    rate_limit_max_requests: int = Field(
        default=60, description="窗口内最大请求数"
    )
    rate_limit_window_seconds: int = Field(
        default=60, description="限流窗口（秒）"
    )

    # --- 密钥与认证（仅变量名/值经环境变量注入，D7/J16） ---
    jwt_secret: str = Field(
        default="dev-insecure-secret-please-replace-in-prod-env",
        description="JWT 签名密钥（与 langgraph-server 共享，J16/J19；≥32 字节，生产经 env 注入随机值）",
    )
    deepseek_api_key: Optional[str] = Field(
        default=None, description="models.yaml api_key_ref=DEEPSEEK_API_KEY"
    )
    openai_api_key: Optional[str] = Field(
        default=None, description="models.yaml api_key_ref=OPENAI_API_KEY"
    )
    local_key: Optional[str] = Field(
        default=None, description="本地端点占位密钥（可为空串）"
    )
    tavily_api_key: Optional[str] = Field(
        default=None, description="Web 搜索主轨（缺省自动降级 DDG，J4）"
    )

    # --- 认证凭证（单元 10.2；开发默认值，生产经 env 注入，D7/J16） ---
    admin_username: str = Field(default="admin", description="管理员用户名（password grant）")
    admin_password: str = Field(
        default="admin-dev-password", description="管理员密码（开发默认，生产收紧）"
    )
    valid_api_keys: str = Field(
        default="dev-api-key-0001", description="有效 API Key 列表（逗号分隔，api_key grant）"
    )
    token_ttl_seconds: int = Field(default=86400, description="JWT 有效期（秒）")

    # Ollama 配置
    ollama_base_url: str = Field(default="http://localhost:11434", description="Ollama 服务地址")
    langgraph_server_url: str = Field(
        default="http://localhost:8001", description="langgraph-server 地址（J19 双服务）"
    )
    embedding_model: str = Field(default="bge-m3", description="Embedding 模型名称")
    reranker_model: str = Field(default="bge-reranker-v2-m3", description="Reranker 模型名称")

    # Qdrant 配置
    qdrant_host: str = Field(default="localhost", description="Qdrant 服务地址")
    qdrant_port: int = Field(default=6333, description="Qdrant gRPC 端口")
    qdrant_collection: str = Field(default="graphrag_docs", description="默认 Collection 名称")

    # Neo4j 配置
    neo4j_uri: str = Field(default="bolt://localhost:7687", description="Neo4j 连接 URI")
    neo4j_user: str = Field(default="neo4j", description="Neo4j 用户名")
    neo4j_password: str = Field(default="password", description="Neo4j 密码")

    # Redis 配置
    redis_host: str = Field(default="localhost", description="Redis 服务地址")
    redis_port: int = Field(default=6379, description="Redis 端口")
    redis_db: int = Field(default=0, description="Redis DB 编号")

    # Elasticsearch 配置（J5/J6 全文协同）
    elasticsearch_host: str = Field(
        default="http://localhost:9200", description="Elasticsearch 服务地址"
    )

    # Postgres 配置（J21 LangGraph thread checkpoint）
    postgres_dsn: str = Field(
        default="postgresql://graphrag:graphrag@localhost:5433/graphrag",
        description="Postgres checkpoint 连接串",
    )

    # 检索配置
    retrieval_top_k: int = Field(default=20, description="粗排召回数量")
    rerank_top_k: int = Field(default=5, description="精排后保留数量")
    rerank_threshold: float = Field(default=0.3, description="Reranker 分数阈值")

    # LangSmith 配置（第 10 层可观测）
    langchain_tracing_v2: bool = Field(default=False, description="LangSmith 追踪开关")
    langsmith_api_key: Optional[str] = Field(default=None, description="LangSmith API Key")
    langsmith_project: str = Field(default="graphrag", description="LangSmith 项目名称")

    # 分块配置
    chunk_size: int = Field(default=500, description="分块大小 (tokens)")
    chunk_overlap: int = Field(default=80, description="分块重叠大小")


@lru_cache
def get_settings() -> AppSettings:
    """获取全局配置单例。

    Returns:
        AppSettings: 应用配置实例（缓存）。
    """
    return AppSettings()
