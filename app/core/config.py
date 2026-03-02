from pydantic_settings import BaseSettings, SettingsConfigDict


class SETTINGS(BaseSettings):
    DATABASE_URL: str
    REDIS_URL: str
    SENDGRID_API_KEY: str
    SENDGRID_SENDER: str
    SECRET_KEY: str
    ALGORITHM: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int
    SUPABASE_URL: str
    SUPABASE_KEY: str
    DEBUG: bool = False
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = SETTINGS(**{})
