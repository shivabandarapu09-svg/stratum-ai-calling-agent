import os
import re
import html
import time
import httpx
from fastapi import APIRouter, Request, Response, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, Dict, Any, Tuple
from sqlalchemy.orm import Session
from app.database import get_db
from app.config import settings
from app.models import Call
from app.voice.conversation_engine import VoiceConversationSession
from app.ai.tts_providers import clean_text_for_speech
from app.telephony.twilio_provider import TwilioProvider
from app.telephony.exotel_provider import ExotelProvider

router = APIRouter(prefix="/telephony", tags=["Telephony"])

def _persist_env_vars(updates: dict):
    """Safely updates or appends environment variables to backend/.env and .env files."""
    env_paths = [
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".env")),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".env")),
    ]
    for env_path in env_paths:
        try:
            content = ""
            if os.path.exists(env_path):
                with open(env_path, "r", encoding="utf-8") as f:
                    content = f.read()

            for key, val in updates.items():
                if val is None:
                    continue
                pattern = rf"^{re.escape(key)}=.*$"
                new_line = f"{key}={val}"
                if re.search(pattern, content, flags=re.MULTILINE):
                    content = re.sub(pattern, new_line, content, flags=re.MULTILINE)
                else:
                    if content and not content.endswith("\n"):
                        content += "\n"
                    content += f"{new_line}\n"

            with open(env_path, "w", encoding="utf-8") as f:
                f.write(content)
        except Exception:
            pass

from app.telephony.twilio_security import (
    validate_twilio_signature,
    compute_twilio_signature,
    verify_twilio_webhook_request,
    redact_telephony_payload,
)

class TelephonyConfigRequest(BaseModel):
    provider: str = "web_simulator" # web_simulator, twilio, exotel
    twilio_account_sid: Optional[str] = None
    twilio_auth_token: Optional[str] = None
    twilio_phone_number: Optional[str] = None
    public_webhook_url: Optional[str] = None
    public_base_url: Optional[str] = None
    exotel_api_key: Optional[str] = None
    exotel_api_token: Optional[str] = None
    exotel_subdomain: Optional[str] = None
    exotel_caller_id: Optional[str] = None

class TestConnectionRequest(BaseModel):
    account_sid: Optional[str] = None
    auth_token: Optional[str] = None

@router.get("/status")
def get_telephony_status():
    twilio = TwilioProvider()
    public_base = settings.get_public_base_url()
    return {
        "active_provider": settings.TELEPHONY_PROVIDER,
        "twilio_configured": twilio.is_configured(),
        "twilio_account_sid_masked": f"{settings.TWILIO_ACCOUNT_SID[:6]}...{settings.TWILIO_ACCOUNT_SID[-4:]}" if settings.TWILIO_ACCOUNT_SID else "",
        "twilio_phone_number": settings.TWILIO_PHONE_NUMBER or "",
        "twilio_has_auth_token": bool(settings.TWILIO_AUTH_TOKEN),
        "public_webhook_url": public_base,
        "public_base_url": public_base,
        "public_is_https": settings.is_public_https(),
        "public_ws_url_sample": settings.get_public_ws_url("/ws/voice/{call_id}"),
        "exotel_configured": bool(settings.EXOTEL_API_KEY and settings.EXOTEL_SUBDOMAIN),
        "exotel_subdomain": settings.EXOTEL_SUBDOMAIN or "",
        "exotel_caller_id": settings.EXOTEL_CALLER_ID or "",
    }

@router.post("/config")
def update_telephony_config(req: TelephonyConfigRequest):
    env_updates = {}
    if req.provider:
        settings.TELEPHONY_PROVIDER = req.provider
        env_updates["TELEPHONY_PROVIDER"] = req.provider
    if req.twilio_account_sid is not None and req.twilio_account_sid.strip():
        settings.TWILIO_ACCOUNT_SID = req.twilio_account_sid.strip()
        env_updates["TWILIO_ACCOUNT_SID"] = settings.TWILIO_ACCOUNT_SID
    if req.twilio_auth_token is not None and req.twilio_auth_token.strip():
        settings.TWILIO_AUTH_TOKEN = req.twilio_auth_token.strip()
        env_updates["TWILIO_AUTH_TOKEN"] = settings.TWILIO_AUTH_TOKEN
    if req.twilio_phone_number is not None and req.twilio_phone_number.strip():
        settings.TWILIO_PHONE_NUMBER = req.twilio_phone_number.strip()
        env_updates["TWILIO_PHONE_NUMBER"] = settings.TWILIO_PHONE_NUMBER
    
    # Handle both public_base_url and public_webhook_url (synonymous)
    chosen_url = None
    if req.public_base_url is not None:
        chosen_url = req.public_base_url.strip().rstrip("/")
    elif req.public_webhook_url is not None:
        chosen_url = req.public_webhook_url.strip().rstrip("/")
    
    if chosen_url is not None:
        settings.PUBLIC_BASE_URL = chosen_url
        settings.PUBLIC_WEBHOOK_URL = chosen_url
        env_updates["PUBLIC_BASE_URL"] = chosen_url
        env_updates["PUBLIC_WEBHOOK_URL"] = chosen_url

    if req.exotel_api_key is not None and req.exotel_api_key.strip():
        settings.EXOTEL_API_KEY = req.exotel_api_key.strip()
        env_updates["EXOTEL_API_KEY"] = settings.EXOTEL_API_KEY
    if req.exotel_api_token is not None and req.exotel_api_token.strip():
        settings.EXOTEL_API_TOKEN = req.exotel_api_token.strip()
        env_updates["EXOTEL_API_TOKEN"] = settings.EXOTEL_API_TOKEN
    if req.exotel_subdomain is not None and req.exotel_subdomain.strip():
        settings.EXOTEL_SUBDOMAIN = req.exotel_subdomain.strip()
        env_updates["EXOTEL_SUBDOMAIN"] = settings.EXOTEL_SUBDOMAIN
    if req.exotel_caller_id is not None and req.exotel_caller_id.strip():
        settings.EXOTEL_CALLER_ID = req.exotel_caller_id.strip()
        env_updates["EXOTEL_CALLER_ID"] = settings.EXOTEL_CALLER_ID

    _persist_env_vars(env_updates)

    twilio = TwilioProvider()
    return {
        "status": "success",
        "message": "Telephony configuration updated and saved successfully",
        "active_provider": settings.TELEPHONY_PROVIDER,
        "twilio_configured": twilio.is_configured(),
        "twilio_account_sid_masked": f"{settings.TWILIO_ACCOUNT_SID[:6]}...{settings.TWILIO_ACCOUNT_SID[-4:]}" if settings.TWILIO_ACCOUNT_SID else "",
        "twilio_phone_number": settings.TWILIO_PHONE_NUMBER or "",
        "public_base_url": settings.get_public_base_url(),
        "public_is_https": settings.is_public_https(),
    }

@router.post("/test-connection")
async def test_twilio_connection(req: TestConnectionRequest):
    sid = req.account_sid.strip() if req.account_sid else settings.TWILIO_ACCOUNT_SID
    token = req.auth_token.strip() if req.auth_token else settings.TWILIO_AUTH_TOKEN

    if not sid or not token:
        raise HTTPException(
            status_code=400,
            detail="Twilio Account SID and Auth Token must be provided to test the connection."
        )

    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}.json"
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(url, auth=(sid, token))
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "success": True,
                    "message": f"Successfully authenticated with Twilio! Account: {data.get('friendly_name', sid)}",
                    "account_status": data.get("status"),
                    "account_type": data.get("type"),
                }
            else:
                data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
                err_msg = data.get("message", resp.text)
                return {
                    "success": False,
                    "message": f"Twilio authentication failed ({resp.status_code}): {err_msg}",
                    "code": data.get("code")
                }
    except Exception as e:
        return {
            "success": False,
            "message": f"Could not reach Twilio API: {str(e)}"
        }

import uuid

# In-memory transient audio cache for Twilio <Play> streaming: audio_id -> (bytes, timestamp, content_type)
_TELEPHONY_AUDIO_CACHE: Dict[str, Tuple[bytes, float, str]] = {}

def _cache_telephony_audio(audio_bytes: Optional[bytes], content_type: str = "audio/mpeg") -> Optional[str]:
    """Caches synthesized neural audio and returns a unique audio ID for Twilio <Play>."""
    if not audio_bytes or len(audio_bytes) < 64:
        return None
    now = time.time()
    # Evict expired audio if cache exceeds 100 entries or older than 15 minutes
    if len(_TELEPHONY_AUDIO_CACHE) > 100:
        expired_keys = [k for k, (_, ts, _) in _TELEPHONY_AUDIO_CACHE.items() if now - ts > 900]
        for k in expired_keys:
            _TELEPHONY_AUDIO_CACHE.pop(k, None)
        if len(_TELEPHONY_AUDIO_CACHE) > 100:
            oldest = sorted(_TELEPHONY_AUDIO_CACHE.keys(), key=lambda k: _TELEPHONY_AUDIO_CACHE[k][1])[:30]
            for k in oldest:
                _TELEPHONY_AUDIO_CACHE.pop(k, None)

    audio_id = str(uuid.uuid4()).replace("-", "")[:16]
    _TELEPHONY_AUDIO_CACHE[audio_id] = (audio_bytes, now, content_type)
    return audio_id


@router.get("/audio/{audio_id}.mp3")
@router.get("/audio/{audio_id}")
async def get_telephony_audio(audio_id: str):
    """
    Serves pre-synthesized neural audio bytes (MP3/WAV) to Twilio <Play> requests.
    Supports HTTP Range requests and caching for stutter-free telephony playback.
    """
    clean_id = audio_id.replace(".mp3", "").replace(".wav", "").strip()
    item = _TELEPHONY_AUDIO_CACHE.get(clean_id)
    if not item:
        raise HTTPException(status_code=404, detail="Audio resource expired or not found")
    audio_bytes, _, content_type = item
    return Response(
        content=audio_bytes,
        media_type=content_type,
        headers={
            "Accept-Ranges": "bytes",
            "Cache-Control": "public, max-age=3600",
            "Content-Length": str(len(audio_bytes)),
        }
    )


def _twiml_voice_and_lang(lang_code: str) -> Tuple[str, str]:
    """Map Stratum language codes to Twilio BCP-47 speech recognition and Amazon Polly Neural voices."""
    mapping = {
        "hi": ("Polly.Aditi-Neural", "hi-IN"),
        "en": ("Polly.Kajal-Neural", "en-IN"),
        "te": ("Google.te-IN-Standard-A", "te-IN"),
        "ta": ("Google.ta-IN-Standard-A", "ta-IN"),
        "ml": ("Google.ml-IN-Standard-A", "ml-IN"),
        "kn": ("Google.kn-IN-Standard-A", "kn-IN"),
    }
    return mapping.get((lang_code or "hi").lower()[:2], ("Polly.Kajal-Neural", "en-IN"))


def _xml_escape_speech(text: str) -> str:
    return html.escape(clean_text_for_speech(text or ""), quote=True)


def _build_twiml_turn_response(
    speech_text: str,
    audio_bytes: Optional[bytes],
    gather_url: str,
    reprompt_url: str,
    lang: str,
    request: Request,
    barge_in: bool = True
) -> str:
    """
    Builds a TwiML <Response> that plays studio-quality neural audio via <Play> when available,
    and falls back cleanly to Twilio Polly Neural <Say> if audio synthesis was skipped or timed out.
    """
    twiml_voice, bcp47 = _twiml_voice_and_lang(lang)
    escaped_text = _xml_escape_speech(speech_text)

    public_base = settings.get_public_base_url()
    audio_id = _cache_telephony_audio(audio_bytes) if audio_bytes else None

    if audio_id and public_base:
        audio_url = settings.get_public_http_url(f"/api/telephony/audio/{audio_id}.mp3", request)
        speech_action = f"""<Play>{audio_url}</Play>"""
    else:
        speech_action = f"""<Say voice="{twiml_voice}" language="{bcp47}">{escaped_text}</Say>"""

    barge_attr = ' bargeIn="true"' if barge_in else ""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Gather input="speech" action="{gather_url}" method="POST" language="{bcp47}" speechTimeout="auto"{barge_attr}>
        {speech_action}
    </Gather>
    <Redirect method="POST">{reprompt_url}</Redirect>
</Response>"""


@router.api_route("/twilio/twiml/{call_id}", methods=["GET", "POST"])
async def twilio_twiml_endpoint(
    call_id: str,
    request: Request,
    mode: str = Query(default="gather"),
    db: Session = Depends(get_db),
):
    """
    TwiML webhook called by Twilio when the outbound or inbound call is answered.
    - Default `mode="gather"`: Starts an interactive multi-turn `<Gather input="speech" bargeIn="true">`
      conversation connected to `VoiceConversationSession` and the company's approved RAG knowledge base.
      Streams studio-quality neural audio via `<Play>` with instant fallback to Polly Neural.
    - Optional `mode="stream"`: Plays greeting and opens bidirectional `<Connect><Stream>` WebSocket.
    """
    call = db.query(Call).filter(Call.id == call_id).first()
    if not call:
        fallback_xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<Response><Say voice=\"Polly.Kajal-Neural\" language=\"en-IN\">We could not locate this call session. Goodbye.</Say><Hangup/></Response>"
        )
        return Response(content=fallback_xml, media_type="application/xml")

    if call.status in ("ringing", "queued", "initiated"):
        call.status = "in_progress"
        db.commit()

    session = VoiceConversationSession(call_id=call_id, db=db)
    greeting_text, lang = session.get_greeting()
    twiml_voice, bcp47 = _twiml_voice_and_lang(lang)
    escaped_greeting = _xml_escape_speech(greeting_text)

    if mode == "stream":
        ws_url = settings.get_public_ws_url(f"/ws/voice/{call_id}", request)
        twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="{twiml_voice}" language="{bcp47}">{escaped_greeting}</Say>
    <Connect>
        <Stream url="{ws_url}" />
    </Connect>
</Response>"""
        return Response(content=twiml, media_type="application/xml")

    # Synthesize neural greeting audio for studio-quality human voice
    speed = getattr(session.agent, "speaking_speed", 1.04) or 1.04
    pitch = getattr(session.agent, "voice_pitch", "+0Hz") or "+0Hz"
    greeting_audio = None
    try:
        greeting_audio = await session.tts.synthesize_speech(
            text=greeting_text,
            language=lang,
            voice_id=session.agent.voice_id,
            speaking_speed=speed,
            pitch=pitch
        )
    except Exception as e:
        print(f"[Greeting Audio Synthesis Note]: {e}")

    gather_url = settings.get_public_http_url(f"/api/telephony/twilio/gather/{call_id}", request)
    reprompt_url = settings.get_public_http_url(f"/api/telephony/twilio/reprompt/{call_id}?attempt=1", request)

    twiml = _build_twiml_turn_response(
        speech_text=greeting_text,
        audio_bytes=greeting_audio,
        gather_url=gather_url,
        reprompt_url=reprompt_url,
        lang=lang,
        request=request,
    )
    return Response(content=twiml, media_type="application/xml")


@router.post("/twilio/gather/{call_id}")
async def twilio_gather_turn_endpoint(
    call_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Processes each customer speech turn captured by Twilio `<Gather input="speech">`
    and returns the AI agent's next response inside a new `<Gather>` so the conversation
    continues across unlimited turns until the customer hangs up or requests transfer.
    Streams neural audio via `<Play>` with instant fallback to Polly Neural.
    """
    speech_result = ""
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        body = await request.json()
        speech_result = str(body.get("SpeechResult") or body.get("speech_result") or "").strip()
    else:
        form_data = await request.form()
        speech_result = str(form_data.get("SpeechResult") or "").strip()

    if not speech_result:
        reprompt_url = settings.get_public_http_url(f"/api/telephony/twilio/reprompt/{call_id}?attempt=1", request)
        twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Redirect method="POST">{reprompt_url}</Redirect>
</Response>"""
        return Response(content=twiml, media_type="application/xml")

    try:
        session = VoiceConversationSession(call_id=call_id, db=db)
        result = await session.process_user_utterance(speech_result)
        ai_text = result.get("ai_text") or "Could you please share a bit more detail?"
        lang = result.get("detected_language") or session.current_language
        audio_bytes = result.get("audio_bytes")
        twiml_voice, bcp47 = _twiml_voice_and_lang(lang)
        escaped_reply = _xml_escape_speech(ai_text)

        if result.get("is_transfer"):
            transfer_num = result.get("transfer_number") or session.agent.transfer_number or "+919876543210"
            twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="{twiml_voice}" language="{bcp47}">{escaped_reply}</Say>
    <Dial>{html.escape(transfer_num, quote=True)}</Dial>
</Response>"""
            return Response(content=twiml, media_type="application/xml")

        if result.get("should_end_call"):
            session.complete_call(final_status="completed")
            twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="{twiml_voice}" language="{bcp47}">{escaped_reply}</Say>
    <Hangup/>
</Response>"""
            return Response(content=twiml, media_type="application/xml")

        gather_url = settings.get_public_http_url(f"/api/telephony/twilio/gather/{call_id}", request)
        reprompt_url = settings.get_public_http_url(f"/api/telephony/twilio/reprompt/{call_id}?attempt=1", request)

        twiml = _build_twiml_turn_response(
            speech_text=ai_text,
            audio_bytes=audio_bytes,
            gather_url=gather_url,
            reprompt_url=reprompt_url,
            lang=lang,
            request=request,
        )
        return Response(content=twiml, media_type="application/xml")

    except Exception as exc:
        # Graceful recovery message on AI/runtime error — never leave dead air or drop without notice
        gather_url = settings.get_public_http_url(f"/api/telephony/twilio/gather/{call_id}", request)
        recovery_msg = "I apologize, I experienced a brief audio delay. Could you please repeat your question?"
        twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Gather input="speech" action="{gather_url}" method="POST" language="en-IN" speechTimeout="auto" bargeIn="true">
        <Say voice="Polly.Kajal-Neural" language="en-IN">{recovery_msg}</Say>
    </Gather>
    <Say voice="Polly.Kajal-Neural" language="en-IN">Thank you for your time. We will follow up with you shortly. Goodbye.</Say>
    <Hangup/>
</Response>"""
        return Response(content=twiml, media_type="application/xml")


@router.post("/twilio/reprompt/{call_id}")
async def twilio_reprompt_endpoint(
    call_id: str,
    request: Request = None,
    attempt: int = Query(default=1),
    db: Session = Depends(get_db),
):
    """
    Keeps the call alive if the customer paused after the greeting or previous response,
    prompting up to 2 times before ending cleanly.
    """
    call = db.query(Call).filter(Call.id == call_id).first()
    if not call:
        return Response(
            content='<?xml version="1.0" encoding="UTF-8"?><Response><Hangup/></Response>',
            media_type="application/xml",
        )

    session = VoiceConversationSession(call_id=call_id, db=db)
    lang = session.current_language
    twiml_voice, bcp47 = _twiml_voice_and_lang(lang)
    company_name = (
        session.tenant_profile.company_name
        if session.tenant_profile
        else getattr(session.agent, "company", "our team")
    )

    if attempt <= 2:
        if lang == "hi":
            prompt_text = f"जी, मैं {company_name} से लाइन पर हूँ—बताइए, मैं आपकी किस प्रकार सहायता कर सकता हूँ?"
        elif lang == "te":
            prompt_text = f"నేను {company_name} నుండి లైన్‌లో ఉన్నానండి—మీకు ఏ వివరాలు కావాలో చెప్తారా?"
        else:
            prompt_text = f"I am still here on the line from {company_name}. What questions can I answer for you today?"

        gather_url = settings.get_public_http_url(f"/api/telephony/twilio/gather/{call_id}", request)
        next_reprompt = settings.get_public_http_url(f"/api/telephony/twilio/reprompt/{call_id}?attempt={attempt + 1}", request)
        twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Gather input="speech" action="{gather_url}" method="POST" language="{bcp47}" speechTimeout="auto" bargeIn="true">
        <Say voice="{twiml_voice}" language="{bcp47}">{_xml_escape_speech(prompt_text)}</Say>
    </Gather>
    <Redirect method="POST">{next_reprompt}</Redirect>
</Response>"""
        return Response(content=twiml, media_type="application/xml")

    # After 2 unanswered reprompts, close the call politely and generate summary
    session.complete_call(final_status="completed")
    closing = f"Thank you for connecting with {company_name}. Feel free to reach out anytime. Goodbye!"
    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="{twiml_voice}" language="{bcp47}">{_xml_escape_speech(closing)}</Say>
    <Hangup/>
</Response>"""
    return Response(content=twiml, media_type="application/xml")


@router.post("/twilio/status/{call_id}")
async def twilio_status_callback(
    call_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Receives Twilio CallStatus lifecycle events and accurately updates Call status:
    ringing, answered, in_progress, completed, busy, no-answer, failed.
    """
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        payload = await request.json()
    else:
        form_data = await request.form()
        payload = dict(form_data)

    raw_status = str(payload.get("CallStatus") or payload.get("call_status") or "").lower().strip()
    call_duration = payload.get("CallDuration") or payload.get("duration")

    call = db.query(Call).filter(Call.id == call_id).first()
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")

    status_map = {
        "queued": "ringing",
        "initiated": "ringing",
        "ringing": "ringing",
        "answered": "answered",
        "in-progress": "in_progress",
        "in_progress": "in_progress",
        "completed": "completed",
        "busy": "busy",
        "no-answer": "no-answer",
        "no_answer": "no-answer",
        "failed": "failed",
        "canceled": "failed",
    }
    mapped_status = status_map.get(raw_status, call.status)

    if mapped_status in ("completed", "busy", "no-answer", "failed"):
        try:
            session = VoiceConversationSession(call_id=call_id, db=db)
            session.complete_call(final_status=mapped_status)
        except Exception:
            call.status = mapped_status
            db.commit()
        if call_duration is not None:
            try:
                call.duration_seconds = max(int(call_duration), call.duration_seconds or 0)
                db.commit()
            except Exception:
                pass
    else:
        call.status = mapped_status
        db.commit()

    return {
        "status": "ok",
        "call_id": call_id,
        "twilio_status": raw_status,
        "mapped_status": call.status,
    }


@router.post("/twilio/webhook")
async def twilio_inbound_webhook(request: Request, db: Session = Depends(get_db)):
    form_data = await request.form()
    payload = dict(form_data)
    twilio = TwilioProvider()
    parsed = twilio.parse_webhook(payload)

    ws_url = settings.get_public_ws_url(f"/ws/voice/{parsed.get('provider_call_id')}", request)

    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="Polly.Aditi" language="hi-IN">नमस्ते! स्ट्रैटम एआई वॉइस असिस्टेंट में आपका स्वागत है।</Say>
    <Connect>
        <Stream url="{ws_url}" />
    </Connect>
</Response>"""

    return Response(content=twiml, media_type="application/xml")

@router.post("/exotel/webhook")
async def exotel_inbound_webhook(request: Request, db: Session = Depends(get_db)):
    form_data = await request.form()
    payload = dict(form_data)
    exotel = ExotelProvider()
    parsed = exotel.parse_webhook(payload)
    return {"status": "ok", "call_id": parsed.get("provider_call_id")}


@router.get("/health/ping")
async def telephony_health_ping():
    """Lightweight health ping endpoint for webhook & tunnel reachability probes."""
    return {
        "status": "ok",
        "app": "Stratum AI",
        "service": "Telephony Webhook Gateway",
        "public_base_configured": bool(settings.get_public_base_url()),
    }


@router.get("/health/public")
async def telephony_public_connectivity_health(
    probe: bool = Query(default=False),
):
    """
    Evaluates public HTTPS reachability and WebSocket connectivity readiness for Twilio.
    Returns explicit diagnostics, webhook templates, and reachability probe results.
    """
    twilio = TwilioProvider()
    public_base = settings.get_public_base_url()
    is_https = settings.is_public_https()
    stream_sample = settings.get_public_ws_url("/ws/voice/{call_id}")
    is_wss = stream_sample.lower().startswith("wss://")

    diagnostics = []
    if not public_base:
        diagnostics.append(
            "Missing PUBLIC_BASE_URL: Twilio PSTN requires a publicly accessible HTTPS domain "
            "(e.g., via ngrok, Cloudflare Tunnel, or production domain) to connect answered calls to the AI engine."
        )
    elif not is_https:
        diagnostics.append(
            f"Insecure scheme ({public_base}): Twilio requires HTTPS for production webhooks and WSS for Media Streams."
        )
    else:
        diagnostics.append("Public base URL is configured with HTTPS.")

    if is_wss:
        diagnostics.append("Media stream WebSocket endpoint is configured with secure WSS protocol.")
    else:
        diagnostics.append("Media stream WebSocket endpoint requires WSS for live bidirectional audio streaming.")

    if not twilio.is_configured():
        diagnostics.append("Twilio credentials incomplete: Account SID, Auth Token, or Phone Number is missing.")
    else:
        diagnostics.append("Twilio carrier credentials configured.")

    probe_result = None
    if probe and public_base:
        probe_target = f"{public_base}/api/telephony/health/ping"
        t0 = time.time()
        try:
            async with httpx.AsyncClient(timeout=3.5, verify=False) as client:
                res = await client.get(probe_target)
                latency_ms = round((time.time() - t0) * 1000, 2)
                probe_result = {
                    "probe_target": probe_target,
                    "reachable": res.status_code == 200,
                    "status_code": res.status_code,
                    "latency_ms": latency_ms,
                    "response": res.json() if res.headers.get("content-type", "").startswith("application/json") else res.text[:100],
                }
        except Exception as exc:
            probe_result = {
                "probe_target": probe_target,
                "reachable": False,
                "latency_ms": round((time.time() - t0) * 1000, 2),
                "error": str(exc),
            }

    overall_status = "healthy" if (public_base and is_https and twilio.is_configured()) else (
        "warning" if public_base else "missing_public_url"
    )

    return {
        "status": overall_status,
        "configured": bool(public_base),
        "public_base_url": public_base,
        "is_https": is_https,
        "media_stream_is_wss": is_wss,
        "endpoints": {
            "twiml_url_template": settings.get_public_http_url("/api/telephony/twilio/twiml/{call_id}"),
            "gather_url_template": settings.get_public_http_url("/api/telephony/twilio/gather/{call_id}"),
            "reprompt_url_template": settings.get_public_http_url("/api/telephony/twilio/reprompt/{call_id}"),
            "status_callback_template": settings.get_public_http_url("/api/telephony/twilio/status/{call_id}"),
            "media_stream_ws_template": stream_sample,
            "inbound_webhook_url": settings.get_public_http_url("/api/telephony/twilio/webhook"),
        },
        "twilio_provider": {
            "configured": twilio.is_configured(),
            "account_sid_masked": f"{settings.TWILIO_ACCOUNT_SID[:6]}...{settings.TWILIO_ACCOUNT_SID[-4:]}" if settings.TWILIO_ACCOUNT_SID else "",
            "phone_number": settings.TWILIO_PHONE_NUMBER or "",
            "has_auth_token": bool(settings.TWILIO_AUTH_TOKEN),
        },
        "reachability_probe": probe_result,
        "diagnostics": diagnostics,
    }
