import os
from typing import List, Dict, Any
from pydantic import ConfigDict
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    model_config = ConfigDict(env_file=".env", extra="ignore")

    # App Information
    APP_NAME: str = "Stratum AI - Hyper-Realistic Multilingual AI Calling Platform"
    PLATFORM_NAME: str = "Stratum Enterprise AI"
    APP_ENV: str = "development"
    DEBUG: bool = True
    PORT: int = 8000
    HOST: str = "0.0.0.0"
    API_PREFIX: str = "/api"

    # Database & Storage
    DATABASE_URL: str = "sqlite:///./stratum.db"
    SECRET_KEY: str = "super-secret-jwt-key-stratum-ai-calling-2026"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days
    ALLOWED_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ]

    # AI Providers Configuration
    DEFAULT_LLM_PROVIDER: str = "mock"      # Options: groq, openai, mock
    DEFAULT_STT_PROVIDER: str = "mock"      # Options: sarvam, deepgram, whisper, mock
    DEFAULT_TTS_PROVIDER: str = "edge_tts"  # Options: edge_tts, sarvam, elevenlabs, mock

    # API Keys (Optional, fallback to Stratum Neural Engine + Edge-TTS if not provided)
    GROQ_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    DEEPGRAM_API_KEY: str = ""
    SARVAM_API_KEY: str = ""
    ELEVENLABS_API_KEY: str = ""

    # Telephony Configuration
    TELEPHONY_PROVIDER: str = "web_simulator"  # Options: web_simulator, twilio, exotel, plivo
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_PHONE_NUMBER: str = ""
    PUBLIC_WEBHOOK_URL: str = ""
    PUBLIC_BASE_URL: str = ""
    EXOTEL_API_KEY: str = ""
    EXOTEL_API_TOKEN: str = ""
    EXOTEL_SUBDOMAIN: str = ""
    EXOTEL_CALLER_ID: str = ""

    # Speed-to-Lead & Webhook Automation
    SPEED_TO_LEAD_AUTO_DIAL: bool = True
    WEBHOOK_SECRET: str = "stratum-speed-lead-secret-key"
    WHATSAPP_API_TOKEN: str = ""
    WHATSAPP_PHONE_NUMBER_ID: str = ""
    WHATSAPP_MOCK_ENABLED: bool = True

    # Stratum Acoustic Realism Engine Defaults
    AMBIENT_SOUND_DEFAULT: str = "office_call_center"  # office_call_center, executive_room, warm_cafe, none
    BACKCHANNEL_ENABLED: bool = True
    FILLER_INJECTION_ENABLED: bool = True
    ENDPOINTING_SILENCE_MS: int = 350

    # Indian Regional & Global Languages Supported
    SUPPORTED_LANGUAGES: List[str] = [
        "hi",  # Hindi / Hinglish
        "en",  # English (Indian Conversational)
        "te",  # Telugu / Tenglish
        "ta",  # Tamil / Tanglish
        "kn",  # Kannada
        "ml",  # Malayalam
        "mr",  # Marathi
        "bn",  # Bengali
        "gu",  # Gujarati
        "pa"   # Punjabi
    ]

    # High-Definition Neural Voice Personas for Indian Languages
    DEFAULT_VOICES: Dict[str, Dict[str, Any]] = {
        "hi": {
            "name": "Hindi / Hinglish (हिंदी)",
            "female": "hi-IN-SwaraNeural",
            "male": "hi-IN-MadhurNeural",
            "default": "hi-IN-SwaraNeural",
            "personas": [
                {
                    "id": "hi-IN-SwaraNeural",
                    "name": "Swara (Warm & Conversational Hinglish)",
                    "gender": "Female",
                    "provider": "Azure Neural / Stratum HD",
                    "style": "Empathetic, Lively, Customer-First",
                    "sample": "नमस्ते जी! मैं स्ट्रैटम एआई से बात कर रही हूँ। बताइए, आज मैं आपकी कैसे मदद कर सकती हूँ?"
                },
                {
                    "id": "hi-IN-MadhurNeural",
                    "name": "Madhur (Consultative & Executive SDR)",
                    "gender": "Male",
                    "provider": "Azure Neural / Stratum HD",
                    "style": "Confident, Persuasive, Senior Advisor",
                    "sample": "नमस्ते! मैं आरव बोल रहा हूँ। आपने हमारी लक्ज़री प्रॉपर्टी के बारे में पूछा था—क्या अभी बात करने का सही समय है?"
                },
                {
                    "id": "sarvam-bulbul-meera",
                    "name": "Meera (Sarvam Bulbul v2 Indic)",
                    "gender": "Female",
                    "provider": "Sarvam AI Bulbul",
                    "style": "Colloquial Indian Pitch & Pacing",
                    "sample": "हाँ जी बिल्कुल, मैंने आपके व्हाट्सएप नंबर पर सारी डिटेल्स भेज दी हैं!"
                }
            ]
        },
        "en": {
            "name": "English (Indian Accent)",
            "female": "en-IN-NeerjaNeural",
            "male": "en-IN-PrabhatNeural",
            "default": "en-IN-NeerjaNeural",
            "personas": [
                {
                    "id": "en-IN-NeerjaNeural",
                    "name": "Neerja (Expressive Indian English)",
                    "gender": "Female",
                    "provider": "Azure Neural / Stratum HD",
                    "style": "Polished, Warm, B2B & Healthcare",
                    "sample": "Hi there! This is Kavya calling from Stratum AI. Do you have a quick minute to chat?"
                },
                {
                    "id": "en-IN-PrabhatNeural",
                    "name": "Prabhat (Executive Enterprise Advisor)",
                    "gender": "Male",
                    "provider": "Azure Neural / Stratum HD",
                    "style": "Calm, Articulate, FinTech & SaaS",
                    "sample": "Hello! I completely understand your point—let me quickly check the best slot for your team this week."
                }
            ]
        },
        "te": {
            "name": "Telugu / Tenglish (తెలుగు)",
            "female": "te-IN-ShrutiNeural",
            "male": "te-IN-MohanNeural",
            "default": "te-IN-ShrutiNeural",
            "personas": [
                {
                    "id": "te-IN-ShrutiNeural",
                    "name": "Shruti (Natural Conversational Telugu)",
                    "gender": "Female",
                    "provider": "Azure Neural / Stratum HD",
                    "style": "Polite, Clear, Regional Native",
                    "sample": "నమస్కారం అండి! నేను స్ట్రాటమ్ ఏఐ నుండి మాట్లాడుతున్నాను. మీకు ఏ విధంగా సహాయం చేయగలను?"
                },
                {
                    "id": "te-IN-MohanNeural",
                    "name": "Mohan (Consultative Telugu SDR)",
                    "gender": "Male",
                    "provider": "Azure Neural / Stratum HD",
                    "style": "Warm, Trustworthy, Advisory",
                    "sample": "తప్పకుండా అండి, పూర్తి వివరాలు మీ వాట్సాప్ నంబర్‌కు ఇప్పుడే పంపిస్తున్నాను."
                }
            ]
        },
        "ta": {
            "name": "Tamil / Tanglish (தமிழ்)",
            "female": "ta-IN-PallaviNeural",
            "male": "ta-IN-ValluvarNeural",
            "default": "ta-IN-PallaviNeural"
        },
        "kn": {
            "name": "Kannada (ಕನ್ನಡ)",
            "female": "kn-IN-SapnaNeural",
            "male": "kn-IN-GaganNeural",
            "default": "kn-IN-SapnaNeural"
        },
        "ml": {
            "name": "Malayalam (മലയാളം)",
            "female": "ml-IN-SobhanaNeural",
            "male": "ml-IN-MidhunNeural",
            "default": "ml-IN-SobhanaNeural"
        },
        "mr": {
            "name": "Marathi (मराठी)",
            "female": "mr-IN-AarohiNeural",
            "male": "mr-IN-ManoharNeural",
            "default": "mr-IN-AarohiNeural"
        },
        "bn": {
            "name": "Bengali (বাংলা)",
            "female": "bn-IN-TanishaaNeural",
            "male": "bn-IN-BashkarNeural",
            "default": "bn-IN-TanishaaNeural"
        },
        "gu": {
            "name": "Gujarati (ગુજરાતી)",
            "female": "gu-IN-DhwaniNeural",
            "male": "gu-IN-NiranjanNeural",
            "default": "gu-IN-DhwaniNeural"
        },
        "pa": {
            "name": "Punjabi (ਪੰਜਾਬੀ)",
            "female": "pa-IN-RaaviNeural",
            "male": "pa-IN-OjasNeural",
            "default": "pa-IN-RaaviNeural"
        }
    }

    # Audio & Streaming Specs
    AUDIO_SAMPLE_RATE: int = 16000
    AUDIO_CHANNELS: int = 1
    VAD_ENERGY_THRESHOLD: float = 0.015
    INTERRUPTION_DEBOUNCE_MS: int = 120

    # Compliance & Business Rules (TRAI 9AM - 8PM Guidelines)
    CALLING_HOURS_START: int = 9   # 9:00 AM IST
    CALLING_HOURS_END: int = 20    # 8:00 PM IST
    MAX_CALL_RETRIES: int = 3
    CONSENT_DISCLOSURE_ENABLED: bool = True

    def get_public_base_url(self) -> str:
        """
        Returns the configured public base URL, prioritizing PUBLIC_BASE_URL
        and falling back to PUBLIC_WEBHOOK_URL. Strips trailing slashes.
        """
        val = (self.PUBLIC_BASE_URL or self.PUBLIC_WEBHOOK_URL or "").strip().rstrip("/")
        return val

    def is_public_https(self) -> bool:
        """Checks if the configured public base URL uses secure HTTPS."""
        base = self.get_public_base_url()
        return base.lower().startswith("https://")

    def get_public_http_url(self, path: str, request: Any = None) -> str:
        """
        Resolves an HTTP(S) URL for webhooks and TwiML actions.
        Guarantees public HTTPS domain when PUBLIC_BASE_URL/PUBLIC_WEBHOOK_URL is configured.
        Falls back to request headers (x-forwarded-proto / x-forwarded-host) when available.
        """
        base = self.get_public_base_url()
        cleaned_path = "/" + path.lstrip("/")
        if base:
            return f"{base}{cleaned_path}"
        if request is not None:
            forwarded_proto = request.headers.get("x-forwarded-proto", "")
            scheme = "https" if forwarded_proto == "https" or "https" in str(request.url) else "http"
            host = request.headers.get("x-forwarded-host") or request.headers.get("host", "localhost:8000")
            return f"{scheme}://{host}{cleaned_path}"
        return cleaned_path

    def get_public_ws_url(self, path: str, request: Any = None) -> str:
        """
        Resolves a WebSocket URL for Twilio Media Streams or client streaming.
        Guarantees 'wss://' whenever public base URL uses HTTPS or proxy is HTTPS.
        """
        base = self.get_public_base_url()
        cleaned_path = "/" + path.lstrip("/")
        if base:
            if base.lower().startswith("https://"):
                ws_base = "wss://" + base[8:]
            elif base.lower().startswith("http://"):
                ws_base = "ws://" + base[7:]
            else:
                ws_base = "wss://" + base.lstrip("/")
            return f"{ws_base}{cleaned_path}"
        if request is not None:
            forwarded_proto = request.headers.get("x-forwarded-proto", "")
            is_ssl = forwarded_proto == "https" or "https" in str(request.url)
            proto = "wss" if is_ssl else "ws"
            host = request.headers.get("x-forwarded-host") or request.headers.get("host", "localhost:8000")
            return f"{proto}://{host}{cleaned_path}"
        return f"wss://localhost:8000{cleaned_path}"

settings = Settings()
