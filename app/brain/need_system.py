"""Need & Goal System — classify each request into a need category.

Mirrors the plan's need priority order; the rank feeds attention/priority so
safety and production protection always outrank experimentation.
"""
from __future__ import annotations

# Lower rank = higher priority need.
NEED_PRIORITY = [
    "safety_legal",        # 1. safety and legal protection
    "production",          # 2. production system protection
    "client_trust",        # 3. client trust
    "revenue_growth",      # 4. revenue and business growth
    "product_quality",     # 5. product quality
    "speed",               # 6. speed
    "experimentation",     # 7. experimentation
]

_KEYWORDS: dict[str, tuple[str, ...]] = {
    "safety_legal": ("security", "legal", "breach", "leak", "gdpr", "privacy",
                     "vulnerab", "hack", "compliance", "fraud"),
    "production": ("production", "prod", "down", "outage", "live", "crash",
                   "500", "broken", "urgent bug", "data loss"),
    "client_trust": ("client", "customer", "school", "complaint", "trust",
                     "demo", "deadline", "deliver"),
    "revenue_growth": ("revenue", "price", "pricing", "sales", "proposal",
                       "payment", "invoice", "growth", "market"),
    "product_quality": ("feature", "quality", "refactor", "improve", "ux",
                        "design", "test"),
    "speed": ("fast", "quick", "speed", "performance", "optimize"),
    "experimentation": ("experiment", "try", "prototype", "idea", "research"),
}


def classify(text: str) -> dict:
    """Return the dominant need plus its priority rank (1 = most important)."""
    t = (text or "").lower()
    best = "experimentation"
    best_rank = len(NEED_PRIORITY)
    for need in NEED_PRIORITY:
        if any(k in t for k in _KEYWORDS[need]):
            best = need
            best_rank = NEED_PRIORITY.index(need) + 1
            break  # NEED_PRIORITY is ordered, first match wins
    return {"need": best, "rank": best_rank}
