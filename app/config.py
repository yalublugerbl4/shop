from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    telegram_bot_token: str  # Токен нужен только для проверки initData от Telegram WebApp
    database_url: str
    admin_tgid: str
    frontend_url: str
    node_env: str = "production"
    port: int = 8000
    cors_origins: Optional[str] = None
    # Примечание: бот управляется через n8n, токен нужен только для валидации initData

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()

