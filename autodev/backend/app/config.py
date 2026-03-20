from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://autodev:autodev_password@localhost:5432/autodev_db"

    # Redis
    REDIS_URL: str = "redis://localhost:6379"

    # Security
    SECRET_KEY: str = "change-me-in-production-min-32-chars-long"
    ENCRYPTION_KEY: str = "change-me-32-byte-base64-encoded-key="
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # CORS
    CORS_ORIGINS: str = "http://localhost:3000"

    # Zoho OAuth
    ZOHO_CLIENT_ID: str = "1000.HTU6DWQXE99HBQ19MZWW4GXBZ2RLOR"
    ZOHO_CLIENT_SECRET: str = ""
    ZOHO_REDIRECT_URI: str = "http://localhost:3000/zoho-callback"

    # GitHub OAuth
    GITHUB_CLIENT_ID: str = ""
    GITHUB_CLIENT_SECRET: str = ""
    GITHUB_REDIRECT_URI: str = "http://localhost:3000/github-callback"
    # GitHub Webhook — set this to the secret you enter in GitHub → repo → Settings → Webhooks
    GITHUB_WEBHOOK_SECRET: str = ""

    # App
    APP_ENV: str = "development"
    DEBUG: bool = True

    @property
    def cors_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]


settings = Settings()
