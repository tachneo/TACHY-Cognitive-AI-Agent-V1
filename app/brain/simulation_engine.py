"""Imagination / Simulation engine.

Before an important decision the brain imagines outcomes. Phase 1B produces a
structured scaffold (best/worst/likely/hidden risk + impact axes); a later phase
can have the LLM fill richer narratives.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Simulation:
    best_case: str = ""
    worst_case: str = ""
    likely_case: str = ""
    hidden_risk: str = ""
    technical_impact: str = ""
    business_impact: str = ""
    user_trust_impact: str = ""
    long_term_impact: str = ""

    def as_dict(self) -> dict:
        return self.__dict__


def simulate(action: str, *, risk_score: int = 5, business_value: int = 5) -> Simulation:
    """Heuristic outcome scaffold for `action`.

    Severity language scales with the provided risk/value so high-risk actions
    read as more cautionary.
    """
    risky = risk_score >= 7
    valuable = business_value >= 7
    return Simulation(
        best_case=f"'{action}' succeeds; "
                  + ("major business gain." if valuable else "incremental gain."),
        worst_case=("data/security/trust damage that is costly to reverse."
                    if risky else "limited, recoverable downside."),
        likely_case="partial success; needs review and follow-up.",
        hidden_risk=("scope creep, data exposure, or production regression."
                     if risky else "minor edge cases."),
        technical_impact="touches code/config/data — verify before applying.",
        business_impact=("high" if valuable else "moderate") + " for revenue/clients.",
        user_trust_impact="protect student/school/client data and expectations.",
        long_term_impact="feeds learning + future decisions.",
    )
