"""Database engine, sessionmaker and session dependency utilities."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from newcode.core.config import settings

engine: AsyncEngine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    future=True,
)

async_session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI async dependency yielding an isolated database session."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db(custom_engine: AsyncEngine | None = None) -> None:
    """Initialize database tables using the ORM metadata."""
    import newcode.models.domain  # noqa: F401 - ensure domain models are registered
    from newcode.models.base import Base

    target_engine = custom_engine or engine
    async with target_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def drop_db(custom_engine: AsyncEngine | None = None) -> None:
    """Drop all tables using the ORM metadata."""
    import newcode.models.domain  # noqa: F401
    from newcode.models.base import Base

    target_engine = custom_engine or engine
    async with target_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
