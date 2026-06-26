"""Base skill agent — shared LLM-backed reasoning with memory grounding.

A skill agent specialises the system prompt; the brain (memory recall, decision,
safety) stays underneath. With no LLM key, the heuristic provider keeps it runnable.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.brain.decision_engine import as_dict, decide
from app.llm.provider import get_provider
from app.memory.base_memory import recall


@dataclass
class AgentResult:
    agent: str
    reply: str
    decision: dict
    recalled: list[dict]


class BaseAgent:
    name: str = "base"
    system_prompt: str = "You are a TACHY skill agent."

    def run(self, message: str, *, project: str | None = None) -> AgentResult:
        decision = as_dict(decide(message))
        hits = recall(message, project=project, limit=5)
        memo = "\n".join(f"- [{h.memory_type}] {h.title}" for h in hits) or "- (none)"
        prompt = (
            f"Task: {message}\n\n"
            f"Detected project: {decision['project']} | action: {decision['action']} "
            f"| risk: {decision['risk_tier']} | approval needed: {decision['requires_approval']}\n"
            f"Relevant memory:\n{memo}\n\n"
            "Respond with a concrete, production-ready answer and a clear next step. "
            "If the action is high-risk, recommend requesting approval — never claim "
            "to have executed it."
        )
        try:
            reply = get_provider().complete(self.system_prompt, prompt)
        except Exception as exc:
            reply = f"[{self.name} fallback — LLM error: {type(exc).__name__}]"
        return AgentResult(
            agent=self.name, reply=reply, decision=decision,
            recalled=[{"id": h.id, "type": h.memory_type, "title": h.title} for h in hits],
        )
