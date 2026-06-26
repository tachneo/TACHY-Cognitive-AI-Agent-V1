"""Central configuration for TACHY Cognitive Brain OS V1.

Loaded once from the environment (.env). Never log secrets.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App
    app_name: str = "TACHY Cognitive AI"
    app_env: str = "development"
    app_host: str = "127.0.0.1"
    app_port: int = 8200

    # Identity / guardian
    guardian_name: str = "Rohit Kumar"
    company_name: str = "TACHY EDTECH PRIVATE LIMITED"

    # Database
    db_url: str = "mysql+pymysql://USER:PASSWORD@127.0.0.1:3306/tachy_brain"

    # LLM provider (modular)
    llm_provider: str = "anthropic"
    llm_model: str = "claude-opus-4-8"
    llm_api_key: str = ""

    # Safety
    safety_enforce: bool = True
    high_risk_require_approval: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
