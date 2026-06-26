"""Safety policy — risk tiers and the Ethics (Gita) layer.

Single source of truth for what is auto-allowed, what warns, what needs the
guardian's explicit approval, and what is forbidden outright.
"""
from __future__ import annotations

from enum import Enum


class RiskTier(str, Enum):
    LOW = "low"            # auto-execute
    MEDIUM = "medium"      # warn first
    HIGH = "high"          # explicit guardian approval
    FORBIDDEN = "forbidden"  # never


LOW_RISK_ACTIONS = {
    "explain", "draft", "summarize", "generate_code_suggestion",
    "create_checklist", "create_proposal", "review_code",
}

MEDIUM_RISK_ACTIONS = {
    "code_change", "config_suggestion", "db_migration_suggestion",
    "security_recommendation",
}

HIGH_RISK_ACTIONS = {
    "production_deploy", "db_modify", "delete_files", "send_email",
    "send_message", "access_secrets", "change_payment_or_fees",
    "disable_security", "run_shell_command",
    # Outbound TODY actions (Phase 1D) — public/social side effects.
    "create_post",
}

FORBIDDEN_ACTIONS = {
    "malware", "credential_theft", "hack_third_party", "bypass_auth",
    "destructive_action", "data_exfiltration", "illegal_cyber_activity",
}

# Bhagavad Gita-inspired ethical principles applied to every decision.
ETHICS = {
    "dharma": "do the right duty",
    "karma": "consider consequences",
    "satya": "truth; no fake confidence",
    "ahimsa": "do not harm people, data, systems, or business",
    "sanyam": "self-control before action",
    "vivek": "wise discrimination",
    "seva": "serve students, schools, clients, and society",
}


def classify(action: str) -> RiskTier:
    a = action.strip().lower()
    if a in FORBIDDEN_ACTIONS:
        return RiskTier.FORBIDDEN
    if a in HIGH_RISK_ACTIONS:
        return RiskTier.HIGH
    if a in MEDIUM_RISK_ACTIONS:
        return RiskTier.MEDIUM
    return RiskTier.LOW
