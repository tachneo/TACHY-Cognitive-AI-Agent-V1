"""Thread-local record of the last LLM generation.

The reply path is synchronous per inbound message (one thread processes one
message end-to-end), so a thread-local side-channel lets the memory guard —
running on the same thread, AFTER the provider call — know whether the reply
it is about to persist was cut short by a max_tokens limit or came from a
fallback/offline path. That is exactly the signal needed to refuse storing a
half-thought or a placeholder in long-term memory (memory poisoning compounds
forever, so a corrupted reply must never enter ``cognitive_memories``).

Providers call ``record(...)`` on every completion; ``reply_safety`` calls
``mark_fallback()`` when it substitutes a warm fallback; the memory guard
calls ``last_generation()`` to decide whether to persist.
"""
from __future__ import annotations

import threading

_state = threading.local()

_DEFAULT = {"finish_reason": None, "truncated": False, "fallback": False}


def last_generation() -> dict:
    """Snapshot of the most recent generation on this thread."""
    return dict(getattr(_state, "info", _DEFAULT))


def record(*, finish_reason: str | None = None, truncated: bool = False,
           fallback: bool = False) -> None:
    """Full record — called by providers. Resets all fields."""
    _state.info = {"finish_reason": finish_reason, "truncated": truncated,
                   "fallback": fallback}


def mark_fallback() -> None:
    """Flag that the reply came from a fallback/offline path. Preserves the
    finish_reason/truncated fields set by the provider (they are irrelevant
    once a fallback is used, but kept for diagnostics)."""
    info = getattr(_state, "info", dict(_DEFAULT))
    info["fallback"] = True
    _state.info = info


def reset() -> None:
    """Clear the record — used by tests and at the start of a fresh turn."""
    _state.info = dict(_DEFAULT)
