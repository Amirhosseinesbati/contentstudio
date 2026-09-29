from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    mode: str = "demo"
    database_url: str = "sqlite:///./contentstudio.db"
    media_root: Path = Path("./data/media")
    fixtures_root: Path = Path("../../fixtures")
    service_token: str = ""
    n8n_intake_webhook: str = ""
    n8n_health_url: str = ""
    n8n_api_key: str = ""
    n8n_timeout_seconds: float = 5.0
    cookie_secure: bool = False
    session_hours: int = 12
    demo_password: str = "DemoStudio!2026"
    upload_limit_mb: int = 25
    model_provider: str = "fixture"
    model_id: str = ""
    openai_api_key: str = ""
    transcription_provider: str = "fixture"
    transcription_model: str = "whisper-1"
    wordpress_base_url: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
