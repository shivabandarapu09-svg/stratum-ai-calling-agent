import os
import httpx
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from app.config import settings

class BaseSTTProvider(ABC):
    @abstractmethod
    async def transcribe_audio(self, audio_bytes: bytes, language_hint: Optional[str] = None) -> Dict[str, Any]:
        """Transcribe audio bytes to text and detected language."""
        pass

class SarvamSTTProvider(BaseSTTProvider):
    """Sarvam AI Saarika v2 - Indian language specialist STT with code-switching."""
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.SARVAM_API_KEY
        self.endpoint = "https://api.sarvam.ai/speech-to-text"

    async def transcribe_audio(self, audio_bytes: bytes, language_hint: Optional[str] = "te-IN") -> Dict[str, Any]:
        if not self.api_key:
            raise ValueError("SARVAM_API_KEY is not configured")

        files = {"file": ("audio.wav", audio_bytes, "audio/wav")}
        data = {"model": "saarika:v2", "language_code": language_hint or "unknown"}

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                self.endpoint,
                headers={"api-subscription-key": self.api_key},
                files=files,
                data=data
            )
            resp.raise_for_status()
            res = resp.json()
            return {
                "transcript": res.get("transcript", "").strip(),
                "language": res.get("language_code", language_hint)
            }

class DeepgramSTTProvider(BaseSTTProvider):
    """Deepgram Nova-2 Multilingual streaming STT."""
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.DEEPGRAM_API_KEY
        self.endpoint = "https://api.deepgram.com/v1/listen?model=nova-2&detect_language=true"

    async def transcribe_audio(self, audio_bytes: bytes, language_hint: Optional[str] = None) -> Dict[str, Any]:
        if not self.api_key:
            raise ValueError("DEEPGRAM_API_KEY is not configured")

        headers = {
            "Authorization": f"Token {self.api_key}",
            "Content-Type": "audio/wav"
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(self.endpoint, headers=headers, content=audio_bytes)
            resp.raise_for_status()
            data = resp.json()
            channel = data["results"]["channels"][0]["alternatives"][0]
            return {
                "transcript": channel.get("transcript", "").strip(),
                "language": channel.get("languages", ["en"])[0]
            }

class MockSTTProvider(BaseSTTProvider):
    """Simulated STT for local testing and web speech fallback."""
    async def transcribe_audio(self, audio_bytes: bytes, language_hint: Optional[str] = None) -> Dict[str, Any]:
        return {
            "transcript": "నాకు వరి పంట fertilizer price వివరాలు కావాలి.",
            "language": language_hint or "te"
        }

def get_stt_provider() -> BaseSTTProvider:
    if settings.SARVAM_API_KEY:
        return SarvamSTTProvider()
    if settings.DEEPGRAM_API_KEY:
        return DeepgramSTTProvider()
    return MockSTTProvider()
