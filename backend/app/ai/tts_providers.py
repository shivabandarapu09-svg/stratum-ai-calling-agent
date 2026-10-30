import os
import io
import re
import time
import asyncio
import httpx
from abc import ABC, abstractmethod
from typing import Optional, Tuple
from app.config import settings

def normalize_indian_phonetics(text: str) -> str:
    """
    Normalizes numbers, Indian currencies, property units, dates, and technical abbreviations
    into natural spoken phonetics so TTS neural engines pronounce them fluently.
    """
    if not text:
        return ""
    t = text
    # 1. Indian Currencies: ₹5.5 Cr -> 5.5 crore rupees
    t = re.sub(r"₹\s*(\d+(?:\.\d+)?)\s*(?:Cr|Crore|crores?)\b", r"\1 crore rupees", t, flags=re.IGNORECASE)
    t = re.sub(r"₹\s*(\d+(?:\.\d+)?)\s*(?:L|Lakh|lakhs?|lac|lacs?)\b", r"\1 lakh rupees", t, flags=re.IGNORECASE)
    t = re.sub(r"₹\s*(\d+(?:,\d+)*(?:\.\d+)?)", r"\1 rupees", t)
    t = re.sub(r"\bRs\.?\s*(\d+(?:\.\d+)?)\s*(?:Cr|Crore|crores?)\b", r"\1 crore rupees", t, flags=re.IGNORECASE)
    t = re.sub(r"\bRs\.?\s*(\d+(?:\.\d+)?)\s*(?:L|Lakh|lakhs?|lac|lacs?)\b", r"\1 lakh rupees", t, flags=re.IGNORECASE)
    t = re.sub(r"\bRs\.?\s*(\d+(?:,\d+)*(?:\.\d+)?)", r"\1 rupees", t, flags=re.IGNORECASE)

    # 2. Real estate & engineering units
    t = re.sub(r"\b(\d+)\s*BHK\b", r"\1 B H K", t, flags=re.IGNORECASE)
    t = re.sub(r"\bsq\.?\s*ft\.?\b|\bsqft\b", "square feet", t, flags=re.IGNORECASE)
    t = re.sub(r"\bsq\.?\s*yds?\.?\b|\bsqyd\b", "square yards", t, flags=re.IGNORECASE)
    t = re.sub(r"\bsq\.?\s*m(?:tr)?s?\.?\b|\bsqm\b", "square meters", t, flags=re.IGNORECASE)
    t = re.sub(r"\bkW\b|\bkw\b", "kilowatt", t)
    t = re.sub(r"\bkVA\b|\bkva\b", "k V A", t)

    # 3. Conversational acronyms
    t = re.sub(r"\bROI\b", "R O I", t)
    t = re.sub(r"\bEMI\b", "E M I", t)
    t = re.sub(r"\bSDR\b", "S D R", t)
    t = re.sub(r"\bCRM\b", "C R M", t)
    t = re.sub(r"\bAI\b", "A I", t)
    t = re.sub(r"\bAM\b", "A M", t)
    t = re.sub(r"\bPM\b", "P M", t)
    t = re.sub(r"\bvs\.?\b", "versus", t, flags=re.IGNORECASE)
    t = re.sub(r"\betc\.?\b", "etcetera", t, flags=re.IGNORECASE)

    return t

def clean_text_for_speech(text: str) -> str:
    """
    Sanitize text before TTS synthesis so neural voices sound completely natural:
    - Strip markdown asterisks, hashes, brackets, bullets
    - Phonetically normalize currencies, units, and acronyms
    - Clean whitespace for smooth acoustic transitions
    """
    if not text:
        return ""
    cleaned = re.sub(r"[\*\#\_\`\~]", "", text)
    cleaned = re.sub(r"\[.*?\]", "", cleaned)
    cleaned = re.sub(r"^\s*[\-\•\*\>]\s*", "", cleaned, flags=re.MULTILINE)
    cleaned = normalize_indian_phonetics(cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned

class BaseTTSProvider(ABC):
    @abstractmethod
    async def synthesize_speech(
        self,
        text: str,
        language: str = "hi",
        voice_id: Optional[str] = None,
        speaking_speed: float = 1.04,
        pitch: str = "+0Hz"
    ) -> bytes:
        """Synthesize text into audio bytes (MP3/WAV)."""
        pass

    async def synthesize(
        self,
        text: str,
        language: str = "hi",
        voice_id: Optional[str] = None,
        speaking_speed: float = 1.04,
        pitch: str = "+0Hz"
    ) -> Tuple[bytes, int]:
        t0 = time.time()
        audio = await self.synthesize_speech(
            text=text,
            language=language,
            voice_id=voice_id,
            speaking_speed=speaking_speed,
            pitch=pitch
        )
        dur_ms = int((time.time() - t0) * 1000)
        return audio, max(dur_ms, 15)


class EdgeTTSProvider(BaseTTSProvider):
    """
    Microsoft Azure Neural Indian Voices via edge-tts.
    Zero-cost, ultra-high quality, native pronunciation of Indian languages,
    conversational prosody control (rate & pitch), and code-mixed Hinglish/Tenglish fluency.
    """
    def __init__(self):
        try:
            import edge_tts
            self.edge_tts = edge_tts
        except ImportError:
            self.edge_tts = None

    def get_voice_for_language(self, language: str, preferred_voice: Optional[str] = None) -> str:
        # Map custom persona aliases to valid neural voices
        alias_map = {
            "sarvam-bulbul-meera": "hi-IN-SwaraNeural",
            "sarvam-bulbul-amol": "hi-IN-MadhurNeural",
            "elevenlabs-rachel-in": "en-IN-NeerjaNeural",
        }
        if preferred_voice in alias_map:
            preferred_voice = alias_map[preferred_voice]

        # If caller switched language mid-call, pick matching gender voice in the target language
        lang_conf = settings.DEFAULT_VOICES.get(language, settings.DEFAULT_VOICES.get("hi", {}))
        if preferred_voice and preferred_voice.startswith(f"{language}-"):
            return preferred_voice

        if preferred_voice and any(m in preferred_voice.lower() for m in ["madhur", "prabhat", "mohan", "valluvar", "gagan", "midhun", "manohar", "bashkar", "niranjan", "ojas"]):
            return lang_conf.get("male", "hi-IN-MadhurNeural")

        if preferred_voice and "Neural" in preferred_voice and language == "hi" and preferred_voice.startswith("hi-"):
            return preferred_voice

        return lang_conf.get("default", "hi-IN-SwaraNeural")

    async def synthesize_speech(
        self,
        text: str,
        language: str = "hi",
        voice_id: Optional[str] = None,
        speaking_speed: float = 1.04,
        pitch: str = "+0Hz"
    ) -> bytes:
        if not self.edge_tts:
            return b""

        spoken_text = clean_text_for_speech(text)
        if not spoken_text:
            return b""

        voice = self.get_voice_for_language(language, voice_id)

        # Calculate rate string e.g. "+4%" or "-5%"
        pct = int(round((speaking_speed - 1.0) * 100))
        pct = max(-25, min(35, pct))
        rate_str = f"+{pct}%" if pct >= 0 else f"{pct}%"
        pitch_str = pitch if pitch and ("Hz" in pitch) else "+0Hz"

        try:
            loop = asyncio.get_running_loop()
            await asyncio.wait_for(
                loop.getaddrinfo("speech.platform.bing.com", 443),
                timeout=1.0
            )
            communicate = self.edge_tts.Communicate(
                text=spoken_text,
                voice=voice,
                rate=rate_str,
                pitch=pitch_str
            )
            audio_stream = bytearray()

            async def _collect():
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        audio_stream.extend(chunk["data"])

            await asyncio.wait_for(_collect(), timeout=3.5)
            return bytes(audio_stream)
        except Exception as e:
            print(f"[Stratum EdgeTTS Info] Neural stream fallback ({e})")
            return b""


class SarvamTTSProvider(BaseTTSProvider):
    """Sarvam AI Bulbul v2 Indian Neural TTS with native Hinglish & Regional prosody."""
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.SARVAM_API_KEY
        self.endpoint = "https://api.sarvam.ai/text-to-speech"

    async def synthesize_speech(
        self,
        text: str,
        language: str = "hi",
        voice_id: Optional[str] = "meera",
        speaking_speed: float = 1.04,
        pitch: str = "+0Hz"
    ) -> bytes:
        if not self.api_key:
            return await EdgeTTSProvider().synthesize_speech(text, language, voice_id, speaking_speed, pitch)

        lang_map = {
            "hi": "hi-IN",
            "en": "en-IN",
            "te": "te-IN",
            "ta": "ta-IN",
            "kn": "kn-IN",
            "ml": "ml-IN",
            "mr": "mr-IN",
            "bn": "bn-IN",
            "gu": "gu-IN",
            "pa": "pa-IN"
        }
        lang_code = lang_map.get(language, "hi-IN")
        speaker = "amol" if voice_id and "madhur" in voice_id.lower() else "meera"

        payload = {
            "inputs": [clean_text_for_speech(text)],
            "target_language_code": lang_code,
            "speaker": speaker,
            "pitch": 0,
            "pace": round(speaking_speed, 2),
            "loudness": 1.2,
            "speech_sample_rate": 16000,
            "enable_preprocessing": True,
            "model": "bulbul:v1"
        }

        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.post(
                    self.endpoint,
                    headers={"api-subscription-key": self.api_key, "Content-Type": "application/json"},
                    json=payload
                )
                resp.raise_for_status()
                data = resp.json()
                import base64
                aud_b64 = data["audios"][0]
                return base64.b64decode(aud_b64)
        except Exception as e:
            print(f"[Sarvam TTS Fallback to EdgeTTS]: {e}")
            return await EdgeTTSProvider().synthesize_speech(text, language, voice_id, speaking_speed, pitch)


class ElevenLabsTTSProvider(BaseTTSProvider):
    """ElevenLabs Multilingual v2 TTS provider adapter (optional third-party integration)."""
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.ELEVENLABS_API_KEY

    async def synthesize_speech(
        self,
        text: str,
        language: str = "hi",
        voice_id: Optional[str] = None,
        speaking_speed: float = 1.04,
        pitch: str = "+0Hz"
    ) -> bytes:
        if not self.api_key:
            return await EdgeTTSProvider().synthesize_speech(text, language, voice_id, speaking_speed, pitch)

        eleven_voice = "21m00Tcm4TlvDq8ikWAM"
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{eleven_voice}"
        payload = {
            "text": clean_text_for_speech(text),
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {
                "stability": 0.45,
                "similarity_boost": 0.82,
                "style": 0.35,
                "use_speaker_boost": True
            }
        }
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.post(
                    url,
                    headers={"xi-api-key": self.api_key, "Content-Type": "application/json"},
                    json=payload
                )
                resp.raise_for_status()
                return resp.content
        except Exception:
            return await EdgeTTSProvider().synthesize_speech(text, language, voice_id, speaking_speed, pitch)


class MockTTSProvider(BaseTTSProvider):
    """Fallback mock audio synthesizer for deterministic unit testing."""
    async def synthesize_speech(
        self,
        text: str,
        language: str = "hi",
        voice_id: Optional[str] = None,
        speaking_speed: float = 1.04,
        pitch: str = "+0Hz"
    ) -> bytes:
        header = b'RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x80>\x00\x00\x00}\x00\x00\x02\x00\x10\x00data\x00\x00\x00\x00'
        return header


def get_tts_provider() -> BaseTTSProvider:
    if settings.DEFAULT_TTS_PROVIDER == "sarvam" and settings.SARVAM_API_KEY:
        return SarvamTTSProvider()
    if settings.DEFAULT_TTS_PROVIDER == "elevenlabs" and settings.ELEVENLABS_API_KEY:
        return ElevenLabsTTSProvider()
    if settings.DEFAULT_TTS_PROVIDER == "mock":
        return MockTTSProvider()
    return EdgeTTSProvider()
