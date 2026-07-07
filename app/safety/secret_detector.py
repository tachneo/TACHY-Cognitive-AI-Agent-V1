"""Secret detector — find and redact secrets before they reach the LLM, logs,
terminal, or a git commit.

Shree reads repo files and runs shell commands; without this layer a real API
key, DB password, or private key inside a file or `git diff` would be sent
verbatim to the LLM provider and printed to Rohit's terminal. That is an
exfiltration path and an audit failure. This module is the single source of
truth for "what counts as a secret" across the coding agent.

Two operations:
  - ``scan(text)``    -> list[Finding]   (alert channel; includes entropy heuristics)
  - ``redact(text)``  -> (text, findings) (high-precision inline redaction used
                          before sending content to the LLM / terminal / logs)

``redact`` uses ONLY high-precision curated patterns so it never mangles normal
code and never breaks an exact-match ``edit_file`` by altering a string the
agent needs to match. ``scan`` additionally flags high-entropy standalone
tokens as lower-confidence *alerts* (surfaced to Rohit, not redacted inline).
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

# High-precision patterns. Each yields a Finding with a stable `kind`.
# Order matters only for readability; matches are non-overlapping per pass.
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("private_key", re.compile(
        r"-----BEGIN (?:RSA |EC |OPENSSH |PGP |DSA |ECDSA )?PRIVATE KEY-----"
        r"[\s\S]*?-----END (?:RSA |EC |OPENSSH |PGP |DSA |ECDSA )?PRIVATE KEY-----")),
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("aws_secret", re.compile(r"(?i)aws(?:_secret)?_access_key\s*[=:]\s*['\"]?"
                              r"[A-Za-z0-9/+=]{40}")),
    ("anthropic_key", re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,}\b")),
    ("openai_key", re.compile(r"\bsk-proj-[A-Za-z0-9_\-]{20,}\b|\bsk-[A-Za-z0-9]{40,}\b")),
    ("github_token", re.compile(r"\b(?:gh[pousr])_[A-Za-z0-9]{36,}\b")),
    ("slack_token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("google_api", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("stripe_key", re.compile(r"\b(?:sk|pk|rk)_(?:live|test)_[0-9A-Za-z]{16,}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.eyJ[A-Za-z0-9_\-]{8,}"
                       r"\.[A-Za-z0-9_\-]{8,}\b")),
    # DB URLs carrying credentials: scheme://user:pass@host
    ("db_url", re.compile(r"\b(?:mysql|postgres|postgresql|mongodb|redis|amqp)"
                          r"(?:\+[a-z]+)?://[^\s:/@]+:[^\s:/@]+@[^\s/]+")),
    # Naked credential assignments:  password = "..." / api_key: ... / SECRET=...
    # Require a label so we do not redact ordinary code identifiers.
    ("credential", re.compile(
        r"(?i)\b(?:api[_-]?key|apikey|secret|password|passwd|pwd|token|access[_-]?token|"
        r"private[_-]?token|client[_-]?secret|db[_-]?password|database[_-]?password|"
        r"auth|credential)\b\s*[:=]\s*['\"]?[A-Za-z0-9_\-./+=]{12,}['\"]?")),
    # .env-style VAR="..." only when the var name screams secret
    ("env_secret", re.compile(
        r"(?m)^[ \t]*(?:[A-Z0-9_]*(?:API_KEY|APIKEY|SECRET|PASSWORD|PASSWD|TOKEN|"
        r"PRIVATE_KEY|CLIENT_SECRET|DB_PASSWORD|ACCESS_KEY|CREDENTIAL)[A-Z0-9_]*)"
        r"\s*=\s*[\"']?[A-Za-z0-9_\-./+=]{8,}[\"']?")),
]

_REDACT_LABEL = "***REDACTED:{kind}***"

# Files whose contents are treated as secrets-by-location: reading them returns
# keys with values redacted rather than the raw file, so structure is visible
# without leaking values.
_SECRETS_FILES = re.compile(
    r"(^|/)(?:\.env(?:\.[A-Za-z0-9_]+)?|\.envrc|credentials|credentials\.json|"
    r"creds\.json|secrets\.json|secrets\.yaml|secrets\.yml|\.netrc|\.npmrc|"
    r"\.pypirc|\.aws/credentials|id_rsa|id_ed25519|id_ecdsa|.*\.pem|.*\.key"
    r"|.*\.keystore)$", re.I)


@dataclass
class Finding:
    kind: str
    line: int
    preview: str  # masked, safe to log/print


def _mask(value: str) -> str:
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}…{value[-2:]} (len={len(value)})"


def _line_of(text: str, idx: int) -> int:
    return text.count("\n", 0, idx) + 1


def scan(text: str) -> list[Finding]:
    """High-precision + entropy scan. Use for the alert/warn channel."""
    text = text or ""
    out: list[Finding] = []
    for kind, rx in _PATTERNS:
        for m in rx.finditer(text):
            out.append(Finding(kind, _line_of(text, m.start()), _mask(m.group(0))))
    out.extend(_entropy_findings(text))
    return out


def redact(text: str) -> tuple[str, list[Finding]]:
    """High-precision inline redaction. Returns (redacted_text, findings).

    Only curated patterns are replaced so normal code (and the exact strings
    ``edit_file`` must match) is never altered.
    """
    text = text or ""
    findings: list[Finding] = []
    out = text
    for kind, rx in _PATTERNS:
        def _sub(m: re.Match[str], _k: str = kind) -> str:
            findings.append(Finding(_k, _line_of(out, m.start()), _mask(m.group(0))))
            return _REDACT_LABEL.format(kind=_k)
        out = rx.sub(_sub, out)
    return out, findings


def is_secrets_path(path: str) -> bool:
    """True for files that should never have their values exposed on read."""
    return bool(_SECRETS_FILES.search(path or ""))


def redact_env_values(text: str) -> tuple[str, list[Finding]]:
    """For .env-style files: keep KEY names, replace only the values.

    Lets the agent see the file's structure (which keys exist) without ever
    leaking the secret values to the LLM or terminal.
    """
    text = text or ""
    findings: list[Finding] = []
    redacted_lines: list[str] = []
    for i, line in enumerate(text.splitlines(), 1):
        m = re.match(r"^([ \t]*(?:export[ \t]+)?[A-Za-z_][A-Za-z0-9_]*)(=)(.*)$",
                     line)
        if m and m.group(3).strip():
            val = m.group(3).strip().strip("'\"")
            if val and not val.lower() in {"", "none", "null", "true", "false"} \
                    and not val.replace(".", "").replace("-", "").isdigit():
                findings.append(Finding("env_value", i, _mask(val)))
                redacted_lines.append(f"{m.group(1)}{m.group(2)}***REDACTED:env***")
                continue
        redacted_lines.append(line)
    return "\n".join(redacted_lines), findings


def _entropy_findings(text: str) -> list[Finding]:
    """Flag long high-entropy standalone tokens as lower-confidence alerts.

    Intentionally conservative: 40+ chars within [A-Za-z0-9_-=+/] and Shannon
    entropy >= 4.5. Catches leaked bare tokens that miss the curated patterns
    while avoiding normal code (which rarely has 40-char high-entropy runs).
    """
    out: list[Finding] = []
    seen: set[str] = set()
    for m in re.finditer(r"[A-Za-z0-9_\-+/=]{40,}", text or ""):
        tok = m.group(0)
        if tok in seen:
            continue
        seen.add(tok)
        if _shannon(tok) >= 4.5:
            out.append(Finding("high_entropy_token", _line_of(text, m.start()),
                               _mask(tok)))
    return out


def _shannon(s: str) -> float:
    if not s:
        return 0.0
    counts: dict[str, int] = {}
    for ch in s:
        counts[ch] = counts.get(ch, 0) + 1
    n = len(s)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())
