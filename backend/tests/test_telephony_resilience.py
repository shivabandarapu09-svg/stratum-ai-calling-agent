"""
Stratum AI Telephony Resilience, Webhook Verification, and Signature Tests
==========================================================================
Tests the complete outbound call flow, public URL validation, TwiML generation,
multi-turn gather loops, reprompts, status callbacks, and carrier HMAC signature checks.
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from unittest.mock import AsyncMock
from fastapi.testclient import TestClient
from app.main import app
from app.config import settings
from app.database import get_db, SessionLocal
from app.models import Agent, Call, Customer, Organization, User
from app.telephony.twilio_security import (
    compute_twilio_signature,
    validate_twilio_signature,
    redact_telephony_payload
)
from app.api.auth import create_access_token
from app.ai.tts_providers import EdgeTTSProvider

client = TestClient(app)

@pytest.fixture(autouse=True)
def mock_edge_tts(monkeypatch):
    monkeypatch.setattr(EdgeTTSProvider, "synthesize_speech", AsyncMock(return_value=b"mock_mp3_bytes"))


@pytest.fixture(scope="module")
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="module")
def auth_headers(db):
    user = db.query(User).filter(User.email == "founder@stratumai.internal").first()
    if not user:
        org = db.query(Organization).first()
        if not org:
            org = Organization(id="org-test-01", name="Test Org", slug="test-org")
            db.add(org)
            db.commit()
        user = User(
            id="usr-test-01",
            organization_id=org.id,
            email="founder@stratumai.internal",
            hashed_password="hash",
            full_name="Founder",
            role="superadmin"
        )
        db.add(user)
        db.commit()
    token = create_access_token(user)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def sample_call(db):
    agent = db.query(Agent).first()
    if not agent:
        org = db.query(Organization).first()
        agent = Agent(
            id="ag-resilience-01",
            organization_id=org.id,
            name="Aarav Test",
            role="Sales Development",
            company="Stratum Enterprise",
            system_prompt="You are a professional sales agent.",
            default_language="hi"
        )
        db.add(agent)
        db.commit()

    cust = db.query(Customer).first()
    if not cust:
        cust = Customer(
            organization_id=agent.organization_id,
            name="Rajesh Test",
            phone="+919876543210"
        )
        db.add(cust)
        db.commit()

    call_id = "call-test-resilience-001"
    call = db.query(Call).filter(Call.id == call_id).first()
    if not call:
        call = Call(
            id=call_id,
            organization_id=agent.organization_id,
            agent_id=agent.id,
            customer_id=cust.id,
            customer_phone="+919876543210",
            direction="outbound",
            status="ringing",
            primary_language="hi"
        )
        db.add(call)
        db.commit()
    else:
        call.status = "ringing"
        db.commit()
    db.refresh(call)
    return call


# =====================================================================
# 1. PUBLIC URL VALIDATION & PLACEHOLDER DETECTION
# =====================================================================

def test_placeholder_url_detection():
    # Placeholders must be rejected
    assert settings.is_placeholder_url("") is True
    assert settings.is_placeholder_url("https://your-domain.ngrok-free.app") is True
    assert settings.is_placeholder_url("https://your-tunnel.ngrok-free.app") is True
    assert settings.is_placeholder_url("https://example.com/webhook") is True
    assert settings.is_placeholder_url("http://localhost:8000") is True
    assert settings.is_placeholder_url("http://127.0.0.1:8000") is True

    # Real public tunnel / domains must be accepted
    assert settings.is_placeholder_url("https://a4b1-103-241.ngrok-free.app") is False
    assert settings.is_placeholder_url("https://calling.stratumai.com") is False
    assert settings.is_placeholder_url("https://stratum-agent.fly.dev") is False


def test_validate_public_url_messages():
    # Empty
    valid, msg = settings.validate_public_url("")
    assert not valid
    assert "not configured" in msg

    # Placeholder
    valid, msg = settings.validate_public_url("https://your-domain.ngrok-free.app")
    assert not valid
    assert "placeholder" in msg

    # Non-HTTPS
    valid, msg = settings.validate_public_url("http://active-tunnel.ngrok-free.app")
    assert not valid
    assert "HTTPS" in msg

    # Valid
    valid, msg = settings.validate_public_url("https://active-tunnel.ngrok-free.app")
    assert valid
    assert "ready" in msg.lower()


# =====================================================================
# 2. OUTBOUND CALL PRE-FLIGHT BLOCKING
# =====================================================================

def test_initiate_call_blocks_unconfigured_twilio(auth_headers, sample_call):
    # Ensure public base is empty or placeholder
    old_base = settings.PUBLIC_BASE_URL
    old_hook = settings.PUBLIC_WEBHOOK_URL
    try:
        settings.PUBLIC_BASE_URL = ""
        settings.PUBLIC_WEBHOOK_URL = ""

        resp = client.post(
            "/api/calls/initiate",
            json={
                "agent_id": sample_call.agent_id,
                "customer_phone": "+919876543210",
                "customer_name": "Test Caller",
                "provider": "twilio"
            },
            headers=auth_headers
        )
        assert resp.status_code == 400
        assert "Public Webhook URL is not configured" in resp.json()["detail"]

        # Now test with placeholder
        settings.PUBLIC_BASE_URL = "https://your-domain.ngrok-free.app"
        settings.PUBLIC_WEBHOOK_URL = "https://your-domain.ngrok-free.app"

        resp = client.post(
            "/api/calls/initiate",
            json={
                "agent_id": sample_call.agent_id,
                "customer_phone": "+919876543210",
                "customer_name": "Test Caller",
                "provider": "twilio"
            },
            headers=auth_headers
        )
        assert resp.status_code == 400
        assert "placeholder domain" in resp.json()["detail"]

    finally:
        settings.PUBLIC_BASE_URL = old_base
        settings.PUBLIC_WEBHOOK_URL = old_hook


# =====================================================================
# 3. TWIML VOICE WEBHOOK & APPLICATION/XML VERIFICATION
# =====================================================================

def test_twilio_twiml_endpoint_returns_valid_xml(sample_call):
    resp = client.get(f"/api/telephony/twilio/twiml/{sample_call.id}")
    assert resp.status_code == 200
    assert "application/xml" in resp.headers.get("content-type", "")
    content = resp.text
    assert content.startswith("<?xml")
    assert "<Response>" in content
    assert "</Response>" in content
    assert "<Gather" in content
    assert "action=" in content
    assert "method=\"POST\"" in content


def test_twilio_gather_turn_endpoint_multi_turn(sample_call):
    # Customer speaks
    resp = client.post(
        f"/api/telephony/twilio/gather/{sample_call.id}",
        data={"SpeechResult": "हाँ मुझे 3 BHK फ्लैट की जानकारी चाहिए", "CallSid": "CA12345"}
    )
    assert resp.status_code == 200
    assert "application/xml" in resp.headers.get("content-type", "")
    content = resp.text
    assert "<Response>" in content
    assert "<Gather" in content
    assert "action=" in content


def test_twilio_reprompt_endpoint(sample_call):
    # Attempt 1
    resp = client.post(f"/api/telephony/twilio/reprompt/{sample_call.id}?attempt=1")
    assert resp.status_code == 200
    assert "application/xml" in resp.headers.get("content-type", "")
    assert "<Gather" in resp.text
    assert "attempt=2" in resp.text

    # Attempt 3 (Final graceful termination)
    resp3 = client.post(f"/api/telephony/twilio/reprompt/{sample_call.id}?attempt=3")
    assert resp3.status_code == 200
    assert "<Hangup/>" in resp3.text


def test_twilio_status_callback_completed(sample_call, db):
    resp = client.post(
        f"/api/telephony/twilio/status/{sample_call.id}",
        data={"CallStatus": "completed", "CallDuration": "45"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["mapped_status"] == "completed"

    # Verify DB persistence
    db.expire_all()
    updated_call = db.query(Call).filter(Call.id == sample_call.id).first()
    assert updated_call.status == "completed"
    assert updated_call.duration_seconds >= 45


# =====================================================================
# 4. CARRIER HMAC SIGNATURE INTEGRITY & FORM PARAMS
# =====================================================================

def test_twilio_signature_computation():
    url = "https://active-tunnel.ngrok-free.app/api/telephony/twilio/twiml/call-123"
    auth_token = "dummy_auth_token_for_hmac"
    params = {"CallSid": "CA999", "From": "+17372212163", "To": "+919876543210"}

    sig = compute_twilio_signature(url, params, auth_token)
    assert bool(sig)
    assert validate_twilio_signature(url, params, sig, auth_token) is True
    # Forged signature must fail
    assert validate_twilio_signature(url, params, "bad_signature", auth_token) is False
    # Altered params must fail
    assert validate_twilio_signature(url, {"CallSid": "CA888"}, sig, auth_token) is False


def test_redact_telephony_payload():
    payload = {
        "auth_token": "secret123",
        "api_key": "key456",
        "to": "+919876543210",
        "CallSid": "CA12345678",
        "message": "Hello from Stratum"
    }
    redacted = redact_telephony_payload(payload)
    assert redacted["auth_token"] == "[REDACTED_SECRET]"
    assert redacted["api_key"] == "[REDACTED_SECRET]"
    assert redacted["to"] == "+91***10"
    assert redacted["CallSid"] == "CA12345678"
    assert redacted["message"] == "Hello from Stratum"
