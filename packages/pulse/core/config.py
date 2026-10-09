from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PULSE_", env_file=".env", extra="ignore")
    database_url: str = "sqlite:///./pulse.db"
    admin_token: str = Field(default="", repr=False)
    adapter_url: str = "http://127.0.0.1:8001"
    adapter_token: str = Field(default="", repr=False)
    prometheus_url: str = "http://127.0.0.1:9090"
    web_origin: str = "http://localhost:3000"
    llm_model: str = ""
    llm_api_base: str | None = None
    llm_api_key: str | None = Field(default=None, repr=False)
    llm_timeout: float = 30
    tool_timeout: float = 12
    probe_urls: dict[str, str] = {}
    probe_allowed_hosts: list[str] = ["faulty-app", "localhost", "127.0.0.1"]
    monitor_enabled: bool = True

    @field_validator("llm_api_base", "llm_api_key", mode="before")
    @classmethod
    def empty_optional(cls, value):
        return value or None


@lru_cache
def get_config() -> Config:
    return Config()
