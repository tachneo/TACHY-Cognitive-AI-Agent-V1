"""Memory-poisoning guard + nemotron truncation fix (Phase 2K).

Two guarantees that stop corruption at the mouth AND the memory:
  1. NvidiaProvider (nemotron) now tracks finish_reason and trims a max_tokens
     cut back to the last complete sentence — the pool chat provider already did.
  2. reply_safety.is_safe_to_remember() refuses to persist a truncated or
     fallback reply, so a half-thought never enters cognitive_memories.
"""
import httpx

from app.llm import gen_state


# ── NvidiaProvider truncation ─────────────────────────────────────


class _FakeStream:
    def __init__(self, lines):
        self._lines = lines

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def raise_for_status(self):
        return None

    def iter_lines(self):
        yield from self._lines


def _patch_stream(monkeypatch, lines):
    def fake_stream(*args, **kwargs):
        return _FakeStream(lines)
    monkeypatch.setattr(httpx, "stream", fake_stream)


def test_nemotron_trims_on_length_cut_and_flags_truncated(monkeypatch):
    from app.llm.provider import NvidiaProvider

    gen_state.reset()
    content = ("This is the first complete sentence that is long enough to "
               "pass the halfway mark. Then a second part cut off mid wor")
    _patch_stream(monkeypatch, [
        f'data: {{"choices":[{{"delta":{{"content":"{content}"}}}}]}}',
        'data: {"choices":[{"delta":{},"finish_reason":"length"}]}',
        "data: [DONE]",
    ])
    prov = NvidiaProvider("k", "nvidia/nemotron-3-ultra-550b-a55b",
                          "https://integrate.api.nvidia.com/v1")
    out = prov.complete("sys", "p", max_tokens=10)

    assert out == "This is the first complete sentence that is long enough to pass the halfway mark."
    assert gen_state.last_generation()["truncated"] is True
    assert gen_state.last_generation()["finish_reason"] == "length"


def test_nemotron_no_trim_when_stop_finish_reason(monkeypatch):
    from app.llm.provider import NvidiaProvider

    gen_state.reset()
    _patch_stream(monkeypatch, [
        'data: {"choices":[{"delta":{"content":"A clean short reply."}}]}',
        'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}',
        "data: [DONE]",
    ])
    prov = NvidiaProvider("k", "nvidia/nemotron-3-ultra-550b-a55b",
                          "https://integrate.api.nvidia.com/v1")
    out = prov.complete("sys", "p", max_tokens=10)

    assert out == "A clean short reply."
    assert gen_state.last_generation()["truncated"] is False


def test_nemotron_appends_ellipsis_when_no_sentence_boundary(monkeypatch):
    from app.llm.provider import NvidiaProvider

    gen_state.reset()
    _patch_stream(monkeypatch, [
        'data: {"choices":[{"delta":{"content":"cut off mid word with no end"}}]}',
        'data: {"choices":[{"delta":{},"finish_reason":"length"}]}',
        "data: [DONE]",
    ])
    prov = NvidiaProvider("k", "nvidia/nemotron-3-ultra-550b-a55b",
                          "https://integrate.api.nvidia.com/v1")
    out = prov.complete("sys", "p", max_tokens=10)

    assert out.endswith("…")
    assert gen_state.last_generation()["truncated"] is True


# ── is_safe_to_remember guard ─────────────────────────────────────


def test_safe_to_remember_clean_reply():
    gen_state.reset()
    ok, reason = __import__("app.brain.reply_safety", fromlist=["is_safe_to_remember"]).is_safe_to_remember("A real answer.")
    assert (ok, reason) == (True, "ok")


def test_not_safe_when_truncated_flagged():
    gen_state.reset()
    gen_state.record(finish_reason="length", truncated=True)
    from app.brain.reply_safety import is_safe_to_remember
    ok, reason = is_safe_to_remember("trimmed reply")
    assert ok is False and reason == "truncated"


def test_not_safe_when_fallback_flagged():
    gen_state.reset()
    gen_state.record(finish_reason="stop", truncated=False)
    gen_state.mark_fallback()
    from app.brain.reply_safety import is_safe_to_remember
    ok, reason = is_safe_to_remember("my reasoning is offline")
    assert ok is False and reason == "fallback"


def test_not_safe_when_empty_or_fallback_prefix():
    gen_state.reset()
    from app.brain.reply_safety import is_safe_to_remember
    assert is_safe_to_remember("")[0] is False
    assert is_safe_to_remember("   ")[0] is False
    assert is_safe_to_remember("[reply fallback: boom]")[0] is False


def test_finalize_reply_marks_fallback_so_guard_blocks_it():
    gen_state.reset()
    from app.brain.reply_safety import finalize_reply, is_safe_to_remember
    # Empty raw → finalize substitutes a warm fallback and flags it.
    out = finalize_reply("", message="what is 2+2?", person="Papa")
    assert out  # never empty
    ok, reason = is_safe_to_remember(out)
    assert ok is False and reason == "fallback"


def test_finalize_reply_keeps_real_reply_safe():
    gen_state.reset()
    gen_state.record(finish_reason="stop", truncated=False)
    from app.brain.reply_safety import finalize_reply, is_safe_to_remember
    out = finalize_reply("The answer is 4.", message="what is 2+2?", person="Papa")
    assert out == "The answer is 4."
    ok, reason = is_safe_to_remember(out)
    assert (ok, reason) == (True, "ok")
