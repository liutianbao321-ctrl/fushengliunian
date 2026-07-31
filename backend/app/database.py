from collections.abc import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings

settings = get_settings()
engine = create_async_engine(
    settings.database_url,
    future=True,
    pool_pre_ping=True,
    pool_size=settings.database_pool_size,
    max_overflow=settings.database_max_overflow,
)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def check_database_ready() -> None:
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
        if settings.require_migrations:
            version = await connection.scalar(text("SELECT version_num FROM alembic_version LIMIT 1"))
            if version != settings.expected_schema_revision:
                raise RuntimeError(
                    f"数据库迁移版本不匹配: expected={settings.expected_schema_revision}, actual={version or 'none'}"
                )
