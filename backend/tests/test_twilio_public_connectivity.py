"""
Stratum AI – Twilio Public Connectivity, Webhook URLs, and 8 kHz μ-law Media Stream Tests
========================================================================================
Verifies:
1. PUBLIC_BASE_URL and PUBLIC_WEBHOOK_URL configuration resolution.
2. Webhook URLs use public HTTPS domain (twiml, gather, reprompt, status callback).
3. Media-stream URLs use wss:// (not ws://) under HTTPS / reverse-proxy SSL.
4. TwiML Speech Gather Loop endpoint accepts requests and returns valid TwiML XML.
5. Multi-turn Gather endpoint accepts Twilio speech turns and continues conversation.
6. Twilio Media Stream format & 8 kHz μ-law audio conversion.
7. Public health diagnostic endpoints (/api/telephony/health/ping, /api/telephony/health/public).
8. Twilio HMAC-SHA1 signature verification logic.
"""

import json
import asyncio
import pytest
from starlette.requests import Request
from app.config import settings
from app.database import init_db, SessionLocal
from app.models import Agent, Call
from app.schemas import CallInitiateRequest
from app.api.calls import initiate_call
from app.api.telephony import (
    twilio_twiml_endpoint,
    twilio_gather_turn_endpoint,
    twilio_reprompt_endpoint,
    telephony_health_ping,
    telephony_public_connectivity_health,
)
from app.telephony.twilio_security import (
    compute_twilio_signature,
    validate_twilio_signature,
    redact_telephony_payload,
)
from app.voice.audio_codec import (
    pcm16_to_mulaw,
    mulaw_to_pcm16,
    validate_twilio_media_format,
)


def _run_coro(coro):
    try:
        while True:
            coro.send(None)
    except StopIteration as e:
        return e.value


def _make_request(
    path: str,
    method: str = "GET",
    headers: list = None,
    body: dict = None,
    form_data: dict = None,
    query_string: bytes = b"",
) -> Request:
    if body is not None:
        body_bytes = json.dumps(body).encode("utf-8")
        default_ct = (b"content-type", b"application/json")
    elif form_data is not None:
        import urllib.parse
        body_bytes = urllib.parse.urlencode(form_data).encode("utf-8")
        default_ct = (b"content-type", b"application/x-www-form-urlencoded")
    else:
        body_bytes = b""
        default_ct = (b"content-type", b"text/plain")

    raw_headers = headers or [(b"host", b"stratum.example.com")]
    if not any(k.lower() == b"content-type" for k, _ in raw_headers):
        raw_headers.append(default_ct)

    async def receive():
        return {"type": "http.request", "body": body_bytes, "more_body": False}

    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "headers": raw_headers,
        "query_string": query_string,
    }
    return Request(scope, receive)


@pytest.fixture(scope="module")
def db():
    init_db()
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture(scope="module")
def existing_call(db):
    agent = db.query(Agent).first()
    call_out = _run_coro(
        initiate_call(
            req=CallInitiateRequest(
                agent_id=agent.id,
                customer_phone="+919876543210",
                customer_name="Test Caller",
                preferred_language="en",
                provider="web_simulator",
            ),
            db=db,
        )
    )
    call_id = call_out.id
    call = db.query(Call).filter(Call.id == call_id).first()
    call.status = "ringing"
    db.commit()
    return call_id


# ==============================================================================
# 1. PUBLIC_BASE_URL & HTTPS / WSS URL Resolution Tests
# ==============================================================================

def test_public_base_url_resolution():
    orig_base = settings.PUBLIC_BASE_URL
    orig_webhook = settings.PUBLIC_WEBHOOK_URL
    try:
        # Case A: PUBLIC_BASE_URL set to HTTPS domain with trailing slash
        settings.PUBLIC_BASE_URL = "https://voice.stratum-ai.com/"
        settings.PUBLIC_WEBHOOK_URL = ""
        assert settings.get_public_base_url() == "https://voice.stratum-ai.com"
        assert settings.is_public_https() is True

        http_url = settings.get_public_http_url("/api/telephony/twilio/twiml/call-123")
        assert http_url == "https://voice.stratum-ai.com/api/telephony/twilio/twiml/call-123"

        ws_url = settings.get_public_ws_url("/ws/voice/call-123")
        assert ws_url == "wss://voice.stratum-ai.com/ws/voice/call-123"
        assert ws_url.startswith("wss://")

        # Case B: PUBLIC_BASE_URL empty, fallback to PUBLIC_WEBHOOK_URL
        settings.PUBLIC_BASE_URL = ""
        settings.PUBLIC_WEBHOOK_URL = "https://tunnel.ngrok-free.app"
        assert settings.get_public_base_url() == "https://tunnel.ngrok-free.app"
        assert settings.is_public_https() is True

        ws_ngrok = settings.get_public_ws_url("/ws/voice/call-456")
        assert ws_ngrok == "wss://tunnel.ngrok-free.app/ws/voice/call-456"

        # Case C: Dynamic header fallback when no public base is configured
        settings.PUBLIC_BASE_URL = ""
        settings.PUBLIC_WEBHOOK_URL = ""
        assert settings.get_public_base_url() == ""
        assert settings.is_public_https() is False

        mock_req = _make_request(
            "/test",
            headers=[
                (b"host", b"api.mysite.com"),
                (b"x-forwarded-proto", b"https"),
            ],
        )

        dyn_http = settings.get_public_http_url("/api/test", mock_req)
        assert dyn_http == "https://api.mysite.com/api/test"

        dyn_ws = settings.get_public_ws_url("/ws/voice/call-789", mock_req)
        assert dyn_ws == "wss://api.mysite.com/ws/voice/call-789"

    finally:
        settings.PUBLIC_BASE_URL = orig_base
        settings.PUBLIC_WEBHOOK_URL = orig_webhook


# ==============================================================================
# 2. TwiML Speech Gather Loop & Stream Mode Tests
# ==============================================================================

def test_twiml_gather_endpoint_returns_valid_xml_with_https(db, existing_call):
    orig_base = settings.PUBLIC_BASE_URL
    try:
        settings.PUBLIC_BASE_URL = "https://voice.stratum-ai.com"
        call_id = existing_call

        req = _make_request(f"/api/telephony/twilio/twiml/{call_id}")
        resp = _run_coro(
            twilio_twiml_endpoint(call_id=call_id, request=req, mode="gather", db=db)
        )
        assert resp.status_code == 200
        assert "application/xml" in resp.media_type

        xml_text = resp.body.decode("utf-8")
        assert "<Response>" in xml_text
        assert "<Gather" in xml_text
        assert 'input="speech"' in xml_text
        assert f'action="https://voice.stratum-ai.com/api/telephony/twilio/gather/{call_id}"' in xml_text
        assert ("<Say" in xml_text or "<Play" in xml_text)
        assert f"https://voice.stratum-ai.com/api/telephony/twilio/reprompt/{call_id}?attempt=1" in xml_text
        assert "<Hangup/>" not in xml_text

    finally:
        settings.PUBLIC_BASE_URL = orig_base


def test_twiml_stream_endpoint_returns_wss_url(db, existing_call):
    orig_base = settings.PUBLIC_BASE_URL
    try:
        settings.PUBLIC_BASE_URL = "https://voice.stratum-ai.com"
        call_id = existing_call

        req = _make_request(f"/api/telephony/twilio/twiml/{call_id}")
        resp = _run_coro(
            twilio_twiml_endpoint(call_id=call_id, request=req, mode="stream", db=db)
        )
        assert resp.status_code == 200
        assert "application/xml" in resp.media_type

        xml_text = resp.body.decode("utf-8")
        assert "<Response>" in xml_text
        assert "<Stream" in xml_text
        assert f'url="wss://voice.stratum-ai.com/ws/voice/{call_id}"' in xml_text
        assert "ws://" not in xml_text

    finally:
        settings.PUBLIC_BASE_URL = orig_base


# ==============================================================================
# 3. Twilio Gather Turn & Reprompt Endpoint Tests
# ==============================================================================

def test_twilio_gather_turn_accepts_speech_and_continues_conversation(db, existing_call):
    orig_base = settings.PUBLIC_BASE_URL
    try:
        settings.PUBLIC_BASE_URL = "https://voice.stratum-ai.com"
        call_id = existing_call

        req = _make_request(
            f"/api/telephony/twilio/gather/{call_id}",
            method="POST",
            form_data={
                "SpeechResult": "Can you tell me about the project pricing and floor plans?",
                "Confidence": "0.95",
            },
        )
        resp = _run_coro(twilio_gather_turn_endpoint(call_id=call_id, request=req, db=db))
        assert resp.status_code == 200
        assert "application/xml" in resp.media_type

        xml_text = resp.body.decode("utf-8")
        assert "<Response>" in xml_text
        assert "<Gather" in xml_text
        assert f'action="https://voice.stratum-ai.com/api/telephony/twilio/gather/{call_id}"' in xml_text
        assert ("<Say" in xml_text or "<Play" in xml_text)
        assert "<Hangup/>" not in xml_text

    finally:
        settings.PUBLIC_BASE_URL = orig_base


def test_twilio_reprompt_endpoint_lifecycle(db, existing_call):
    orig_base = settings.PUBLIC_BASE_URL
    try:
        settings.PUBLIC_BASE_URL = "https://voice.stratum-ai.com"
        call_id = existing_call

        # Attempt 1: Re-prompts the caller with Gather and redirect to attempt=2
        req1 = _make_request(f"/api/telephony/twilio/reprompt/{call_id}?attempt=1", method="POST")
        resp1 = _run_coro(
            twilio_reprompt_endpoint(call_id=call_id, request=req1, attempt=1, db=db)
        )
        assert resp1.status_code == 200
        xml1 = resp1.body.decode("utf-8")
        assert "<Gather" in xml1
        assert f"https://voice.stratum-ai.com/api/telephony/twilio/gather/{call_id}" in xml1
        assert "attempt=2" in xml1

        # Attempt 3: Hangs up politely after unanswered reprompts
        req3 = _make_request(f"/api/telephony/twilio/reprompt/{call_id}?attempt=3", method="POST")
        resp3 = _run_coro(
            twilio_reprompt_endpoint(call_id=call_id, request=req3, attempt=3, db=db)
        )
        assert resp3.status_code == 200
        xml3 = resp3.body.decode("utf-8")
        assert "<Hangup/>" in xml3

    finally:
        settings.PUBLIC_BASE_URL = orig_base


# ==============================================================================
# 4. Twilio Media Stream Format & 8 kHz μ-law Handling Tests
# ==============================================================================

def test_twilio_media_stream_format_and_mulaw_codec():
    # Verify 8000 Hz mu-law format compatibility check
    twilio_fmt = {
        "encoding": "audio/x-mulaw",
        "sampleRate": 8000,
        "channels": 1
    }
    check = validate_twilio_media_format(twilio_fmt)
    assert check["is_compatible"] is True
    assert check["sample_rate"] == 8000
    assert check["encoding"] == "audio/x-mulaw"

    # Verify μ-law roundtrip conversion with sample speech PCM
    test_pcm = b"\x00\x00\x80\x0f\x00\x10\xff\x7f" * 100
    mulaw = pcm16_to_mulaw(test_pcm)
    assert len(mulaw) == len(test_pcm) // 2

    decoded_pcm = mulaw_to_pcm16(mulaw)
    assert len(decoded_pcm) == len(test_pcm)


# ==============================================================================
# 5. Twilio Signature Verification & Security Tests
# ==============================================================================

def test_twilio_hmac_sha1_signature_verification():
    auth_token = "1234567890abcdef1234567890abcdef"
    url = "https://voice.stratum-ai.com/api/telephony/twilio/gather/call-1"
    params = {
        "SpeechResult": "Hello, I am interested in property pricing.",
        "Confidence": "0.92",
        "CallSid": "CA1234567890",
    }

    # Compute expected signature
    sig = compute_twilio_signature(url=url, params=params, auth_token=auth_token)
    assert len(sig) > 0

    # Verification passes with correct signature
    is_valid = validate_twilio_signature(url=url, params=params, signature=sig, auth_token=auth_token)
    assert is_valid is True

    # Verification fails if parameters are altered
    altered_params = dict(params)
    altered_params["SpeechResult"] = "Tampered speech turn"
    assert validate_twilio_signature(url=url, params=altered_params, signature=sig, auth_token=auth_token) is False

    # Verification fails if URL is altered
    assert validate_twilio_signature(url="http://insecure.com", params=params, signature=sig, auth_token=auth_token) is False

    # Verification fails if signature is bogus
    assert validate_twilio_signature(url=url, params=params, signature="bogus_signature", auth_token=auth_token) is False


def test_redact_telephony_payload_masks_secrets_and_phones():
    payload = {
        "auth_token": "secret-auth-token-12345",
        "From": "+919876543210",
        "CallSid": "CA123456789",
        "SpeechResult": "What is the cost?",
    }
    redacted = redact_telephony_payload(payload)
    assert redacted["auth_token"] == "[REDACTED_SECRET]"
    assert redacted["From"] == "+91***10"
    assert redacted["CallSid"] == "CA123456789"
    assert redacted["SpeechResult"] == "What is the cost?"


# ==============================================================================
# 6. Public Health & Diagnostic Endpoint Tests
# ==============================================================================

def test_telephony_health_ping():
    res = _run_coro(telephony_health_ping())
    assert res.get("status") == "ok"
    assert res.get("service") == "Telephony Webhook Gateway"


def test_telephony_health_public_diagnostics():
    orig_base = settings.PUBLIC_BASE_URL
    try:
        settings.PUBLIC_BASE_URL = "https://voice.stratum-ai.com"
        res = _run_coro(telephony_public_connectivity_health(probe=False))

        assert res.get("configured") is True
        assert res.get("is_https") is True
        assert res.get("media_stream_is_wss") is True
        assert res.get("public_base_url") == "https://voice.stratum-ai.com"

        endpoints = res.get("endpoints", {})
        assert endpoints.get("twiml_url_template") == "https://voice.stratum-ai.com/api/telephony/twilio/twiml/{call_id}"
        assert endpoints.get("gather_url_template") == "https://voice.stratum-ai.com/api/telephony/twilio/gather/{call_id}"
        assert endpoints.get("media_stream_ws_template") == "wss://voice.stratum-ai.com/ws/voice/{call_id}"
        assert len(res.get("diagnostics", [])) > 0

    finally:
        settings.PUBLIC_BASE_URL = orig_base


# ==============================================================================
# 7. Indian Phonetic Normalization & Neural Audio Cache Tests
# ==============================================================================

def test_indian_phonetic_normalization_and_audio_streaming():
    from app.ai.tts_providers import normalize_indian_phonetics, clean_text_for_speech
    from app.api.telephony import _cache_telephony_audio, get_telephony_audio

    # Test currency and real estate conversions
    text = "The price is ₹4.5 Cr for a 3 BHK unit with 2150 sq.ft and ₹50,000 monthly EMI."
    normalized = normalize_indian_phonetics(text)
    assert "4.5 crore rupees" in normalized
    assert "3 B H K" in normalized
    assert "square feet" in normalized
    assert "E M I" in normalized

    # Test markdown and citation stripping
    raw_ai_text = "**Hello!** [Source: Aura Solar FAQ #1] *The rooftop system* is 5 kW."
    cleaned = clean_text_for_speech(raw_ai_text)
    assert "kilowatt" in cleaned
    assert "*" not in cleaned
    assert "[Source:" not in cleaned

    # Test audio caching and dynamic endpoint retrieval
    sample_mp3 = b"\xff\xfb\x90\x44" + b"\x00" * 200
    audio_id = _cache_telephony_audio(sample_mp3, "audio/mpeg")
    assert audio_id is not None

    resp = _run_coro(get_telephony_audio(f"{audio_id}.mp3"))
    assert resp.status_code == 200
    assert resp.media_type == "audio/mpeg"
    assert resp.body == sample_mp3

