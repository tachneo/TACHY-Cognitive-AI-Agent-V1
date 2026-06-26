"""Main agent — routes a request to the right skill agent over the brain.

Intent routing is keyword-based in Phase 1C; a later phase can let the LLM pick.
"""
from __future__ import annotations

from app.agents.base_agent import AgentResult
from app.agents.business_agent import BusinessAgent
from app.agents.coding_agent import CodingAgent
from app.agents.security_agent import SecurityAgent

_SECURITY = SecurityAgent()
_CODING = CodingAgent()
_BUSINESS = BusinessAgent()

_AGENTS = {a.name: a for a in (_SECURITY, _CODING, _BUSINESS)}


def route(message: str) -> str:
    """Pick a skill agent name from the message."""
    t = (message or "").lower()
    if any(k in t for k in ("security", "vulnerab", "sql", "csrf", "xss",
                            "auth", "hack", "leak", "idor")):
        return "security"
    if any(k in t for k in ("client", "proposal", "price", "pricing", "quote",
                            "negotiat", "invoice", "deadline", "scope")):
        return "business"
    if any(k in t for k in ("code", "bug", "function", "php", "python", "api",
                            "query", "refactor", "implement", "fix")):
        return "coding"
    return "coding"  # safe default skill


def handle(message: str, *, agent: str | None = None,
           project: str | None = None) -> AgentResult:
    """Run the chosen (or auto-routed) skill agent."""
    name = agent if agent in _AGENTS else route(message)
    return _AGENTS[name].run(message, project=project)
