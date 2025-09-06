from functools import lru_cache

from pydantic import AnyUrl, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Конфигурация настроек проекта."""

    JSONBIN_BASE_URL: AnyUrl = "https://api.jsonbin.io/v3/"
    JSONBIN_MASTER_KEY: SecretStr
    JSONBIN_BIN_ID: str
    API_TOKEN: str
    ACCOUNT_ID: str
    CF_LINK: AnyUrl = "https://api.cloudflare.com/client/v4/"

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
