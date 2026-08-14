"""
Configuración de base de datos - SQLAlchemy + asyncpg para auditoría.
"""

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.base import Base
from app.core.config import get_audit_db_url, settings
from app.models import (  # noqa: F401
    Breed,
    Dog,
    DogHealth,
    DogMedia,
    DogStatusHistory,
    Litter,
)

# Convención de nombres para constraints (mejora migraciones Alembic)
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

# metadata = MetaData(naming_convention=NAMING_CONVENTION)


# class Base(DeclarativeBase):
#     metadata = metadata


# Engine asíncrono para PostgreSQL
engine = create_async_engine(
    get_audit_db_url(settings).replace("postgresql://", "postgresql+asyncpg://"),
    echo=settings.ENVIRONMENT == "development",
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    pool_recycle=3600,
)

# Session factory
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncSession:
    """Dependency para obtener sesión de base de datos."""
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_redis() -> Redis:
    """Dependency para obtener cliente Redis."""
    redis = Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        password=settings.REDIS_PASSWORD or None,
        db=0,
        decode_responses=True,
    )
    try:
        yield redis
    finally:
        await redis.close()


async def get_redis_client() -> Redis:
    """Obtener cliente Redis directo (para health checks)."""
    return Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        password=settings.REDIS_PASSWORD or None,
        db=0,
        decode_responses=True,
    )


async def init_db():
    """Inicializar base de datos - crear tablas."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db():
    """Cerrar conexiones."""
    await engine.dispose()
