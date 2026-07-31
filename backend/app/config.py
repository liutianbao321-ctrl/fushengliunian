from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "浮生流年 API"
    env: Literal["development", "staging", "production"] = "development"
    api_prefix: str = "/api"
    secret_key: str = Field(
        default="change-this-in-production",
        description="JWT secret key",
    )
    access_token_expire_minutes: int = 60 * 24 * 7

    database_url: str = Field(default="postgresql+asyncpg://postgres:postgres@localhost:5432/fushengliunian")
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ]
    )

    llm_backend: Literal["mock", "openai_compatible"] = "mock"
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    llm_model: str = "deepseek-chat"
    llm_fallback_model: str | None = None
    llm_fallback_models: list[str] = Field(default_factory=list)
    llm_planning_model: str | None = None
    llm_planning_fallback_model: str | None = None
    llm_planning_fallback_models: list[str] = Field(default_factory=list)
    llm_aliyun_base_url: str | None = None
    llm_aliyun_api_key: str | None = None
    llm_aliyun_model: str | None = None
    llm_aliyun_planning_model: str | None = None
    llm_deepseek_base_url: str | None = None
    llm_deepseek_api_key: str | None = None
    llm_deepseek_model: str | None = None
    llm_timeout_seconds: int = 180
    llm_max_retries: int = 3
    web_search_enabled: bool = True
    web_search_base_url: str | None = None
    web_search_api_key: str | None = None
    web_search_mcp_url: str | None = None
    web_search_model: str = "qwen3.6-plus"
    web_search_timeout_seconds: int = 240
    web_search_max_sources: int = 8
    # 生成节点 token 上限：正文类（writer/humanizer/editor）给充足上限，结构化节点收紧
    generation_max_tokens_prose: int = 8192
    generation_max_tokens_structured: int = 4096
    generation_node_timeout_seconds: int = 240
    generation_pipeline_timeout_seconds: int = 900
    embedding_base_url: str | None = None
    embedding_api_key: str | None = None
    embedding_model: str = "qwen3.7-text-embedding"
    embedding_dimensions: int = 1024
    embedding_provider: Literal["openai_compatible", "aliyun_dashscope"] = "openai_compatible"
    embedding_batch_size: int = 16
    embedding_concurrency: int = 2
    # Milvus is a documented scale-out target, not an active backend in this build.
    vector_store: Literal["pgvector"] = "pgvector"
    milvus_uri: str | None = None
    milvus_token: str | None = None
    milvus_collection: str = "fushengliunian_knowledge"
    writing_knowledge_root: str | None = None
    writing_knowledge_enabled: bool = True

    generation_worker_enabled: bool = True
    generation_poll_seconds: float = 0.5
    generation_lease_seconds: int = 900
    generation_max_attempts: int = 3
    import_worker_enabled: bool = True
    import_poll_seconds: float = 1.0
    import_lease_seconds: int = 900
    import_max_attempts: int = 3
    import_analysis_batch_characters: int = Field(default=60_000, ge=12_000, le=120_000)
    import_analysis_batch_chapters: int = Field(default=24, ge=4, le=50)
    import_analysis_concurrency: int = Field(default=4, ge=1, le=8)
    index_worker_enabled: bool = True
    index_poll_seconds: float = 1.0
    index_lease_seconds: int = 300
    index_max_attempts: int = 3
    outbox_worker_enabled: bool = True
    outbox_poll_seconds: float = 0.5
    outbox_max_attempts: int = 10
    outbox_webhook_url: str | None = None
    outbox_webhook_secret: str | None = None
    database_pool_size: int = 10
    database_max_overflow: int = 20
    require_migrations: bool = True
    expected_schema_revision: str = "0013"

    sse_heartbeat_seconds: int = 15
    max_parallel_generations: int = 2

    @model_validator(mode="after")
    def validate_production_settings(self) -> "Settings":
        if self.embedding_api_key:
            if not self.embedding_model.strip():
                raise ValueError("配置 EMBEDDING_API_KEY 时必须指定 EMBEDDING_MODEL")
            if self.embedding_dimensions != 1024:
                raise ValueError("当前 pgvector 数据库契约要求 EMBEDDING_DIMENSIONS=1024")
        web_search_values = (
            self.web_search_base_url,
            self.web_search_api_key,
            self.web_search_mcp_url,
        )
        if any(web_search_values) and not all(web_search_values):
            raise ValueError("配置 WebSearch 时必须同时指定 BASE_URL、API_KEY 和 MCP_URL")
        if self.env != "production":
            return self
        if self.secret_key == "change-this-in-production" or len(self.secret_key) < 32:
            raise ValueError("生产环境 SECRET_KEY 必须是至少 32 字符的随机值")
        if "*" in self.cors_origins:
            raise ValueError("生产环境启用凭据时 CORS_ORIGINS 不能包含通配符")
        if self.llm_backend == "mock":
            raise ValueError("生产环境不能使用 LLM_BACKEND=mock")
        if self.llm_aliyun_model and (not self.llm_aliyun_base_url or not self.llm_aliyun_api_key):
            raise ValueError("配置 LLM_ALIYUN_MODEL 时必须同时配置 LLM_ALIYUN_BASE_URL 和 LLM_ALIYUN_API_KEY")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
