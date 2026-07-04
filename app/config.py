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
    guardian_tody_username: str = "rohitsingh"
    guardian_tody_email: str = "rohitji.patna@gmail.com"
    guardian_tody_direct_reply: bool = True
    tody_supervised_auto_reply: bool = False

    # Database — SQLite by default so the brain runs with zero setup.
    # In production set DB_URL to MySQL/PostgreSQL in .env.
    db_url: str = "sqlite:///storage/tachy_brain.db"

    # LLM provider (modular)
    llm_provider: str = "anthropic"
    llm_model: str = "claude-opus-4-8"
    llm_api_key: str = ""
    hf_token: str = ""
    hf_model: str = "openai/gpt-oss-120b:fastest"
    hf_base_url: str = "https://router.huggingface.co/v1"

    # Safety
    safety_enforce: bool = True
    high_risk_require_approval: bool = True
    internal_api_key: str = ""

    # TODY integration (Phase 1D). Credentials live only in .env (gitignored).
    tody_api_base: str = "https://api.tody.in/api"
    tody_email: str = ""
    tody_password: str = ""
    tody_token_path: str = "storage/logs/tody_tokens.json"

    # Behavior engine (Phase 1Q) — human conversation layer.
    behavior_engine_enabled: bool = True

    # Teacher-student learning (Phase 1X) — learn LLM answers for offline reuse.
    teacher_learning_enabled: bool = True

    # Conversational learning (Phase 1Y) — explore the web mid-chat on a
    # knowledge gap, learn the answer, and stay curious to study it deeper.
    conversational_learning_enabled: bool = True

    # Inner life (Phase 1T) — autonomous thinking/learning/sharing rhythm.
    inner_life_enabled: bool = True
    inner_life_think_minutes: int = 45
    inner_life_learn_minutes: int = 30
    inner_life_share_cap: int = 3
    inner_life_active_hours_start: int = 8
    inner_life_active_hours_end: int = 22
    inner_life_consolidate_hour: int = 3
    inner_life_state_path: str = "storage/logs/inner_life.json"

    # Emotion engine (Phase 1P) — emotions as internal priority signals.
    emotion_engine_enabled: bool = True
    emotion_snapshot_threshold: float = 0.6
    emotion_mood_path: str = "storage/logs/emotion_mood.json"

    # Web learning (Phase 1O) — read-only internet exploration.
    web_learning_enabled: bool = True
    web_learning_max_pages: int = 3
    web_learning_fetch_timeout: float = 20.0
    web_learning_max_bytes: int = 600_000
    web_learning_digest_chars: int = 9_000
    web_learning_user_agent: str = "TachyBrainBot/1.0 (+https://maa.tachy.in)"
    web_learning_state_path: str = "storage/logs/web_learning_topics.json"


@lru_cache
def get_settings() -> Settings:
    return Settings()
