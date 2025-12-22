from sqlalchemy import create_engine
from app.core.config import settings


sync_engine = create_engine(settings.SYNC_DATABASE_URL)
