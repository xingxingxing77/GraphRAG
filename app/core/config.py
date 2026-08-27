"""
应用配置管理。

使用 pydantic-settings 管理所有配置项，支持环境变量和 .env 文件加载。
"""

# --- 标准库 ---
import os
from functools import lru_cache
from typing import Optional

# 本机存储（Qdrant 等）经 localhost 访问时禁用系统代理——
# qdrant-client 底层 httpx 默认 trust_env，Windows 系统代理未对 localhost
# 旁路时会把内网请求转发返回 502（误判存储 down）。NO_PROXY 仅影响
# 本地地址，外部 API（tavily/ddg 等）仍走代理不受影响。
os.environ.setdefault("NO_PROXY", "localhost,127.0.0.1")
os.environ.setdefault("no_proxy", "localhost,127.0.0.1")

# .env 绝对路径（app/core/config.py 的上三级 = 项目根）——
# 相对路径会让 pydantic-settings 在实例化时调用 os.getcwd() 同步阻塞，
# 触发 langgraph dev 的 BlockingError（阻塞检测）。用 os.path.abspath 推导
# 绝对路径（__file__ 已是绝对路径，abspath 不触发 getcwd；Path.resolve() 在
# Windows 会走 realpath→getcwd，反而踩坑）。
_ENV_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    ".env",
)

# --- 第三方库 ---
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    """应用基础配置。"""

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
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
        default=False,
        description="admin 调试端点开关（fail-closed，D7；/admin/debug/* 等，置 False 返回 SYS_403_DEBUG_DISABLED，dev 经 DEBUG_ENABLED=true 显式开启，02 §3.11）",
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

    # --- 安全默认值标记（P0-01 fail-fast 用） ---
    _DEV_JWT_SECRET = "dev-insecure-secret-please-replace-in-prod-env"
    _DEV_ADMIN_PASSWORD = "admin-dev-password"
    _DEV_API_KEY = "dev-api-key-0001"

    def is_dev_defaults(self) -> bool:
        """是否仍使用开发默认密钥（生产应经 env 注入覆盖）。"""
        return (
            self.jwt_secret == self._DEV_JWT_SECRET
            or self.admin_password == self._DEV_ADMIN_PASSWORD
            or self.valid_api_keys == self._DEV_API_KEY
        )

    def validate_prod_secrets(self) -> None:
        """生产环境强校验：dev 默认密钥未覆盖则拒绝启动（fail-fast，D7/J16）。

        Raises:
            SystemExit: 仍使用 dev 默认密钥且非显式 dev 环境。
        """
        # 显式 dev 模式放行（DEBUG=true 或 ENV=dev/test）
        env_marker = (os.environ.get("ENV", "") + os.environ.get("APP_ENV", "")).lower()
        if self.debug or env_marker in ("dev", "test", "development", "devtest"):
            return
        if self.jwt_secret == self._DEV_JWT_SECRET:
            raise SystemExit(
                "[fail-fast] JWT_SECRET 仍为开发默认值，生产必须经环境变量注入 ≥32 字节随机值（D7/J16）"
            )
        if len(self.jwt_secret) < 32:
            raise SystemExit("[fail-fast] JWT_SECRET 长度不足 32 字节，拒绝启动")
        if self.admin_password == self._DEV_ADMIN_PASSWORD:
            raise SystemExit("[fail-fast] ADMIN_PASSWORD 仍为开发默认值，生产必须覆盖")
        if self.valid_api_keys == self._DEV_API_KEY:
            # valid_api_keys 为可选但若使用 api_key grant 则必须覆盖；此处警告
            import logging as _log

            _log.getLogger(__name__).warning(
                "[security] VALID_API_KEYS 仍为开发默认值，若启用 api_key 鉴权请覆盖"
            )

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


# 模块导入时（同步上下文）预热配置单例——
# AppSettings 首次实例化会经 sysconfig._safe_realpath 触发 os.getcwd() 同步
# 阻塞调用，若发生在 langgraph async 节点内会被其阻塞检测抛 BlockingError
# （表现为 load_memory/generator 的 no-memory/llm-fallback 降级）。在导入期
# 提前触发，把这次同步调用移出 async 节点上下文。
get_settings()
