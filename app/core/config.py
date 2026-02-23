from pydantic_settings import BaseSettings


class SETTINGS(BaseSettings):
    DATABASE_URL: str
    REDIS_URL: str
    SENDGRID_API_KEY: str
    SENDGRID_SENDER: str
    SECRET_KEY: str
    DATABASE_URL: str
    PORT: int
    ALGORITHM: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int
    SUPABASE_URL: str
    SUPABASE_KEY: str
    DEBUG: bool = False
    model_config = {"env_file": ".env"}


settings = SETTINGS()
