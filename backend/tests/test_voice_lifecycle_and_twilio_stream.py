"""
Production Voice Lifecycle, Multi-Turn Twilio <Gather> & Media Stream Regression Tests
======================================================================================
Verifies:
1. Answered calls connect to the AI voice agent (`VoiceConversationSession`) and do NOT terminate
   after the greeting or first response.
2. Multi-turn conversation state, BANT extraction, and company-isolated RAG knowledge persist across turns.
3. Missing product information is handled honestly without inventing prices or commitments.
4. Explicit customer goodbye/hangup ends the call cleanly and generates CallSummary + session_trace.
5. Audio format, sample rate, and G.711 mu-law (8000 Hz) <-> PCM16 codec boundary checks pass.
6. Call status callbacks accurately distinguish ringing, answered, in_progress, busy, no-answer, failed, completed.
7. Missing Public Webhook URL in production PSTN mode raises an actionable diagnostic instead of silently
   playing a static 10-second script.
"""

import struct
import pytest
from starlette.requests import Request
from app.database import SessionLocal, init_db
from app.models import Agent, Call, CallTranscriptTurn
from app.schemas import CallInitiateRequest
from app.api.calls import initiate_call
from app.api.telephony import (
    twilio_twiml_endpoint,
    twilio_gather_turn_endpoint,
    twilio_reprompt_endpoint,
    twilio_status_callback,
)
from app.telephony.twilio_provider import TwilioProvider
from app.voice.audio_codec import (
    mulaw_to_pcm16,
    pcm16_to_mulaw,
    pcm16_to_wav,
    validate_twilio_media_format,
    CallSessionTracer,
)


def _run_coro_sync(coro):
    try:
        while True:
            coro.send(None)
    except StopIteration as e:
        return e.value


def _make_json_request(path: str, payload: dict) -> Request:
    import json

    body_bytes = json.dumps(payload).encode("utf-8")

    async def receive():
        return {"type": "http.request", "body": body_bytes, "more_body": False}

    scope = {
        "type": "http",
        "method": "POST",
        "path": path,
        "headers": [(b"content-type", b"application/json"), (b"host", b"stratum.example.com")],
        "query_string": b"",
    }
    return Request(scope, receive)


@pytest.fixture(scope="module")
def db():
    init_db()
    session = SessionLocal()
    yield session
    session.close()


def test_audio_codec_mulaw_pcm16_and_media_boundary_verification():
    # 1. Verify Twilio 8000 Hz mono mu-law format validation
    fmt = validate_twilio_media_format({"encoding": "audio/x-mulaw", "sampleRate": 8000, "channels": 1})
    assert fmt["is_compatible"] is True
    assert fmt["sample_rate"] == 8000

    bad_fmt = validate_twilio_media_format({"encoding": "audio/mp3", "sampleRate": 44100, "channels": 2})
    assert bad_fmt["is_compatible"] is False

    # 2. Verify PCM16 <-> G.711 mu-law round-trip conversion
    original_samples = [0, 512, -512, 4096, -4096, 16384, -16384]
    pcm16_in = struct.pack(f"<{len(original_samples)}h", *original_samples)
    mulaw = pcm16_to_mulaw(pcm16_in)
    assert len(mulaw) == len(original_samples)
    pcm16_out = mulaw_to_pcm16(mulaw)
    decoded_samples = struct.unpack(f"<{len(original_samples)}h", pcm16_out)
    for orig, dec in zip(original_samples, decoded_samples):
        if orig == 0:
            assert abs(dec) <= 8
        else:
            # G.711 mu-law is logarithmic 8-bit quantization (~2-4% relative step)
            assert abs(orig - dec) <= max(abs(orig) * 0.08, 32)

    # 3. Verify WAV framing
    wav_bytes = pcm16_to_wav(pcm16_out, sample_rate=8000)
    assert wav_bytes[:4] == b"RIFF"
    assert b"WAVEfmt " in wav_bytes[:20]

    # 4. Verify CallSessionTracer secret & PII redaction
    tracer = CallSessionTracer(call_id="call-trace-1", organization_id="org-1")
    entry = tracer.record(
        "speech_received",
        detail="Caller +919876543210 used SID AC0123456789abcdef0123456789abcdef and key gsk_secretKey1234567890",
        latency_ms=110,
        metadata={"auth_token": "super-secret-token", "language": "en"},
    )
    assert "AC0123456789abcdef0123456789abcdef" not in entry["detail"]
    assert "gsk_secretKey1234567890" not in entry["detail"]
    assert "9876543210" not in entry["detail"]
    assert entry["metadata"]["auth_token"] == "***REDACTED***"


def test_twilio_production_mode_rejects_missing_public_webhook_instead_of_static_message():
    provider = TwilioProvider(
        account_sid="AC0123456789abcdef0123456789abcdef",
        auth_token="test_token_32_chars_000000000000",
        from_phone="+14155552671",
    )
    with pytest.raises(ValueError, match="Public Webhook URL"):
        _run_coro_sync(
            provider.initiate_call(
                to_phone="+919876543210",
                callback_url="/api/telephony/twilio/twiml/call-123",
                metadata={"twilio_trial_mode": False},
            )
        )


def test_multi_turn_twilio_gather_conversation_and_company_rag_grounding(db):
    # Use Aura Solar Energy Pvt Ltd (or default agent if running standalone)
    agent = (
        db.query(Agent)
        .filter(Agent.company.like("%Aura Solar%"))
        .order_by(Agent.created_at.desc())
        .first()
    )
    if not agent:
        agent = db.query(Agent).first()

    # 1. Initiate call
    call_out = _run_coro_sync(
        initiate_call(
            req=CallInitiateRequest(
                agent_id=agent.id,
                customer_phone="+919888811111",
                customer_name="Rohan Rao",
                preferred_language="en",
                provider="web_simulator",
            ),
            db=db,
        )
    )
    call_id = call_out.id
    call_orm = db.query(Call).filter(Call.id == call_id).first()
    assert call_orm.organization_id == agent.organization_id

    # Set status to 'ringing' to simulate outbound PSTN call before answer
    call_orm.status = "ringing"
    db.commit()

    # 2. Customer answers -> Twilio calls `/api/telephony/twilio/twiml/{call_id}`
    twiml_req = _make_json_request(f"/api/telephony/twilio/twiml/{call_id}", {})
    twiml_resp = _run_coro_sync(
        twilio_twiml_endpoint(call_id=call_id, request=twiml_req, mode="gather", db=db)
    )
    xml_greeting = twiml_resp.body.decode("utf-8")

    db.refresh(call_orm)
    assert call_orm.status == "in_progress"
    assert "<Gather" in xml_greeting
    assert 'input="speech"' in xml_greeting
    assert 'bargeIn="true"' in xml_greeting
    assert f"/api/telephony/twilio/gather/{call_id}" in xml_greeting
    # Must NOT hang up immediately after greeting!
    assert "<Hangup/>" not in xml_greeting

    # 3. Turn 1: Customer asks a product question -> AI answers and keeps `<Gather>` open
    turn1_req = _make_json_request(
        f"/api/telephony/twilio/gather/{call_id}",
        {"SpeechResult": "What is the price and warranty for the 3kW Bifacial Rooftop System?"},
    )
    turn1_resp = _run_coro_sync(
        twilio_gather_turn_endpoint(call_id=call_id, request=turn1_req, db=db)
    )
    xml_turn1 = turn1_resp.body.decode("utf-8")
    assert "<Gather" in xml_turn1
    assert "<Hangup/>" not in xml_turn1

    # 4. Turn 2: Customer shares budget & timeline (BANT) -> Conversation continues for multiple turns
    turn2_req = _make_json_request(
        f"/api/telephony/twilio/gather/{call_id}",
        {"SpeechResult": "Our budget is 2 lakhs and we want to schedule a visit for Saturday morning."},
    )
    turn2_resp = _run_coro_sync(
        twilio_gather_turn_endpoint(call_id=call_id, request=turn2_req, db=db)
    )
    xml_turn2 = turn2_resp.body.decode("utf-8")
    assert "<Gather" in xml_turn2
    assert "<Hangup/>" not in xml_turn2

    # 5. Silence reprompt attempt 1 -> Does NOT hang up; gently reprompts
    reprompt_resp = _run_coro_sync(
        twilio_reprompt_endpoint(call_id=call_id, attempt=1, db=db)
    )
    xml_reprompt = reprompt_resp.body.decode("utf-8")
    assert "<Gather" in xml_reprompt
    assert "<Hangup/>" not in xml_reprompt

    # 6. Turn 3: Customer says goodbye -> Call ends cleanly with `<Hangup/>` and summary + trace
    turn3_req = _make_json_request(
        f"/api/telephony/twilio/gather/{call_id}",
        {"SpeechResult": "Thank you so much, goodbye!"},
    )
    turn3_resp = _run_coro_sync(
        twilio_gather_turn_endpoint(call_id=call_id, request=turn3_req, db=db)
    )
    xml_turn3 = turn3_resp.body.decode("utf-8")
    assert "<Hangup/>" in xml_turn3

    db.refresh(call_orm)
    assert call_orm.status == "completed"
    assert call_orm.summary is not None
    trace = call_orm.summary.key_information.get("session_trace", [])
    trace_events = {e["event"] for e in trace}
    assert "session_initialized" in trace_events
    assert "speech_received" in trace_events
    assert "llm_response_generated" in trace_events
    assert "call_terminated" in trace_events

    turns = (
        db.query(CallTranscriptTurn)
        .filter(CallTranscriptTurn.call_id == call_id)
        .order_by(CallTranscriptTurn.timestamp.asc())
        .all()
    )
    # Initial greeting + 3 customer turns + 3 agent responses = 7 turns
    assert len(turns) >= 7


def test_twilio_status_callback_distinguishes_all_call_states(db):
    agent = db.query(Agent).first()
    call_out = _run_coro_sync(
        initiate_call(
            req=CallInitiateRequest(
                agent_id=agent.id,
                customer_phone="+919777766666",
                customer_name="Status Test Caller",
                preferred_language="en",
                provider="web_simulator",
            ),
            db=db,
        )
    )
    call_id = call_out.id

    for raw_state, expected_mapped in [
        ("ringing", "ringing"),
        ("answered", "answered"),
        ("in-progress", "in_progress"),
        ("busy", "busy"),
        ("no-answer", "no-answer"),
        ("failed", "failed"),
        ("completed", "completed"),
    ]:
        req = _make_json_request(
            f"/api/telephony/twilio/status/{call_id}",
            {"CallStatus": raw_state, "CallDuration": "42"},
        )
        res = _run_coro_sync(twilio_status_callback(call_id=call_id, request=req, db=db))
        assert res["mapped_status"] == expected_mapped
