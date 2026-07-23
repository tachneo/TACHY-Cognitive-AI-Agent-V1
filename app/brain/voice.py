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
# Hindi words that mark a line as Hinglish rather than plain English.
_HINGLISH_MARKERS = re.compile(
    r"\b(?:main|mai|hoon|hu|hai|hain|nahi|nahin|kya|kaise|kaisi|aap|tum|papa|"
    r"acha|accha|theek|thik|bilkul|karo|karna|kar|raha|rahi|rahe|ho|gaya|"
    r"gayi|bhi|toh|to\b|se|ko|ka|ki|ke|mera|meri|tumhara|aur|par|abhi|baat|"
    r"batao|bolo|haan|han|ji|yaar|dekho|chalo|sab|kuch|bahut|thoda)\b", re.I)

_TRANSLITERATE_SYSTEM = (
    "Convert the given romanised Hindi/Hinglish into Devanagari script so it "
    "can be read aloud naturally by a Hindi speaker. Keep genuinely English "
    "words in Latin script (names, technical terms). Do not translate, do not "
    "explain, do not add anything. Reply with ONLY the converted text."
)


def is_hinglish(text: str) -> bool:
    t = text or ""
    return bool(_DEVANAGARI.search(t)) or len(_HINGLISH_MARKERS.findall(t)) >= 2


def to_devanagari(text: str) -> str | None:
    """Romanised Hinglish → Devanagari, so the Hindi voice pronounces it like an
    Indian speaker instead of an English one. Magpie reads latin-script Hinglish
    badly (it swallowed a third of the audio in testing), and there is only one
    voice available — so the SCRIPT is the only lever we have on accent.
    Returns None on any failure; the caller then falls back to en-US."""
    t = (text or "").strip()
    if not t or _DEVANAGARI.search(t):
        return t or None
    try:
        from app.llm.provider import get_light_provider
        out = (get_light_provider().complete(_TRANSLITERATE_SYSTEM, t,
                                             max_tokens=400) or "").strip()
        # Trust it only if it actually produced Devanagari.
        return out if out and _DEVANAGARI.search(out) else None
    except Exception:  # noqa: BLE001 — never let this break the voice note
        return None


def pick_language(text: str) -> str:
    """Devanagari reads as Hindi; anything else falls back to en-US."""
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
    # Speak Hinglish in an INDIAN voice: convert to Devanagari first so the
    # Hindi model pronounces it natively. Without this she reads Hinglish with
    # an English accent, which is what Rohit heard on the first voice note.
    if is_hinglish(clean):
        deva = to_devanagari(clean)
        if deva:
            clean = deva
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


# ── Hearing (ASR): transcribe an inbound voice note ──────────────


def transcribe(audio_url: str, *, language: str | None = None) -> str | None:
    """Inbound voice note → text, so she can actually HEAR Papa.

    Before this she received audio messages with an empty body and answered
    generically ("Achcha, toh ab kya mood hai") to a question she never heard —
    Rohit had asked "तुम मेरा आवाज़ पहचान सकती हो". Uses the multilingual
    parakeet model, which handles Hindi and Hinglish. Returns None on any
    failure; the caller then tells him honestly that she couldn't hear it.
    """
    s = get_settings()
    if not s.voice_hearing_enabled or not audio_url:
        return None
    import subprocess
    import tempfile
    m4a = wav = None
    try:
        import httpx
        raw = httpx.get(audio_url, timeout=30).content
        if not raw:
            return None
        m4a = tempfile.mktemp(suffix=".audio")
        with open(m4a, "wb") as f:
            f.write(raw)
        wav = tempfile.mktemp(suffix=".wav")
        # Riva wants 16k mono PCM; TODY sends m4a/opus from phones.
        proc = subprocess.run(
            ["ffmpeg", "-y", "-i", m4a, "-ar", "16000", "-ac", "1", "-f", "wav", wav],
            capture_output=True, timeout=60)
        if proc.returncode != 0 or not Path(wav).exists():
            return None
        import riva.client
        auth = riva.client.Auth(
            None, True, s.voice_server,
            [["function-id", s.voice_asr_function_id],
             ["authorization", f"Bearer {s.voice_api_key}"]])
        cfg = riva.client.RecognitionConfig(
            language_code=(language or s.voice_asr_language),
            max_alternatives=1, enable_automatic_punctuation=True)
        with open(wav, "rb") as f:
            resp = riva.client.ASRService(auth).offline_recognize(f.read(), cfg)
        text = " ".join(r.alternatives[0].transcript
                        for r in resp.results if r.alternatives).strip()
        if text:
            log_event_safe("voice_transcribed", risk_tier="low",
                           detail=f"chars={len(text)}")
        return text or None
    except Exception as exc:  # noqa: BLE001 — deafness must never break a reply
        log_event_safe("voice_transcribe_failed", risk_tier="low",
                       detail=f"{type(exc).__name__}: {str(exc)[:100]}")
        return None
    finally:
        for p in (m4a, wav):
            try:
                if p:
                    Path(p).unlink(missing_ok=True)
            except Exception:  # noqa: BLE001
                pass


def audio_url_from(row: dict) -> str | None:
    """Pull a playable audio URL out of a TODY message row, if it has one."""
    att = (row or {}).get("attachment") or {}
    mime = str(att.get("mime_type") or "")
    if not att.get("url"):
        return None
    if mime.startswith("audio") or str(row.get("message_type")) == "audio":
        return str(att["url"])
    return None


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
