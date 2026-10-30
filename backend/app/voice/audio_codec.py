"""
Audio Codec & Media-Stream Boundary Verification + Call-Session Tracer
======================================================================
Provides pure-Python G.711 mu-law (8000 Hz mono) <-> 16-bit Linear PCM conversion
compatible with Python 3.13/3.14+ (where stdlib `audioop` was removed), WAV framing
for STT providers, Twilio Media Stream format verification, and PII/secret-redacted
call-session trace logging.
"""

import io
import re
import struct
import wave
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


# Precomputed G.711 mu-law -> 16-bit signed linear PCM lookup table (256 entries)
_MULAW_DECODE_TABLE: List[int] = []
for _b in range(256):
    _u = ~_b & 0xFF
    _sign = _u & 0x80
    _exponent = (_u >> 4) & 0x07
    _mantissa = _u & 0x0F
    _sample = (((_mantissa << 3) + 0x84) << _exponent) - 0x84
    _MULAW_DECODE_TABLE.append(-_sample if _sign else _sample)


def _linear16_sample_to_mulaw(sample: int) -> int:
    """Encode a single 16-bit signed PCM sample (-32768..32767) into 8-bit G.711 mu-law."""
    BIAS = 0x84
    CLIP = 32635
    sign = 0x80 if sample < 0 else 0x00
    if sample < 0:
        sample = -sample
    if sample > CLIP:
        sample = CLIP
    sample += BIAS

    exponent = 7
    exp_mask = 0x4000
    while exponent > 0 and (sample & exp_mask) == 0:
        exponent -= 1
        exp_mask >>= 1

    mantissa = (sample >> (exponent + 3)) & 0x0F
    mulaw_byte = ~(sign | (exponent << 4) | mantissa) & 0xFF
    return mulaw_byte


def mulaw_to_pcm16(mulaw_bytes: bytes) -> bytes:
    """Convert 8-bit G.711 mu-law bytes (8000 Hz) to 16-bit signed little-endian PCM bytes."""
    if not mulaw_bytes:
        return b""
    samples = [_MULAW_DECODE_TABLE[b] for b in mulaw_bytes]
    return struct.pack(f"<{len(samples)}h", *samples)


def pcm16_to_mulaw(pcm16_bytes: bytes) -> bytes:
    """Convert 16-bit signed little-endian PCM bytes to 8-bit G.711 mu-law bytes."""
    if not pcm16_bytes:
        return b""
    usable_len = len(pcm16_bytes) - (len(pcm16_bytes) % 2)
    if usable_len <= 0:
        return b""
    samples = struct.unpack(f"<{usable_len // 2}h", pcm16_bytes[:usable_len])
    return bytes(_linear16_sample_to_mulaw(s) for s in samples)


def pcm16_to_wav(pcm16_bytes: bytes, sample_rate: int = 8000, channels: int = 1) -> bytes:
    """Wrap raw 16-bit signed little-endian PCM bytes in a RIFF WAV container for STT APIs."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm16_bytes)
    return buf.getvalue()


def validate_twilio_media_format(media_format: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Verify Twilio Media Stream format metadata at the WebSocket boundary.
    Twilio streams default to encoding='audio/x-mulaw', sampleRate=8000, channels=1.
    """
    fmt = media_format or {}
    encoding = str(fmt.get("encoding", "audio/x-mulaw")).lower()
    sample_rate = int(fmt.get("sampleRate", 8000) or 8000)
    channels = int(fmt.get("channels", 1) or 1)
    is_compatible = encoding in ("audio/x-mulaw", "audio/pcmu", "mulaw") and sample_rate in (8000, 16000) and channels == 1
    return {
        "encoding": encoding,
        "sample_rate": sample_rate,
        "channels": channels,
        "is_compatible": is_compatible,
    }


def redact_sensitive_text(value: str) -> str:
    """Redact API keys, tokens, Account SIDs, and mask phone numbers in trace logs."""
    if not value:
        return ""
    redacted = re.sub(r"\bAC[a-fA-F0-9]{32}\b", "AC***REDACTED***", value)
    redacted = re.sub(r"\b(?:gsk_|sk-)[a-zA-Z0-9_\-]{12,}\b", "***REDACTED_KEY***", redacted)
    redacted = re.sub(r"(\+\d{2,3})\d{6}(\d{2,4})", r"\1******\2", redacted)
    return redacted


class CallSessionTracer:
    """
    Structured per-call trace recorder with ISO-8601 UTC timestamps and secret/PII redaction.
    Tracks:
    - session_initialized
    - greeting_delivered
    - speech_received
    - transcription_completed
    - rag_retrieval_completed
    - llm_response_generated
    - audio_playback_started
    - barge_in_interrupted
    - error_recovered
    - call_terminated
    """

    def __init__(self, call_id: str, organization_id: str):
        self.call_id = call_id
        self.organization_id = organization_id
        self.events: List[Dict[str, Any]] = []

    def record(
        self,
        event_type: str,
        detail: str = "",
        latency_ms: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        safe_meta: Dict[str, Any] = {}
        for k, v in (metadata or {}).items():
            if any(sec in k.lower() for sec in ("token", "secret", "password", "authorization", "api_key")):
                safe_meta[k] = "***REDACTED***"
            elif isinstance(v, str):
                safe_meta[k] = redact_sensitive_text(v)
            else:
                safe_meta[k] = v

        entry: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event_type,
            "detail": redact_sensitive_text(detail),
        }
        if latency_ms is not None:
            entry["latency_ms"] = latency_ms
        if safe_meta:
            entry["metadata"] = safe_meta

        self.events.append(entry)
        return entry

    def to_list(self) -> List[Dict[str, Any]]:
        return list(self.events)
