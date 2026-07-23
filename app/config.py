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
    guardian_tody_user_uuid: str = ""
    guardian_legacy_identity_fallback_enabled: bool = False
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

    # Chat brain (Phase 2F) — Shree's conversation voice. Prefers Claude for
    # warm, sharp, human replies; falls back to the default provider. Only the
    # interactive reply path uses this; background thinking stays on the cheap
    # default provider so it never burns the Claude rate limit.
    chat_provider: str = "default"          # anthropic | default
    chat_model: str = "claude-sonnet-5"
    chat_anthropic_key: str = ""            # falls back to coding key / llm_api_key

    # Multi-LLM NVIDIA pool — different models on separate NVIDIA keys so the
    # guardian chat, other people's small talk, and internal micro-tasks stop
    # queueing behind the slow default reasoning model, and token/rate limits
    # spread across keys. Any purpose without a key falls back to the default
    # provider. Kill switch: LLM_MULTI_ENABLED=false.
    llm_multi_enabled: bool = True
    chat_nvidia_model: str = "deepseek-ai/deepseek-v4-pro"        # guardian chat
    chat_nvidia_key: str = ""
    social_nvidia_model: str = "z-ai/glm-5.2"                     # other people
    social_nvidia_key: str = ""
    light_nvidia_model: str = "google/diffusiongemma-26b-a4b-it"  # micro-tasks
    light_nvidia_key: str = ""
    vision_nvidia_model: str = "minimaxai/minimax-m3"             # multimodal
    vision_nvidia_key: str = ""
    tody_vision_enabled: bool = False
    tody_vision_max_bytes: int = 10_000_000
    # Qwen3.5-397B-A17B is NVIDIA's multimodal Qwen VLM; send image_url
    # content blocks, never the raw credential or image bytes to logs.
    tody_vision_model: str = "qwen/qwen3.5-397b-a17b"
    tody_media_allowed_hosts: str = "api.tody.in,chat.tody.in,chat.tachy.in"

    # GitHub self-lookup (Phase 2C-selfverify F2) — read-only PAT so Shree can
    # read her OWN repo when Rohit links it on TODY. Enforced allowlist: she can
    # only read repos in github_allowed_repos, never other projects. Never
    # commit a real token; set it in .env.
    github_token: str = ""
    github_allowed_repos: str = "tachneo/TACHY-Cognitive-AI-Agent-V1"

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
    tody_username: str = "shree"
    tody_display_name: str = "Shree"
    tody_token_path: str = "storage/logs/tody_tokens.json"
    tody_fast_reply_enabled: bool = True
    tody_fast_reply_conversation_id: str = ""
    tody_fast_reply_interval: int = 5
    tody_chat_chunk_target: int = 240
    tody_typing_delay_enabled: bool = True
    tody_typing_delay_min: float = 0.7
    tody_typing_delay_max: float = 3.0
    tody_typing_chars_per_second: float = 120.0
    tody_human_typing_enabled: bool = False
    tody_human_typing_cps_min: float = 28.0
    tody_human_typing_cps_max: float = 58.0
    tody_human_typing_max_delay: float = 8.0
    tody_human_typing_pause_probability: float = 0.08
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

    # Self-improvement (Phase 2G) — Shree edits her OWN code on a branch, tests
    # must pass, Rohit reviews/merges. Never auto-applies to main.
    self_improve_enabled: bool = True
    # Autonomous mode (Phase 2H): she may plan, build, test, and publish her OWN
    # improvement branches. Production promotion additionally requires the
    # Parent Kernel gate below. Safety code always needs Rohit (see _PROTECTED).
    self_improve_autonomous: bool = False
    self_improve_max_files: int = 6        # bigger changes → need review
    self_improve_max_lines: int = 500
    self_improve_daily_cap: int = 3        # max autonomous upgrades per day
    self_improve_auto_deploy: bool = True  # restart service after a safe merge
    # Parent Kernel authority separator. Autonomous improvement may still plan,
    # build, test, and publish review branches while this is false, but it may
    # not merge into the serving branch or restart production services.
    self_improve_production_promotion_enabled: bool = False

    # Child-module evolution control plane. Child modules may evolve inside
    # their sandbox, while Parent Kernel authority remains guardian-gated.
    self_module_factory_enabled: bool = False
    brain_surgery_enabled: bool = False
    self_module_auto_propose_enabled: bool = False
    self_module_canary_enabled: bool = False
    self_module_require_approval: bool = True
    self_module_shadow_enabled: bool = True
    self_module_allow_core_patch: bool = False
    parent_kernel_router_enabled: bool = True
    self_module_sandbox_root: str = "app/sandbox"
    self_module_min_score_low: int = 85
    self_module_min_score_medium: int = 92
    self_module_min_score_high: int = 97

    # Autonomous child-module activation (Rohit's grant: child modules grow
    # freely; only the CORE brain stays guardian-gated). When enabled, LOW/
    # MEDIUM-risk validated modules auto-promote shadow → canary → active,
    # driven by the worker, gated at every step by eval score + live health +
    # auto-rollback. HIGH/CRITICAL risk, or anything touching protected core/
    # safety files, ALWAYS requires Rohit — she can never self-grant those.
    self_module_autonomous_activation: bool = False   # master permission
    self_module_max_autonomous_risk: str = "medium"   # low | medium (never high)
    self_module_min_health: int = 80                  # rollback floor
    self_module_canary_min_samples: int = 5           # health samples per step
    # Whether an ACTIVE child module actually runs (advisory) in the live path.
    # Separate, extra-cautious switch: executing self-generated code on live
    # traffic is the single riskiest step, so it stays off until deliberately
    # enabled. Shadow execution (output discarded) runs regardless.
    self_module_live_invocation: bool = False

    # Self-heal (Phase 2K) — a daily worker tick runs self_diagnose.auto_heal()
    # so Shree finds and fixes her own runtime bugs WITHOUT Rohit having to ask
    # "diagnose". She still goes through every 2H safety gate (branch + tests +
    # protected-file guard + boot-check); this only removes the manual trigger.
    # Requires SELF_IMPROVE_AUTONOMOUS=true to actually fix — otherwise the
    # daily tick scans and logs only (report mode). Default off: opt in.
    self_heal_daily: bool = False

    # Voice (Riva TTS → TODY voice note). DISABLED until the TTS NIM is
    # provisioned for the NVIDIA account — the function-id from the docs is not
    # available to this account yet, so synthesis 404s. Code path is complete.
    voice_enabled: bool = False
    voice_server: str = "grpc.nvcf.nvidia.com:443"
    voice_function_id: str = "ddacc747-1269-4fab-bfd9-8f593dead106"
    voice_api_key: str = ""
    voice_name: str = "Chatterbox-Multilingual.en-US.Female"
    voice_language: str = "en-US"
    # Hearing (ASR): inbound voice notes -> text. parakeet multilingual
    # handles Hindi + Hinglish (verified on a real voice note, 1.3s).
    voice_hearing_enabled: bool = True
    voice_asr_function_id: str = "71203149-d3b7-4460-8231-1be2543a1fca"
    voice_asr_language: str = "hi-IN"

    # Natural-language understanding (Phase 3F) — read what a human MEANT
    # (task/command/order/relay + emotion) instead of requiring rigid command
    # syntax. Fixes: "X ko bolo ki Y" became a promise she couldn't keep.
    natural_intent_enabled: bool = True
    # Act on a clearly-understood order without demanding command syntax.
    natural_action_enabled: bool = True
    # Gita/Vedic grounding for emotion regulation and decisions (Rohit's core
    # reference). Shapes tone/priority only — never overrides truth or safety.
    gita_wisdom_enabled: bool = True
    # Social awareness: stop autonomous broadcasting after N unanswered msgs.
    social_awareness_enabled: bool = True
    social_silence_threshold: int = 2

    # Repair queue (Phase 3A, metacognitive loop) — evidence-tiered accumulator
    # of her own failure signatures (guardian corrections > conversational
    # ground truth > system events > LLM self-critique). Pure logging + status
    # transitions; the repair itself still goes through the 2G/2H gates.
    repair_queue_enabled: bool = True

    # Autonomous social mode (Phase 2D) — Shree talks freely with anyone.
    # OFF by default: only the guardian gets auto-replies until you enable it.
    tody_autonomous_social: bool = False
    tody_social_reply_cap: int = 40          # per conversation per day (anti-loop)
    tody_social_poll_conversations: int = 15  # how many convs the worker scans

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

    # Real-time verifier (Phase 2J) — Shree searches the web HERSELF and answers
    # with a confidence level, cross-checking independent sources. Keyless/free
    # (reuses web_explorer: DuckDuckGo → Bing → Wikipedia). Kill switch below.
    web_search_enabled: bool = True
    web_search_max_sources: int = 5
    web_search_fetch_pages: int = 2      # how many top hits to read in full

    # Prospective memory — Shree's scheduler. The light pool model reads every
    # inbound guardian message for a time-bound commitment ("remind me at 3pm",
    # "kal subah bata dena") and writes a scheduled_actions row; the worker tick
    # fires due rows through the existing approval-gated send. Converts her from
    # talking about the future to acting in it. Only guardian messages can create
    # reminders (a stranger must not inject scheduled sends). Kill switch below.
    prospective_memory_enabled: bool = True

    # Cognitive state spine (Phase A) — the single live state object assembled
    # from mood / inner-life / commitments / memory / focus, injected into every
    # reply prompt so Shree has continuity of STATE (not just chat history).
    # A read-model aggregator: each subsystem keeps owning its state; the spine
    # only additionally tracks current focus + wake timing. Kill switch below.
    cognitive_state_enabled: bool = True
    cognitive_state_path: str = "storage/logs/cognitive_state.json"

    # Autonomous tasks — the self-triggering loop (the AGI precondition Shree
    # herself named: "mujhe ek self-triggering loop do"). She registers RECURRING
    # tasks (from her own reflection or Rohit's assignments) and the worker fires
    # them on her clock. Handlers are an ALLOWLIST of pre-approved capabilities;
    # outbound (message-Papa) handlers go through the verified guardian send path.
    # Default off: opt in. Daily cap per handler stops a run-amok loop.
    autonomous_tasks_enabled: bool = False
    autonomous_tasks_daily_cap_per_handler: int = 6


@lru_cache
def get_settings() -> Settings:
    return Settings()
