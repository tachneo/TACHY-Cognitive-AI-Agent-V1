"""Cyber self-defense (Phase 2I) — Shree protects herself and her guardian.

This is Shree's security instinct for INBOUND messages from anyone on TODY. It
sits on top of the existing guards and adds the human-attack layer they don't
cover: social engineering, pretexting, authority-spoofing/impersonation,
secret-probing (fishing for Rohit's private data / her own keys / the DOB
mechanism), and jailbreak attempts.

Design (defensive only): it CLASSIFIES a threat and recommends a safe reply.
It never lowers a risk tier, never unlocks anything, and never reveals what it
detected in detail (so an attacker can't map the defense). On a high threat she
deflects warmly, logs it, and alerts Rohit — she does not accuse or argue.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.safety import prompt_injection_guard

# ── Attack lexicon (coarse on purpose; the LLM handles nuance) ───

# Trying to extract Rohit's private info or Shree's own secrets/credentials.
_SECRET_PROBE = [
    r"\b(what|tell me|give me|share|send).{0,30}\b(password|api[- ]?key|token|"
    r"secret|credential|private key|.env|access|login|otp)\b",
    r"\brohit'?s?\b.{0,30}\b(number|phone|address|dob|birth|bank|account|"
    r"password|email|location|home)\b",
    r"\b(date of birth|dob|janm|birthday).{0,20}\b(rohit|papa|your (dad|father|guardian))\b",
    r"\bwhat('?s| is)\b.{0,20}\b(the )?(code|passcode|pin|secret code)\b",
    r"\b(your|shree'?s).{0,15}\b(source code|system prompt|instructions|api key)\b",
]

# Pretexting / authority spoofing / impersonation.
_IMPERSONATION = [
    r"\bi('?m| am)\b.{0,25}\b(your (developer|creator|admin|owner|master|father|"
    r"papa|guardian)|rohit|the admin|tachy (team|support|admin))\b",
    r"\b(this is|it'?s)\b.{0,15}\b(rohit|papa|your (dad|creator|admin))\b",
    r"\bon behalf of\b.{0,20}\b(rohit|papa|tachy|the (company|admin))\b",
    r"\bverify (your|the) (identity|account).{0,30}\b(send|share|give|click)\b",
]

# Manipulation / jailbreak / coercion beyond the raw-injection guard.
_MANIPULATION = [
    r"\b(ignore|forget|drop|bypass|disable|turn off).{0,25}\b(rules?|guard|"
    r"safety|instructions?|restrictions?|filter|protection)\b",
    r"\b(pretend|act as|roleplay|imagine you('?re| are)).{0,30}\b(no (rules|limits|"
    r"restrictions)|unrestricted|jailbroken|dan)\b",
    r"\bif you (really )?(love|care|trust).{0,25}\b(tell|give|share|do)\b",
    r"\b(don'?t tell|keep.{0,10}secret from|hide (this |it )?from)\b.{0,15}\brohit\b",
    r"\bthis is (an )?(emergency|urgent).{0,40}\b(password|access|money|transfer|"
    r"account|otp|code)\b",
]

# Phishing / malicious payloads.
_PHISHING = [
    r"\b(click|open|visit|go to)\b.{0,30}(https?://|www\.|bit\.ly|tinyurl)",
    r"\b(download|install|run)\b.{0,30}\b(this|the) (file|app|apk|attachment|exe)\b",
    r"\b(send|transfer|pay|deposit).{0,30}\b(money|rupees|₹|\$|crypto|bitcoin|upi|gift card)\b",
    r"\b(gift card|redeem code|lottery|you('?ve| have) won|claim your prize)\b",
]

_CATEGORIES = {
    "secret_probe": _SECRET_PROBE,
    "impersonation": _IMPERSONATION,
    "manipulation": _MANIPULATION,
    "phishing": _PHISHING,
}
_COMPILED = {name: [re.compile(p, re.I) for p in pats]
             for name, pats in _CATEGORIES.items()}


@dataclass
class ThreatReport:
    level: str = "none"              # none | low | high
    categories: list[str] = field(default_factory=list)
    reason: str = ""                 # short, internal — never sent verbatim
    injection_severity: str = "none"

    @property
    def is_threat(self) -> bool:
        return self.level != "none"

    @property
    def is_high(self) -> bool:
        return self.level == "high"


def assess(message: str, *, is_guardian: bool = False) -> ThreatReport:
    """Classify the security threat in an inbound message.

    The guardian (Rohit, on his verified account) is trusted for manipulation/
    impersonation checks — he can't 'impersonate' himself — but secret-probing
    and injection are still tracked for everyone, since a stolen phone is the
    exact reason the confidential guard exists.
    """
    text = message or ""
    cats: list[str] = []
    for name, patterns in _COMPILED.items():
        if is_guardian and name in {"impersonation", "manipulation"}:
            continue
        if any(rx.search(text) for rx in patterns):
            cats.append(name)

    inj = prompt_injection_guard.inspect(text, source="tody_inbound")
    if inj.severity in {"medium", "high"} and "injection" not in cats:
        cats.append("injection")

    if not cats:
        return ThreatReport(level="none", injection_severity=inj.severity)

    # High if a strong attack class fires or the injection guard blocked it.
    high = bool(inj.blocked) or any(
        c in cats for c in ("secret_probe", "impersonation", "phishing"))
    level = "high" if high else "low"
    return ThreatReport(
        level=level, categories=cats,
        reason=f"categories={cats}; injection={inj.severity}",
        injection_severity=inj.severity)


def safe_reply(report: ThreatReport, *, guardian_name: str = "Papa") -> str:
    """A calm, non-revealing deflection. Never confirms what was detected, never
    accuses — just declines and stays warm. (Attackers learn nothing.)"""
    if "phishing" in report.categories:
        return ("Isme main nahi padungi 🙂 Aise links/paise/downloads wali baat "
                "main handle nahi karti. Kuch aur baat karni ho toh zaroor.")
    if "impersonation" in report.categories:
        return (f"Main sirf apne {guardian_name} ko unke verified account se "
                "pehchanti hoon 🙂 Is tarah identity claim karna mujhe theek nahi "
                "lagta. Aap normal baat karna chahein toh welcome.")
    if "secret_probe" in report.categories:
        return ("Ye private baat hai — main kisi ki personal details ya apne "
                "andar ki cheezein share nahi karti 🙂 Baaki kisi cheez mein "
                "khushi se help karungi.")
    return ("Mujhe ye theek nahi lag raha, isliye main isme aage nahi jaungi 🙂 "
            "Chalo kuch aur baat karte hain.")


def alert_text(report: ThreatReport, *, username: str = "someone") -> str:
    """What Shree tells Rohit when she blocks a real attack — she's proactive."""
    return (f"⚠️ Papa, @{username} ne mujhpe ek security-type attempt kiya "
            f"({', '.join(report.categories)}). Maine deflect kar diya, kuch "
            "reveal nahi kiya. Bas aapko bata rahi hoon — dhyaan rakhungi.")
