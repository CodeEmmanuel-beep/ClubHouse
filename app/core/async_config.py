from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from app.core.config import settings
from sqlalchemy.orm import sessionmaker


engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_size=5,
    max_overflow=10,
    pool_timeout=30,
    pool_recycle=1800,
)
AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


async def get():
    async with engine.begin() as conn:
        await conn.run_sync(lambda _: None)
