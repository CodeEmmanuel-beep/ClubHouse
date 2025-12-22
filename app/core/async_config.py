from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from app.core.config import settings
from sqlalchemy.orm import sessionmaker


engine = create_async_engine(settings.DATABASE_URL, echo=True)
AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)
