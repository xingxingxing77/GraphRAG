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
    )

    # 应用信息
    app_name: str = Field(default="GraphRAG", description="应用名称")
    app_version: str = Field(default="0.1.0", description="应用版本")
    debug: bool = Field(default=False, description="调试模式")

    # CORS
    cors_origins: list[str] = Field(default=["*"], description="允许的跨域来源")

    # Ollama 配置
    ollama_base_url: str = Field(default="http://localhost:11434", description="Ollama 服务地址")
    llm_model: str = Field(default="qwen2.5:32b", description="主 LLM 模型名称")
    llm_query_model: str = Field(default="qwen2.5:7b", description="查询理解用轻量模型")
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

    # 检索配置
    retrieval_top_k: int = Field(default=20, description="粗排召回数量")
    rerank_top_k: int = Field(default=5, description="精排后保留数量")
    rerank_threshold: float = Field(default=0.3, description="Reranker 分数阈值")

    # LangSmith 配置
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
