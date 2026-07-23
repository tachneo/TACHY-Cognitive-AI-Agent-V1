"""Voice — Shree speaks (NVIDIA Riva TTS → TODY voice note).

Gives her a real voice: synthesize speech with Riva and deliver it into the
chat as an audio attachment, so Papa can HEAR her rather than only read her.

STATUS (23 Jul 2026): WORKING. The documented chatterbox-multilingual-tts NIM
is not provisioned for this NVIDIA account, but ai-magpie-tts-multilingual IS
(function 877104f7-...), and it speaks both English and Hindi — verified live
at ~1s per utterance. Voice "Magpie-Multilingual" is the only voice it exposes.

Design notes:
  - Synthesis happens off the reply path. A voice note is an EXTRA, never a
    blocker: if TTS fails she still sends the text, so a dead voice service can
    never make her go quiet.
  - Text is cleaned before synthesis (emoji/markdown stripped) — a TTS engine
    reading "💛" or "**bold**" aloud sounds broken.
  - Length-capped: a voice note is a message, not a podcast.
"""
from __future__ import annotations

import re
import tempfile
import wave
from pathlib import Path

from app.config import get_settings
from app.safety.audit_logger import log_event_safe

_MAX_CHARS = 600           # a voice note, not a lecture
_SAMPLE_RATE = 44100

# Strip what should never be spoken aloud.
_EMOJI = re.compile("[\U0001f300-\U0001faff☀-➿←-⇿⬀-⯿]")
_MD = re.compile(r"[*_`>#]|\[(.*?)\]\(.*?\)")


def speakable(text: str) -> str:
    """Turn a chat reply into something that sounds right read aloud."""
    t = _EMOJI.sub("", text or "")
    t = _MD.sub(r"\1", t)
    t = re.sub(r"https?://\S+", "link", t)          # don't read out URLs
    t = re.sub(r"\n{2,}", ". ", t).replace("\n", ". ")
    t = re.sub(r"\s{2,}", " ", t).strip(" .,-")
    return t[:_MAX_CHARS]


def _auth():
    import riva.client
    s = get_settings()
    return riva.client.Auth(
        None, True, s.voice_server,
        [["function-id", s.voice_function_id],
         ["authorization", f"Bearer {s.voice_api_key}"]])


_DEVANAGARI = re.compile(r"[ऀ-ॿ]")


def pick_language(text: str) -> str:
    """Magpie is multilingual, so match the language she actually wrote in.
    Devanagari → hi-IN; romanised Hinglish and English both read best as
    en-US (hi-IN mangles latin-script Hinglish)."""
    return "hi-IN" if _DEVANAGARI.search(text or "") else "en-US"


def synthesize(text: str, *, voice: str | None = None) -> str | None:
    """Synthesize speech → path to a .wav, or None on any failure. Never raises:
    a broken voice service must never break a reply."""
    s = get_settings()
    if not s.voice_enabled:
        return None
    clean = speakable(text)
    if not clean:
        return None
    try:
        import riva.client
        tts = riva.client.SpeechSynthesisService(_auth())
        resp = tts.synthesize(clean, voice_name=(voice or s.voice_name),
                              language_code=pick_language(clean),
                              sample_rate_hz=_SAMPLE_RATE)
        audio = getattr(resp, "audio", None)
        if not audio:
            return None
        path = Path(tempfile.gettempdir()) / f"shree_voice_{abs(hash(clean))}.wav"
        # Riva returns raw PCM; wrap it so players/TODY see a valid wav.
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(_SAMPLE_RATE)
            w.writeframes(audio)
        return str(path)
    except Exception as exc:  # noqa: BLE001 — voice is an extra, never a blocker
        log_event_safe("voice_synthesis_failed", risk_tier="low",
                       detail=f"{type(exc).__name__}: {str(exc)[:120]}")
        return None


def send_voice_note(conversation_id: int, text: str) -> dict:
    """Speak `text` into a TODY conversation as an audio attachment. Returns
    {"sent": bool, "reason": ...}. The caller still sends the TEXT reply — the
    voice note accompanies it, it does not replace it."""
    if not get_settings().voice_enabled:
        return {"sent": False, "reason": "voice disabled"}
    path = synthesize(text)
    if not path:
        return {"sent": False, "reason": "synthesis unavailable"}
    try:
        from app.integrations.tody_client import get_client
        client = get_client()
        up = client.upload_attachment(path, media_type="audio/wav")
        att = (up or {}).get("attachment") or up or {}
        att_id = att.get("id") or att.get("attachment_id")
        if not att_id:
            return {"sent": False, "reason": "upload returned no attachment id"}
        client.send_message(conversation_id, "", attachment_id=int(att_id),
                            message_type="audio")
        log_event_safe("voice_note_sent", risk_tier="low",
                       detail=f"conv={conversation_id}; chars={len(text or '')}")
        return {"sent": True, "attachment_id": att_id}
    except Exception as exc:  # noqa: BLE001
        log_event_safe("voice_note_failed", risk_tier="low",
                       detail=f"{type(exc).__name__}: {str(exc)[:120]}")
        return {"sent": False, "reason": type(exc).__name__}
    finally:
        try:
            Path(path).unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            pass


# "voice me bolo" / "audio bhejo" / "bol ke sunao" / "speak it"
_VOICE_CMD = re.compile(
    r"\b(?:voice\s*(?:me|mein|note)?|audio|awaaz|awaz|bol\s*ke\s*suna|"
    r"bolkar\s*suna|speak|sunao|sunaao)\b", re.I)


def wants_voice(message: str) -> bool:
    """Did they ask to HEAR the answer?"""
    return bool(get_settings().voice_enabled and _VOICE_CMD.search(message or ""))


def describe() -> dict:
    s = get_settings()
    return {"enabled": s.voice_enabled, "voice": s.voice_name,
            "language": s.voice_language, "server": s.voice_server,
            "note": ("Riva TTS NIM not provisioned for this NVIDIA account as "
                     "of 23 Jul 2026 — enable it, then set VOICE_ENABLED=true")}
