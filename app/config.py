"""Central configuration for TACHY Cognitive Brain OS V1.

Loaded once from the environment (.env). Never log secrets. The .env is
resolved from the project root (the parent of this package) so the brain
configures correctly no matter which directory a process runs from — e.g.
`shree` invoked from Rohit's home still loads /var/www/maa.tachy.in/.env.
Real environment variables still take priority over the file.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_ENV_FILE = _PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(_ENV_FILE), extra="ignore")

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
    nvidia_api_key: str = ""
    nvidia_model: str = "nvidia/nemotron-3-ultra-550b-a55b"
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"
    nvidia_reasoning_budget: int = 16384
    nvidia_temperature: float = 1.0
    nvidia_top_p: float = 0.95

    # Coding agent (Phase 2B) — Shree's expert coder. Prefers Claude for
    # top-tier agentic coding + tool use; falls back to the default provider
    # (NVIDIA today) when no Anthropic key is set, so it always works.
    coding_provider: str = "anthropic"      # anthropic | default
    coding_anthropic_key: str = ""          # sk-ant-... (falls back to llm_api_key)
    coding_model: str = "claude-sonnet-5"   # claude-sonnet-5 | claude-opus-4-8
    coding_max_steps: int = 40
    coding_autonomy: str = "plan_first"     # plan_first | auto_low_risk | yolo
    coding_verify: bool = True              # run tests + self-review before 'done'
    coding_test_command: str = ""           # override auto-detected test command
    # NVIDIA is a slow reasoning model; a small budget keeps the tool loop snappy
    # (Claude, when configured, ignores this).
    coding_nvidia_reasoning_budget: int = 1536

    # Safety
    safety_enforce: bool = True
    high_risk_require_approval: bool = True
    internal_api_key: str = ""

    # TODY integration (Phase 1D). Credentials live only in .env (gitignored).
    tody_api_base: str = "https://api.tody.in/api"
    tody_email: str = ""
    tody_password: str = ""
    tody_token_path: str = "storage/logs/tody_tokens.json"
    tody_fast_reply_enabled: bool = True
    tody_fast_reply_conversation_id: str = ""
    tody_fast_reply_interval: int = 5
    tody_chat_chunk_target: int = 240
    tody_typing_delay_enabled: bool = True
    tody_typing_delay_min: float = 0.7
    tody_typing_delay_max: float = 3.0
    tody_typing_chars_per_second: float = 120.0
    tody_native_typing_enabled: bool = True
    tody_native_typing_keepalive_seconds: float = 2.0
    tody_native_typing_preview: str = ""
    tody_presence_heartbeat_enabled: bool = True

    # Behavior engine (Phase 1Q) — human conversation layer.
    behavior_engine_enabled: bool = True

    # Teacher-student learning (Phase 1X) — learn LLM answers for offline reuse.
    teacher_learning_enabled: bool = True

    # Offline local brain — deterministic no-LLM replies from identity, memory,
    # curriculum, interests, and capability truth.
    offline_brain_enabled: bool = True

    # Conversational learning (Phase 1Y) — explore the web mid-chat on a
    # knowledge gap, learn the answer, and stay curious to study it deeper.
    conversational_learning_enabled: bool = True

    # Confidential guard (Phase 1Z) — hidden DOB second factor for private data.
    confidential_guard_enabled: bool = True
    confidential_dob: str = "25-08-1987"
    confidential_unlock_ttl_minutes: int = 30

    # Curriculum mastery — CBSE/NCERT foundation through Class 12, then exam tracks.
    curriculum_learning_enabled: bool = True
    curriculum_state_path: str = "storage/logs/curriculum_mastery.json"

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
